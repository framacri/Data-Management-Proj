"""Configurazione condivisa da tutti gli script della pipeline.

Host, porte e credenziali stavano duplicati in quattro file: bastava cambiare
una porta nel docker-compose per doverla inseguire ovunque. Qui stanno in un
posto solo, sovrascrivibili da variabile d'ambiente per chi gira i database
altrove che in locale.
"""
import os

POSTGRES = {
    "host": os.environ.get("PGHOST", "localhost"),
    "port": os.environ.get("PGPORT", "15432"),
    "user": os.environ.get("PGUSER", "imdb"),
    "password": os.environ.get("PGPASSWORD", "imdbpassword"),
    "dbname": os.environ.get("PGDATABASE", "imdb"),
}

NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_AUTH = (
    os.environ.get("NEO4J_USER", "neo4j"),
    os.environ.get("NEO4J_PASSWORD", "imdbpassword"),
)

DATA_DIR = "data"
ANALYSIS_DIR = "analysis"

# Soglia di voti predefinita del working set.
DEFAULT_MIN_VOTES = 1000


def data_subdir(min_votes):
    """Sottocartella di data/ per una soglia di voti.

    I CSV devono restare sotto data/, che il docker-compose monta come cartella
    di import di Neo4j: e' da li' che LOAD CSV legge 'file:///...'.
    """
    return f"mv{min_votes}"


def data_path(min_votes, filename=""):
    return os.path.join(DATA_DIR, data_subdir(min_votes), filename)
