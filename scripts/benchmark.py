import argparse
import csv
import json
import os
import statistics
import sys
import time
from decimal import Decimal

import psycopg2
from psycopg2 import errors as pg_errors
from neo4j import GraphDatabase, Query
from neo4j.exceptions import Neo4jError

from config import POSTGRES, NEO4J_URI, NEO4J_AUTH, ANALYSIS_DIR, DEFAULT_MIN_VOTES

PG_QUERY_DIR = os.path.join("postgres", "queries")
NEO4J_QUERY_DIR = os.path.join("neo4j", "queries")
RESULTS_CSV = os.path.join(ANALYSIS_DIR, "results.csv")
PLANS_DIR = os.path.join(ANALYSIS_DIR, "plans")

THE_MATRIX = "tt0133093"
TIMEOUT = "timeout"
FIELDNAMES = ["query", "case", "system", "run", "seconds", "rows", "min_votes", "note"]


def load_query(directory, name, extension):
    with open(os.path.join(directory, f"{name}.{extension}")) as f:
        text = f.read()
    return text.strip().rstrip(";") if extension == "cypher" else text


def normalise(rows):
    # PostgreSQL returns NUMERIC as Decimal and Neo4j returns float. Both queries
    # round averages to three decimals, so comparing at three decimals is exact.
    def value(v):
        if isinstance(v, (Decimal, float)):
            return round(float(v), 3)
        return v

    return [tuple(value(v) for v in row) for row in rows]


def time_postgres(conn, sql, params):
    with conn.cursor() as cursor:
        start = time.perf_counter()
        try:
            cursor.execute(sql, params or None)
            rows = cursor.fetchall() if cursor.description else []
        except pg_errors.QueryCanceled:
            conn.rollback()
            return TIMEOUT, time.perf_counter() - start
        elapsed = time.perf_counter() - start
    conn.commit()
    return normalise(rows), elapsed


def time_neo4j(session, cypher, params, timeout):
    start = time.perf_counter()
    try:
        result = session.run(Query(cypher, timeout=timeout), **params)
        rows = [tuple(record.values()) for record in result]
    except Neo4jError as exc:
        if "timeout" in str(exc).lower() or "terminated" in str(exc).lower():
            return TIMEOUT, time.perf_counter() - start
        raise
    return normalise(rows), time.perf_counter() - start


def run_case(case, conn, session, args, writer):
    print(f"\n{'=' * 72}\n{case['label']}\n{'=' * 72}")

    for _ in range(args.warmup):
        time_postgres(conn, case["pg_sql"], case["pg_params"])
        time_neo4j(session, case["cypher"], case["neo4j_params"], args.timeout)

    pg_times, neo4j_times = [], []
    pg_result = neo4j_result = None

    for run in range(1, args.runs + 1):
        # Alternate which system goes first, so neither systematically finds the
        # operating-system cache warmed by the other.
        if run % 2 == 1:
            pg_result, pg_elapsed = time_postgres(conn, case["pg_sql"], case["pg_params"])
            neo4j_result, neo4j_elapsed = time_neo4j(
                session, case["cypher"], case["neo4j_params"], args.timeout)
        else:
            neo4j_result, neo4j_elapsed = time_neo4j(
                session, case["cypher"], case["neo4j_params"], args.timeout)
            pg_result, pg_elapsed = time_postgres(conn, case["pg_sql"], case["pg_params"])

        for system, elapsed, result, times in (
            ("postgresql", pg_elapsed, pg_result, pg_times),
            ("neo4j", neo4j_elapsed, neo4j_result, neo4j_times),
        ):
            timed_out = result == TIMEOUT
            if not timed_out:
                times.append(elapsed)
            writer.writerow({
                "query": case["name"], "case": case["case"], "system": system, "run": run,
                "seconds": "" if timed_out else f"{elapsed:.6f}",
                "rows": "" if timed_out else len(result),
                "min_votes": args.min_votes, "note": TIMEOUT if timed_out else "",
            })

        if TIMEOUT in (pg_result, neo4j_result):
            print(f"  timed out after {args.timeout}s — skipping the remaining runs")
            break

    report(pg_times, neo4j_times, pg_result, neo4j_result, args)
    return agree(pg_result, neo4j_result)


def summarise(times):
    if not times:
        return f"{TIMEOUT:>12}"
    return f"{statistics.median(times):8.4f}s [{min(times):.4f}-{max(times):.4f}]"


def report(pg_times, neo4j_times, pg_result, neo4j_result, args):
    print(f"  PostgreSQL  {summarise(pg_times)}   ({len(pg_times)} runs)")
    print(f"  Neo4j       {summarise(neo4j_times)}   ({len(neo4j_times)} runs)")

    if pg_times and neo4j_times:
        pg_median, neo4j_median = statistics.median(pg_times), statistics.median(neo4j_times)
        faster, ratio = (("Neo4j", pg_median / neo4j_median) if neo4j_median < pg_median
                         else ("PostgreSQL", neo4j_median / pg_median))
        print(f"  -> {faster} faster by {ratio:.1f}x (medians)")

    rows = pg_result if pg_result != TIMEOUT else neo4j_result
    if rows and rows != TIMEOUT:
        print("  result:")
        for row in rows[:args.show]:
            print(f"    {row}")


