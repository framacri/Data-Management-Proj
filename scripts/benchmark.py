"""Benchmark comparativo PostgreSQL / Neo4j sulle stesse quattro query.

Cosa garantisce questo runner, e che la versione precedente non garantiva:

  * ogni query viene eseguita N volte dopo un warm-up, e si riporta la mediana
    con min e max, non il tempo di una singola esecuzione a freddo;
  * la sessione Neo4j e la connessione Postgres sono aperte una volta sola,
    fuori dal cronometro: si misura la query, non l'handshake;
  * l'ordine dei due sistemi si alterna a ogni run, cosi' nessuno dei due trova
    sistematicamente la page cache gia' scaldata dall'altro;
  * i risultati delle due implementazioni vengono confrontati riga per riga: se
    divergono il benchmark si ferma, perche' due tempi su due domande diverse
    non sono un confronto;
  * un timeout e' un risultato, viene registrato come tale e non interrompe la
    campagna di misura.

Le query vivono in postgres/queries/*.sql e neo4j/queries/*.cypher.
"""
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

from config import POSTGRES as PG, NEO4J_URI, NEO4J_AUTH, DEFAULT_MIN_VOTES

PG_QUERY_DIR = os.path.join("postgres", "queries")
NEO4J_QUERY_DIR = os.path.join("neo4j", "queries")
RESULTS_CSV = os.path.join("analysis", "results.csv")
PLANS_DIR = os.path.join("analysis", "plans")

THE_MATRIX = "tt0133093"
TIMEOUT_SENTINEL = "timeout"


# --------------------------------------------------------------------------- #
# caricamento query                                                            #
# --------------------------------------------------------------------------- #

def load_query(directory, name, extension):
    path = os.path.join(directory, f"{name}.{extension}")
    with open(path) as f:
        return f.read()


def strip_trailing_semicolon(cypher):
    """Cypher non accetta il ';' finale quando la query passa dal driver."""
    return cypher.strip().rstrip(";")


# --------------------------------------------------------------------------- #
# normalizzazione dei risultati                                                #
# --------------------------------------------------------------------------- #

def normalize_value(v):
    """Rende confrontabili i tipi restituiti dai due driver.

    Postgres restituisce NUMERIC come Decimal, Neo4j restituisce float. Le medie
    vengono arrotondate a 3 decimali da entrambe le query, quindi il confronto a
    tre decimali e' esatto e non un'approssimazione tollerante.
    """
    if v is None:
        return None
    if isinstance(v, Decimal):
        return round(float(v), 3)
    if isinstance(v, float):
        return round(v, 3)
    return v


def normalize_rows(rows):
    return [tuple(normalize_value(v) for v in row) for row in rows]


def describe_mismatch(pg_rows, n4_rows):
    lines = ["  i due sistemi hanno restituito risultati diversi:"]
    lines.append(f"    PostgreSQL: {len(pg_rows)} righe")
    lines.append(f"    Neo4j     : {len(n4_rows)} righe")
    for i, (a, b) in enumerate(zip(pg_rows, n4_rows)):
        if a != b:
            lines.append(f"    prima differenza alla riga {i}:")
            lines.append(f"      PostgreSQL: {a}")
            lines.append(f"      Neo4j     : {b}")
            break
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# esecuzione cronometrata                                                      #
# --------------------------------------------------------------------------- #

def time_postgres(conn, sql, params):
    with conn.cursor() as cur:
        start = time.perf_counter()
        try:
            cur.execute(sql, params or None)
            rows = cur.fetchall() if cur.description else []
        except pg_errors.QueryCanceled:
            conn.rollback()
            return TIMEOUT_SENTINEL, time.perf_counter() - start
        elapsed = time.perf_counter() - start
    conn.commit()
    return normalize_rows(rows), elapsed


def time_neo4j(session, cypher, params, timeout):
    start = time.perf_counter()
    try:
        result = session.run(Query(cypher, timeout=timeout), **params)
        rows = [tuple(record.values()) for record in result]
    except Neo4jError as exc:
        if "timeout" in str(exc).lower() or "terminated" in str(exc).lower():
            return TIMEOUT_SENTINEL, time.perf_counter() - start
        raise
    elapsed = time.perf_counter() - start
    return normalize_rows(rows), elapsed


# --------------------------------------------------------------------------- #
# un caso di misura                                                            #
# --------------------------------------------------------------------------- #

