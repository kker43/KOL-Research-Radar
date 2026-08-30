from datetime import datetime, timezone
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
)
from kol_radar.storage.repository import Repository


def test_repository_round_trip_and_article_idempotency(tmp_path: Path):
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(
        Source(name="Test Source", provider="article_url", external_id="test-source")
    )
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
