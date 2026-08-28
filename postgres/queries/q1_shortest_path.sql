-- Degrees of separation: is there a chain of collaborations of length
-- <= max_depth between two actors, and what is the shortest?
--
-- A recursive CTE cannot maintain a global visited set: the recursive term sees
-- only the current iteration's working table, so an actor reached at depth 1 is
-- expanded again at depth 2 and beyond.

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
