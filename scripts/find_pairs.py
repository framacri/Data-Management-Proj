"""Trova coppie di attori a distanza 1, 2, 3 e 4 da un attore di riferimento.

Misurare i gradi di separazione su una coppia sola non e' un risultato: Kevin
Bacon e Tom Hanks hanno recitato insieme in Apollo 13, quindi la risposta e' 1 e
nessuno dei due sistemi ha molto da dimostrare. Con quattro coppie a distanza
crescente il confronto diventa una curva.

Il campione di candidati e' deterministico (ordinato per nconst, a passo fisso)
perche' il benchmark deve essere riproducibile: due esecuzioni devono misurare
le stesse coppie.
"""
import argparse
import json
import os

from neo4j import GraphDatabase

NEO4J_URI = "neo4j://localhost:7687"
NEO4J_AUTH = ("neo4j", "imdbpassword")

KEVIN_BACON = "nm0000102"
OUT_PATH = os.path.join("analysis", "pairs.json")

SAMPLE = """
MATCH (p:Person)-[:ACTED_IN]->(:Title)
WITH DISTINCT p ORDER BY p.nconst
WITH collect(p) AS actors
UNWIND range(0, size(actors) - 1, $stride) AS i
RETURN actors[i].nconst AS nconst, actors[i].primaryName AS name
"""

DISTANCE = """
MATCH path = shortestPath(
    (a:Person {nconst: $src})-[:ACTED_IN*..12]-(b:Person {nconst: $dst})
)
RETURN length(path) / 2 AS degrees
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=KEVIN_BACON, help="nconst dell'attore di riferimento")
    parser.add_argument("--stride", type=int, default=137,
                        help="passo del campionamento deterministico dei candidati")
    parser.add_argument("--max-distance", type=int, default=4)
    args = parser.parse_args()

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    found = {}

    with driver.session() as session:
        src_name = session.run(
            "MATCH (p:Person {nconst: $n}) RETURN p.primaryName AS name", n=args.src
        ).single()
        if src_name is None:
            raise SystemExit(f"{args.src} non presente nel grafo — hai caricato i dati?")
        src_name = src_name["name"]
        print(f"Riferimento: {src_name} ({args.src})\n")

        candidates = list(session.run(SAMPLE, stride=args.stride))
        print(f"Campionati {len(candidates)} attori candidati (passo {args.stride}).")

        for record in candidates:
            if len(found) == args.max_distance:
                break
            dst = record["nconst"]
            if dst == args.src:
                continue
            row = session.run(DISTANCE, src=args.src, dst=dst).single()
            if row is None:
                continue
            d = row["degrees"]
            if 1 <= d <= args.max_distance and d not in found:
                found[d] = {"nconst": dst, "name": record["name"], "distance": d}
                print(f"  distanza {d}: {record['name']} ({dst})")

    driver.close()

    missing = [d for d in range(1, args.max_distance + 1) if d not in found]
    if missing:
        print(f"\nNessun candidato trovato a distanza {missing}. "
              f"Riprova con --stride piu' piccolo per campionare piu' attori.")

    pairs = {
        "source": {"nconst": args.src, "name": src_name},
        "targets": [found[d] for d in sorted(found)],
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(pairs, f, indent=2, ensure_ascii=False)
    print(f"\nScritto {OUT_PATH} con {len(found)} coppie.")


if __name__ == "__main__":
    main()
