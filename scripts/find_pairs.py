import argparse
import json
import os

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_AUTH, ANALYSIS_DIR, DEFAULT_MIN_VOTES

KEVIN_BACON = "nm0000102"

# Candidates are sampled at a fixed stride over an ordered list rather than at
# random, so that re-running the benchmark measures the same pairs.
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


def pairs_path(min_votes):
    return os.path.join(ANALYSIS_DIR, f"pairs_mv{min_votes}.json")


def main():
    parser = argparse.ArgumentParser(
        description="Find actors at increasing distance from a reference actor.")
    parser.add_argument("--src", default=KEVIN_BACON, help="reference actor")
    parser.add_argument("--stride", type=int, default=137, help="candidate sampling stride")
    parser.add_argument("--max-distance", type=int, default=4)
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="vote threshold of the loaded dataset, labelling the output file")
    args = parser.parse_args()

    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    found = {}

    with driver.session() as session:
        record = session.run(
            "MATCH (p:Person {nconst: $n}) RETURN p.primaryName AS name", n=args.src).single()
        if record is None:
            raise SystemExit(f"{args.src} is not in the graph — has the data been loaded?")
        src_name = record["name"]
        print(f"Reference: {src_name} ({args.src})\n")

        candidates = list(session.run(SAMPLE, stride=args.stride))
        print(f"Sampled {len(candidates)} candidates at stride {args.stride}.")

        for candidate in candidates:
            if len(found) == args.max_distance:
                break
            if candidate["nconst"] == args.src:
                continue
            row = session.run(DISTANCE, src=args.src, dst=candidate["nconst"]).single()
            if row is None:
                continue
            distance = row["degrees"]
            if 1 <= distance <= args.max_distance and distance not in found:
                found[distance] = {"nconst": candidate["nconst"],
                                   "name": candidate["name"],
                                   "distance": distance}
                print(f"  distance {distance}: {candidate['name']} ({candidate['nconst']})")

    driver.close()

    missing = [d for d in range(1, args.max_distance + 1) if d not in found]
    if missing:
        print(f"\nNo candidate found at distance {missing}. Retry with a smaller --stride.")

    out_path = pairs_path(args.min_votes)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"min_votes": args.min_votes,
                   "source": {"nconst": args.src, "name": src_name},
                   "targets": [found[d] for d in sorted(found)]}, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path} with {len(found)} pairs.")


if __name__ == "__main__":
    main()
