-- Q1 · Gradi di separazione tra due attori (Six Degrees of Separation)
--
-- Domanda: esiste una catena di collaborazioni di lunghezza <= :max_depth che
-- collega i due attori? In caso affermativo, qual e' la piu' corta?
--
-- Nota sul limite di SQL: una CTE ricorsiva non puo' mantenere un visited-set
-- globale, perche' la parte ricorsiva vede solo la working table dell'iterazione
-- corrente, non il risultato accumulato. UNION (non ALL) deduplica su
-- (nconst, depth), quindi un attore raggiunto al livello 1 viene comunque
-- riespanso al livello 2, al 3 e cosi' via. Il costo cresce con la profondita'
-- richiesta: e' esattamente il prezzo che il modello dichiarativo paga qui, ed
-- e' il motivo per cui questa query e' il caso di studio del confronto.

WITH RECURSIVE bfs(nconst, depth) AS (
        SELECT %(src)s::VARCHAR, 0

    UNION

        SELECT tp2.nconst, b.depth + 1
        FROM bfs b
        JOIN Title_Principals tp1
          ON tp1.nconst = b.nconst
         AND tp1.category IN ('actor', 'actress')
        JOIN Title_Principals tp2
          ON tp2.tconst = tp1.tconst
         AND tp2.category IN ('actor', 'actress')
        WHERE b.depth < %(max_depth)s
          AND tp2.nconst <> b.nconst
)
SELECT MIN(depth) AS degrees
FROM bfs
WHERE nconst = %(dst)s;
