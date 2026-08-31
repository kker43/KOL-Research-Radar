from datetime import datetime, timezone

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
from kol_radar.query.digest import DigestService
from kol_radar.storage.repository import Repository


def test_digest_is_incremental_and_omits_empty_sections(tmp_path):
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(Source(name="Digest Source", provider="fixture", external_id="d1"))
    author_one = repo.upsert_author(Author(name="研究员甲", author_type=AuthorType.person))
    author_two = repo.upsert_author(Author(name="研究员乙", author_type=AuthorType.person))

    def add_opinion(index, author, published_at, topic, stance, thesis):
        article = repo.upsert_article(
            Article(
                source_id=source.id,
                author_id=author.id,
                title=f"Digest article {index}",
                url=f"https://example.test/digest-{index}",
                published_at=published_at,
                content=thesis,
                content_hash=f"digest-hash-{index}",
            )
        )
        repo.insert_opinion(
            Opinion(
                topic=topic,
                subject="美股",
                raw_subject="美股",
                subject_key="US_EQUITIES",
                subject_type=SubjectType.market,
                stance=stance,
                thesis=thesis,
                rationale=[],
                published_at=published_at,
                source_article_id=article.id,
                author_id=author.id,
                source_excerpt=thesis,
                source_location="p1",
            )
        )

    cutoff = datetime(2026, 8, 30, tzinfo=timezone.utc)
    add_opinion(
        1,
        author_one,
        datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        Topic.risk,
        Stance.neutral,
        "旧观点：风险保持中性。",
    )
    add_opinion(
        2,
        author_one,
        datetime(2026, 8, 30, 8, tzinfo=timezone.utc),
        Topic.risk,
        Stance.deteriorating,
        "新观点：美股风险正在扩大。",
    )
    add_opinion(
        3,
        author_one,
        datetime(2026, 8, 30, 9, tzinfo=timezone.utc),
        Topic.opportunity,
        Stance.positive,
        "新机会：美股存在结构性机会。",
    )
    add_opinion(
        4,
        author_two,
        datetime(2026, 8, 30, 10, tzinfo=timezone.utc),
        Topic.opportunity,
        Stance.negative,
        "分歧：美股机会的赔率不足。",
    )

    digest = DigestService(repo).generate(cutoff)

    assert "旧观点" not in digest.text
    assert "New Important Opinions" in digest.sections
    assert "Opinion Changes" in digest.sections
    assert "Opportunities" in digest.sections
    assert "Risks" in digest.sections
    assert "Consensus / Divergence" in digest.sections
    assert "Positioning" not in digest.sections
    assert "divergence" in digest.text
