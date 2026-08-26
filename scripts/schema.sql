DROP TABLE IF EXISTS Title_Genres;
DROP TABLE IF EXISTS Title_Principals;
DROP TABLE IF EXISTS Genres;
DROP TABLE IF EXISTS Persons;
DROP TABLE IF EXISTS Titles;

CREATE TABLE Titles (
    tconst VARCHAR(15) PRIMARY KEY,
    titleType VARCHAR(50),
    primaryTitle TEXT,
    originalTitle TEXT,
    isAdult BOOLEAN,
    startYear INTEGER,
    endYear INTEGER,
    runtimeMinutes INTEGER,
    averageRating NUMERIC(3,1),
    numVotes INTEGER
);

CREATE TABLE Persons (
    nconst VARCHAR(15) PRIMARY KEY,
    primaryName TEXT,
    birthYear INTEGER,
    deathYear INTEGER
);

CREATE TABLE Genres (
    genre_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE
);

CREATE TABLE Title_Genres (
    tconst VARCHAR(15) REFERENCES Titles(tconst),
    genre_id INTEGER REFERENCES Genres(genre_id),
    PRIMARY KEY (tconst, genre_id)
);

CREATE TABLE Title_Principals (
    tconst VARCHAR(15) REFERENCES Titles(tconst),
    nconst VARCHAR(15),
    ordering INTEGER,
    category VARCHAR(255),
    job TEXT,
    characters TEXT,
    PRIMARY KEY (tconst, nconst, ordering)
);

-- Indices to optimize analytical queries
CREATE INDEX idx_principals_nconst ON Title_Principals(nconst);
CREATE INDEX idx_principals_tconst ON Title_Principals(tconst);
CREATE INDEX idx_titles_startYear ON Titles(startYear);
CREATE INDEX idx_title_genres_genre_id ON Title_Genres(genre_id);
CREATE INDEX idx_title_genres_tconst ON Title_Genres(tconst);
