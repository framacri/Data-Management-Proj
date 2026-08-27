-- Q3 · Rating medio per genere, film del decennio 2010-2019
--
-- La soglia HAVING COUNT(*) >= 50 evita che la classifica sia dominata da
-- generi rarissimi con una manciata di titoli, dove la media non e'
-- significativa. La stessa soglia e' applicata lato Cypher dopo il WITH.

SELECT g.name AS genre,
       ROUND(AVG(t.averageRating), 3) AS avg_rating,
       COUNT(*) AS movies
FROM Titles t
JOIN Title_Genres tg ON tg.tconst = t.tconst
JOIN Genres g ON g.genre_id = tg.genre_id
WHERE t.startYear >= 2010
  AND t.startYear < 2020
  AND t.averageRating IS NOT NULL
GROUP BY g.name
HAVING COUNT(*) >= 50
ORDER BY avg_rating DESC, genre
LIMIT 10;
