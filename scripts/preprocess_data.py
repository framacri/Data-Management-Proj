import pandas as pd
import numpy as np
import os

DATA_DIR = "data"

def process_data():
    print("Loading title.basics.tsv...")
    titles = pd.read_csv(os.path.join(DATA_DIR, "title.basics.tsv"), sep='\t', na_values='\\N', low_memory=False)
    
    print("Loading title.ratings.tsv...")
    ratings = pd.read_csv(os.path.join(DATA_DIR, "title.ratings.tsv"), sep='\t', na_values='\\N')
    
    print("Filtering titles...")
    movies = titles[titles['titleType'] == 'movie'].copy()
    movies['startYear'] = pd.to_numeric(movies['startYear'], errors='coerce').astype('Int64')
    movies['endYear'] = pd.to_numeric(movies['endYear'], errors='coerce').astype('Int64')
    movies['runtimeMinutes'] = pd.to_numeric(movies['runtimeMinutes'], errors='coerce').astype('Int64')
    movies = movies[movies['startYear'] > 1990]
    
    print("Filtering ratings...")
    ratings = ratings[ratings['numVotes'] >= 1000].copy()
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
                
    genres_df = pd.DataFrame({'name': list(all_genres)})
    genres_df['genre_id'] = range(1, len(genres_df) + 1)
    
    title_genres_df = pd.DataFrame(title_genres)
    title_genres_df = pd.merge(title_genres_df, genres_df, on='name', how='inner')[['tconst', 'genre_id', 'name']]
    
    # Save Relational Entities
    print("Saving postgres entities...")
    target_movies[['tconst', 'titleType', 'primaryTitle', 'originalTitle', 'isAdult', 'startYear', 'endYear', 'runtimeMinutes', 'averageRating', 'numVotes']].to_csv(os.path.join(DATA_DIR, "pg_titles.csv"), index=False)
    genres_df[['genre_id', 'name']].to_csv(os.path.join(DATA_DIR, "pg_genres.csv"), index=False)
    title_genres_df[['tconst', 'genre_id']].to_csv(os.path.join(DATA_DIR, "pg_title_genres.csv"), index=False)

    # Save Neo4j Nodes/Edges
    print("Saving neo4j entities (Titles and Genres)...")
    target_movies[['tconst', 'primaryTitle', 'startYear', 'runtimeMinutes', 'averageRating', 'numVotes']].to_csv(os.path.join(DATA_DIR, "neo4j_nodes_titles.csv"), index=False)
    genres_df[['name']].to_csv(os.path.join(DATA_DIR, "neo4j_nodes_genres.csv"), index=False)
    title_genres_df[['tconst', 'name']].rename(columns={'name': 'genre_name'}).to_csv(os.path.join(DATA_DIR, "neo4j_edges_has_genre.csv"), index=False)

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
    
    print("Saving postgres entities...")
    final_principals[['tconst', 'nconst', 'ordering', 'category', 'job', 'characters']].to_csv(os.path.join(DATA_DIR, "pg_principals.csv"), index=False)

    print("Saving neo4j entities (Edges)...")
    # Separate into ACTED_IN and DIRECTED based on category
    acted_in = final_principals[final_principals['category'].isin(['actor', 'actress', 'self'])]
    directed = final_principals[final_principals['category'] == 'director']
    
    acted_in[['nconst', 'tconst']].to_csv(os.path.join(DATA_DIR, "neo4j_edges_acted_in.csv"), index=False)
    directed[['nconst', 'tconst']].to_csv(os.path.join(DATA_DIR, "neo4j_edges_directed.csv"), index=False)

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
    
    print("Saving postgres entities...")
    final_names[['nconst', 'primaryName', 'birthYear', 'deathYear']].to_csv(os.path.join(DATA_DIR, "pg_persons.csv"), index=False)
    
    print("Saving neo4j entities (Nodes)...")
    final_names[['nconst', 'primaryName', 'birthYear']].to_csv(os.path.join(DATA_DIR, "neo4j_nodes_persons.csv"), index=False)

    print("Preprocessing complete!")

if __name__ == "__main__":
    process_data()
