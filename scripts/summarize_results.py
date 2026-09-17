import argparse
import csv
import os
import statistics
from collections import defaultdict

from config import ANALYSIS_DIR

RESULTS_CSV = os.path.join(ANALYSIS_DIR, "results.csv")

LABELS = {
    "q2_most_connected": "Q2 - most connected actors",
    "q3_genre_by_decade": "Q3 - average rating by genre",
    "q4_recommendations": "Q4 - recommendations",
}


def label_for(case):
    if case.startswith("q1_distance_"):
        return f"Q1 - degrees of separation, distance {case.rsplit('_', 1)[1]}"
    return LABELS.get(case, case)


def load(path):
    medians = {}
    grouped = defaultdict(list)
    timed_out = set()

    with open(path) as f:
        for row in csv.DictReader(f):
            key = (int(row["min_votes"]), row["case"], row["system"])
            if row["note"] == "timeout" or not row["seconds"]:
                timed_out.add(key)
            else:
                grouped[key].append(float(row["seconds"]))

    for key, times in grouped.items():
        medians[key] = statistics.median(times)
    for key in timed_out:
        medians.setdefault(key, None)
    return medians


def fmt(seconds):
    if seconds is None:
        return "timeout"
    return f"{seconds * 1000:.1f} ms" if seconds < 1 else f"{seconds:.3f} s"


def ratio(pg, neo4j):
    if pg is None or neo4j is None:
        return "-"
    if neo4j < pg:
        return f"**Neo4j {pg / neo4j:.1f}x**"
    if pg < neo4j:
        return f"**PostgreSQL {neo4j / pg:.1f}x**"
    return "tie"


def main():
    parser = argparse.ArgumentParser(
        description="Generate the report tables from analysis/results.csv.")
    parser.add_argument("--results", default=RESULTS_CSV)
    args = parser.parse_args()

    if not os.path.exists(args.results):
        raise SystemExit(f"{args.results} not found — run the benchmark first.")

    medians = load(args.results)
    thresholds = sorted({key[0] for key in medians}, reverse=True)
    cases = sorted({key[1] for key in medians})

    for min_votes in thresholds:
        print(f"\n### Threshold: numVotes >= {min_votes}\n")
        print("| Query | PostgreSQL | Neo4j | Ratio |")
        print("|---|---:|---:|---|")
        for case in cases:
            key = (min_votes, case)
            if (*key, "postgresql") not in medians:
                continue
            pg = medians[(*key, "postgresql")]
            neo4j = medians.get((*key, "neo4j"))
            print(f"| {label_for(case)} | {fmt(pg)} | {fmt(neo4j)} | {ratio(pg, neo4j)} |")

    if len(thresholds) > 1:
        print("\n### Q1 scaling (medians)\n")
        print("| Case | System | " + " | ".join(f">={mv} votes" for mv in thresholds) + " |")
        print("|---|---|" + "---:|" * len(thresholds))
        for case in [c for c in cases if c.startswith("q1_")]:
            for system, name in (("postgresql", "PostgreSQL"), ("neo4j", "Neo4j")):
                cells = [fmt(medians.get((mv, case, system))) for mv in thresholds]
                print(f"| {label_for(case)} | {name} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
