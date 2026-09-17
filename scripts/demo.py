import argparse
import os
import re
import statistics
import sys
import time
from types import SimpleNamespace

import pandas as pd
import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2 import extensions, extras
from neo4j import READ_ACCESS, GraphDatabase, Query
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from benchmark import (NEO4J_QUERY_DIR, PG_QUERY_DIR, THE_MATRIX, build_cases, load_pairs,
                       load_query, normalise)
from config import POSTGRES, NEO4J_URI, NEO4J_AUTH

# Title counts produced by each vote threshold (PROJECT_REPORT.md, section 4). Detecting the
# threshold from the data, rather than trusting a flag, stops the demo pairing the loaded graph
# with the Q1 actor pairs of a different threshold.
THRESHOLDS = {10118: 10000, 36711: 1000, 104931: 100}
TIMEOUT_S = 300
# Whichever engine runs first after an idle pause is slowed down for its first ~100 ms of work, and
# in the demo there is always a pause before a query: a single run let that penalty decide Q3 and
# Q4. So executions that start inside SETTLE_S are discarded, and the median of RUNS back-to-back
# executions is reported. A run that alone outlasts SETTLE_S is kept: against its own cost the
# penalty is noise, and discarding it would double the wait on Q1 and Q2. The benchmark needs
# none of this: it has no pauses and alternates the order.
RUNS = 3
SETTLE_S = 0.1
ENGINES = {"p": ("postgresql",), "n": ("neo4j",), "b": ("postgresql", "neo4j")}
FLAG_ENGINES = {"pg": "p", "neo4j": "n", "both": "b"}
BENCHMARK_QUERIES = {"q1_shortest_path", "q2_most_connected", "q3_genre_by_decade",
                     "q4_recommendations"}

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
            rows = cursor.fetchall() if cursor.description else []
        except (pg_errors.QueryCanceled, KeyboardInterrupt) as exc:
            # wait_select turns Ctrl-C into a server-side cancel, which also arrives as
            # QueryCanceled: only the message tells it apart from statement_timeout.
            conn.rollback()
            raise Failed("timed out" if "timeout" in str(exc) else "interrupted") from None
        except psycopg2.Error as exc:
            # A query written on the spot can be wrong; report it and keep the demo running.
            conn.rollback()
            raise Failed(f"error: {first_line(exc)}") from None
        elapsed = time.perf_counter() - start
        columns = [column.name for column in cursor.description or []]
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
        raise Failed(f"error: {first_line(exc)}") from None
    elapsed = time.perf_counter() - start
    return columns, normalise(tuple(r.values()) for r in records), elapsed


def first_line(exc):
    message = getattr(exc, "pgerror", None) or getattr(exc, "message", None) or str(exc)
    lines = message.strip().splitlines()
    return re.sub(r"^ERROR:\s*", "", lines[0]) if lines else type(exc).__name__


def median_time(run_once, runs):
    times, start = [], time.perf_counter()
    while len(times) < runs:
        began = time.perf_counter() - start
        columns, rows, elapsed = run_once()
        if began >= SETTLE_S or elapsed >= SETTLE_S:
            times.append(elapsed)
    return columns, rows, statistics.median(times)


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
        except psycopg2.Error as exc:
            conn.rollback()
            raise Failed(f"instrumented run: {first_line(exc)}") from None
    conn.commit()
    return plan["Shared Hit Blocks"] + plan["Shared Read Blocks"]


def neo4j_accesses(session, cypher, params):
    try:
        profile = session.run(Query("PROFILE " + cypher, timeout=TIMEOUT_S), **params).consume().profile
    except Neo4jError as exc:
        raise Failed(f"instrumented run: {first_line(exc)}") from None
    match = profile and re.search(r"Total database accesses: (\d+)",
                                  profile["args"]["string-representation"])
    if not match:
        raise Failed("instrumented run: no access count in the profile")
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


def extra_cases():
    # Query files beyond the four of the benchmark, e.g. one written on request during the
    # discussion. q5_x.sql and q5_x.cypher pair up by name; a file on one side runs on that engine
    # only. The directories are read again at every menu, so a new file shows up without
    # restarting, and the file is read again at every run, so a fix is picked up at once.
    def stems(directory, extension):
        return {name[:-len(extension) - 1] for name in os.listdir(directory)
                if name.endswith("." + extension) and not name.startswith(".")}

    sql, cypher = stems(PG_QUERY_DIR, "sql"), stems(NEO4J_QUERY_DIR, "cypher")
    cases = []
    for stem in sorted((sql | cypher) - BENCHMARK_QUERIES):
        engines = " + ".join(e for e, present in (("SQL", stem in sql), ("Cypher", stem in cypher))
                             if present)
        cases.append({"name": stem, "case": stem, "extra": True,
                      "short": f"{stem}  (extra · {engines})",
                      "has_sql": stem in sql, "has_cypher": stem in cypher,
                      "pg_params": {}, "neo4j_params": {}})
    return cases


def load_extra(case):
    try:
        if case["has_sql"]:
            case["pg_sql"] = load_query(PG_QUERY_DIR, case["name"], "sql")
        if case["has_cypher"]:
            case["cypher"] = load_query(NEO4J_QUERY_DIR, case["name"], "cypher")
    except OSError as exc:
        raise Failed(f"cannot read the query file: {exc}") from None


def systems_of(case):
    return [system for system, present in (("postgresql", case.get("pg_sql") is not None),
                                           ("neo4j", case.get("cypher") is not None)) if present]


