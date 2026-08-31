import json
import subprocess

import pytest

from kol_radar.domain import Topic
from kol_radar.extraction.base import OpinionExtractionError
from kol_radar.extraction.codex_extractor import (
    CodexCLIRunner,
    CodexOpinionExtractor,
)
from kol_radar.providers.base import FetchedArticle, Paragraph


def _article() -> FetchedArticle:
    return FetchedArticle(
        title="测试文章",
        url="https://mp.weixin.qq.com/s/codex-test",
        source_name="测试公众号",
        author_name="测试作者",
        published_at=None,
        content="AI Capex 需求仍然强劲。\n\n我们会降低股票仓位。",
        paragraphs=[
            Paragraph("p1", "AI Capex 需求仍然强劲。"),
            Paragraph("p2", "我们会降低股票仓位。"),
        ],
    )


class FakeCodexRunner:
    def __init__(self, payload):
        self.payload = payload
        self.prompt = None
        self.schema = None

    def generate(self, *, prompt, schema):
        self.prompt = prompt
        self.schema = schema
        return json.dumps(self.payload, ensure_ascii=False)


def test_codex_structured_output_is_parsed_into_existing_opinion_draft():
    runner = FakeCodexRunner(
        {
            "opinions": [
                {
                    "topic": "trend",
                    "raw_subject": "AI Capex",
                    "stance": "positive",
                    "thesis": "AI Capex remains strong.",
                    "rationale": ["Demand is resilient."],
                    "source_excerpt": "AI Capex 需求仍然强劲。",
                    "source_location": "p1",
                }
            ]
        }
    )

    extractor = CodexOpinionExtractor(runner=runner)
    opinions = extractor.extract(_article())

    assert len(opinions) == 1
    assert opinions[0].topic is Topic.trend
    assert opinions[0].source_location == "p1"
    assert "[p1] AI Capex 需求仍然强劲。" in runner.prompt
    assert runner.schema["required"] == ["opinions"]
    assert runner.schema["additionalProperties"] is False


def test_codex_invalid_evidence_is_rejected_by_shared_validation():
    runner = FakeCodexRunner(
        {
            "opinions": [
                {
                    "topic": "risk",
                    "raw_subject": "US equities",
                    "stance": "deteriorating",
                    "thesis": "Risk is increasing.",
                    "rationale": [],
                    "source_excerpt": "原文并不存在的证据",
                    "source_location": "p1",
                }
            ]
        }
    )
    extractor = CodexOpinionExtractor(runner=runner)

    assert extractor.extract(_article()) == []
    assert extractor.last_rejected_count == 1


def test_codex_rejects_positioning_inferred_from_market_view():
    runner = FakeCodexRunner(
        {
            "opinions": [
                {
                    "topic": "positioning",
                    "raw_subject": "AI Capex",
                    "stance": "positive",
                    "thesis": "Increase exposure.",
                    "rationale": [],
                    "source_excerpt": "AI Capex 需求仍然强劲。",
                    "source_location": "p1",
                }
            ]
        }
    )

    assert CodexOpinionExtractor(runner=runner).extract(_article()) == []


def test_codex_invalid_json_raises_typed_error():
    extractor = CodexOpinionExtractor(runner=FakeCodexRunner("not-json"))

    with pytest.raises(OpinionExtractionError, match="invalid structured JSON"):
        extractor.extract(_article())


def test_codex_rejects_fields_outside_existing_opinion_schema():
    runner = FakeCodexRunner(
        {
            "opinions": [
                {
                    "topic": "trend",
                    "raw_subject": "AI Capex",
                    "stance": "positive",
                    "thesis": "AI Capex remains strong.",
                    "rationale": [],
                    "source_excerpt": "AI Capex 需求仍然强劲。",
                    "source_location": "p1",
                    "confidence": 0.9,
                }
            ]
        }
    )

    with pytest.raises(OpinionExtractionError, match="invalid structured JSON"):
        CodexOpinionExtractor(runner=runner).extract(_article())


def test_codex_cli_uses_chatgpt_login_without_openai_api_key(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[1:3] == ["login", "status"]:
            return subprocess.CompletedProcess(
                command, 0, stdout="", stderr="Logged in using ChatGPT\n"
            )
        schema_path = command[command.index("--output-schema") + 1]
        assert json.loads(open(schema_path, encoding="utf-8").read())["type"] == "object"
        return subprocess.CompletedProcess(
            command, 0, stdout='{"opinions": []}\n', stderr=""
        )

    monkeypatch.setattr("shutil.which", lambda executable: "/usr/local/bin/codex")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-codex")
    runner = CodexCLIRunner(command_runner=fake_run)

    assert json.loads(runner.generate(prompt="extract", schema={"type": "object"})) == {
        "opinions": []
    }
    assert len(calls) == 2
    assert "OPENAI_API_KEY" not in calls[0][1]["env"]
    assert "OPENAI_API_KEY" not in calls[1][1]["env"]
    assert "--sandbox" in calls[1][0]
    assert calls[1][0][-1] == "-"


def test_codex_cli_reports_actionable_authentication_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda executable: "/usr/local/bin/codex")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="not logged in")

    runner = CodexCLIRunner(command_runner=fake_run)

    with pytest.raises(OpinionExtractionError, match="codex login"):
        runner.generate(prompt="extract", schema={"type": "object"})
