import argparse
import re
import sys
import time
from types import SimpleNamespace

import pandas as pd
import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2 import extensions, extras
from neo4j import GraphDatabase, Query
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from benchmark import THE_MATRIX, build_cases, load_pairs, normalise
from config import POSTGRES, NEO4J_URI, NEO4J_AUTH

# Title counts produced by each vote threshold (PROJECT_REPORT.md, section 4). Detecting the
# threshold from the data, rather than trusting a flag, stops the demo pairing the loaded graph
# with the Q1 actor pairs of a different threshold.
THRESHOLDS = {10118: 10000, 36711: 1000, 104931: 100}
TIMEOUT_S = 300
ENGINES = {"p": ("postgresql",), "n": ("neo4j",), "b": ("postgresql", "neo4j")}
FLAG_ENGINES = {"pg": "p", "neo4j": "n", "both": "b"}

# Makes a running PostgreSQL query cancellable with Ctrl-C. Without it the interrupt is only
# delivered once the query has finished, which on Q2 at the lowest threshold is seconds away.
extensions.set_wait_callback(extras.wait_select)


class Failed(Exception):
    """A query that timed out or was interrupted: reported, not raised to the user."""


def connect():
    try:
        conn = psycopg2.connect(**POSTGRES)
        with conn.cursor() as cursor:
            cursor.execute(f"SET statement_timeout = '{TIMEOUT_S}s'")
        conn.commit()
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        driver.verify_connectivity()
    except (psycopg2.OperationalError, ServiceUnavailable) as exc:
        sys.exit(f"Cannot reach the databases — is `docker compose up -d --wait` running?\n  {exc}")
    return conn, driver


def detect_threshold(conn, session, override):
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM Titles")
        pg_titles = cursor.fetchone()[0]
    conn.commit()
    neo4j_titles = session.run("MATCH (t:Title) RETURN count(t) AS n").single()["n"]

    if pg_titles != neo4j_titles:
        sys.exit(f"The databases disagree: {pg_titles} titles in PostgreSQL, {neo4j_titles} in "
                 "Neo4j. Run scripts/verify_counts.py before demoing anything.")
    if override is not None:
        return override, pg_titles
    if pg_titles not in THRESHOLDS:
        sys.exit(f"{pg_titles} titles does not match a known threshold; pass --min-votes.")
    return THRESHOLDS[pg_titles], pg_titles


def run_postgres(conn, sql, params):
    # Same timed section as benchmark.time_postgres: execute and fetch, connection already open.
    with conn.cursor() as cursor:
        start = time.perf_counter()
        try:
            cursor.execute(sql, params or None)
            rows = cursor.fetchall()
        except (pg_errors.QueryCanceled, KeyboardInterrupt) as exc:
            # wait_select turns Ctrl-C into a server-side cancel, which also arrives as
            # QueryCanceled: only the message tells it apart from statement_timeout.
            conn.rollback()
            raise Failed("timed out" if "timeout" in str(exc) else "interrupted") from None
        elapsed = time.perf_counter() - start
        columns = [column.name for column in cursor.description]
    conn.commit()
    return columns, normalise(rows), elapsed


def run_neo4j(session, cypher, params):
    # Same timed section as benchmark.time_neo4j: run and consume, session already open.
    start = time.perf_counter()
    try:
        result = session.run(Query(cypher, timeout=TIMEOUT_S), **params)
        records = list(result)
        columns = result.keys()
    except Neo4jError as exc:
        if "timeout" in str(exc).lower() or "terminated" in str(exc).lower():
            raise Failed("timed out") from None
        raise
    elapsed = time.perf_counter() - start
    return columns, normalise(tuple(r.values()) for r in records), elapsed


def postgres_accesses(conn, sql, params):
    # A second, instrumented execution. The root node's buffer counts are cumulative over the
    # whole plan, the CTE included.
    with conn.cursor() as cursor:
        try:
            cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params or None)
            plan = cursor.fetchone()[0][0]["Plan"]
        except (pg_errors.QueryCanceled, KeyboardInterrupt):
            conn.rollback()
            raise Failed("instrumented run interrupted") from None
    conn.commit()
    return plan["Shared Hit Blocks"] + plan["Shared Read Blocks"]


def neo4j_accesses(session, cypher, params):
    profile = session.run(Query("PROFILE " + cypher, timeout=TIMEOUT_S), **params).consume().profile
    match = re.search(r"Total database accesses: (\d+)", profile["args"]["string-representation"])
    return int(match.group(1))


def format_time(seconds):
    if seconds >= 1:
        return f"{seconds:.3f} s"
    return f"{seconds * 1000:.1f} ms" if seconds >= 0.01 else f"{seconds * 1000:.2f} ms"


