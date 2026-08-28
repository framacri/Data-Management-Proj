import argparse
import os

import psycopg2

from config import POSTGRES, DEFAULT_MIN_VOTES, data_path

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

# Persons must precede Title_Principals, which has a foreign key to it.
TABLES = [
    ("Titles", "pg_titles.csv"),
    ("Persons", "pg_persons.csv"),
    ("Genres", "pg_genres.csv"),
    ("Title_Genres", "pg_title_genres.csv"),
    ("Title_Principals", "pg_principals.csv"),
]


def load_data(min_votes):
    conn = psycopg2.connect(**POSTGRES)
    conn.autocommit = True
    cursor = conn.cursor()

    print("Applying schema...")
    with open(SCHEMA_PATH) as f:
        cursor.execute(f.read())

    for table, filename in TABLES:
        path = data_path(min_votes, filename)
        print(f"Loading {table} from {path}...")
        with open(path) as f:
            next(f)
            cursor.copy_expert(f"COPY {table} FROM STDIN WITH CSV", f)

    # COPY does not update planner statistics. Without this, plans depend on when
    # autovacuum happens to run, and queries issued in the meantime are planned
    # blind. See PROJECT_REPORT.md, section 10.
    print("ANALYZE...")
    cursor.execute("ANALYZE")

    print("Done.")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load the PostgreSQL tables from the CSVs.")
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="vote threshold, selecting the data/mv<threshold>/ directory")
    load_data(parser.parse_args().min_votes)
