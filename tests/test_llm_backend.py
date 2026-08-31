import openai
from typer.testing import CliRunner

from kol_radar.cli import (
    FixturePipelineExtractor,
    _golden_records,
    _live_extractor,
    app,
)
from kol_radar.config import LLMBackend, Settings
from kol_radar.extraction.codex_extractor import CodexOpinionExtractor
from kol_radar.extraction.openai_extractor import OpenAIOpinionExtractor


runner = CliRunner()


def test_backend_defaults_to_codex_without_openai_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    settings = Settings(_env_file=None)

    assert settings.llm_backend is LLMBackend.codex
    assert isinstance(_live_extractor(settings), CodexOpinionExtractor)


def test_openai_backend_still_works_when_explicitly_selected(monkeypatch):
    client = object()
    monkeypatch.setattr(openai, "OpenAI", lambda api_key: client)
    settings = Settings(
        _env_file=None,
        llm_backend=LLMBackend.openai,
        openai_api_key="test-key",
        openai_model="test-model",
    )

    extractor = _live_extractor(settings)

    assert isinstance(extractor, OpenAIOpinionExtractor)
    assert extractor.client is client
    assert extractor.model == "test-model"


def test_fixture_eval_does_not_initialize_any_live_backend(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("fixture eval must stay offline")

    monkeypatch.setattr("kol_radar.cli._live_extractor", fail_if_called)

    result = runner.invoke(app, ["eval", "--fixture"])

    assert result.exit_code == 0, result.output
    assert "evaluation_mode=fixture_pipeline_acceptance" in result.output


def test_codex_live_eval_uses_existing_ten_article_golden_dataset(monkeypatch):
    selected_backends = []

    def fake_live_extractor(settings, backend=None):
        selected_backends.append(backend)
        return FixturePipelineExtractor(_golden_records())

    monkeypatch.setattr("kol_radar.cli._live_extractor", fake_live_extractor)

    result = runner.invoke(app, ["eval", "--live", "--backend", "codex"])

    assert result.exit_code == 0, result.output
    assert selected_backends == [LLMBackend.codex]
    assert "evaluation_mode=live_model_eval" in result.output
    assert "articles_total=10" in result.output
    assert "evidence_validity=1.0" in result.output
    assert "hallucination_count=0" in result.output
