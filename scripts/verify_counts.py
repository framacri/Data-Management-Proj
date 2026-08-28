import sys

import psycopg2
from neo4j import GraphDatabase

from config import POSTGRES, NEO4J_URI, NEO4J_AUTH

ACTING = "('actor', 'actress')"
DIRECTING = "('director')"

# The Neo4j load uses MERGE, so two principal rows sharing (tconst, nconst) and
# category produce a single relationship. The PostgreSQL side must therefore
# count DISTINCT keys rather than rows.
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
    ("actors / ACTED_IN",
     f"SELECT COUNT(DISTINCT (tconst, nconst)) FROM Title_Principals WHERE category IN {ACTING}",
     "MATCH ()-[r:ACTED_IN]->() RETURN count(r)"),
    ("directors / DIRECTED",
     f"SELECT COUNT(DISTINCT (tconst, nconst)) FROM Title_Principals WHERE category IN {DIRECTING}",
     "MATCH ()-[r:DIRECTED]->() RETURN count(r)"),
    ("other roles / WORKED_ON",
     f"SELECT COUNT(DISTINCT (tconst, nconst, category)) FROM Title_Principals "
     f"WHERE category NOT IN {ACTING} AND category NOT IN {DIRECTING}",
     "MATCH ()-[r:WORKED_ON]->() RETURN count(r)"),
]

PG_ASSERTIONS = [
    ("principals with a dangling nconst",
     "SELECT COUNT(*) FROM Title_Principals tp "
     "LEFT JOIN Persons p ON tp.nconst = p.nconst WHERE p.nconst IS NULL", 0),
    ("titles without a rating",
     "SELECT COUNT(*) FROM Titles WHERE averageRating IS NULL", 0),
]


def main():
    try:
        conn = psycopg2.connect(**POSTGRES)
    except psycopg2.OperationalError as exc:
        sys.exit(f"PostgreSQL unreachable on {POSTGRES['host']}:{POSTGRES['port']} — {exc}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        sys.exit(f"Neo4j unreachable on {NEO4J_URI} — {exc}")

    failures = 0
    width = max(len(label) for label, _, _ in CHECKS)
    print(f"{'':<{width}}  {'PostgreSQL':>12}  {'Neo4j':>12}   status")
    print("-" * (width + 44))

    with conn.cursor() as cur, driver.session() as session:
        for label, sql, cypher in CHECKS:
            cur.execute(sql)
            pg_count = cur.fetchone()[0]
            neo4j_count = session.run(cypher).single()[0]
            match = pg_count == neo4j_count
            failures += not match
            status = "ok" if match else f"MISMATCH ({pg_count - neo4j_count:+,})"
            print(f"{label:<{width}}  {pg_count:>12,}  {neo4j_count:>12,}   {status}")

        print()
        for label, sql, expected in PG_ASSERTIONS:
            cur.execute(sql)
            actual = cur.fetchone()[0]
            failures += actual != expected
            status = "ok" if actual == expected else f"EXPECTED {expected}"
            print(f"{label:<{width}}  {actual:>12,}  {'':>12}   {status}")

    conn.close()
    driver.close()
    print()

    if failures:
        print(f"{failures} checks failed: the two databases do not hold the same data.")
        print("Do not run the benchmark — the measurements would not be comparable.")
        return 1

    print("All checks passed: the two databases hold the same data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