def show_query_text(case):
    print(f"\n{'─' * 72}\n{case['short']}\n{'─' * 72}")
    if case.get("pg_sql") is not None:
        print("\n  PostgreSQL (SQL)\n")
        print("\n".join("    " + line for line in without_comments(case["pg_sql"], "--").splitlines()))
    if case.get("cypher") is not None:
        print("\n  Neo4j (Cypher)\n")
        print("\n".join("    " + line for line in without_comments(case["cypher"], "//").splitlines()))
    params = case["pg_params"]
    if params:
        print(f"\n  parameters: {params}")


def run_case(case, engine_key, state):
    conn, session = state.conn, state.session
    extra = case.get("extra", False)
    if extra:
        try:
            load_extra(case)
        except Failed as failure:
            print(f"\n  {failure}")
            return
        # A query written on the spot runs several times: read-only on both engines, so a
        # stray CREATE or UPDATE is rejected instead of changing the data the demo just verified.
        conn.rollback()
        conn.readonly = True
        session = state.read_session
    print(f"\n{'═' * 72}\n{case['short']}\n{'═' * 72}")

    try:
        outcome = run_systems(case, engine_key, state, conn, session)
    finally:
        if extra:
            conn.rollback()
            conn.readonly = False
    summarise(outcome, state.accesses, state.runs)


def run_systems(case, engine_key, state, conn, session):
    outcome = {}
    for system in [s for s in ENGINES[engine_key] if s in systems_of(case)]:
        try:
            if system == "postgresql":
                columns, rows, elapsed = median_time(
                    lambda: run_postgres(conn, case["pg_sql"], case["pg_params"]), state.runs)
                accesses = (postgres_accesses(conn, case["pg_sql"], case["pg_params"])
                            if state.accesses else None)
            else:
                columns, rows, elapsed = median_time(
                    lambda: run_neo4j(session, case["cypher"], case["neo4j_params"]), state.runs)
                accesses = (neo4j_accesses(session, case["cypher"], case["neo4j_params"])
                            if state.accesses else None)
        except Failed as failure:
            print(f"\n  {system}: {failure}")
            continue
        outcome[system] = (rows, elapsed, accesses)
        name = "PostgreSQL" if system == "postgresql" else "Neo4j"
        show_table(f"{name} · {format_time(elapsed)}", columns, rows, state.max_rows)
    return outcome


def describe_runs(runs):
    return "single run" if runs == 1 else f"median of {runs} runs"


def summarise(outcome, with_accesses, runs):
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
    print(f"\n  → {faster} faster by {ratio:,.1f}× ({describe_runs(runs)} — benchmark medians of ten"
          " are in the report)")
    if pg_rows == neo4j_rows:
        print("  ✓ identical results in both systems")
    else:
        print("  ✗ RESULTS DIFFER")
        for i, (a, b) in enumerate(zip(pg_rows, neo4j_rows)):
            if a != b:
                print(f"    first difference at row {i}: PostgreSQL {a} / Neo4j {b}")
                break
    if with_accesses:
        print(f"  (time: {describe_runs(runs)}; accesses from a further, instrumented run —\n"
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
          f" · accesses {'ON' if state.accesses else 'off'}"
          + (" · extra queries ON" if state.extra else ""))


def menu(benchmark_cases, state):
    while True:
        cases = benchmark_cases + (extra_cases() if state.extra else [])
        header(state)
        for i, case in enumerate(cases, 1):
            print(f"  {i}) {case['short']}")
        print("  a) toggle accesses   w) warm up   q) quit")
        choice = input("\n> ").strip().lower()

        try:
            if choice == "":
                continue
            if choice == "q":
                return
            if choice == "a":
                state.accesses = not state.accesses
            elif choice == "w":
                # Only the benchmark's queries: an extra one may still be half-written.
                warm_up(benchmark_cases, state)
            elif choice.isdigit() and 1 <= int(choice) <= len(cases):
                case = cases[int(choice) - 1]
                if case.get("extra"):
                    load_extra(case)
                available = systems_of(case)
                default = "b" if len(available) == 2 else available[0][0]
                options = {"b": "p) PostgreSQL  n) Neo4j  b) both", "p": "p) PostgreSQL",
                           "n": "n) Neo4j"}[default]
                while True:
                    engine = input(f"  engine: {options}  t) show query text  [{default}] > "
                                   ).strip().lower() or default
                    if engine == "t":
                        show_query_text(case)
                        continue
                    if engine in (ENGINES if default == "b" else {default}):
                        run_case(case, engine, state)
                    else:
                        print("  ?")
                    break
            else:
                print("  ?")
        except Failed as failure:
            print(f"  {failure}")
        except KeyboardInterrupt:
            # Leaves the session in an unknown state mid-stream; start a clean one.
            print("\n  interrupted")
            state.conn.rollback()
            state.conn.readonly = False
            state.session.close()
            state.session = state.driver.session()
            state.read_session.close()
            state.read_session = state.driver.session(default_access_mode=READ_ACCESS)


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
    parser.add_argument("--extra-queries", action="store_true",
                        help="also list query files added to postgres/queries or neo4j/queries "
                             "beyond the four of the benchmark (read-only)")
    parser.add_argument("--runs", type=int, default=RUNS,
                        help=f"back-to-back runs per engine, median reported (default {RUNS})")
    args = parser.parse_args()

    conn, driver = connect()
    session = driver.session()
    min_votes, titles = detect_threshold(conn, session, args.min_votes)
    cases = label_cases(build_cases(SimpleNamespace(min_votes=min_votes, tconst=args.tconst)),
                        conn, min_votes, args.tconst)

    state = SimpleNamespace(conn=conn, driver=driver, session=session, min_votes=min_votes,
                            titles=titles, accesses=args.accesses, max_rows=args.max_rows,
                            runs=max(1, args.runs), extra=args.extra_queries,
                            read_session=driver.session(default_access_mode=READ_ACCESS))
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
        state.read_session.close()
        driver.close()
        conn.close()


if __name__ == "__main__":
    main()
