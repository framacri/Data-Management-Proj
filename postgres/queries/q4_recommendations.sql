-- Films sharing the most cast and crew with a given title.
--
-- COUNT(DISTINCT nconst) rather than COUNT(*): someone credited twice on the
-- same film must count once. No category filter, since all roles count here.

SELECT t2.tconst,
       t2.primaryTitle AS title,
       COUNT(DISTINCT tp2.nconst) AS shared_people
FROM Title_Principals tp1
JOIN Title_Principals tp2
  ON tp2.nconst = tp1.nconst
 AND tp2.tconst <> tp1.tconst
JOIN Titles t2
  ON t2.tconst = tp2.tconst
WHERE tp1.tconst = %(tconst)s
GROUP BY t2.tconst, t2.primaryTitle
ORDER BY shared_people DESC, t2.tconst
LIMIT 10;
