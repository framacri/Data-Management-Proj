"""Verifica che PostgreSQL e Neo4j contengano esattamente gli stessi dati.

E' il cancello della Fase 1: finche' questo script non esce con 0, qualsiasi
misura di performance confronta carichi di lavoro diversi ed e' da buttare.

Nota sul confronto degli archi: il caricamento Neo4j usa MERGE (idempotente sui
retry), quindi due righe di principals con lo stesso (tconst, nconst) e la
stessa categoria producono UN SOLO arco. Il conteggio Postgres corrispondente
deve quindi essere DISTINCT sulle stesse chiavi, non un COUNT(*) di righe.
"""
import sys

import psycopg2
from neo4j import GraphDatabase

PG = dict(host="localhost", port="15432", user="imdb", password="imdbpassword", dbname="imdb")
NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "imdbpassword")

ACTING = "('actor', 'actress')"
DIRECTING = "('director')"

# (etichetta, SQL Postgres, Cypher Neo4j)
CHECKS = [
    ("Titles / :Title",
     "SELECT COUNT(*) FROM Titles",
     "MATCH (n:Title) RETURN count(n)"),
    ("Persons / :Person",
     "SELECT COUNT(*) FROM Persons",
     "MATCH (n:Person) RETURN count(n)"),
    ("Genres / :Genre",
     "SELECT COUNT(*) FROM Genres",
     "MATCH (n:Genre) RETURN count(n)"),
    ("Title_Genres / HAS_GENRE",
     "SELECT COUNT(*) FROM Title_Genres",
     "MATCH ()-[r:HAS_GENRE]->() RETURN count(r)"),
    ("attori / ACTED_IN",
     f"SELECT COUNT(DISTINCT (tconst, nconst)) FROM Title_Principals WHERE category IN {ACTING}",
     "MATCH ()-[r:ACTED_IN]->() RETURN count(r)"),
    ("registi / DIRECTED",
     f"SELECT COUNT(DISTINCT (tconst, nconst)) FROM Title_Principals WHERE category IN {DIRECTING}",
     "MATCH ()-[r:DIRECTED]->() RETURN count(r)"),
    ("altri ruoli / WORKED_ON",
     f"SELECT COUNT(DISTINCT (tconst, nconst, category)) FROM Title_Principals "
     f"WHERE category NOT IN {ACTING} AND category NOT IN {DIRECTING}",
     "MATCH ()-[r:WORKED_ON]->() RETURN count(r)"),
]

# Controlli che devono valere solo su Postgres.
PG_ASSERTIONS = [
    ("principals con nconst pendente",
     "SELECT COUNT(*) FROM Title_Principals tp "
     "LEFT JOIN Persons p ON tp.nconst = p.nconst WHERE p.nconst IS NULL",
     0),
    ("titoli senza rating",
     "SELECT COUNT(*) FROM Titles WHERE averageRating IS NULL",
     0),
]


def scalar_pg(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def scalar_neo4j(session, cypher):
    return session.run(cypher).single()[0]


def main():
    try:
        conn = psycopg2.connect(**PG)
    except psycopg2.OperationalError as exc:
        sys.exit(f"PostgreSQL non raggiungibile su {PG['host']}:{PG['port']} — {exc}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        sys.exit(f"Neo4j non raggiungibile su {NEO4J_URI} — {exc}")

    failures = 0
    width = max(len(label) for label, _, _ in CHECKS)

    print(f"{'':<{width}}  {'PostgreSQL':>12}  {'Neo4j':>12}   esito")
    print("-" * (width + 44))

    with conn.cursor() as cur, driver.session() as session:
        for label, sql, cypher in CHECKS:
            pg_n = scalar_pg(cur, sql)
            n4_n = scalar_neo4j(session, cypher)
            ok = pg_n == n4_n
            failures += not ok
            mark = "ok" if ok else f"DIVERGE ({pg_n - n4_n:+,})"
            print(f"{label:<{width}}  {pg_n:>12,}  {n4_n:>12,}   {mark}")

        print()
        for label, sql, expected in PG_ASSERTIONS:
            actual = scalar_pg(cur, sql)
            ok = actual == expected
            failures += not ok
            print(f"{label:<{width}}  {actual:>12,}  {'':>12}   {'ok' if ok else 'ATTESO ' + str(expected)}")

    conn.close()
    driver.close()

    print()
    if failures:
        print(f"{failures} controlli falliti — i due database NON contengono gli stessi dati.")
        print("Non proseguire con il benchmark: le misure non sarebbero confrontabili.")
        return 1

    print("Tutti i controlli passati: i due database contengono gli stessi dati.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
