"""Carica nodi e archi in Neo4j a partire dai CSV prodotti da preprocess_data.py."""
import argparse
import os

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_AUTH, DEFAULT_MIN_VOTES, data_subdir

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "neo4j_schema.cypher")

BATCH = 50000

# I nodi vanno prima degli archi: i MATCH degli archi cercano nodi gia' esistenti.
# Ogni blocco e' batchato, nodi compresi: :Person sono centinaia di migliaia e in
# una transazione sola non entrerebbero nell'heap da 1G.
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

# I tre tipi di relazione persona-titolo partizionano le righe di
# Title_Principals: quello che entra in Postgres entra anche qui.
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


def batched_load_csv(csv_uri, body):
    return f"""
        LOAD CSV WITH HEADERS FROM '{csv_uri}' AS row
        CALL {{
            WITH row
            {body.strip()}
        }} IN TRANSACTIONS OF {BATCH} ROWS
    """


DELETE_BATCH = 10000


def reset(session):
    """Svuota il database prima di ricaricare.

    Serve davvero: i caricamenti usano MERGE, quindi senza svuotare, i dati di una
    soglia di voti precedente resterebbero nel grafo e si sommerebbero ai nuovi.
    I constraint non vengono toccati: sono schema, non dati.

    Sulla forma della cancellazione. L'idioma

        MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS

    non basta: il MATCH a monte produce comunque l'intero flusso di nodi, e su un
    grafo da centinaia di migliaia di nodi con milioni di archi esaurisce il
    memory pool prima che il batching serva a qualcosa. Qui il limite e' dentro
    ogni statement (WITH ... LIMIT), quindi la memoria di ogni transazione e'
    limitata per costruzione, indipendentemente da quanto e' grande il grafo.
    Gli archi vanno cancellati prima dei nodi: e' molto piu' leggero di un
    DETACH DELETE, che per ogni nodo deve risalire a tutte le sue relazioni.
    """
    print("Svuotamento del database...")

    def delete_all(cypher, counter):
        total = 0
        while True:
            summary = session.run(cypher, batch=DELETE_BATCH).consume()
            deleted = getattr(summary.counters, counter)
            if deleted == 0:
                return total
            total += deleted

    rels = delete_all("MATCH ()-[r]->() WITH r LIMIT $batch DELETE r", "relationships_deleted")
    print(f"  archi cancellati: {rels}")
    nodes = delete_all("MATCH (n) WITH n LIMIT $batch DELETE n", "nodes_deleted")
    print(f"  nodi cancellati:  {nodes}")


def load_data(min_votes, do_reset):
    subdir = data_subdir(min_votes)
    driver = connect()

    with driver.session() as session:
        if do_reset:
            reset(session)

        print("Creazione di constraint e indici...")
        with open(SCHEMA_PATH) as f:
            for statement in f.read().split(';'):
                if statement.strip():
                    session.run(statement)

        for label, filename, body in NODE_LOADS + EDGE_LOADS:
            print(f"Caricamento {label} da {subdir}/{filename}...")
            session.run(batched_load_csv(f"file:///{subdir}/{filename}", body))

        # Simmetrico all'ANALYZE lato Postgres: garantisce che gli indici siano
        # online e popolati prima che qualcuno misuri una query.
        print("Attesa che gli indici siano online...")
        session.run("CALL db.awaitIndexes()")

        print("Caricamento completato.")

    driver.close()


def connect():
    return GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="soglia di voti del working set: determina la sottocartella di data/")
    parser.add_argument("--reset", action="store_true",
                        help="svuota il database prima di caricare (necessario per ricaricare "
                             "una soglia diversa: il load usa MERGE e non sovrascrive)")
    args = parser.parse_args()
    load_data(args.min_votes, args.reset)
