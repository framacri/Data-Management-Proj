// Q4 · Film consigliati a partire da un titolo, per cast e troupe condivisi
//
// I tre tipi di relazione insieme coprono esattamente le righe di
// Title_Principals: la controparte SQL non filtra su category, quindi neanche
// questa query lo fa. count(DISTINCT p) perche' una persona legata a un film da
// piu' relazioni WORKED_ON (ruoli diversi) deve contare una volta sola.
//
// Come nella Q2, il WITH esplicito su m2 raggruppa per identita' del nodo:
// raggruppare su m2.primaryTitle fonderebbe i film omonimi in un gruppo solo.

MATCH (m1:Title {tconst: $tconst})<-[:ACTED_IN|DIRECTED|WORKED_ON]-(p:Person)
      -[:ACTED_IN|DIRECTED|WORKED_ON]->(m2:Title)
WHERE m1 <> m2
WITH m2, count(DISTINCT p) AS shared_people
RETURN m2.tconst AS tconst,
       m2.primaryTitle AS title,
       shared_people
ORDER BY shared_people DESC, tconst
LIMIT 10;