def agree(pg_result, neo4j_result):
    if TIMEOUT in (pg_result, neo4j_result):
        print("  result comparison skipped: one system timed out")
        return True
    if pg_result == neo4j_result:
        print("  identical results in both systems")
        return True

    print("  MISMATCH")
    print(f"    PostgreSQL: {len(pg_result)} rows, Neo4j: {len(neo4j_result)} rows")
    for i, (a, b) in enumerate(zip(pg_result, neo4j_result)):
        if a != b:
            print(f"    first difference at row {i}:\n      PostgreSQL: {a}\n      Neo4j:      {b}")
            break
    return False


def capture_plans(cases, conn, session, min_votes):
    out_dir = os.path.join(PLANS_DIR, f"mv{min_votes}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n{'=' * 72}\nExecution plans -> {out_dir}/\n{'=' * 72}")

    for case in cases:
        with conn.cursor() as cursor:
            try:
                cursor.execute("EXPLAIN (ANALYZE, BUFFERS) " + case["pg_sql"],
                               case["pg_params"] or None)
                plan = "\n".join(line[0] for line in cursor.fetchall())
            except pg_errors.QueryCanceled:
                conn.rollback()
                plan = "-- query cancelled: timeout"
        conn.commit()
        with open(os.path.join(out_dir, f"{case['case']}.postgresql.txt"), "w") as f:
            f.write(plan + "\n")

        try:
            result = session.run("PROFILE " + case["cypher"], **case["neo4j_params"])
            profile = str(result.consume().profile)
        except Neo4jError as exc:
            profile = f"// query failed or was cancelled: {exc}"
        with open(os.path.join(out_dir, f"{case['case']}.neo4j.txt"), "w") as f:
            f.write(profile + "\n")

        print(f"  {case['case']}")


def build_cases(args):
    pairs = load_pairs(args.min_votes)
    q1_sql = load_query(PG_QUERY_DIR, "q1_shortest_path", "sql")
    q1_cypher = load_query(NEO4J_QUERY_DIR, "q1_shortest_path", "cypher")

    cases = []
    for target in pairs["targets"]:
        distance = target["distance"]
        # Both systems get the same explicit depth limit, so they answer the same
        # question: is there a path of length <= distance?
        cases.append({
            "name": "q1_shortest_path",
            "case": f"q1_distance_{distance}",
            "label": (f"Q1 - degrees of separation: {pairs['source']['name']} -> "
                      f"{target['name']} (expected {distance}, limit {distance})"),
            "pg_sql": q1_sql,
            "cypher": q1_cypher.replace("__MAXLEN__", str(2 * distance)),
            "pg_params": {"src": pairs["source"]["nconst"], "dst": target["nconst"],
                          "max_depth": distance},
            "neo4j_params": {"src": pairs["source"]["nconst"], "dst": target["nconst"]},
        })

    for name, label, params in (
        ("q2_most_connected", "Q2 - most connected actors (top 10)", {}),
        ("q3_genre_by_decade", "Q3 - average rating by genre, 2010s", {}),
        ("q4_recommendations", f"Q4 - films recommended from {args.tconst}",
         {"tconst": args.tconst}),
    ):
        cases.append({
            "name": name, "case": name, "label": label,
            "pg_sql": load_query(PG_QUERY_DIR, name, "sql"),
            "cypher": load_query(NEO4J_QUERY_DIR, name, "cypher"),
            "pg_params": params, "neo4j_params": params,
        })

    return cases


def load_pairs(min_votes):
    path = os.path.join(ANALYSIS_DIR, f"pairs_mv{min_votes}.json")
    if not os.path.exists(path):
        sys.exit(f"{path} not found — run: python scripts/find_pairs.py --min-votes {min_votes}")
    with open(path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Run the four queries on both databases and compare timings.")
    parser.add_argument("--runs", type=int, default=10, help="timed executions per query")
    parser.add_argument("--warmup", type=int, default=2, help="untimed warm-up executions")
    parser.add_argument("--timeout", type=int, default=300, help="per-query timeout in seconds")
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="vote threshold of the loaded dataset")
    parser.add_argument("--tconst", default=THE_MATRIX, help="starting title for Q4")
    parser.add_argument("--show", type=int, default=5, help="result rows to print")
    parser.add_argument("--append", action="store_true",
                        help="append to results.csv instead of overwriting it")
    parser.add_argument("--no-plans", action="store_true", help="skip execution plan capture")
    args = parser.parse_args()

    cases = build_cases(args)

    conn = psycopg2.connect(**POSTGRES)
    with conn.cursor() as cursor:
        cursor.execute(f"SET statement_timeout = '{args.timeout}s'")
    conn.commit()

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    driver.verify_connectivity()

    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    append = args.append and os.path.exists(RESULTS_CSV)
    mismatches = []

    with open(RESULTS_CSV, "a" if append else "w", newline="") as f, driver.session() as session:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not append:
            writer.writeheader()

        for case in cases:
            if not run_case(case, conn, session, args, writer):
                mismatches.append(case["case"])

        if not args.no_plans:
            capture_plans(cases, conn, session, args.min_votes)

    conn.close()
    driver.close()

    print(f"\nResults written to {RESULTS_CSV}")
    if mismatches:
        print(f"\n{len(mismatches)} queries returned different results in the two systems: "
              f"{', '.join(mismatches)}")
        print("The timings are not comparable until this is resolved.")
        return 1

    print("All queries returned identical results in both systems.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
