import os
import urllib.request
import gzip
import shutil

BASE_URL = "https://datasets.imdbws.com/"
FILES = [
    "title.basics.tsv.gz",
    "name.basics.tsv.gz",
    "title.principals.tsv.gz",
    "title.crew.tsv.gz",
    "title.ratings.tsv.gz"
]
DATA_DIR = "data"

def download_and_extract():
    os.makedirs(DATA_DIR, exist_ok=True)
    for file in FILES:
        url = BASE_URL + file
        gz_path = os.path.join(DATA_DIR, file)
        tsv_path = gz_path[:-3] # remove .gz

        if os.path.exists(tsv_path):
            print(f"{tsv_path} already exists. Skipping download.")
            continue
            
        print(f"Downloading {url} to {gz_path}...")
        urllib.request.urlretrieve(url, gz_path)
        print("Download complete.")
        
        print(f"Extracting {gz_path} to {tsv_path}...")
        with gzip.open(gz_path, 'rb') as f_in:
            with open(tsv_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        print(f"Extraction complete. Deleting {gz_path}...")
        os.remove(gz_path)

if __name__ == "__main__":
    download_and_extract()
    print("All downloads and extractions complete.")
