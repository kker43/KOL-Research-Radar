import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_synced_at TEXT,
    UNIQUE(provider, external_id)
);

CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    author_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    published_at TEXT,
    author_id INTEGER NOT NULL REFERENCES authors(id),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    fetched_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS opinions (
    id INTEGER PRIMARY KEY,
    topic TEXT NOT NULL,
    subject TEXT NOT NULL,
    raw_subject TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    stance TEXT NOT NULL,
    thesis TEXT NOT NULL,
    rationale TEXT NOT NULL,
    published_at TEXT,
    source_article_id INTEGER NOT NULL REFERENCES articles(id),
    author_id INTEGER NOT NULL REFERENCES authors(id),
    source_excerpt TEXT NOT NULL CHECK(length(source_excerpt) > 0),
    source_location TEXT NOT NULL CHECK(length(source_location) > 0),
    UNIQUE(source_article_id, topic, subject_key, thesis)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    opinion_count INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
