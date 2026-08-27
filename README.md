# IMDb DBMS Comparison — PostgreSQL vs Neo4j

Confronto fra un DBMS relazionale (PostgreSQL) e un database a grafo (Neo4j) sulle stesse
quattro query analitiche, sul dataset IMDb Non-Commercial.

Progetto di Data Management 2025/2026 — Sapienza Università di Roma.
Lorenzo Ventrone (1802393) · Francesco Macrì (2055851)

## Il principio che regge il confronto

1. **Ogni riga che entra in un sistema entra anche nell'altro.** I CSV per Neo4j sono derivati
   dallo stesso dataframe che alimenta Postgres; i tre tipi di relazione persona–titolo
   (`ACTED_IN`, `DIRECTED`, `WORKED_ON`) ne sono una partizione. `verify_counts.py` lo verifica
   dopo ogni caricamento.
2. **Ogni query filtra per ruolo esplicitamente in entrambi i linguaggi.** In Neo4j il ruolo è
   il tipo di relazione; in SQL è un `WHERE category IN (...)` servito da un indice dedicato.
3. **Nessun numero finisce nel report se non viene da `analysis/results.csv`.**

## Prerequisiti

- Docker & Docker Compose
- Python 3.9+
- ~15 GB liberi su disco (i TSV IMDb scompattati pesano circa 10 GB)

## Esecuzione

### 1 · Avviare i database

```bash
docker-compose up -d
```

- Neo4j Browser: http://localhost:7474 — `neo4j` / `imdbpassword`
- PostgreSQL: `localhost:15432` — utente `imdb`, password `imdbpassword`, database `imdb`

Entrambi i motori sono configurati con memoria comparabile nel compose: senza questo, Postgres
girerebbe con `work_mem` a 4MB contro 1GB di page cache per Neo4j, e il benchmark misurerebbe
la configurazione invece dell'architettura.

Attendere che i container siano pronti prima di procedere (una decina di secondi).

### 2 · Ambiente Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3 · Scaricare e preparare i dati

```bash
python scripts/download_data.py      # TSV da datasets.imdbws.com in data/
python scripts/preprocess_data.py    # filtra e genera i CSV per entrambi i DB
```

Filtro applicato: `titleType == 'movie'`, `startYear > 1990`, `numVotes >= 1000`.

### 4 · Caricare

```bash
python scripts/load_postgres.py
python scripts/load_neo4j.py
```

### 5 · Verificare che i due database siano allineati

```bash
python scripts/verify_counts.py
```

**È un cancello, non un controllo di cortesia.** Confronta righe Postgres e archi Neo4j per
tutte e sette le categorie ed esce con codice diverso da 0 se divergono. Finché non passa, ogni
misura di performance confronta carichi di lavoro diversi.

### 6 · Misurare

```bash
python scripts/find_pairs.py                     # coppie di attori a distanza 1-4
python scripts/benchmark.py --runs 10 --warmup 2
```

Il benchmark scrive `analysis/results.csv` (una riga per run) e i piani di esecuzione in
`analysis/plans/`. Esce con codice diverso da 0 se le due implementazioni di una query
restituiscono risultati diversi.

Opzioni utili: `--timeout` (default 300 s), `--min-votes` (etichetta della soglia nel CSV),
`--no-plans`, `--show`.

## Le query

| # | Domanda | File |
|---|---|---|
| Q1 | Gradi di separazione fra due attori | `postgres/queries/q1_shortest_path.sql` · `neo4j/queries/q1_shortest_path.cypher` |
| Q2 | Attori più connessi (centralità) | `q2_most_connected.sql` · `.cypher` |
| Q3 | Rating medio per genere, decennio 2010-2019 | `q3_genre_by_decade.sql` · `.cypher` |
| Q4 | Film consigliati per cast e troupe condivisi | `q4_recommendations.sql` · `.cypher` |

La Q1 viene misurata su quattro coppie a distanza crescente: su una coppia sola il tempo non
dice nulla sullo scaling, che è il punto del confronto. Entrambi i sistemi ricevono lo stesso
limite di profondità esplicito.

## Struttura

```
scripts/          download, preprocess, load, verify, find_pairs, benchmark
postgres/queries/ le quattro query in SQL
neo4j/queries/    le stesse quattro query in Cypher
analysis/         results.csv, plans/, pairs.json, baseline_pre_fix.md
```
