// Average rating per genre for films released in the 2010s.
// Cypher has no HAVING: the aggregate must be materialised with WITH and
// filtered afterwards.

MATCH (t:Title)-[:HAS_GENRE]->(g:Genre)
WHERE t.startYear >= 2010
  AND t.startYear < 2020
  AND t.averageRating IS NOT NULL
WITH g.name AS genre,
     avg(t.averageRating) AS avg_rating,
     count(t) AS movies
WHERE movies >= 50
RETURN genre, round(avg_rating, 3) AS avg_rating, movies
ORDER BY avg_rating DESC, genre
LIMIT 10;
