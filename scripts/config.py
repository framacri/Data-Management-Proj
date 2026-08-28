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
DEFAULT_MIN_VOTES = 1000


def data_subdir(min_votes):
    return f"mv{min_votes}"


def data_path(min_votes, filename=""):
    # Generated CSVs must stay under DATA_DIR: docker-compose mounts it as
    # Neo4j's import directory, which is where LOAD CSV reads 'file:///...'.
    return os.path.join(DATA_DIR, data_subdir(min_votes), filename)