def show_table(title, columns, rows, max_rows):
    print(f"\n  {title} — {len(rows)} row{'s' if len(rows) != 1 else ''}")
    if not rows:
        print("    (no rows)")
        return
    frame = pd.DataFrame(rows[:max_rows], columns=columns)
    print("\n".join("    " + line for line in frame.to_string(index=False).splitlines()))
    if len(rows) > max_rows:
        print(f"    … {len(rows) - max_rows} more")


def without_comments(text, marker):
    # The query files open with comments written for someone reading the repository; on a
    # projector they only push the query itself off the screen.
    lines = [line for line in text.strip().splitlines() if not line.lstrip().startswith(marker)]
    return "\n".join(lines).strip()


def show_query_text(case):
    print(f"\n{'─' * 72}\n{case['short']}\n{'─' * 72}")
    print("\n  PostgreSQL (SQL)\n")
    print("\n".join("    " + line for line in without_comments(case["pg_sql"], "--").splitlines()))
    print("\n  Neo4j (Cypher)\n")
    print("\n".join("    " + line for line in without_comments(case["cypher"], "//").splitlines()))
    params = case["pg_params"]
    if params:
        print(f"\n  parameters: {params}")


def run_case(case, engine_key, state):
    conn, session = state.conn, state.session
    print(f"\n{'═' * 72}\n{case['short']}\n{'═' * 72}")

    outcome = {}
    for system in ENGINES[engine_key]:
        try:
            if system == "postgresql":
                columns, rows, elapsed = run_postgres(conn, case["pg_sql"], case["pg_params"])
                accesses = (postgres_accesses(conn, case["pg_sql"], case["pg_params"])
                            if state.accesses else None)
            else:
                columns, rows, elapsed = run_neo4j(session, case["cypher"], case["neo4j_params"])
                accesses = (neo4j_accesses(session, case["cypher"], case["neo4j_params"])
                            if state.accesses else None)
        except Failed as failure:
            print(f"\n  {system}: {failure}")
            continue
        outcome[system] = (rows, elapsed, accesses)
        name = "PostgreSQL" if system == "postgresql" else "Neo4j"
        show_table(f"{name} · {format_time(elapsed)}", columns, rows, state.max_rows)

    summarise(outcome, state.accesses)


def summarise(outcome, with_accesses):
    if not outcome:
        return
    print(f"\n  {'':<12}{'time':>12}" + (f"{'accesses':>26}" if with_accesses else ""))
    for system, (_, elapsed, accesses) in outcome.items():
        name = "PostgreSQL" if system == "postgresql" else "Neo4j"
        unit = "8 KB pages" if system == "postgresql" else "records"
        line = f"  {name:<12}{format_time(elapsed):>12}"
        if with_accesses:
            line += f"{accesses:>15,} {unit:<10}"
        print(line)

    if len(outcome) < 2:
        return
    (pg_rows, pg_time, _), (neo4j_rows, neo4j_time, _) = outcome["postgresql"], outcome["neo4j"]
    faster, ratio = (("Neo4j", pg_time / neo4j_time) if neo4j_time < pg_time
                     else ("PostgreSQL", neo4j_time / pg_time))
    print(f"\n  → {faster} faster by {ratio:,.1f}× (single run — benchmark medians are in the report)")
    if pg_rows == neo4j_rows:
        print("  ✓ identical results in both systems")
    else:
        print("  ✗ RESULTS DIFFER")
        for i, (a, b) in enumerate(zip(pg_rows, neo4j_rows)):
            if a != b:
                print(f"    first difference at row {i}: PostgreSQL {a} / Neo4j {b}")
                break
    if with_accesses:
        print("  (time from the first run; accesses from a second, instrumented run —\n"
              "   pages and records are different units)")


def warm_up(cases, state, neo4j_rounds=5):
    # The first execution measures caches and query compilation, not the query. One round
    # settles PostgreSQL; Neo4j's millisecond queries take a few rounds to reach the timings of
    # the benchmark, and those rounds are cheap.
    print("\nWarming up every query on both systems", end="", flush=True)
    start = time.perf_counter()
    for case in cases:
        try:
            run_postgres(state.conn, case["pg_sql"], case["pg_params"])
        except Failed:
            pass
        print(".", end="", flush=True)
    for _ in range(neo4j_rounds):
        for case in cases:
            try:
                run_neo4j(state.session, case["cypher"], case["neo4j_params"])
            except Failed:
                pass
        print(".", end="", flush=True)
    print(f" done in {format_time(time.perf_counter() - start)}")


