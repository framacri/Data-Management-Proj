// Q2 · Attori piu' connessi (centralita' nella rete di collaborazioni)
//
// Il tipo di relazione ACTED_IN svolge qui il ruolo che in SQL svolge il filtro
// esplicito su category: in Neo4j il ruolo e' parte della topologia del grafo,
// non un attributo da filtrare dopo la scansione.
//
// ATTENZIONE alla chiave di raggruppamento. In Cypher il raggruppamento e'
// implicito: la chiave e' l'espressione non aggregata che compare nel RETURN.
// Scrivendo direttamente
//     RETURN p1.primaryName, count(DISTINCT p2)
// si raggrupperebbe per NOME e non per persona, fondendo in un gruppo solo gli
// omonimi (IMDb ne ha molti) e sommandone i co-attori. Il WITH esplicito su p1
// raggruppa per identita' del nodo, che e' l'equivalente di GROUP BY nconst.

MATCH (p1:Person)-[:ACTED_IN]->(:Title)<-[:ACTED_IN]-(p2:Person)
WHERE p1 <> p2
WITH p1, count(DISTINCT p2) AS coactors
RETURN p1.nconst AS nconst,
       p1.primaryName AS name,
       coactors
ORDER BY coactors DESC, nconst
LIMIT 10;