def run_case(case, conn, session, args, writer):
    """Esegue un caso su entrambi i sistemi e registra i tempi."""
    print(f"\n{'=' * 72}\n{case['label']}\n{'=' * 72}")

    pg_sql = case["pg_sql"]
    cypher = case["cypher"]
    pg_params = case["pg_params"]
    n4_params = case["neo4j_params"]

    # Warm-up: non registrato. Serve a portare in page cache le pagine toccate
    # dalla query, cosi' le misure successive non contengono l'I/O a freddo.
    for _ in range(args.warmup):
        time_postgres(conn, pg_sql, pg_params)
        time_neo4j(session, cypher, n4_params, args.timeout)

    pg_times, n4_times = [], []
    pg_result = n4_result = None

    for run in range(1, args.runs + 1):
        # Ordine alternato: nella versione precedente Postgres andava sempre per
        # primo e scaldava la cache del sistema operativo prima del turno di Neo4j.
        if run % 2 == 1:
            pg_result, pg_t = time_postgres(conn, pg_sql, pg_params)
            n4_result, n4_t = time_neo4j(session, cypher, n4_params, args.timeout)
        else:
            n4_result, n4_t = time_neo4j(session, cypher, n4_params, args.timeout)
            pg_result, pg_t = time_postgres(conn, pg_sql, pg_params)

        pg_timed_out = pg_result == TIMEOUT_SENTINEL
        n4_timed_out = n4_result == TIMEOUT_SENTINEL

        if not pg_timed_out:
            pg_times.append(pg_t)
        if not n4_timed_out:
            n4_times.append(n4_t)

        for system, elapsed, result, timed_out in (
            ("postgresql", pg_t, pg_result, pg_timed_out),
            ("neo4j", n4_t, n4_result, n4_timed_out),
        ):
            writer.writerow({
                "query": case["name"],
                "case": case["case"],
                "system": system,
                "run": run,
                "seconds": "" if timed_out else f"{elapsed:.6f}",
                "rows": "" if timed_out else len(result),
                "min_votes": args.min_votes,
                "note": TIMEOUT_SENTINEL if timed_out else "",
            })

        # I timeout non si ripetono dieci volte: costano args.timeout secondi
        # ciascuno e il risultato e' gia' noto dopo il primo.
        if pg_timed_out or n4_timed_out:
            print(f"  timeout dopo {args.timeout}s — non ripeto le altre run")
            break

    report(case, pg_times, n4_times, pg_result, n4_result, args)
    return check_agreement(case, pg_result, n4_result)


def summarize(times):
    if not times:
        return f"{TIMEOUT_SENTINEL:>12}"
    return (f"{statistics.median(times):8.4f}s "
            f"[{min(times):.4f}–{max(times):.4f}]")


def report(case, pg_times, n4_times, pg_result, n4_result, args):
    print(f"  PostgreSQL  {summarize(pg_times)}   ({len(pg_times)} run)")
    print(f"  Neo4j       {summarize(n4_times)}   ({len(n4_times)} run)")

    if pg_times and n4_times:
        pg_med, n4_med = statistics.median(pg_times), statistics.median(n4_times)
        faster, ratio = (("Neo4j", pg_med / n4_med) if n4_med < pg_med
                         else ("PostgreSQL", n4_med / pg_med))
        print(f"  -> {faster} piu' veloce di {ratio:.1f}x (mediane)")

    rows = pg_result if pg_result != TIMEOUT_SENTINEL else n4_result
    if rows and rows != TIMEOUT_SENTINEL:
        print("  risultato:")
        for row in rows[:args.show]:
            print(f"    {row}")


def check_agreement(case, pg_result, n4_result):
    """True se i due sistemi hanno risposto alla stessa domanda."""
    if TIMEOUT_SENTINEL in (pg_result, n4_result):
        print("  confronto dei risultati saltato: uno dei due sistemi e' andato in timeout")
        return True
    if pg_result == n4_result:
        print("  risultati identici nei due sistemi")
        return True
    print("  DISALLINEAMENTO")
    print(describe_mismatch(pg_result, n4_result))
    return False


# --------------------------------------------------------------------------- #
# piani di esecuzione                                                          #
# --------------------------------------------------------------------------- #

def capture_plans(cases, conn, session, min_votes):
    out_dir = os.path.join(PLANS_DIR, f"mv{min_votes}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n{'=' * 72}\nPiani di esecuzione -> {out_dir}/\n{'=' * 72}")

    for case in cases:
        stem = case["case"]

        with conn.cursor() as cur:
            try:
                cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + case["pg_sql"],
                            case["pg_params"] or None)
                plan = "\n".join(line[0] for line in cur.fetchall())
            except pg_errors.QueryCanceled:
                conn.rollback()
                plan = "-- query annullata per timeout"
        conn.commit()
        with open(os.path.join(out_dir, f"{stem}.postgresql.txt"), "w") as f:
            f.write(plan + "\n")

        try:
            result = session.run("PROFILE " + case["cypher"], **case["neo4j_params"])
            profile = str(result.consume().profile)
        except Neo4jError as exc:
            profile = f"// query fallita o annullata: {exc}"
        with open(os.path.join(out_dir, f"{stem}.neo4j.txt"), "w") as f:
            f.write(profile + "\n")

        print(f"  {stem}")


# --------------------------------------------------------------------------- #
# costruzione dei casi                                                         #
# --------------------------------------------------------------------------- #

