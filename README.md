# IMDb DBMS Comparison Project

This project compares a Relational DBMS (PostgreSQL) and a Graph Database (Neo4j) on the IMDb dataset.

## Prerequisites
- Docker & Docker Compose
- Python 3.9+

## Setup Instructions

### 1. Start Databases
Run Docker Compose to start PostgreSQL and Neo4j locally:
```bash
docker-compose up -d
```
Neo4j browser: http://localhost:7474 (neo4j / imdbpassword)
PostgreSQL: localhost:15432 (user: imdb, password: imdbpassword)

### 2. Prepare Python Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Download Data
```bash
python scripts/download_data.py
```
This downloads the required `.tsv.gz` files into the `data/` directory and extracts them.

### 4. Preprocess Data
```bash
python scripts/preprocess_data.py
```
This filters the dataset (Feature films >1990, >=1000 votes) and generates normalized CSV files for both PostgreSQL and Neo4j.

### 5. Load Data
**PostgreSQL:**
```bash
python scripts/load_postgres.py
```

**Neo4j:**
```bash
python scripts/load_neo4j.py
```

## Running Queries & Benchmarking
(To be implemented in `scripts/benchmark.py`)
