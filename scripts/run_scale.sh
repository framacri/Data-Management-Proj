#!/usr/bin/env bash
#
# Fase 4 — asse della scala.
#
# Esegue l'intera pipeline a tre dimensioni del dataset e accumula i tempi in un
# unico analysis/results.csv, con la soglia come colonna. Serve a riportare i
# risultati come curve invece che come numeri singoli: e' la differenza fra dire
# "Neo4j e' N volte piu' veloce" e mostrare che i due sistemi hanno complessita'
# diverse.
#
# Nota metodologica sulla Q1: le coppie di attori vengono ricercate a ogni
# soglia, quindi non sono le stesse fra una soglia e l'altra — a un grafo piu'
# denso corrispondono distanze diverse. Cio' che resta costante, e che e' quindi
# l'oggetto della misura, e' la domanda: "dimostra che esiste un cammino di
# lunghezza <= d". Confrontiamo il costo di quella domanda al crescere del grafo.
#
# Uso:  bash scripts/run_scale.sh
# Tempo: parecchie ore. La soglia >= 100 voti produce un dataset ~4x piu' grande
# e la Q1 in SQL a distanza 4 e' la query lunga.

set -euo pipefail

THRESHOLDS=(10000 1000 100)
RUNS=10
WARMUP=2

append_flag=""

for mv in "${THRESHOLDS[@]}"; do
    echo
    echo "############################################################"
    echo "# soglia: numVotes >= ${mv}"
    echo "############################################################"

    python scripts/preprocess_data.py --min-votes "$mv"
    python scripts/load_postgres.py  --min-votes "$mv"
    python scripts/load_neo4j.py     --min-votes "$mv" --reset

    # Cancello: se i due database divergono, set -e ferma tutto qui.
    python scripts/verify_counts.py

    python scripts/find_pairs.py --min-votes "$mv"
    python scripts/benchmark.py  --min-votes "$mv" --runs "$RUNS" --warmup "$WARMUP" $append_flag

    append_flag="--append"
done

echo
echo "Tutte le soglie completate. Riepilogo:"
python scripts/summarize_results.py
