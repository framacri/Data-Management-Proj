// Q1 · Gradi di separazione tra due attori (Six Degrees of Separation)
//
// Stessa domanda della controparte SQL: esiste una catena di collaborazioni di
// lunghezza <= max_depth? Il limite superiore del pattern a lunghezza variabile
// e' __MAXLEN__ = 2 * max_depth, perche' ogni grado di separazione attraversa
// due relazioni (Persona -> Film -> Persona).
//
// __MAXLEN__ viene sostituito dal runner: Cypher non accetta parametri come
// limite di un pattern a lunghezza variabile.

MATCH path = shortestPath(
    (a:Person {nconst: $src})-[:ACTED_IN*..__MAXLEN__]-(b:Person {nconst: $dst})
)
RETURN length(path) / 2 AS degrees;
