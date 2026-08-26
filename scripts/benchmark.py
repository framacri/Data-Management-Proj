import time
import psycopg2
from neo4j import GraphDatabase

DB_HOST = "localhost"
DB_PORT = "15432" # Changed to 15432 as per docker-compose
DB_USER = "imdb"
DB_PASS = "imdbpassword"
DB_NAME = "imdb"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "imdbpassword"

def run_postgres_query(conn, query, params=None):
    with conn.cursor() as cursor:
        start_time = time.time()
        cursor.execute(query, params)
        if cursor.description:
            results = cursor.fetchall()
        else:
            results = None
        end_time = time.time()
        return results, end_time - start_time

def run_neo4j_query(driver, query, params=None):
    with driver.session() as session:
        start_time = time.time()
        result = session.run(query, params)
        records = [record.values() for record in result]
        end_time = time.time()
        return records, end_time - start_time

def run_benchmarks():
    print("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME)
    
    print("Connecting to Neo4j...")
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    print("\n" + "="*50)
    print("QUERY 1: Shortest Path (Kevin Bacon to Tom Hanks)")
    print("="*50)
    
    pg_q1 = """
    WITH RECURSIVE path(actor, depth) AS (
        SELECT 'nm0000102'::VARCHAR, 0
        UNION
        SELECT tp2.nconst, p.depth + 1
        FROM path p
        JOIN title_principals tp1 ON p.actor = tp1.nconst
        JOIN title_principals tp2 ON tp1.tconst = tp2.tconst
        WHERE p.depth < 2 AND tp2.nconst != p.actor
    )
    SELECT MIN(depth) as degrees FROM path WHERE actor = 'nm0000158';
    """
    neo4j_q1 = """
    MATCH p=shortestPath((p1:Person {nconst: 'nm0000102'})-[:ACTED_IN*]-(p2:Person {nconst: 'nm0000158'}))
    RETURN length(p)/2 AS degrees_of_separation
    """
    
    pg_res, pg_time = run_postgres_query(pg_conn, pg_q1)
    print(f"[PostgreSQL] Result: {pg_res[0][0]} degrees | Time: {pg_time:.4f}s")
    
    n4j_res, n4j_time = run_neo4j_query(neo4j_driver, neo4j_q1)
    # n4j shortestPath returns a path. The length is number of relationships (edges).
    # Since relationships are Person->Title, length is 2 * degrees.
    res_val = n4j_res[0][0] if n4j_res else None
    print(f"[Neo4j] Result: {res_val} degrees | Time: {n4j_time:.4f}s")
    
    print("\n" + "="*50)
    print("QUERY 2: Most Connected Actors (Top 5)")
    print("="*50)
    
    pg_q2 = """
    SELECT tp1.nconst, COUNT(DISTINCT tp2.nconst) as coactors
    FROM Title_Principals tp1
    JOIN Title_Principals tp2 ON tp1.tconst = tp2.tconst AND tp1.nconst != tp2.nconst
    GROUP BY tp1.nconst
    ORDER BY coactors DESC
    LIMIT 5;
    """
    neo4j_q2 = """
    MATCH (p1:Person)-[:ACTED_IN|DIRECTED]->(t:Title)<-[:ACTED_IN|DIRECTED]-(p2:Person)
    RETURN p1.primaryName AS name, COUNT(DISTINCT p2) AS coactors
    ORDER BY coactors DESC
    LIMIT 5
    """
    
    pg_res, pg_time = run_postgres_query(pg_conn, pg_q2)
    print(f"[PostgreSQL] Time: {pg_time:.4f}s")
    for r in pg_res: print(f"  - {r}")
    
    n4j_res, n4j_time = run_neo4j_query(neo4j_driver, neo4j_q2)
    print(f"[Neo4j] Time: {n4j_time:.4f}s")
    for r in n4j_res: print(f"  - {r}")

    print("\n" + "="*50)
    print("QUERY 3: Genre Aggregation (Avg rating per genre in 2010s)")
    print("="*50)
    
    pg_q3 = """
    SELECT g.name, AVG(t.averageRating) as avg_rating, COUNT(*) as count
    FROM Titles t
    JOIN Title_Genres tg ON t.tconst = tg.tconst
    JOIN Genres g ON tg.genre_id = g.genre_id
    WHERE t.startYear >= 2010 AND t.startYear < 2020 AND t.averageRating IS NOT NULL
    GROUP BY g.name
    ORDER BY avg_rating DESC
    LIMIT 5;
    """
    neo4j_q3 = """
    MATCH (t:Title)-[:HAS_GENRE]->(g:Genre)
    WHERE t.startYear >= 2010 AND t.startYear < 2020 AND t.averageRating IS NOT NULL
    RETURN g.name, avg(t.averageRating) AS avg_rating, count(t) AS movie_count
    ORDER BY avg_rating DESC
    LIMIT 5
    """
    
    pg_res, pg_time = run_postgres_query(pg_conn, pg_q3)
    print(f"[PostgreSQL] Time: {pg_time:.4f}s")
    for r in pg_res: print(f"  - {r[0]}: Avg {r[1]:.2f} ({r[2]} movies)")
    
    n4j_res, n4j_time = run_neo4j_query(neo4j_driver, neo4j_q3)
    print(f"[Neo4j] Time: {n4j_time:.4f}s")
    for r in n4j_res: print(f"  - {r[0]}: Avg {r[1]:.2f} ({r[2]} movies)")

    print("\n" + "="*50)
    print("QUERY 4: Movie Recommendations (Based on 'The Matrix')")
    print("="*50)
    
    pg_q4 = """
    SELECT t2.primaryTitle, COUNT(*) as shared_crew
    FROM Title_Principals tp1
    JOIN Title_Principals tp2 ON tp1.nconst = tp2.nconst AND tp1.tconst != tp2.tconst
    JOIN Titles t2 ON tp2.tconst = t2.tconst
    WHERE tp1.tconst = 'tt0133093' -- The Matrix
    GROUP BY t2.tconst, t2.primaryTitle
    ORDER BY shared_crew DESC, t2.primaryTitle
    LIMIT 5;
    """
    neo4j_q4 = """
    MATCH (m1:Title {tconst: 'tt0133093'})<--(p:Person)-->(m2:Title)
    WHERE m1 <> m2
    RETURN m2.primaryTitle AS title, count(p) AS shared_crew
    ORDER BY shared_crew DESC, title
    LIMIT 5
    """
    
    pg_res, pg_time = run_postgres_query(pg_conn, pg_q4)
    print(f"[PostgreSQL] Time: {pg_time:.4f}s")
    for r in pg_res: print(f"  - {r[0]} ({r[1]} shared crew)")
    
    n4j_res, n4j_time = run_neo4j_query(neo4j_driver, neo4j_q4)
    print(f"[Neo4j] Time: {n4j_time:.4f}s")
    for r in n4j_res: print(f"  - {r[0]} ({r[1]} shared crew)")

    pg_conn.close()
    neo4j_driver.close()

if __name__ == "__main__":
    run_benchmarks()
