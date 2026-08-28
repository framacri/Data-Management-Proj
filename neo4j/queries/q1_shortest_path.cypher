// Degrees of separation, bounded to the same depth as its SQL counterpart.
// __MAXLEN__ is substituted by the runner with 2 * max_depth, since each degree
// spans two relationships; Cypher does not accept a parameter as the upper bound
// of a variable-length pattern.

MATCH path = shortestPath(
    (a:Person {nconst: $src})-[:ACTED_IN*..__MAXLEN__]-(b:Person {nconst: $dst})
)
RETURN length(path) / 2 AS degrees;
