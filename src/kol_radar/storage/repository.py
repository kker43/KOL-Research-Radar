from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from kol_radar.domain import (
    Article,
    Author,
    AuthorType,
    Opinion,
    Source,
    Stance,
    SubjectType,
    Topic,
    utc_now,
)
from kol_radar.storage.schema import initialize_schema


def _dump_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _load_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Repository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            initialize_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def upsert_source(self, source: Source) -> Source:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sources(name, provider, external_id, status, created_at, last_synced_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, external_id) DO UPDATE SET
                    name = excluded.name,
                    status = excluded.status,
                    last_synced_at = COALESCE(excluded.last_synced_at, sources.last_synced_at)
                """,
                (
                    source.name,
                    source.provider,
                    source.external_id,
                    source.status,
                    _dump_datetime(source.created_at),
                    _dump_datetime(source.last_synced_at),
                ),
            )
            row = connection.execute(
                "SELECT * FROM sources WHERE provider = ? AND external_id = ?",
                (source.provider, source.external_id),
            ).fetchone()
        return self._source_from_row(row)

    def upsert_author(self, author: Author) -> Author:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM authors WHERE name = ? AND author_type = ?",
                (author.name, author.author_type.value),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    "INSERT INTO authors(name, author_type, created_at) VALUES (?, ?, ?)",
                    (author.name, author.author_type.value, _dump_datetime(author.created_at)),
                )
                row = connection.execute(
                    "SELECT * FROM authors WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
        return self._author_from_row(row)

    def get_source(self, source_id: int) -> Source | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        return self._source_from_row(row) if row else None

    def list_sources(self) -> list[Source]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM sources ORDER BY id").fetchall()
        return [self._source_from_row(row) for row in rows]

    def update_source_last_synced(
        self, source_id: int, last_synced_at: datetime
    ) -> Source:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sources SET last_synced_at = ? WHERE id = ?",
                (_dump_datetime(last_synced_at), source_id),
            )
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Source {source_id} does not exist")
        return self._source_from_row(row)

    def record_sync_run(
        self, result, started_at: datetime, completed_at: datetime
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sync_runs(
                    source_id, started_at, completed_at, status,
                    discovered_count, new_count, skipped_count, failed_count,
                    opinion_count, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.source_id,
                    _dump_datetime(started_at),
                    _dump_datetime(completed_at),
                    result.status,
                    result.discovered,
                    result.new,
                    result.skipped,
                    result.failed,
                    result.opinions,
                    result.error,
                ),
            )
            return int(cursor.lastrowid)

    def list_sync_runs(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM sync_runs ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def upsert_article(self, article: Article) -> Article:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE url = ? OR content_hash = ? LIMIT 1",
                (article.url, article.content_hash),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO articles(
                        source_id, title, url, published_at, author_id, content,
                        content_hash, fetched_at, processed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.source_id,
                        article.title,
                        article.url,
                        _dump_datetime(article.published_at),
                        article.author_id,
                        article.content,
                        article.content_hash,
                        _dump_datetime(article.fetched_at),
                        _dump_datetime(article.processed_at),
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM articles WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
        return self._article_from_row(row)

    def get_author(self, author_id: int) -> Author | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM authors WHERE id = ?", (author_id,)
            ).fetchone()
        return self._author_from_row(row) if row else None

    def find_author_by_name(self, name: str) -> Author | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM authors WHERE name = ? COLLATE NOCASE ORDER BY id LIMIT 1",
                (name,),
            ).fetchone()
        return self._author_from_row(row) if row else None

    def insert_opinion(self, opinion: Opinion) -> Opinion:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO opinions(
                    topic, subject, raw_subject, subject_key, subject_type, stance,
                    thesis, rationale, published_at, source_article_id, author_id,
                    source_excerpt, source_location
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    opinion.topic.value,
                    opinion.subject,
                    opinion.raw_subject,
                    opinion.subject_key,
                    opinion.subject_type.value,
                    opinion.stance.value,
                    opinion.thesis,
                    json.dumps(opinion.rationale, ensure_ascii=False),
                    _dump_datetime(opinion.published_at),
                    opinion.source_article_id,
                    opinion.author_id,
                    opinion.source_excerpt,
                    opinion.source_location,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM opinions
                WHERE source_article_id = ? AND topic = ? AND subject_key = ? AND thesis = ?
                """,
                (
                    opinion.source_article_id,
                    opinion.topic.value,
                    opinion.subject_key,
                    opinion.thesis,
                ),
            ).fetchone()
        return self._opinion_from_row(row)

    def list_articles(self) -> list[Article]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM articles ORDER BY published_at DESC, id DESC"
            ).fetchall()
        return [self._article_from_row(row) for row in rows]

    def get_article_by_url(self, url: str) -> Article | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE url = ?", (url,)
            ).fetchone()
        return self._article_from_row(row) if row else None

    def get_article(self, article_id: int) -> Article | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
        return self._article_from_row(row) if row else None

    def mark_article_processed(self, article_id: int) -> Article:
        with self._connect() as connection:
            connection.execute(
                "UPDATE articles SET processed_at = ? WHERE id = ?",
                (_dump_datetime(utc_now()), article_id),
            )
            row = connection.execute(
                "SELECT * FROM articles WHERE id = ?", (article_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Article {article_id} does not exist")
        return self._article_from_row(row)

    def list_opinions_for_article(self, article_id: int) -> list[Opinion]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM opinions WHERE source_article_id = ? ORDER BY id",
                (article_id,),
            ).fetchall()
        return [self._opinion_from_row(row) for row in rows]

    def article_has_opinions(self, article_id: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM opinions WHERE source_article_id = ? LIMIT 1",
                (article_id,),
            ).fetchone()
        return row is not None

    def get_previous_opinion(
        self,
        author_id: int,
        subject_key: str,
        topic: Topic,
        before: datetime,
    ) -> Opinion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM opinions
                WHERE author_id = ? AND subject_key = ? AND topic = ?
                  AND published_at < ?
                ORDER BY published_at DESC, id DESC
                LIMIT 1
                """,
                (author_id, subject_key, topic.value, _dump_datetime(before)),
            ).fetchone()
        return self._opinion_from_row(row) if row else None

    def list_opinions(
        self,
        *,
        topic: Topic | None = None,
        subject_key: str | None = None,
        author_id: int | None = None,
        since: datetime | None = None,
    ) -> list[Opinion]:
        clauses: list[str] = []
        parameters: list[object] = []
        if topic is not None:
            clauses.append("topic = ?")
            parameters.append(topic.value)
        if subject_key is not None:
            clauses.append("subject_key = ?")
            parameters.append(subject_key)
        if author_id is not None:
            clauses.append("author_id = ?")
            parameters.append(author_id)
        if since is not None:
            clauses.append("published_at >= ?")
            parameters.append(_dump_datetime(since))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM opinions{where} ORDER BY published_at DESC, id DESC",
                parameters,
            ).fetchall()
        return [self._opinion_from_row(row) for row in rows]

    @staticmethod
    def _source_from_row(row: sqlite3.Row) -> Source:
        return Source(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            external_id=row["external_id"],
            status=row["status"],
            created_at=_load_datetime(row["created_at"]),
            last_synced_at=_load_datetime(row["last_synced_at"]),
        )

    @staticmethod
    def _author_from_row(row: sqlite3.Row) -> Author:
        return Author(
            id=row["id"],
            name=row["name"],
            author_type=AuthorType(row["author_type"]),
            created_at=_load_datetime(row["created_at"]),
        )

    @staticmethod
    def _article_from_row(row: sqlite3.Row) -> Article:
        return Article(
            id=row["id"],
            source_id=row["source_id"],
            title=row["title"],
            url=row["url"],
            published_at=_load_datetime(row["published_at"]),
            author_id=row["author_id"],
            content=row["content"],
            content_hash=row["content_hash"],
            fetched_at=_load_datetime(row["fetched_at"]),
            processed_at=_load_datetime(row["processed_at"]),
        )

    @staticmethod
    def _opinion_from_row(row: sqlite3.Row) -> Opinion:
        return Opinion(
            id=row["id"],
            topic=Topic(row["topic"]),
            subject=row["subject"],
            raw_subject=row["raw_subject"],
            subject_key=row["subject_key"],
            subject_type=SubjectType(row["subject_type"]),
            stance=Stance(row["stance"]),
            thesis=row["thesis"],
            rationale=json.loads(row["rationale"]),
            published_at=_load_datetime(row["published_at"]),
            source_article_id=row["source_article_id"],
            author_id=row["author_id"],
            source_excerpt=row["source_excerpt"],
            source_location=row["source_location"],
        )
