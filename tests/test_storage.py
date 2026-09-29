from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from kol_radar.domain import (
    Article,
    Author,
    AuthorType,
    Opinion,
    Source,
    Stance,
    SubjectType,
    Topic,
)
from kol_radar.storage.repository import Repository


def test_repository_round_trip_and_article_idempotency(tmp_path: Path):
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(
        Source(
            name="Test Source",
            provider="article_url",
            external_id="test-source",
            registry_source_id="src_1234abcd",
        )
    )
    assert source.registry_source_id == "src_1234abcd"
    author = repo.upsert_author(
        Author(name="Test Author", author_type=AuthorType.person)
    )
    article = Article(
        source_id=source.id,
        author_id=author.id,
        title="AI capex is still rising",
        url="https://mp.weixin.qq.com/s/test",
        published_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        content="AI capex remains strong.",
        content_hash="hash-1",
    )

    first = repo.upsert_article(article)
    second = repo.upsert_article(article)

    assert first.id == second.id
    assert len(repo.list_articles()) == 1

    opinion = repo.insert_opinion(
        Opinion(
            topic=Topic.trend,
            subject="AI Capex",
            raw_subject="AI capex",
            subject_key="AI_CAPEX",
            subject_type=SubjectType.theme,
            stance=Stance.positive,
            thesis="AI capex remains in an uptrend.",
            rationale=["Cloud demand remains strong."],
            published_at=article.published_at,
            source_article_id=first.id,
            author_id=author.id,
            source_excerpt="AI capex remains strong.",
            source_location="p1",
        )
    )
    assert opinion.id is not None
    assert (
        repo.list_opinions(subject_key="AI_CAPEX")[0].thesis
        == "AI capex remains in an uptrend."
    )
    previous = repo.get_previous_opinion(
        author_id=author.id,
        subject_key="AI_CAPEX",
        topic=Topic.trend,
        before=article.published_at + timedelta(seconds=1),
    )
    assert previous is not None
    assert previous.id == opinion.id



def test_repository_migrates_legacy_source_table_and_binds_registry_id(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE sources (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_synced_at TEXT,
            UNIQUE(provider, external_id)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO sources(
            name, provider, external_id, status, created_at, last_synced_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("Legacy Source", "wewe", "LEGACY_FEED", "active", "2026-08-30T00:00:00+00:00", None),
    )
    connection.commit()
    connection.close()

    repo = Repository(db_path)
    source = repo.get_source(1)

    assert source is not None
    assert source.registry_source_id is None

    bound = repo.bind_source_registry_id(1, "src_deadbeef")

    assert bound.registry_source_id == "src_deadbeef"
    assert repo.get_source(1).registry_source_id == "src_deadbeef"


def test_registry_binding_is_preserved_when_source_is_upserted_without_binding(tmp_path: Path):
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(
        Source(
            name="Tracked KOL",
            provider="wewe",
            external_id="MP_REAL",
            registry_source_id="src_abcdef12",
        )
    )
    updated = repo.upsert_source(
        Source(name="Tracked KOL Renamed", provider="wewe", external_id="MP_REAL")
    )

    assert updated.id == source.id
    assert updated.registry_source_id == "src_abcdef12"
    assert updated.name == "Tracked KOL Renamed"