def header(state):
    print(f"\nDataset: numVotes >= {state.min_votes:,} · {state.titles:,} titles"
          f" · accesses {'ON' if state.accesses else 'off'}")


def menu(cases, state):
    while True:
        header(state)
        for i, case in enumerate(cases, 1):
            print(f"  {i}) {case['short']}")
        print("  a) toggle accesses   w) warm up   q) quit")
        choice = input("\n> ").strip().lower()

        try:
            if choice == "q":
                return
            if choice == "a":
                state.accesses = not state.accesses
            elif choice == "w":
                warm_up(cases, state)
            elif choice.isdigit() and 1 <= int(choice) <= len(cases):
                case = cases[int(choice) - 1]
                while True:
                    engine = input("  engine: p) PostgreSQL  n) Neo4j  b) both  t) show query"
                                   " text  [b] > ").strip().lower() or "b"
                    if engine == "t":
                        show_query_text(case)
                        continue
                    if engine in ENGINES:
                        run_case(case, engine, state)
                    else:
                        print("  ?")
                    break
            else:
                print("  ?")
        except KeyboardInterrupt:
            # Leaves the session in an unknown state mid-stream; start a clean one.
            print("\n  interrupted")
            state.conn.rollback()
            state.session.close()
            state.session = state.driver.session()


def label_cases(cases, conn, min_votes, tconst):
    pairs = load_pairs(min_votes)
    source = pairs["source"]["name"]
    names = {f"q1_distance_{t['distance']}": t["name"] for t in pairs["targets"]}
    with conn.cursor() as cursor:
        cursor.execute("SELECT primaryTitle FROM Titles WHERE tconst = %s", (tconst,))
        row = cursor.fetchone()
    conn.commit()
    title = row[0] if row else tconst

    for case in cases:
        if case["name"] == "q1_shortest_path":
            distance = case["case"].rsplit("_", 1)[1]
            case["short"] = f"Q1  degrees of separation, distance {distance}: {source} → {names[case['case']]}"
        elif case["name"] == "q2_most_connected":
            case["short"] = "Q2  most connected actors (top 10)"
        elif case["name"] == "q3_genre_by_decade":
            case["short"] = "Q3  average rating by genre, 2010s"
        else:
            case["short"] = f"Q4  films sharing the most people with {title}"
    return cases


def select_case(cases, query, distance):
    if query == "q1":
        name = f"q1_distance_{distance}"
        matches = [c for c in cases if c["case"] == name]
        if not matches:
            available = [c["case"][-1] for c in cases if c["name"] == "q1_shortest_path"]
            sys.exit(f"No Q1 pair at distance {distance}; available: {', '.join(available)}")
        return matches[0]
    prefix = {"q2": "q2_", "q3": "q3_", "q4": "q4_"}[query]
    return next(c for c in cases if c["case"].startswith(prefix))


def main():
    parser = argparse.ArgumentParser(
        description="Run one query on PostgreSQL, Neo4j or both, and show results and timing. "
                    "Without --query it opens an interactive menu.")
    parser.add_argument("--query", choices=["q1", "q2", "q3", "q4"])
    parser.add_argument("--distance", type=int, default=4, help="Q1 distance (default 4)")
    parser.add_argument("--engine", choices=list(FLAG_ENGINES), default="both")
    parser.add_argument("--accesses", action="store_true",
                        help="also show page / record accesses from an instrumented run")
    parser.add_argument("--show-query", action="store_true", help="print SQL and Cypher first")
    parser.add_argument("--warmup", action="store_true", help="warm up every query first")
    parser.add_argument("--min-votes", type=int,
                        help="threshold of the loaded data (detected when omitted)")
    parser.add_argument("--tconst", default=THE_MATRIX, help="starting title for Q4")
    parser.add_argument("--max-rows", type=int, default=10)
    args = parser.parse_args()

    conn, driver = connect()
    session = driver.session()
    min_votes, titles = detect_threshold(conn, session, args.min_votes)
    cases = label_cases(build_cases(SimpleNamespace(min_votes=min_votes, tconst=args.tconst)),
                        conn, min_votes, args.tconst)

    state = SimpleNamespace(conn=conn, driver=driver, session=session, min_votes=min_votes,
                            titles=titles, accesses=args.accesses, max_rows=args.max_rows)
    try:
        if args.warmup:
            warm_up(cases, state)
        if args.query:
            case = select_case(cases, args.query, args.distance)
            if args.show_query:
                show_query_text(case)
            run_case(case, FLAG_ENGINES[args.engine], state)
        else:
            menu(cases, state)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        state.session.close()
        driver.close()
        conn.close()


if __name__ == "__main__":
    main()
