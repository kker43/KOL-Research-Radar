from datetime import datetime, timezone

from kol_radar.domain import OpinionDraft, Stance, Topic
from kol_radar.ingestion.service import IngestionService
from kol_radar.providers.base import FetchedArticle, Paragraph
from kol_radar.storage.repository import Repository


class FakeExtractor:
    def __init__(self):
        self.calls = 0

    def extract(self, article):
        self.calls += 1
        return [
            OpinionDraft(
                topic=Topic.trend,
                raw_subject="AI Capex",
                stance=Stance.positive,
                thesis="AI Capex 需求仍处于上升趋势。",
                rationale=["云厂商需求强劲。"],
                source_excerpt="AI Capex 需求仍然强劲。",
                source_location="p1",
            )
        ]


def test_ingest_same_article_twice_does_not_duplicate(tmp_path):
    fetched_article = FetchedArticle(
        title="AI Capex 趋势",
        url="https://mp.weixin.qq.com/s/ingestion-test",
        source_name="测试公众号",
        author_name="测试作者",
        published_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        content="AI Capex 需求仍然强劲。",
        paragraphs=[Paragraph("p1", "AI Capex 需求仍然强劲。")],
    )
    repo = Repository(tmp_path / "radar.db")
    extractor = FakeExtractor()
    service = IngestionService(repo, extractor)

    first = service.ingest_fetched(fetched_article, provider_name="article_url")
    second = service.ingest_fetched(fetched_article, provider_name="article_url")

    assert first.article_id == second.article_id
    assert second.skipped_existing is True
    assert extractor.calls == 1
    assert len(repo.list_articles()) == 1
    opinions = repo.list_opinions()
    assert len(opinions) == 1
    assert opinions[0].source_excerpt == "AI Capex 需求仍然强劲。"
    assert opinions[0].source_location == "p1"
