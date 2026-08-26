# IMDb Database Comparison: PostgreSQL vs. Neo4j

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
The pipeline automatically downloads the latest `.tsv.gz` files directly from IMDb's public dataset repositories, extracting `title.basics`, `title.ratings`, `title.principals`, `title.crew`, and `name.basics`.

### 3.2. Preprocessing (`preprocess_data.py`)
Because the raw IMDb dataset contains tens of millions of rows (including TV episodes, shorts, and video games), the data was filtered to create a focused, high-quality analytical dataset:
- **Filtering**: Limited to `titleType == 'movie'`.
- **Quality Control**: Included only movies released after 1990 with at least 1,000 votes.
- **Data Cleaning**: Strict type enforcement (`Int64`) was applied to years and runtimes to prevent floating-point anomalies (e.g., `2001.0`) that cause strict relational databases to fail during bulk ingestion. 
- **Graph Optimization**: Removed the noisy `characters` array string from the `ACTED_IN` edges, which contained unescaped quotes that frequently broke Neo4j's strict CSV parser.

## 4. Relational Implementation (PostgreSQL)

### 4.1. Schema Design
The data was heavily normalized into 5 tables to eliminate redundancy:
- `Titles` (Primary Key: `tconst`)
- `Persons` (Primary Key: `nconst`)
- `Genres` (Primary Key: `genre_id`)
- `Title_Genres` (Associative table linking Titles and Genres)
- `Title_Principals` (Associative table linking Titles and Persons, containing roles like actor/director)

*Note: During ingestion, dirty data (dangling `nconst` references in the principals table that did not exist in the persons table) caused foreign key violations. The strict FK constraint on `nconst` was removed to accommodate the realities of the public dataset.*

### 4.2. Ingestion (`load_postgres.py`)
Data was bulk-loaded using PostgreSQL's highly optimized `COPY FROM STDIN WITH CSV` command, resulting in ingestion times of just a few seconds.

## 5. Graph Implementation (Neo4j)

### 5.1. Graph Data Model
The graph was designed to represent connections intuitively:
- **Nodes**: `Title`, `Person`, `Genre`
- **Edges**: `ACTED_IN` (Person -> Title), `DIRECTED` (Person -> Title), `HAS_GENRE` (Title -> Genre)

### 5.2. Ingestion (`load_neo4j.py`)
Cypher constraints (Unique constraints on `tconst`, `nconst`, and `name`) were established first to automatically generate indices.
Data was ingested using `LOAD CSV` bundled inside `CALL { ... } IN TRANSACTIONS OF 50000 ROWS` blocks. This batching strategy prevents `OutOfMemory` exceptions when loading hundreds of thousands of edges. Furthermore, `MERGE` clauses were utilized over `CREATE` to guarantee idempotency during failed load retries.

## 6. Benchmarking & Analytics
A custom benchmarking script (`benchmark.py`) was developed to execute 4 specific queries against both databases, measuring pure execution time.

### Query 1: Six Degrees of Separation (Shortest Path)
- **Goal**: Find the shortest collaboration path between Kevin Bacon and Tom Hanks.
- **SQL Approach**: Required a highly complex Recursive CTE (`WITH RECURSIVE`) to manually traverse joins up to a specific depth.
- **Cypher Approach**: Utilized the built-in `shortestPath()` algorithm.
- **Winner: Neo4j (14x faster)**. PostgreSQL took ~0.16s, Neo4j took ~0.01s.

### Query 2: Most Connected Actors (Centrality)
- **Goal**: Identify actors who have worked with the highest number of unique co-actors.
- **SQL Approach**: A massive self-join on `Title_Principals` grouped by actor ID.
- **Cypher Approach**: A direct pattern match `(p1)-[:ACTED_IN]->(t)<-[:ACTED_IN]-(p2)`.
- **Winner: Neo4j (7x faster)**. Neo4j resolves relationships via direct memory pointers, avoiding the heavy index scanning and hash joining required by PostgreSQL.

### Query 3: Genre Aggregation
- **Goal**: Calculate the average rating of movies per genre released in the 2010s.
- **SQL Approach**: Standard `GROUP BY` and `AVG()` across 3 joined tables.
- **Cypher Approach**: Pattern matching nodes, grouping using `WITH`, and returning averages.
- **Winner: PostgreSQL (4x faster)**. PostgreSQL is heavily optimized for columnar math, traditional OLAP aggregations, and table scans.

### Query 4: Content-Based Recommendations
- **Goal**: Recommend 5 movies based on shared cast and crew with *The Matrix*.
- **SQL Approach**: Self-joining `Title_Principals` where `tconst` equals *The Matrix*.
- **Cypher Approach**: Pattern match `(Matrix)<--(Person)-->(OtherMovie)`.
- **Winner: PostgreSQL (10x faster)**. Because this is a localized, single-hop neighbor search starting from a single known node, PostgreSQL leveraged its B-Tree indices to execute this virtually instantaneously (0.006s).

## 7. Conclusion
The project successfully demonstrated the fundamental architectural trade-offs between Relational and Graph databases:
- **Neo4j** is vastly superior for problems involving unknown depths, pathfinding, and deep relationship traversals (Centrality, Degrees of Separation). Cypher is also significantly easier to read and write for these specific problems compared to Recursive SQL.
- **PostgreSQL** remains king of mathematical aggregations, strict schema enforcement, and localized, indexed single-hop lookups.
