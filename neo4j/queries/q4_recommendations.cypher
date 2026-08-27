// Q4 · Film consigliati a partire da un titolo, per cast e troupe condivisi
//
// I tre tipi di relazione insieme coprono esattamente le righe di
// Title_Principals: la controparte SQL non filtra su category, quindi neanche
// questa query lo fa. count(DISTINCT p) perche' una persona legata a un film da
// piu' relazioni WORKED_ON (ruoli diversi) deve contare una volta sola.

MATCH (m1:Title {tconst: $tconst})<-[:ACTED_IN|DIRECTED|WORKED_ON]-(p:Person)
      -[:ACTED_IN|DIRECTED|WORKED_ON]->(m2:Title)
WHERE m1 <> m2
RETURN m2.primaryTitle AS title,
       count(DISTINCT p) AS shared_people
ORDER BY shared_people DESC, title
LIMIT 10;
