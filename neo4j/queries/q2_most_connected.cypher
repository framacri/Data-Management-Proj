// Actors with the largest number of distinct co-actors.
//
// The explicit WITH groups by node identity. Returning p1.primaryName directly
// would group by name instead, merging homonymous people into one row, since
// Cypher's grouping key is the non-aggregated expression in the RETURN.

MATCH (p1:Person)-[:ACTED_IN]->(:Title)<-[:ACTED_IN]-(p2:Person)
WHERE p1 <> p2
WITH p1, count(DISTINCT p2) AS coactors
RETURN p1.nconst AS nconst,
       p1.primaryName AS name,
       coactors
ORDER BY coactors DESC, nconst
LIMIT 10;
