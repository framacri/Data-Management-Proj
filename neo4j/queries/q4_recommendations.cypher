// Films sharing the most cast and crew with a given title.
//
// All three relationship types together cover exactly the rows of
// Title_Principals, matching the unfiltered SQL counterpart. The WITH groups by
// node identity, so homonymous films stay distinct.

MATCH (m1:Title {tconst: $tconst})<-[:ACTED_IN|DIRECTED|WORKED_ON]-(p:Person)
      -[:ACTED_IN|DIRECTED|WORKED_ON]->(m2:Title)
WHERE m1 <> m2
WITH m2, count(DISTINCT p) AS shared_people
RETURN m2.tconst AS tconst,
       m2.primaryTitle AS title,
       shared_people
ORDER BY shared_people DESC, tconst
LIMIT 10;
