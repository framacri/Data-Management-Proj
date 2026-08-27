# IMDb Database Comparison: PostgreSQL vs. Neo4j

> ⚠️ **I numeri di performance in questo documento non sono validi e sono in corso di
> rifacimento sul branch `fix/benchmark-fairness`.** Sono stati misurati quando i due
> database contenevano insiemi di archi diversi e tre query su quattro facevano domande
> diverse nei due sistemi. Le misure originali sono conservate in
> `analysis/baseline_pre_fix.md`; quelle nuove verranno generate da `analysis/results.csv`.
> Vedi l'audit (B1–B5) per il dettaglio.

## 1. Project Overview
This project is a comprehensive comparison between a Relational Database Management System (RDBMS), **PostgreSQL**, and a Graph Database, **Neo4j**, using the massive, real-world IMDb dataset. The primary objective is to evaluate the expressiveness, readability, and performance of SQL versus Cypher across a variety of analytical queries, ranging from simple aggregations to deep relationship traversals.

## 2. Technology Stack
- **Databases**: PostgreSQL 15, Neo4j 5.12
- **Environment**: Docker & Docker Compose (for consistent, reproducible local environments)
- **Data Processing**: Python 3.12, Pandas (for ETL pipelines)
- **Database Drivers**: `psycopg2-binary` (PostgreSQL), `neo4j` Python driver

## 3. Data Pipeline & ETL
The ETL (Extract, Transform, Load) pipeline is handled entirely through custom Python scripts to ensure data consistency across both databases.

### 3.1. Extraction (`download_data.py`)
The pipeline automatically downloads the latest `.tsv.gz` files directly from IMDb's public dataset repositories, extracting `title.basics`, `title.ratings`, `title.principals`, and `name.basics`. `title.crew` is deliberately not used: directors come from `title.principals` (`category = 'director'`), so that the same rows feed both databases.

### 3.2. Preprocessing (`preprocess_data.py`)
Because the raw IMDb dataset contains tens of millions of rows (including TV episodes, shorts, and video games), the data was filtered to create a focused, high-quality analytical dataset:
- **Filtering**: Limited to `titleType == 'movie'`.
- **Quality Control**: Included only movies released after 1990 with at least 1,000 votes.
- **Data Cleaning**: Strict type enforcement (`Int64`) was applied to years and runtimes to prevent floating-point anomalies (e.g., `2001.0`) that cause strict relational databases to fail during bulk ingestion. 
- **Symmetry**: The `characters` and `job` columns are dropped from **both** targets. No query uses them, and keeping them only on the relational side would have made PostgreSQL scan much wider tuples than the two-column edges Neo4j reads.
- **Referential integrity**: Principals whose `nconst` is absent from `name.basics` are dropped upstream. Previously they were kept by PostgreSQL and silently discarded by Neo4j (the `MATCH` on the Person node simply found nothing), so the two databases held different data.

## 4. Relational Implementation (PostgreSQL)

### 4.1. Schema Design
The data was heavily normalized into 5 tables to eliminate redundancy:
- `Titles` (Primary Key: `tconst`)
- `Persons` (Primary Key: `nconst`)
- `Genres` (Primary Key: `genre_id`)
- `Title_Genres` (Associative table linking Titles and Genres)
- `Title_Principals` (Associative table linking Titles and Persons, containing roles like actor/director)

*Note: the public dataset contains principals whose `nconst` is missing from `name.basics`. Rather than dropping the foreign key, these rows are filtered out during preprocessing, so `Title_Principals.nconst REFERENCES Persons(nconst)` holds and both databases contain the same set of person–title links.*

### 4.2. Ingestion (`load_postgres.py`)
Data was bulk-loaded using PostgreSQL's highly optimized `COPY FROM STDIN WITH CSV` command, resulting in ingestion times of just a few seconds.

## 5. Graph Implementation (Neo4j)

