-- Average rating per genre for films released in the 2010s.
-- The minimum-film threshold keeps rare genres with a handful of titles, where
-- the average is not meaningful, out of the ranking.

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
