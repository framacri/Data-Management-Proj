-- Q4 · Film consigliati a partire da un titolo, per cast e troupe condivisi
--
-- COUNT(DISTINCT tp2.nconst) e non COUNT(*): una persona che compare due volte
-- nello stesso film con ruoli diversi (per esempio regista e sceneggiatore)
-- deve contare una volta sola, esattamente come count(DISTINCT p) in Cypher.
-- Nessun filtro su category: qui contano tutti i ruoli, e la controparte Cypher
-- attraversa infatti tutti e tre i tipi di relazione.
--
-- Raggruppamento e ordinamento su tconst: i titoli omonimi sono film diversi.

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
