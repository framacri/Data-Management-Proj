-- Actors with the largest number of distinct co-actors.
--
-- Grouping is by nconst, not by name: IMDb contains distinct people sharing a
-- primaryName. nconst is returned and used as the secondary sort key so the
-- result is deterministic and comparable row by row with the Cypher version.

SELECT tp1.nconst,
       p.primaryName AS name,
       COUNT(DISTINCT tp2.nconst) AS coactors
FROM Title_Principals tp1
JOIN Title_Principals tp2
  ON tp2.tconst = tp1.tconst
 AND tp2.nconst <> tp1.nconst
 AND tp2.category IN ('actor', 'actress')
JOIN Persons p
  ON p.nconst = tp1.nconst
WHERE tp1.category IN ('actor', 'actress')
GROUP BY tp1.nconst, p.primaryName
ORDER BY coactors DESC, tp1.nconst
LIMIT 10;
