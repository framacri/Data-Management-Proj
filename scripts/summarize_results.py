"""Genera le tabelle del report a partire da analysis/results.csv.

Invariante del progetto: nessun numero finisce nel report se non viene da qui.
Le tabelle si rigenerano, non si trascrivono a mano — cosi' non possono divergere
dai dati come era successo fra PROJECT_REPORT.md ed experiment_results.md.
"""
import argparse
import csv
import os
import statistics
from collections import defaultdict

from config import ANALYSIS_DIR

RESULTS_CSV = os.path.join(ANALYSIS_DIR, "results.csv")

LABELS = {
    "q2_most_connected": "Q2 · Attori più connessi",
    "q3_genre_by_decade": "Q3 · Rating medio per genere",
    "q4_recommendations": "Q4 · Film consigliati",
}


def label_for(case):
    if case.startswith("q1_distanza_"):
        return f"Q1 · Gradi di separazione, distanza {case.rsplit('_', 1)[1]}"
    return LABELS.get(case, case)


def load(path):
    grouped = defaultdict(list)
    timeouts = set()
    with open(path) as f:
        for row in csv.DictReader(f):
            key = (int(row["min_votes"]), row["case"], row["system"])
            if row["note"] == "timeout" or not row["seconds"]:
                timeouts.add(key)
            else:
                grouped[key].append(float(row["seconds"]))
    return grouped, timeouts


def fmt(seconds):
    if seconds is None:
        return "timeout"
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms"
    return f"{seconds:.3f} s"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=RESULTS_CSV)
    args = parser.parse_args()

    if not os.path.exists(args.results):
        raise SystemExit(f"{args.results} non trovato — esegui prima il benchmark.")

    grouped, timeouts = load(args.results)
    thresholds = sorted({k[0] for k in list(grouped) + list(timeouts)}, reverse=True)
    cases = sorted({k[1] for k in list(grouped) + list(timeouts)})

    for mv in thresholds:
        print(f"\n### Soglia: numVotes >= {mv}\n")
        print("| Query | PostgreSQL | Neo4j | Rapporto |")
        print("|---|---:|---:|---|")
        for case in cases:
            pg = grouped.get((mv, case, "postgresql"))
            n4 = grouped.get((mv, case, "neo4j"))
            if pg is None and (mv, case, "postgresql") not in timeouts:
                continue
            pg_med = statistics.median(pg) if pg else None
            n4_med = statistics.median(n4) if n4 else None

            if pg_med and n4_med:
                if n4_med < pg_med:
                    ratio = f"**Neo4j {pg_med / n4_med:.1f}×**"
                elif pg_med < n4_med:
                    ratio = f"**PostgreSQL {n4_med / pg_med:.1f}×**"
                else:
                    ratio = "pari"
            else:
                ratio = "—"
            print(f"| {label_for(case)} | {fmt(pg_med)} | {fmt(n4_med)} | {ratio} |")

    if len(thresholds) > 1:
        print("\n### Scaling della Q1 (mediane)\n")
        header = " | ".join(f"≥{mv} voti" for mv in thresholds)
        print(f"| Caso | Sistema | {header} |")
        print("|---|---|" + "---:|" * len(thresholds))
        for case in [c for c in cases if c.startswith("q1_")]:
            for system, name in (("postgresql", "PostgreSQL"), ("neo4j", "Neo4j")):
                cells = []
                for mv in thresholds:
                    times = grouped.get((mv, case, system))
                    cells.append(fmt(statistics.median(times)) if times else "timeout")
                print(f"| {label_for(case)} | {name} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
