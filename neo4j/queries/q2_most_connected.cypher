// Q2 · Attori piu' connessi (centralita' nella rete di collaborazioni)
//
// Il tipo di relazione ACTED_IN svolge qui il ruolo che in SQL svolge il filtro
// esplicito su category: in Neo4j il ruolo e' parte della topologia del grafo,
// non un attributo da filtrare dopo la scansione.

MATCH (p1:Person)-[:ACTED_IN]->(:Title)<-[:ACTED_IN]-(p2:Person)
WHERE p1 <> p2
RETURN p1.primaryName AS name,
       count(DISTINCT p2) AS coactors
ORDER BY coactors DESC, name
LIMIT 10;
