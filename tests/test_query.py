from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

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
from kol_radar.query.planner import QueryKind, QueryPlan, QueryPlanner
from kol_radar.query.service import QueryService
from kol_radar.storage.repository import Repository


class FakeResponses:
    def __init__(self, payload):
        self.payload = payload
        self.last_input = None

    def parse(self, **kwargs):
        self.last_input = kwargs["input"]
        return SimpleNamespace(
            output_parsed=kwargs["text_format"].model_validate(self.payload)
        )


@pytest.mark.parametrize(
    ("text", "payload", "expected_kind"),
    [
        (
            "最近30天最大的风险是什么",
            {"kind": "recent_by_topic", "topic": "risk", "since_days": 30},
            QueryKind.recent_by_topic,
        ),
        (
            "最近谁开始看多存储",
            {
                "kind": "subject_change",
                "topic": "opportunity",
                "subject": "DRAM",
                "since_days": 30,
            },
            QueryKind.subject_change,
        ),
        (
            "过去两个月某KOL怎么看美股",
            {
                "kind": "author_subject_history",
                "subject": "美股",
                "author_name": "某KOL",
                "since_days": 60,
            },
            QueryKind.author_subject_history,
        ),
        (
            "多个KOL对AI Capex有什么分歧",
            {
                "kind": "cross_kol_compare",
                "subject": "AI Capex",
                "since_days": 30,
            },
            QueryKind.cross_kol_compare,
        ),
    ],
)
def test_query_planner_returns_one_of_four_locked_plans(text, payload, expected_kind):
    responses = FakeResponses(payload)
    planner = QueryPlanner(SimpleNamespace(responses=responses), model="test-model")

    plan = planner.plan(text)

    assert plan.kind == expected_kind
    assert text in str(responses.last_input)


def test_query_service_reads_recent_risks_from_local_sqlite(tmp_path):
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(Source(name="本地来源", provider="fixture", external_id="s1"))
    author = repo.upsert_author(Author(name="研究员甲", author_type=AuthorType.person))
    article = repo.upsert_article(
        Article(
            source_id=source.id,
            author_id=author.id,
            title="风险上升",
            url="https://example.test/risk",
            published_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
            content="美股回撤风险正在增加。",
            content_hash="query-hash-1",
        )
    )
    repo.insert_opinion(
        Opinion(
            topic=Topic.risk,
            subject="美股",
            raw_subject="美股",
            subject_key="US_EQUITIES",
            subject_type=SubjectType.market,
            stance=Stance.deteriorating,
            thesis="美股回撤风险正在增加。",
            rationale=[],
            published_at=article.published_at,
            source_article_id=article.id,
            author_id=author.id,
            source_excerpt="美股回撤风险正在增加。",
            source_location="p1",
        )
    )
    service = QueryService(
        repo, clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    )

    result = service.execute(
        QueryPlan(kind=QueryKind.recent_by_topic, topic=Topic.risk, since_days=30)
    )

    assert len(result.records) == 1
    assert "研究员甲" in result.text
    assert "美股回撤风险正在增加" in result.text
