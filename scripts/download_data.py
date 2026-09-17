import gzip
import os
import shutil
import urllib.request

from config import DATA_DIR

BASE_URL = "https://datasets.imdbws.com/"

# title.crew is not downloaded: directors come from title.principals, so that a
# single filtered dataframe feeds both databases.
FILES = [
    "title.basics.tsv.gz",
    "name.basics.tsv.gz",
    "title.principals.tsv.gz",
    "title.ratings.tsv.gz",
]


def download_and_extract():
    os.makedirs(DATA_DIR, exist_ok=True)

    for filename in FILES:
        gz_path = os.path.join(DATA_DIR, filename)
        tsv_path = gz_path[:-3]

        if os.path.exists(tsv_path):
            print(f"{tsv_path} already present, skipping.")
            continue

        print(f"Downloading {BASE_URL + filename}...")
        urllib.request.urlretrieve(BASE_URL + filename, gz_path)

        print(f"Extracting {tsv_path}...")
        with gzip.open(gz_path, "rb") as src, open(tsv_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.remove(gz_path)

    print("Done.")


if __name__ == "__main__":
    download_and_extract()
