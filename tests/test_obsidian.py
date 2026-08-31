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
from kol_radar.obsidian.exporter import ObsidianExporter, resolve_obsidian_root


def test_export_article_is_idempotent_and_scoped(tmp_path):
    root = tmp_path / "vault" / "KOL-Research"
    source = Source(
        id=1, name="测试/公众号", provider="article_url", external_id="source-1"
    )
    author = Author(id=1, name="测试作者", author_type=AuthorType.person)
    article = Article(
        id=1,
        source_id=1,
        author_id=1,
        title="AI Capex: 趋势",
        url="https://mp.weixin.qq.com/s/test",
        published_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        content="AI Capex 需求仍然强劲。",
        content_hash="hash-1",
    )
    opinions = [
        Opinion(
            id=1,
            topic=Topic.trend,
            subject="AI Capex",
            raw_subject="AI Capex",
            subject_key="AI_CAPEX",
            subject_type=SubjectType.theme,
            stance=Stance.positive,
            thesis="AI Capex 仍处于上升趋势。",
            rationale=["需求仍然强劲。"],
            published_at=article.published_at,
            source_article_id=1,
            author_id=1,
            source_excerpt="AI Capex 需求仍然强劲。",
            source_location="p1",
        )
    ]

    exporter = ObsidianExporter(root)
    first = exporter.export_article(article, source, author, opinions)
    original = first.read_text()
    second = exporter.export_article(article, source, author, opinions)

    assert first == second
    assert second.read_text() == original
    assert second.is_relative_to(root)
    assert "article_id: 1" in original
    assert "## Opinions" in original
    assert "## Source" in original


def test_resolve_obsidian_root_defaults_to_project_local_directory(tmp_path):
    assert resolve_obsidian_root(None, project_root=tmp_path) == tmp_path / "KOL-Research"
    assert resolve_obsidian_root(tmp_path / "vault") == tmp_path / "vault" / "KOL-Research"
    explicit = tmp_path / "vault" / "KOL-Research"
    assert resolve_obsidian_root(explicit) == explicit
