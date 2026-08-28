#!/usr/bin/env bash
#
# Runs the whole pipeline at three dataset sizes, accumulating every timing into
# a single analysis/results.csv with the threshold as a column.
#
# The Q1 actor pairs are searched again at each threshold, so they differ between
# thresholds: a denser graph has different distances. What stays constant, and is
# therefore what gets measured, is the question "prove a path of length <= d
# exists" as the graph grows.
#
# Takes several hours. Stops if verify_counts.py fails at any threshold.

set -euo pipefail

THRESHOLDS=(10000 1000 100)
RUNS=10
WARMUP=2

append=""

for min_votes in "${THRESHOLDS[@]}"; do
    echo
    echo "############################################################"
    echo "# threshold: numVotes >= ${min_votes}"
    echo "############################################################"

    python scripts/preprocess_data.py --min-votes "$min_votes"
    python scripts/load_postgres.py   --min-votes "$min_votes"
    python scripts/load_neo4j.py      --min-votes "$min_votes" --reset
    python scripts/verify_counts.py
    python scripts/find_pairs.py      --min-votes "$min_votes"
    python scripts/benchmark.py       --min-votes "$min_votes" \
                                      --runs "$RUNS" --warmup "$WARMUP" $append

    append="--append"
done

echo
echo "All thresholds complete."
python scripts/summarize_results.py
