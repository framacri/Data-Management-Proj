import argparse
import os

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_AUTH, DEFAULT_MIN_VOTES, data_subdir

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neo4j_schema.cypher")

LOAD_BATCH = 50000
DELETE_BATCH = 10000

NODE_LOADS = [
    ("Titles", "neo4j_nodes_titles.csv", """
        MERGE (t:Title {tconst: row.tconst})
        SET t.primaryTitle = row.primaryTitle,
            t.startYear = toInteger(row.startYear),
            t.runtimeMinutes = toInteger(row.runtimeMinutes),
            t.averageRating = toFloat(row.averageRating),
            t.numVotes = toInteger(row.numVotes)
    """),
    ("Genres", "neo4j_nodes_genres.csv", """
        MERGE (g:Genre {name: row.name})
    """),
    ("Persons", "neo4j_nodes_persons.csv", """
        MERGE (p:Person {nconst: row.nconst})
        SET p.primaryName = row.primaryName,
            p.birthYear = toInteger(row.birthYear)
    """),
]

EDGE_LOADS = [
    ("HAS_GENRE", "neo4j_edges_has_genre.csv", """
        MATCH (t:Title {tconst: row.tconst})
        MATCH (g:Genre {name: row.genre_name})
        MERGE (t)-[:HAS_GENRE]->(g)
    """),
    ("ACTED_IN", "neo4j_edges_acted_in.csv", """
        MATCH (t:Title {tconst: row.tconst})
        MATCH (p:Person {nconst: row.nconst})
        MERGE (p)-[r:ACTED_IN]->(t)
        SET r.ordering = toInteger(row.ordering)
    """),
    ("DIRECTED", "neo4j_edges_directed.csv", """
        MATCH (t:Title {tconst: row.tconst})
        MATCH (p:Person {nconst: row.nconst})
        MERGE (p)-[:DIRECTED]->(t)
    """),
    ("WORKED_ON", "neo4j_edges_worked_on.csv", """
        MATCH (t:Title {tconst: row.tconst})
        MATCH (p:Person {nconst: row.nconst})
        MERGE (p)-[:WORKED_ON {category: row.category}]->(t)
    """),
]


def batched_load(csv_uri, body):
    return f"""
        LOAD CSV WITH HEADERS FROM '{csv_uri}' AS row
        CALL {{
            WITH row
            {body.strip()}
        }} IN TRANSACTIONS OF {LOAD_BATCH} ROWS
    """


def reset(session):
    # Bounding each statement with WITH ... LIMIT keeps transaction memory
    # constant. The documented `MATCH (n) CALL { ... } IN TRANSACTIONS` idiom
    # still streams every node through the outer MATCH and exhausts the memory
    # pool on a graph this size. Relationships go first: much cheaper than
    # DETACH DELETE, which walks every node's relationships.
    def delete_all(cypher, counter):
        total = 0
        while True:
            summary = session.run(cypher, batch=DELETE_BATCH).consume()
            deleted = getattr(summary.counters, counter)
            if deleted == 0:
                return total
            total += deleted

    print("Clearing the database...")
    rels = delete_all("MATCH ()-[r]->() WITH r LIMIT $batch DELETE r", "relationships_deleted")
    nodes = delete_all("MATCH (n) WITH n LIMIT $batch DELETE n", "nodes_deleted")
    print(f"Deleted {rels} relationships and {nodes} nodes")


def load_data(min_votes, do_reset):
    subdir = data_subdir(min_votes)
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

    with driver.session() as session:
        if do_reset:
            reset(session)

        # Constraints before data: they generate the indexes the MATCH inside
        # each LOAD CSV relies on.
        print("Creating constraints and indexes...")
        with open(SCHEMA_PATH) as f:
            for statement in f.read().split(";"):
                if statement.strip():
                    session.run(statement)

        for label, filename, body in NODE_LOADS + EDGE_LOADS:
            print(f"Loading {label} from {subdir}/{filename}...")
            session.run(batched_load(f"file:///{subdir}/{filename}", body))

        session.run("CALL db.awaitIndexes()")
        print("Done.")

    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load the Neo4j graph from the CSVs.")
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="vote threshold, selecting the data/mv<threshold>/ directory")
    parser.add_argument("--reset", action="store_true",
                        help="clear the database first; required when reloading a different "
                             "threshold, since the load uses MERGE and does not overwrite")
    args = parser.parse_args()
    load_data(args.min_votes, args.reset)