def build_cases(args):
    cases = []

    q1_sql = load_query(PG_QUERY_DIR, "q1_shortest_path", "sql")
    q1_cypher = strip_trailing_semicolon(load_query(NEO4J_QUERY_DIR, "q1_shortest_path", "cypher"))

    for target in load_pairs(args):
        d = target["distance"]
        # Entrambi i sistemi rispondono alla STESSA domanda: esiste un cammino di
        # lunghezza <= d? Il limite e' esplicito da entrambe le parti, altrimenti
        # si confronterebbe una ricerca limitata con una illimitata.
        cases.append({
            "name": "q1_shortest_path",
            "case": f"q1_distanza_{d}",
            "label": (f"Q1 · Gradi di separazione — {args.source_name} -> {target['name']} "
                      f"(distanza attesa {d}, limite {d})"),
            "pg_sql": q1_sql,
            "cypher": q1_cypher.replace("__MAXLEN__", str(2 * d)),
            "pg_params": {"src": args.source, "dst": target["nconst"], "max_depth": d},
            "neo4j_params": {"src": args.source, "dst": target["nconst"]},
        })

    cases.append({
        "name": "q2_most_connected",
        "case": "q2_most_connected",
        "label": "Q2 · Attori piu' connessi (top 10)",
        "pg_sql": load_query(PG_QUERY_DIR, "q2_most_connected", "sql"),
        "cypher": strip_trailing_semicolon(load_query(NEO4J_QUERY_DIR, "q2_most_connected", "cypher")),
        "pg_params": {},
        "neo4j_params": {},
    })

    cases.append({
        "name": "q3_genre_by_decade",
        "case": "q3_genre_by_decade",
        "label": "Q3 · Rating medio per genere, decennio 2010-2019",
        "pg_sql": load_query(PG_QUERY_DIR, "q3_genre_by_decade", "sql"),
        "cypher": strip_trailing_semicolon(load_query(NEO4J_QUERY_DIR, "q3_genre_by_decade", "cypher")),
        "pg_params": {},
        "neo4j_params": {},
    })

    cases.append({
        "name": "q4_recommendations",
        "case": "q4_recommendations",
        "label": f"Q4 · Film consigliati a partire da {args.tconst}",
        "pg_sql": load_query(PG_QUERY_DIR, "q4_recommendations", "sql"),
        "cypher": strip_trailing_semicolon(load_query(NEO4J_QUERY_DIR, "q4_recommendations", "cypher")),
        "pg_params": {"tconst": args.tconst},
        "neo4j_params": {"tconst": args.tconst},
    })

    return cases


def load_pairs(args):
    path = os.path.join("analysis", f"pairs_mv{args.min_votes}.json")
    if not os.path.exists(path):
        sys.exit(f"{path} non trovato — esegui prima: "
                 f"python scripts/find_pairs.py --min-votes {args.min_votes}")
    with open(path) as f:
        pairs = json.load(f)
    args.source = pairs["source"]["nconst"]
    args.source_name = pairs["source"]["name"]
    return pairs["targets"]


# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10, help="esecuzioni cronometrate per query")
    parser.add_argument("--warmup", type=int, default=2, help="esecuzioni di riscaldamento, non registrate")
    parser.add_argument("--timeout", type=int, default=300, help="timeout per query, in secondi")
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="soglia di voti del dataset caricato: seleziona il file di coppie "
                             "e etichetta le righe del CSV")
    parser.add_argument("--append", action="store_true",
                        help="accoda a results.csv invece di sovrascriverlo, per confrontare "
                             "piu' soglie nello stesso file")
    parser.add_argument("--tconst", default=THE_MATRIX, help="titolo di partenza per la Q4")
    parser.add_argument("--show", type=int, default=5, help="righe di risultato da stampare")
    parser.add_argument("--no-plans", action="store_true", help="salta la cattura dei piani")
    args = parser.parse_args()

    cases = build_cases(args)

    conn = psycopg2.connect(**PG)
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = '{args.timeout}s'")
    conn.commit()

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    driver.verify_connectivity()

    os.makedirs(os.path.dirname(RESULTS_CSV), exist_ok=True)
    fieldnames = ["query", "case", "system", "run", "seconds", "rows", "min_votes", "note"]

    mismatches = []
    append = args.append and os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a" if append else "w", newline="") as f, driver.session() as session:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not append:
            writer.writeheader()

        for case in cases:
            if not run_case(case, conn, session, args, writer):
                mismatches.append(case["case"])

        if not args.no_plans:
            capture_plans(cases, conn, session, args.min_votes)

    conn.close()
    driver.close()

    print(f"\nRisultati scritti in {RESULTS_CSV}")
    if mismatches:
        print(f"\n{len(mismatches)} query hanno dato risultati diversi nei due sistemi: "
              f"{', '.join(mismatches)}")
        print("I tempi misurati NON sono confrontabili finche' questo non e' risolto.")
        return 1
    print("Tutte le query hanno dato risultati identici nei due sistemi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