### 5.1. Graph Data Model
The graph was designed to represent connections intuitively:
- **Nodes**: `Title`, `Person`, `Genre`
- **Edges**: `ACTED_IN {ordering}` (Person -> Title, `category` in *actor*/*actress*), `DIRECTED` (Person -> Title), `WORKED_ON {category}` (Person -> Title, every other role), `HAS_GENRE` (Title -> Genre)

The three person–title relationship types **partition** the rows of `Title_Principals`: every role that reaches one database reaches the other. `scripts/verify_counts.py` asserts this after every load.

### 5.2. Ingestion (`load_neo4j.py`)
Cypher constraints (Unique constraints on `tconst`, `nconst`, and `name`) were established first to automatically generate indices.
Data was ingested using `LOAD CSV` bundled inside `CALL { ... } IN TRANSACTIONS OF 50000 ROWS` blocks. This batching strategy prevents `OutOfMemory` exceptions when loading hundreds of thousands of edges. Furthermore, `MERGE` clauses were utilized over `CREATE` to guarantee idempotency during failed load retries.

## 6. Benchmarking & Analytics
`benchmark.py` runs each query on both databases after a warm-up, repeats it N times and reports the **median** with min–max, alternating which system goes first so neither systematically finds the page cache warmed by the other. Connections and sessions are opened outside the timed section. Every run is written to `analysis/results.csv`; `EXPLAIN (ANALYZE, BUFFERS)` and `PROFILE` output goes to `analysis/plans/`. The runner compares the two result sets row by row and fails if they differ — two timings for two different questions are not a comparison.

### Query 1: Six Degrees of Separation (Shortest Path)
- **Goal**: Find the shortest collaboration path between Kevin Bacon and Tom Hanks.
- **SQL Approach**: Required a highly complex Recursive CTE (`WITH RECURSIVE`) to manually traverse joins up to a specific depth.
- **Cypher Approach**: Utilized the built-in `shortestPath()` algorithm.
- **Winner: Neo4j (14x faster)**. PostgreSQL took ~0.16s, Neo4j took ~0.01s.

### Query 2: Most Connected Actors (Centrality)
- **Goal**: Identify actors who have worked with the highest number of unique co-actors.
- **SQL Approach**: A massive self-join on `Title_Principals` grouped by actor ID.
- **Cypher Approach**: A direct pattern match `(p1)-[:ACTED_IN]->(t)<-[:ACTED_IN]-(p2)`.
- **Winner: Neo4j**. Neo4j traverses this 2-hop pattern using index-free adjacency — fixed-size relationship records reachable by offset from each node — avoiding the index scanning and hash joining PostgreSQL needs for the equivalent self-join.

### Query 3: Genre Aggregation
- **Goal**: Calculate the average rating of movies per genre released in the 2010s.
- **SQL Approach**: Standard `GROUP BY` and `AVG()` across 3 joined tables.
- **Cypher Approach**: Pattern matching nodes, grouping using `WITH`, and returning averages.
- **Winner: PostgreSQL**. PostgreSQL is a row-store, not a columnar engine: its advantage here comes from efficient sequential scans, hash aggregation, and a planner with accurate table statistics — not from columnar execution.

### Query 4: Content-Based Recommendations
- **Goal**: Recommend 5 movies based on shared cast and crew with *The Matrix*.
- **SQL Approach**: Self-joining `Title_Principals` where `tconst` equals *The Matrix*.
- **Cypher Approach**: Pattern match `(Matrix)<--(Person)-->(OtherMovie)`.
- **Winner: PostgreSQL (10x faster)**. Because this is a localized, single-hop neighbor search starting from a single known node, PostgreSQL leveraged its B-Tree indices to execute this virtually instantaneously (0.006s).

## 7. Conclusion
The project successfully demonstrated the fundamental architectural trade-offs between Relational and Graph databases:
- **Neo4j** holds a clear advantage on pathfinding and on traversals whose depth is not known in advance (Degrees of Separation). Note that the centrality query is a 2-hop pattern, not a deep traversal. Cypher is also significantly easier to read and write for these specific problems compared to Recursive SQL.
- **PostgreSQL** remains stronger on set-oriented aggregations, strict schema enforcement, and localised single-hop lookups served by a B-tree index.
