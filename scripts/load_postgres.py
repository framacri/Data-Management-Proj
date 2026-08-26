import psycopg2
import os

DB_HOST = "localhost"
DB_PORT = "15432"
DB_USER = "imdb"
DB_PASS = "imdbpassword"
DB_NAME = "imdb"
DATA_DIR = "data"

def connect():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        dbname=DB_NAME
    )

def load_data():
    conn = connect()
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Load Schema
    print("Applying schema...")
    with open("scripts/schema.sql", "r") as f:
        cursor.execute(f.read())
        
    print("Loading pg_titles.csv...")
    with open(os.path.join(DATA_DIR, "pg_titles.csv"), "r") as f:
        next(f) # Skip header
        cursor.copy_expert("COPY Titles FROM STDIN WITH CSV", f)
        
    print("Loading pg_persons.csv...")
    with open(os.path.join(DATA_DIR, "pg_persons.csv"), "r") as f:
        next(f)
        cursor.copy_expert("COPY Persons FROM STDIN WITH CSV", f)
        
    print("Loading pg_genres.csv...")
    with open(os.path.join(DATA_DIR, "pg_genres.csv"), "r") as f:
        next(f)
        cursor.copy_expert("COPY Genres FROM STDIN WITH CSV", f)
        
    print("Loading pg_title_genres.csv...")
    with open(os.path.join(DATA_DIR, "pg_title_genres.csv"), "r") as f:
        next(f)
        cursor.copy_expert("COPY Title_Genres FROM STDIN WITH CSV", f)
        
    print("Loading pg_principals.csv...")
    with open(os.path.join(DATA_DIR, "pg_principals.csv"), "r") as f:
        next(f)
        cursor.copy_expert("COPY Title_Principals FROM STDIN WITH CSV", f)
        
    print("Data loading complete!")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    load_data()
