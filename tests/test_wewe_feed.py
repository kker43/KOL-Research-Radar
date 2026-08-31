import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from kol_radar.domain import OpinionDraft, Source, Stance, Topic
from kol_radar.ingestion.service import IngestionService, SyncService
from kol_radar.obsidian.exporter import ObsidianExporter
from kol_radar.providers.base import (
    DiscoveredArticle,
    FetchedArticle,
    Paragraph,
    ProviderUnavailable,
)
from kol_radar.providers.wewe_feed import WeWeFeedProvider
from kol_radar.storage.repository import Repository


class FakeExtractor:
    def extract(self, article):
        return [
            OpinionDraft(
                topic=Topic.trend,
                raw_subject="AI Capex",
                stance=Stance.positive,
                thesis="需求趋势保持向上。",
                rationale=[],
                source_excerpt=article.paragraphs[0].text,
                source_location="p1",
            )
        ]


class MetadataArticleProvider:
    def __init__(self, author_name="原文作者"):
        self.author_name = author_name
        self.calls = 0

    def fetch(self, article):
        self.calls += 1
        return FetchedArticle(
            title=article.title,
            url=article.url,
            source_name="测试公众号",
            author_name=self.author_name,
            published_at=article.published_at,
            content="原文页面正文。",
            paragraphs=[Paragraph("p1", "原文页面正文。")],
        )


def feed_payload():
    return json.loads(Path("tests/fixtures/wewe_feed_sample.json").read_text())


