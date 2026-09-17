# IMDb DBMS Comparison — PostgreSQL vs Neo4j

The same four analytical queries, expressed in SQL over a normalised relational schema and in
Cypher over a property graph, run against identical IMDb data in PostgreSQL and Neo4j, at three
dataset sizes.

Data Management 2025/2026, Sapienza Università di Roma.
Lorenzo Ventrone (1802393) · Francesco Macrì (2055851)

Full method, results and analysis: **[PROJECT_REPORT.md](PROJECT_REPORT.md)**.

## What keeps the comparison valid

1. **Every row that enters one system enters the other.** The Neo4j CSVs are derived from the
   same dataframe that feeds PostgreSQL, and the three person–title relationship types
   (`ACTED_IN`, `DIRECTED`, `WORKED_ON`) partition the rows of `Title_Principals`.
   `verify_counts.py` checks this after every load and exits non-zero if it does not hold.
2. **Every query filters by role explicitly in both languages.** In Neo4j the role is the
   relationship type; in SQL it is `WHERE category IN (...)`, served by a dedicated index.
3. **No number reaches the report unless it comes from `analysis/results.csv`.**

## Requirements

- Docker and Docker Compose
- Python 3.9+
- ~15 GB of free disk space for the extracted IMDb TSV files

## Running

### 1. Start the databases

```bash
docker compose up -d --wait
```

Neo4j Browser at http://localhost:7474 (`neo4j` / `imdbpassword`), PostgreSQL on
`localhost:15432` (`imdb` / `imdbpassword`, database `imdb`). Both are given comparable memory
in `docker-compose.yml`.

### 2. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Download and prepare the data

```bash
python scripts/download_data.py
python scripts/preprocess_data.py --min-votes 1000
```

Filters: `titleType == 'movie'`, `startYear > 1990` (1990 itself excluded), and
`numVotes >= <threshold>`. Generated CSVs go to `data/mv<threshold>/`, so several dataset sizes
coexist. They must stay under `data/`, which is mounted as Neo4j's import directory.

### 4. Load

```bash
python scripts/load_postgres.py --min-votes 1000
python scripts/load_neo4j.py    --min-votes 1000 --reset
```

`--reset` clears the graph first. It is required when reloading: the load uses `MERGE`, so
without it the previous dataset's relationships remain and accumulate. PostgreSQL does not need
it because `schema.sql` recreates the tables.

### 5. Check that both databases agree

```bash
python scripts/verify_counts.py
```

A gate, not a courtesy check. It compares PostgreSQL rows against Neo4j relationships across all
seven categories and exits non-zero if any differ. Until it passes, any timing compares
different workloads.

### 6. Measure

```bash
python scripts/find_pairs.py --min-votes 1000
python scripts/benchmark.py  --min-votes 1000 --runs 10 --warmup 2
python scripts/summarize_results.py
```

The benchmark writes one row per run to `analysis/results.csv` and execution plans to
`analysis/plans/mv<threshold>/`. It exits non-zero if the two implementations of a query return
different results.

Useful flags: `--timeout` (default 300 s), `--append`, `--no-plans`, `--show`.

### 7. All three dataset sizes

```bash
bash scripts/run_scale.sh
```

Repeats the pipeline at ≥10,000, ≥1,000 and ≥100 votes, accumulating into a single
`results.csv` so timings can be reported as curves rather than single numbers. Takes several
hours, and stops if `verify_counts.py` fails at any threshold.

### 8. Live demo

```bash
python scripts/demo.py
```

Runs a single query, on PostgreSQL, Neo4j or both, and prints the result tables, its time and —
with both — whether the two systems returned identical results. It executes exactly the
queries of `benchmark.py`, built by the same code, so the demo cannot drift from what was measured.

The loaded threshold is detected from the number of titles, and the matching Q1 pairs are used.
From the menu: a number picks a query, then `p` / `n` / `b` picks the engine and `t` prints SQL
and Cypher one after the other; `a` toggles accesses, `w` warms every query up, `q` quits. Warm
up before presenting: a first execution measures caches and query compilation, not the query.

The time shown is the median of three back-to-back executions (`--runs`), after discarding the
executions that start within the first 100 ms. After an idle pause, such as the minutes spent on
slides, whichever engine runs first is slowed down for about its first 100 ms of work. With a
single run that alone reversed Q3 and Q4, whose whole cost is 1–25 ms. A run longer than 100 ms is
never discarded, so Q1 and Q2 are not repeated needlessly.

With accesses on, a second, instrumented execution reports PostgreSQL buffer pages
(`EXPLAIN (ANALYZE, BUFFERS)`) and Neo4j database accesses (`PROFILE`). The time always comes from
the uninstrumented runs, and the two units are not equivalent: an 8 KB page against a
single record.

Non-interactive, for rehearsal:

```bash
python scripts/demo.py --query q1 --distance 4 --engine both --accesses --warmup
```

Three runs are an illustration, not a measurement; the medians of ten runs are in the report.

## The queries

| | Question | Files |
|---|---|---|
| Q1 | Degrees of separation between two actors | `q1_shortest_path.sql` · `.cypher` |
| Q2 | Most connected actors | `q2_most_connected.sql` · `.cypher` |
| Q3 | Average rating by genre, 2010s | `q3_genre_by_decade.sql` · `.cypher` |
| Q4 | Films recommended by shared cast and crew | `q4_recommendations.sql` · `.cypher` |

Under `postgres/queries/` and `neo4j/queries/`. Q1 is measured on four actor pairs at distances
1 to 4: on a single pair the timing says nothing about how the cost scales, which is the point
of the comparison.

## Layout

```
scripts/           config, download, preprocess, load_*, verify_counts,
                   find_pairs, benchmark, summarize_results, run_scale.sh, demo
postgres/queries/  the four queries in SQL
neo4j/queries/     the same four queries in Cypher
data/mv<n>/        generated CSVs, one directory per dataset size
analysis/          results.csv, plans/, pairs_mv*.json, baseline_pre_fix.md
```
