-- Q2 · Attori piu' connessi (centralita' nella rete di collaborazioni)
--
-- Il filtro sul ruolo e' esplicito da entrambi i lati del self-join: in Neo4j
-- lo stesso filtro e' implicito nel tipo di relazione ACTED_IN. Senza il filtro
-- la query conterebbe anche produttori e sceneggiatori e non risponderebbe piu'
-- alla stessa domanda del Cypher.
--
-- Il raggruppamento e' su nconst, non sul nome: IMDb contiene persone diverse
-- con lo stesso primaryName. nconst e' restituito e usato come criterio di
-- ordinamento secondario perche' il risultato sia deterministico e confrontabile
-- riga per riga con quello del grafo.

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
