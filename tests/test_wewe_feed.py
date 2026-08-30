import json
from datetime import datetime, timezone
from pathlib import Path

from kol_radar.domain import OpinionDraft, Source, Stance, Topic
from kol_radar.ingestion.service import IngestionService, SyncService
from kol_radar.providers.base import ProviderUnavailable
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


def feed_payload():
    return json.loads(Path("tests/fixtures/wewe_feed_sample.json").read_text())


def test_wewe_provider_discovers_articles_since_cutoff(respx_mock):
    respx_mock.get("http://localhost:4000/feeds/MP_TEST.json?limit=100").respond(
        200, json=feed_payload()
    )
    provider = WeWeFeedProvider("http://localhost:4000")

    found = provider.discover(
        "MP_TEST", since=datetime(2026, 8, 1, tzinfo=timezone.utc)
    )

    assert [article.external_id for article in found] == ["article-august"]
    fetched = provider.fetch(found[0])
    assert fetched.source_name == "测试公众号"
    assert fetched.paragraphs[0].location == "p1"


def test_sync_source_is_idempotent_and_records_runs(tmp_path, respx_mock):
    respx_mock.get("http://localhost:4000/feeds/MP_TEST.json?limit=100").respond(
        200, json=feed_payload()
    )
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(
        Source(name="测试公众号", provider="wewe", external_id="MP_TEST")
    )
    provider = WeWeFeedProvider("http://localhost:4000")
    sync = SyncService(
        repo,
        IngestionService(repo, FakeExtractor()),
        {"wewe": provider},
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )

    first = sync.sync_source(source.id, lookback_days=60)
    second = sync.sync_source(source.id, lookback_days=60)

    assert first.new == 2
    assert second.new == 0
    assert len(repo.list_articles()) == 2
    assert len(repo.list_opinions()) == 2
    assert len(repo.list_sync_runs()) == 2


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
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )

    results = sync.sync_all(lookback_days=60)

    assert [result.status for result in results] == ["failed", "success"]
