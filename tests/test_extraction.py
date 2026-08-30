from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from kol_radar.domain import OpinionDraft, Stance, Topic
from kol_radar.extraction.openai_extractor import OpenAIOpinionExtractor
from kol_radar.providers.base import FetchedArticle, Paragraph


class FakeResponses:
    def __init__(self, payload):
        self.payload = payload
        self.last_request = None

    def parse(self, **kwargs):
        self.last_request = kwargs
        parsed = kwargs["text_format"].model_validate(self.payload)
        return SimpleNamespace(output_parsed=parsed)


class FakeClient:
    def __init__(self, payload):
        self.responses = FakeResponses(payload)


def test_opinion_draft_requires_evidence():
    with pytest.raises(ValidationError):
        OpinionDraft(
            topic=Topic.risk,
            raw_subject="AI high valuation stocks",
            stance=Stance.deteriorating,
            thesis="Risk is rising.",
            rationale=["Crowding is rising."],
            source_excerpt="",
            source_location="p3",
        )


def test_positioning_requires_explicit_evidence_marker():
    draft = OpinionDraft(
        topic=Topic.positioning,
        raw_subject="US equities",
        stance=Stance.negative,
        thesis="Reduce equity exposure.",
        rationale=["Valuations are stretched."],
        source_excerpt="我会降低股票仓位。",
        source_location="p2",
    )
    assert "仓位" in draft.source_excerpt


def test_extractor_rejects_drafts_without_exact_evidence():
    payload = {
        "opinions": [
            {
                "topic": "trend",
                "raw_subject": "AI Capex",
                "stance": "positive",
                "thesis": "AI Capex remains strong.",
                "rationale": ["Demand is resilient."],
                "source_excerpt": "AI Capex 需求仍然强劲。",
                "source_location": "p1",
            },
            {
                "topic": "risk",
                "raw_subject": "US equities",
                "stance": "deteriorating",
                "thesis": "Risk is increasing.",
                "rationale": [],
                "source_excerpt": "原文并不存在的证据",
                "source_location": "p2",
            },
        ]
    }
    client = FakeClient(payload)
    article = FetchedArticle(
        title="测试文章",
        url="https://mp.weixin.qq.com/s/test",
        source_name="测试公众号",
        author_name="测试作者",
        published_at=None,
        content="AI Capex 需求仍然强劲。\n\n我们会降低股票仓位。",
        paragraphs=[
            Paragraph("p1", "AI Capex 需求仍然强劲。"),
            Paragraph("p2", "我们会降低股票仓位。"),
        ],
    )

    extractor = OpenAIOpinionExtractor(client=client, model="test-model")
    opinions = extractor.extract(article)

    assert [opinion.source_location for opinion in opinions] == ["p1"]
    assert extractor.last_rejected_count == 1
    request_text = str(client.responses.last_request["input"])
    assert "[p1] AI Capex 需求仍然强劲。" in request_text
    assert client.responses.last_request["model"] == "test-model"
