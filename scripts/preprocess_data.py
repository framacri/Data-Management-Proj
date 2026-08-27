import argparse
import os

import pandas as pd

from config import DATA_DIR, DEFAULT_MIN_VOTES, data_path, data_subdir

# Categorie IMDb mappate sui tipi di relazione Neo4j.
# 'self' e' escluso da ACTED_IN: sono apparizioni in documentari e talk show,
# gonfiano la rete delle collaborazioni e falsano i gradi di separazione.
ACTING_CATEGORIES = ['actor', 'actress']
DIRECTING_CATEGORIES = ['director']

def process_data(min_votes):
    # I TSV sorgente restano nella radice di data/; i CSV generati vanno in una
    # sottocartella per soglia, cosi' piu' dimensioni del dataset convivono senza
    # sovrascriversi. Devono comunque restare sotto data/, che il compose monta
    # come cartella di import di Neo4j.
    out_dir = os.path.join(DATA_DIR, data_subdir(min_votes))
    os.makedirs(out_dir, exist_ok=True)

    def out(filename):
        return data_path(min_votes, filename)

    print(f"Soglia di voti: >= {min_votes}  ->  {out_dir}/")

    print("Loading title.basics.tsv...")
    titles = pd.read_csv(os.path.join(DATA_DIR, "title.basics.tsv"), sep='\t', na_values='\\N', low_memory=False)

    print("Loading title.ratings.tsv...")
    ratings = pd.read_csv(os.path.join(DATA_DIR, "title.ratings.tsv"), sep='\t', na_values='\\N')

    print("Filtering titles...")
    movies = titles[titles['titleType'] == 'movie'].copy()
    movies['startYear'] = pd.to_numeric(movies['startYear'], errors='coerce').astype('Int64')
    movies['endYear'] = pd.to_numeric(movies['endYear'], errors='coerce').astype('Int64')
    movies['runtimeMinutes'] = pd.to_numeric(movies['runtimeMinutes'], errors='coerce').astype('Int64')
    # '> 1990' e non '>= 1990': il 1990 stesso e' escluso. Criterio dichiarato
    # nella proposta come "released after 1990".
    movies = movies[movies['startYear'] > 1990]

    print("Filtering ratings...")
    ratings = ratings[ratings['numVotes'] >= min_votes].copy()
    ratings['numVotes'] = ratings['numVotes'].astype('Int64')

    target_movies = pd.merge(movies, ratings, on='tconst', how='inner')
    print(f"Target movies count: {len(target_movies)}")
    valid_tconsts = set(target_movies['tconst'])

    # Process Genres (for Postgres and Neo4j)
    print("Extracting genres...")
    all_genres = set()
    title_genres = []

    for _, row in target_movies.iterrows():
        tconst = row['tconst']
        if pd.notna(row['genres']):
            for genre in row['genres'].split(','):
                all_genres.add(genre)
                title_genres.append({'tconst': tconst, 'name': genre})

    # sorted() e non list(): l'iterazione di un set Python dipende dall'hash
    # randomization, quindi senza ordinamento i genre_id cambierebbero a ogni
    # esecuzione e due caricamenti dello stesso dataset non sarebbero confrontabili.
    genres_df = pd.DataFrame({'name': sorted(all_genres)})
    genres_df['genre_id'] = range(1, len(genres_df) + 1)

    title_genres_df = pd.DataFrame(title_genres)
    title_genres_df = pd.merge(title_genres_df, genres_df, on='name', how='inner')[['tconst', 'genre_id', 'name']]

    # Save Relational Entities
    print("Saving postgres entities...")
    target_movies[['tconst', 'titleType', 'primaryTitle', 'originalTitle', 'isAdult', 'startYear', 'endYear', 'runtimeMinutes', 'averageRating', 'numVotes']].to_csv(out("pg_titles.csv"), index=False)
    genres_df[['genre_id', 'name']].to_csv(out("pg_genres.csv"), index=False)
    title_genres_df[['tconst', 'genre_id']].to_csv(out("pg_title_genres.csv"), index=False)

    # Save Neo4j Nodes/Edges
    print("Saving neo4j entities (Titles and Genres)...")
    target_movies[['tconst', 'primaryTitle', 'startYear', 'runtimeMinutes', 'averageRating', 'numVotes']].to_csv(out("neo4j_nodes_titles.csv"), index=False)
    genres_df[['name']].to_csv(out("neo4j_nodes_genres.csv"), index=False)
    title_genres_df[['tconst', 'name']].rename(columns={'name': 'genre_name'}).to_csv(out("neo4j_edges_has_genre.csv"), index=False)

    # Process Principals (Actors, Directors, etc.)
    print("Loading and filtering title.principals.tsv...")
    valid_nconsts = set()
    principals_chunks = pd.read_csv(os.path.join(DATA_DIR, "title.principals.tsv"), sep='\t', na_values='\\N', chunksize=1000000)
    filtered_principals = []

    for chunk in principals_chunks:
        filtered_chunk = chunk[chunk['tconst'].isin(valid_tconsts)]
        filtered_principals.append(filtered_chunk)
        valid_nconsts.update(filtered_chunk['nconst'].unique())

    final_principals = pd.concat(filtered_principals, ignore_index=True)
    print(f"Filtered principals count: {len(final_principals)}")

    # Process Names
    print("Loading and filtering name.basics.tsv...")
    names_chunks = pd.read_csv(os.path.join(DATA_DIR, "name.basics.tsv"), sep='\t', na_values='\\N', chunksize=1000000)
    filtered_names = []

    for chunk in names_chunks:
        filtered_chunk = chunk[chunk['nconst'].isin(valid_nconsts)].copy()
        filtered_chunk['birthYear'] = pd.to_numeric(filtered_chunk['birthYear'], errors='coerce').astype('Int64')
        filtered_chunk['deathYear'] = pd.to_numeric(filtered_chunk['deathYear'], errors='coerce').astype('Int64')
        filtered_names.append(filtered_chunk)

    final_names = pd.concat(filtered_names, ignore_index=True)
    print(f"Filtered names count: {len(final_names)}")

    # Drop principals whose nconst is absent from name.basics.
    # Senza questo filtro Postgres conserva le righe pendenti (e la FK su nconst
    # non puo' esistere) mentre Neo4j le scarta in silenzio, perche' il MATCH
    # sul nodo Person non trova nulla e LOAD CSV prosegue senza errore.
    # Risultato: i due database contengono dati diversi. Si taglia a monte.
    known_nconsts = set(final_names['nconst'])
    before = len(final_principals)
    final_principals = final_principals[final_principals['nconst'].isin(known_nconsts)]
    dropped = before - len(final_principals)
    print(f"Dropped {dropped} principals with dangling nconst ({before} -> {len(final_principals)})")

    print("Saving postgres entities...")
    final_names[['nconst', 'primaryName', 'birthYear', 'deathYear']].to_csv(out("pg_persons.csv"), index=False)
    # 'job' e 'characters' sono esclusi: nessuna query li usa, sono TEXT larghi
    # che Postgres dovrebbe scansionare mentre gli archi Neo4j pesano due colonne.
    # Tenerli darebbe a Neo4j un vantaggio di payload per riga.
    final_principals[['tconst', 'nconst', 'ordering', 'category']].to_csv(out("pg_principals.csv"), index=False)

    print("Saving neo4j entities (Nodes)...")
    final_names[['nconst', 'primaryName', 'birthYear']].to_csv(out("neo4j_nodes_persons.csv"), index=False)

    print("Saving neo4j entities (Edges)...")
    # Gli archi derivano dallo STESSO final_principals che alimenta Postgres:
    # ogni riga che entra in un sistema entra anche nell'altro, partizionata per
    # categoria. Nessun ruolo viene perso: acted_in + directed + worked_on
    # ricostruiscono esattamente pg_principals.csv.
    acted_in = final_principals[final_principals['category'].isin(ACTING_CATEGORIES)]
    directed = final_principals[final_principals['category'].isin(DIRECTING_CATEGORIES)]
    worked_on = final_principals[~final_principals['category'].isin(ACTING_CATEGORIES + DIRECTING_CATEGORIES)]

    acted_in[['nconst', 'tconst', 'ordering']].to_csv(out("neo4j_edges_acted_in.csv"), index=False)
    directed[['nconst', 'tconst']].to_csv(out("neo4j_edges_directed.csv"), index=False)
    worked_on[['nconst', 'tconst', 'category']].to_csv(out("neo4j_edges_worked_on.csv"), index=False)

    print(f"  ACTED_IN  : {len(acted_in)}")
    print(f"  DIRECTED  : {len(directed)}")
    print(f"  WORKED_ON : {len(worked_on)}")
    assert len(acted_in) + len(directed) + len(worked_on) == len(final_principals), \
        "La partizione per categoria non copre tutti i principals"

    print("Preprocessing complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="numero minimo di voti perche' un film entri nel working set")
    args = parser.parse_args()
    process_data(args.min_votes)
