# IMDb DBMS Benchmark Results

These are the results of comparing PostgreSQL (Relational) and Neo4j (Graph) on the IMDb dataset. The tests were run locally on a Dockerized environment.

## Overview of Queries

1. **Shortest Path (Six Degrees of Separation)**: Finding the shortest connection between Kevin Bacon and Tom Hanks.
2. **Most Connected Actors**: Identifying the top 5 most central actors/directors in the network.
3. **Genre Aggregation**: Finding the average rating per genre for movies released in the 2010s.
4. **Movie Recommendations**: Finding the top 5 movies recommended based on shared cast and crew with *The Matrix*.

## Results

### Query 1: Shortest Path (Graph Traversal)
- **PostgreSQL**: 0.1666s
- **Neo4j**: 0.0116s
- **Winner**: Neo4j (14x faster)
- *Note*: Neo4j is heavily optimized for pathfinding and graph traversals. PostgreSQL required a complex Recursive CTE to achieve this.

### Query 2: Most Connected Actors (Centrality)
- **PostgreSQL**: 8.9916s
- **Neo4j**: 1.2554s
- **Winner**: Neo4j (7x faster)
- *Note*: Neo4j resolves relationships locally without massive index scans, making it much faster for deep multi-hop neighbor counting.

### Query 3: Genre Aggregation (Filtering & Grouping)
- **PostgreSQL**: 0.0339s
- **Neo4j**: 0.1378s
- **Winner**: PostgreSQL (4x faster)
- *Note*: PostgreSQL shines in traditional aggregations, table scans, and mathematical groupings.

### Query 4: Movie Recommendations (Shared Nodes)
- **PostgreSQL**: 0.0065s
- **Neo4j**: 0.0655s
- **Winner**: PostgreSQL (10x faster)
- *Note*: Because this query requires looking at a single node (*The Matrix*) and grouping by its direct neighbors, PostgreSQL can leverage its highly optimized B-Tree indices to perform the join incredibly fast.

## Conclusion

As expected, **Neo4j** heavily outperforms PostgreSQL on complex relationship traversals and multi-hop queries (like pathfinding and centrality). 
Conversely, **PostgreSQL** is significantly faster and more efficient at traditional OLAP-style aggregations and simple single-hop relational joins.
