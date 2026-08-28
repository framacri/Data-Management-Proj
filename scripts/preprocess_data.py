import argparse
import os

import pandas as pd

from config import DATA_DIR, DEFAULT_MIN_VOTES, data_path, data_subdir

# 'self' is excluded from ACTED_IN: those are appearances in documentaries and
# talk shows, which inflate the collaboration network.
ACTING_CATEGORIES = ["actor", "actress"]
DIRECTING_CATEGORIES = ["director"]

CHUNK_SIZE = 1_000_000


def process_data(min_votes):
    out_dir = os.path.join(DATA_DIR, data_subdir(min_votes))
    os.makedirs(out_dir, exist_ok=True)

    def out(filename):
        return data_path(min_votes, filename)

    def source(filename):
        return os.path.join(DATA_DIR, filename)

    print(f"Vote threshold: >= {min_votes}  ->  {out_dir}/")

    titles = pd.read_csv(source("title.basics.tsv"), sep="\t", na_values="\\N", low_memory=False)
    ratings = pd.read_csv(source("title.ratings.tsv"), sep="\t", na_values="\\N")

    movies = titles[titles["titleType"] == "movie"].copy()
    # Int64 rather than the default float, which would write years as '2001.0'
    # and make COPY reject them.
    for column in ("startYear", "endYear", "runtimeMinutes"):
        movies[column] = pd.to_numeric(movies[column], errors="coerce").astype("Int64")
    movies = movies[movies["startYear"] > 1990]

    ratings = ratings[ratings["numVotes"] >= min_votes].copy()
    ratings["numVotes"] = ratings["numVotes"].astype("Int64")

    target_movies = pd.merge(movies, ratings, on="tconst", how="inner")
    valid_tconsts = set(target_movies["tconst"])
    print(f"Titles: {len(target_movies)}")

    genres_df, title_genres_df = extract_genres(target_movies)

    target_movies[["tconst", "titleType", "primaryTitle", "originalTitle", "isAdult",
                   "startYear", "endYear", "runtimeMinutes", "averageRating",
                   "numVotes"]].to_csv(out("pg_titles.csv"), index=False)
    genres_df[["genre_id", "name"]].to_csv(out("pg_genres.csv"), index=False)
    title_genres_df[["tconst", "genre_id"]].to_csv(out("pg_title_genres.csv"), index=False)

    target_movies[["tconst", "primaryTitle", "startYear", "runtimeMinutes", "averageRating",
                   "numVotes"]].to_csv(out("neo4j_nodes_titles.csv"), index=False)
    genres_df[["name"]].to_csv(out("neo4j_nodes_genres.csv"), index=False)
    title_genres_df[["tconst", "name"]].rename(columns={"name": "genre_name"}).to_csv(
        out("neo4j_edges_has_genre.csv"), index=False)

    principals = read_filtered(source("title.principals.tsv"), "tconst", valid_tconsts)
    names = read_filtered(source("name.basics.tsv"), "nconst", set(principals["nconst"].unique()))
    for column in ("birthYear", "deathYear"):
        names[column] = pd.to_numeric(names[column], errors="coerce").astype("Int64")

    # Principals whose nconst is missing from name.basics are dropped here rather
    # than downstream. PostgreSQL would keep them and Neo4j would discard them
    # silently, leaving the two databases with different contents; dropping them
    # upstream is also what lets Title_Principals keep its foreign key.
    known_nconsts = set(names["nconst"])
    before = len(principals)
    principals = principals[principals["nconst"].isin(known_nconsts)]
    print(f"Dropped {before - len(principals)} principals with a dangling nconst")

    names[["nconst", "primaryName", "birthYear", "deathYear"]].to_csv(
        out("pg_persons.csv"), index=False)
    principals[["tconst", "nconst", "ordering", "category"]].to_csv(
        out("pg_principals.csv"), index=False)
    names[["nconst", "primaryName", "birthYear"]].to_csv(
        out("neo4j_nodes_persons.csv"), index=False)

    write_edges(principals, out)
    print("Done.")


def extract_genres(target_movies):
    exploded = (target_movies[["tconst", "genres"]]
                .dropna(subset=["genres"])
                .assign(name=lambda df: df["genres"].str.split(","))
                .explode("name"))

    # sorted() rather than set iteration order, which varies between runs because
    # of hash randomisation and would give the same dataset different genre ids.
    genres_df = pd.DataFrame({"name": sorted(exploded["name"].unique())})
    genres_df["genre_id"] = range(1, len(genres_df) + 1)

    title_genres_df = exploded.merge(genres_df, on="name")[["tconst", "genre_id", "name"]]
    return genres_df, title_genres_df


def read_filtered(path, key, keep):
    chunks = pd.read_csv(path, sep="\t", na_values="\\N", chunksize=CHUNK_SIZE)
    return pd.concat([chunk[chunk[key].isin(keep)] for chunk in chunks], ignore_index=True)


def write_edges(principals, out):
    acting = principals["category"].isin(ACTING_CATEGORIES)
    directing = principals["category"].isin(DIRECTING_CATEGORIES)

    acted_in = principals[acting]
    directed = principals[directing]
    worked_on = principals[~acting & ~directing]

    acted_in[["nconst", "tconst", "ordering"]].to_csv(
        out("neo4j_edges_acted_in.csv"), index=False)
    directed[["nconst", "tconst"]].to_csv(out("neo4j_edges_directed.csv"), index=False)
    worked_on[["nconst", "tconst", "category"]].to_csv(
        out("neo4j_edges_worked_on.csv"), index=False)

    print(f"ACTED_IN: {len(acted_in)}  DIRECTED: {len(directed)}  WORKED_ON: {len(worked_on)}")

    # The three relationship types must partition Title_Principals, so that every
    # row reaching one database also reaches the other.
    assert len(acted_in) + len(directed) + len(worked_on) == len(principals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter IMDb TSVs into CSVs for both databases.")
    parser.add_argument("--min-votes", type=int, default=DEFAULT_MIN_VOTES,
                        help="minimum number of votes for a film to enter the working set")
    process_data(parser.parse_args().min_votes)
