from neo4j import GraphDatabase
import os

URI = "neo4j://localhost:7687"
AUTH = ("neo4j", "imdbpassword")

# Wait until Neo4j is ready in docker
def connect():
    return GraphDatabase.driver(URI, auth=AUTH)

def load_data():
    driver = connect()
    
    with driver.session() as session:
        print("Creating constraints and indices...")
        with open("scripts/neo4j_schema.cypher", "r") as f:
            queries = f.read().split(';')
            for q in queries:
                if q.strip():
                    session.run(q)
                    
        print("Loading Titles...")
        session.run('''
            LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodes_titles.csv' AS row
            MERGE (t:Title {tconst: row.tconst})
            SET t.primaryTitle = row.primaryTitle,
                t.startYear = toInteger(row.startYear),
                t.runtimeMinutes = toInteger(row.runtimeMinutes),
                t.averageRating = toFloat(row.averageRating),
                t.numVotes = toInteger(row.numVotes)
        ''')
        
        print("Loading Genres...")
        session.run('''
            LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodes_genres.csv' AS row
            MERGE (g:Genre {name: row.name})
        ''')
        
        print("Loading Persons...")
        session.run('''
            LOAD CSV WITH HEADERS FROM 'file:///neo4j_nodes_persons.csv' AS row
            MERGE (p:Person {nconst: row.nconst})
            SET p.primaryName = row.primaryName,
                p.birthYear = toInteger(row.birthYear)
        ''')
        
        print("Loading HAS_GENRE edges...")
        session.run('''
            LOAD CSV WITH HEADERS FROM 'file:///neo4j_edges_has_genre.csv' AS row
            MATCH (t:Title {tconst: row.tconst})
            MATCH (g:Genre {name: row.genre_name})
            MERGE (t)-[:HAS_GENRE]->(g)
        ''')
        
        # Gli archi sono batchati in transazioni da 50k righe per non far
        # esplodere l'heap. I tre file coprono, in partizione, tutte le righe
        # di pg_principals.csv: nessun ruolo entra in un solo sistema.
        print("Loading ACTED_IN edges...")
        session.run('''
            LOAD CSV WITH HEADERS FROM 'file:///neo4j_edges_acted_in.csv' AS row
            CALL {
                WITH row
                MATCH (t:Title {tconst: row.tconst})
                MATCH (p:Person {nconst: row.nconst})
                MERGE (p)-[r:ACTED_IN]->(t)
                SET r.ordering = toInteger(row.ordering)
            } IN TRANSACTIONS OF 50000 ROWS
        ''')
        
        print("Loading DIRECTED edges...")
        session.run('''
            LOAD CSV WITH HEADERS FROM 'file:///neo4j_edges_directed.csv' AS row
            CALL {
                WITH row
                MATCH (t:Title {tconst: row.tconst})
                MATCH (p:Person {nconst: row.nconst})
                MERGE (p)-[:DIRECTED]->(t)
            } IN TRANSACTIONS OF 50000 ROWS
        ''')

        print("Loading WORKED_ON edges...")
        session.run('''
            LOAD CSV WITH HEADERS FROM 'file:///neo4j_edges_worked_on.csv' AS row
            CALL {
                WITH row
                MATCH (t:Title {tconst: row.tconst})
                MATCH (p:Person {nconst: row.nconst})
                MERGE (p)-[:WORKED_ON {category: row.category}]->(t)
            } IN TRANSACTIONS OF 50000 ROWS
        ''')

        print("Data loading complete!")
        
    driver.close()

if __name__ == "__main__":
    load_data()
