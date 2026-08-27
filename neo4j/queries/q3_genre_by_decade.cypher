// Q3 · Rating medio per genere, film del decennio 2010-2019
//
// In Cypher il HAVING non esiste: l'aggregazione va materializzata con WITH e
// filtrata dopo. E' la query in cui il modello relazionale risulta piu' diretto.

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
