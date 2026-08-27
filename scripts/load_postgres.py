"""Carica le tabelle PostgreSQL a partire dai CSV prodotti da preprocess_data.py."""
import argparse
import os

import psycopg2

from config import POSTGRES, DEFAULT_MIN_VOTES, data_path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "schema.sql")

# L'ordine conta: Persons prima di Title_Principals, altrimenti la foreign key
# su nconst non ha nulla da referenziare.
TABLES = [
    ("Titles", "pg_titles.csv"),
    ("Persons", "pg_persons.csv"),
    ("Genres", "pg_genres.csv"),
    ("Title_Genres", "pg_title_genres.csv"),
    ("Title_Principals", "pg_principals.csv"),
]


def connect():
    return psycopg2.connect(**POSTGRES)


def load_data(min_votes):
    conn = connect()
    conn.autocommit = True
    cursor = conn.cursor()

    print("Applicazione dello schema...")
    with open(SCHEMA_PATH) as f:
        cursor.execute(f.read())

    for table, filename in TABLES:
        path = data_path(min_votes, filename)
        print(f"Caricamento {table} da {path}...")
        with open(path) as f:
            next(f)  # intestazione
            cursor.copy_expert(f"COPY {table} FROM STDIN WITH CSV", f)

    # COPY non aggiorna le statistiche del planner: senza ANALYZE esplicito, i
    # piani dipendono da quando l'autovacuum passa per conto suo (naptime 60s di
    # default), e le prime query dopo il caricamento vengono pianificate al buio.
    # E' misurabile: nella campagna del 27/08 la fase Q1 della soglia >=10000 e'
    # girata dentro quella finestra e ha prodotto tempi fino a 13x peggiori del
    # piano reale della stessa query.
    print("ANALYZE...")
    cursor.execute("ANALYZE")

    print("Caricamento completato.")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="soglia di voti del working set: determina la sottocartella di data/")
    args = parser.parse_args()
    load_data(args.min_votes)