def test_wewe_provider_discovers_articles_since_cutoff(respx_mock):
    respx_mock.get(
        "http://localhost:4000/feeds/MP_TEST.json?limit=100&page=1"
    ).respond(
        200, json=feed_payload()
    )
    metadata_provider = MetadataArticleProvider()
    provider = WeWeFeedProvider("http://localhost:4000", metadata_provider)

    found = provider.discover(
        "MP_TEST", since=datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert [article.external_id for article in found] == ["article-august"]
    fetched = provider.fetch(found[0])
    assert fetched.source_name == "测试公众号"
    assert fetched.author_name == "原文作者"
    assert fetched.paragraphs[0].location == "p1"
    assert fetched.paragraphs[0].text == "AI Capex 需求仍然强劲。"
    assert metadata_provider.calls == 1


def test_wewe_provider_pages_until_lookback_cutoff(respx_mock):
    recent_items = [
        {
            "id": f"recent-{index}",
            "url": f"https://mp.weixin.qq.com/s/recent-{index}",
            "title": f"近期文章 {index}",
            "date_published": "2026-08-20T08:00:00Z",
            "content_text": "近期正文。",
        }
        for index in range(100)
    ]
    page_two = [
        {
            "id": "recent-page-two",
            "url": "https://mp.weixin.qq.com/s/recent-page-two",
            "title": "第二页近期文章",
            "date_published": "2026-08-02T08:00:00Z",
            "content_text": "第二页近期正文。",
        },
        {
            "id": "before-cutoff",
            "url": "https://mp.weixin.qq.com/s/before-cutoff",
            "title": "窗口外文章",
            "date_published": "2026-07-31T08:00:00Z",
            "content_text": "窗口外正文。",
        },
    ]
    respx_mock.get(
        "http://localhost:4000/feeds/MP_TEST.json?limit=100&page=1"
    ).respond(200, json={"title": "测试公众号", "items": recent_items})
    respx_mock.get(
        "http://localhost:4000/feeds/MP_TEST.json?limit=100&page=2"
    ).respond(200, json={"title": "测试公众号", "items": page_two})
    provider = WeWeFeedProvider("http://localhost:4000", MetadataArticleProvider())

    found = provider.discover(
        "MP_TEST", since=datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert len(found) == 101
    assert found[-1].external_id == "recent-page-two"


def test_sync_source_is_idempotent_and_records_runs(tmp_path, respx_mock, caplog):
    caplog.set_level(logging.INFO)
    respx_mock.get(
        "http://localhost:4000/feeds/MP_TEST.json?limit=100&page=1"
    ).respond(
        200, json=feed_payload()
    )
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(
        Source(name="测试公众号", provider="wewe", external_id="MP_TEST")
    )
    provider = WeWeFeedProvider("http://localhost:4000", MetadataArticleProvider())
    vault = tmp_path / "KOL-Research"
    sync = SyncService(
        repo,
        IngestionService(repo, FakeExtractor()),
        {"wewe": provider},
        ObsidianExporter(vault),
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )

    first = sync.sync_source(source.id, lookback_days=60)
    notes_after_first = sorted(vault.rglob("*.md"))
    hashes_after_first = {
        path.relative_to(vault): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in notes_after_first
    }
    second = sync.sync_source(source.id, lookback_days=60)
    notes_after_second = sorted(vault.rglob("*.md"))
    hashes_after_second = {
        path.relative_to(vault): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in notes_after_second
    }

    assert first.new == 2
    assert second.new == 0
    assert second.skipped == 1
    assert len(repo.list_articles()) == 2
    assert len(repo.list_opinions()) == 2
    assert len(notes_after_first) == 2
    assert hashes_after_second == hashes_after_first
    assert len(repo.list_sync_runs()) == 2
    assert repo.get_source(source.id).last_synced_at == datetime(
        2026, 8, 20, 8, tzinfo=timezone.utc
    )
    messages = [record.getMessage() for record in caplog.records]
    assert any("sync_start" in message for message in messages)
    assert any("sync_end" in message for message in messages)


def test_sync_all_isolates_unavailable_provider(tmp_path):
    class UnavailableProvider:
        def discover(self, source_external_id, since):
            raise ProviderUnavailable("offline")

    class EmptyProvider:
        def discover(self, source_external_id, since):
            return []

    repo = Repository(tmp_path / "radar.db")
    repo.upsert_source(Source(name="Bad", provider="bad", external_id="bad-1"))
    repo.upsert_source(Source(name="Good", provider="good", external_id="good-1"))
    sync = SyncService(
        repo,
        IngestionService(repo, FakeExtractor()),
        {"bad": UnavailableProvider(), "good": EmptyProvider()},
        ObsidianExporter(tmp_path / "KOL-Research"),
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )

    results = sync.sync_all(lookback_days=60)

    assert [result.status for result in results] == ["failed", "success"]


def test_sync_retries_article_left_unprocessed_after_extraction_failure(tmp_path):
    article = DiscoveredArticle(
        external_id="retry-me",
        title="重试文章",
        url="https://mp.weixin.qq.com/s/retry-me",
        published_at=datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
    )

    class OneArticleProvider:
        def discover(self, source_external_id, since):
            return [article]

        def fetch(self, discovered):
            content = f"{discovered.title}：AI Capex 需求仍然强劲。"
            return FetchedArticle(
                title=discovered.title,
                url=discovered.url,
                source_name="测试公众号",
                author_name="测试作者",
                published_at=discovered.published_at,
                content=content,
                paragraphs=[Paragraph("p1", content)],
            )

    class FailOnceExtractor(FakeExtractor):
        def __init__(self):
            self.calls = 0

        def extract(self, fetched):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary extraction failure")
            return super().extract(fetched)

    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(
        Source(name="测试公众号", provider="wewe", external_id="MP_TEST")
    )
    extractor = FailOnceExtractor()
    sync = SyncService(
        repo,
        IngestionService(repo, extractor),
        {"wewe": OneArticleProvider()},
        ObsidianExporter(tmp_path / "KOL-Research"),
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )

    first = sync.sync_source(source.id, lookback_days=60)
    failed_article = repo.get_article_by_url(article.url)
    second = sync.sync_source(source.id, lookback_days=60)
    recovered_article = repo.get_article_by_url(article.url)

    assert first.status == "partial"
    assert failed_article is not None and failed_article.processed_at is None
    assert second.status == "success"
    assert second.new == 1
    assert recovered_article is not None and recovered_article.processed_at is not None
    assert len(repo.list_opinions_for_article(recovered_article.id)) == 1
    assert len(list((tmp_path / "KOL-Research").rglob("*.md"))) == 1


def test_sync_watermark_uses_publication_time_with_overlap(tmp_path):
    first_article = DiscoveredArticle(
        external_id="first",
        title="先到文章",
        url="https://mp.weixin.qq.com/s/first",
        published_at=datetime(2026, 8, 20, 8, tzinfo=timezone.utc),
    )
    delayed_article = DiscoveredArticle(
        external_id="delayed",
        title="延迟文章",
        url="https://mp.weixin.qq.com/s/delayed",
        published_at=datetime(2026, 8, 19, 12, tzinfo=timezone.utc),
    )

    class DelayedProvider:
        def __init__(self):
            self.calls = 0
            self.since_values = []

        def discover(self, source_external_id, since):
            self.calls += 1
            self.since_values.append(since)
            candidates = (
                [first_article]
                if self.calls == 1
                else [first_article, delayed_article]
            )
            return [item for item in candidates if item.published_at >= since]

        def fetch(self, discovered):
            content = f"{discovered.title}：AI Capex 需求仍然强劲。"
            return FetchedArticle(
                title=discovered.title,
                url=discovered.url,
                source_name="测试公众号",
                author_name="测试作者",
                published_at=discovered.published_at,
                content=content,
                paragraphs=[Paragraph("p1", content)],
            )

    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(
        Source(name="测试公众号", provider="wewe", external_id="MP_TEST")
    )
    provider = DelayedProvider()
    sync = SyncService(
        repo,
        IngestionService(repo, FakeExtractor()),
        {"wewe": provider},
        ObsidianExporter(tmp_path / "KOL-Research"),
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )

    sync.sync_source(source.id, lookback_days=60)
    second = sync.sync_source(source.id, lookback_days=60)

    assert provider.since_values[1] == datetime(2026, 8, 19, 8, tzinfo=timezone.utc)
    assert second.new == 1
    assert len(repo.list_articles()) == 2
    assert repo.get_source(source.id).last_synced_at == first_article.published_at
