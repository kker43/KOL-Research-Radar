from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer

from kol_radar.config import Settings
from kol_radar.domain import OpinionDraft, Source, Topic
from kol_radar.extraction.openai_extractor import OpenAIOpinionExtractor
from kol_radar.ingestion.article_parser import parse_wechat_article
from kol_radar.ingestion.service import IngestionResult, IngestionService, SyncService
from kol_radar.logging_config import configure_logging
from kol_radar.normalization.subjects import normalize_subject
from kol_radar.obsidian.exporter import ObsidianExporter, resolve_obsidian_root
from kol_radar.providers.article_url import ArticleURLProvider
from kol_radar.providers.base import FetchedArticle, Paragraph
from kol_radar.providers.wewe_feed import WeWeFeedProvider
from kol_radar.query.digest import DigestService
from kol_radar.query.planner import QueryKind, QueryPlan, QueryPlanner
from kol_radar.query.service import QueryService
from kol_radar.storage.repository import Repository


app = typer.Typer(no_args_is_help=True, help="Local KOL research radar.")
watchlist_app = typer.Typer(no_args_is_help=True, help="Manage tracked sources.")
app.add_typer(watchlist_app, name="watchlist")


class SampleFixtureExtractor:
    def extract(self, article: FetchedArticle) -> list[OpinionDraft]:
        if not article.paragraphs:
            return []
        first = article.paragraphs[0]
        return [
            OpinionDraft(
                topic=Topic.trend,
                raw_subject="AI Capex",
                stance="positive",
                thesis="AI Capex 需求仍处于上升趋势。",
                rationale=["原文明确表示需求仍然强劲。"],
                source_excerpt=first.text,
                source_location=first.location,
            )
        ]


class GoldenFixtureExtractor:
    def __init__(self, records: list[dict[str, object]]):
        self.expected_by_url = {
            str(record["url"]): list(record["expected_opinions"])
            for record in records
        }

    def extract(self, article: FetchedArticle) -> list[OpinionDraft]:
        drafts = []
        for expected in self.expected_by_url.get(article.url, []):
            payload = dict(expected)
            payload.pop("expected_subject_key", None)
            drafts.append(OpinionDraft.model_validate(payload))
        return drafts


def _repository(settings: Settings) -> Repository:
    return Repository(settings.kol_db_path)


def _live_extractor(settings: Settings) -> OpenAIOpinionExtractor:
    if not settings.openai_api_key or not settings.openai_model:
        raise typer.BadParameter("OPENAI_API_KEY and OPENAI_MODEL are required")
    from openai import OpenAI

    return OpenAIOpinionExtractor(
        OpenAI(api_key=settings.openai_api_key), settings.openai_model
    )


def _export_ingestion(
    settings: Settings, repository: Repository, result: IngestionResult
) -> Path:
    article = repository.get_article(result.article_id)
    source = repository.get_source(result.source_id)
    author = repository.get_author(result.author_id)
    if article is None or source is None or author is None:
        raise RuntimeError("Persisted ingestion records are incomplete")
    exporter = ObsidianExporter(resolve_obsidian_root(settings.obsidian_vault_path))
    return exporter.export_article(
        article,
        source,
        author,
        repository.list_opinions_for_article(result.article_id),
    )


def _ingest_fetched(
    settings: Settings, fetched: FetchedArticle, extractor
) -> tuple[IngestionResult, Path]:
    repository = _repository(settings)
    result = IngestionService(repository, extractor).ingest_fetched(
        fetched, provider_name="article_url"
    )
    return result, _export_ingestion(settings, repository, result)


@watchlist_app.command("list")
def list_watchlist() -> None:
    """List explicitly tracked sources."""
    settings = Settings()
    configure_logging(settings.log_level)
    sources = _repository(settings).list_sources()
    if not sources:
        typer.echo("Watchlist is empty.")
        return
    for source in sources:
        synced = source.last_synced_at.isoformat() if source.last_synced_at else "never"
        typer.echo(
            f"{source.id} | {source.name} | {source.provider} | "
            f"{source.external_id} | last_synced={synced}"
        )


@watchlist_app.command("add")
def add_watchlist(
    name: Optional[str] = typer.Option(None, "--name"),
    provider: str = typer.Option("wewe", "--provider"),
    external_id: Optional[str] = typer.Option(None, "--external-id"),
    url: Optional[str] = typer.Option(None, "--url"),
) -> None:
    """Add a WeWe feed id or ingest one article URL."""
    settings = Settings()
    configure_logging(settings.log_level)
    if url:
        fetched = ArticleURLProvider().fetch_url(url)
        result, note = _ingest_fetched(settings, fetched, _live_extractor(settings))
        typer.echo(f"source_id={result.source_id} article_id={result.article_id} note={note}")
        return
    if not name or not external_id:
        raise typer.BadParameter("--name and --external-id are required without --url")
    if provider != "wewe":
        raise typer.BadParameter("Manual V1 watchlist sources use --provider wewe")
    source = _repository(settings).upsert_source(
        Source(name=name, provider=provider, external_id=external_id)
    )
    typer.echo(f"source_id={source.id} name={source.name} provider={source.provider}")


@app.command("ingest-url")
def ingest_url(
    url: Optional[str] = typer.Argument(None),
    fixture: Optional[Path] = typer.Option(None, "--fixture", exists=True, dir_okay=False),
) -> None:
    """Ingest one WeChat article through the complete local pipeline."""
    settings = Settings()
    configure_logging(settings.log_level)
    if fixture is not None:
        fixture_url = url or "https://mp.weixin.qq.com/s/fixture-article"
        fetched = parse_wechat_article(fixture.read_text(encoding="utf-8"), fixture_url)
        extractor = SampleFixtureExtractor()
    else:
        if not url:
            raise typer.BadParameter("URL is required unless --fixture is used")
        fetched = ArticleURLProvider().fetch_url(url)
        extractor = _live_extractor(settings)
    result, note = _ingest_fetched(settings, fetched, extractor)
    typer.echo(
        f"article_id={result.article_id} opinions={result.opinions_count} "
        f"skipped_existing={str(result.skipped_existing).lower()} note={note}"
    )


@app.command("sync")
def sync(source_id: Optional[int] = typer.Option(None, "--source-id")) -> None:
    """Incrementally sync configured WeWe sources."""
    settings = Settings()
    configure_logging(settings.log_level)
    repository = _repository(settings)
    sources = [repository.get_source(source_id)] if source_id else repository.list_sources()
    sources = [source for source in sources if source is not None and source.provider == "wewe"]
    if not sources:
        typer.echo("No WeWe sources configured.")
        return
    ingestion = IngestionService(repository, _live_extractor(settings))
    service = SyncService(
        repository,
        ingestion,
        {"wewe": WeWeFeedProvider(settings.wewe_rss_base_url)},
    )
    for source in sources:
        result = service.sync_source(source.id, settings.initial_lookback_days)
        typer.echo(
            f"source_id={result.source_id} status={result.status} "
            f"discovered={result.discovered} new={result.new} skipped={result.skipped} "
            f"failed={result.failed} opinions={result.opinions}"
        )


def _fixture_query_plan(text: str) -> QueryPlan:
    if "风险" in text:
        return QueryPlan(kind=QueryKind.recent_by_topic, topic=Topic.risk)
    if "机会" in text:
        return QueryPlan(kind=QueryKind.recent_by_topic, topic=Topic.opportunity)
    if "仓位" in text:
        return QueryPlan(kind=QueryKind.recent_by_topic, topic=Topic.positioning)
    return QueryPlan(kind=QueryKind.recent_by_topic, topic=Topic.trend)


@app.command("query")
def query(
    text: str = typer.Argument(...),
    fixture: bool = typer.Option(False, "--fixture"),
) -> None:
    """Query only the local SQLite knowledge base."""
    settings = Settings()
    configure_logging(settings.log_level)
    if fixture:
        plan = _fixture_query_plan(text)
    else:
        extractor = _live_extractor(settings)
        plan = QueryPlanner(extractor.client, extractor.model).plan(text)
    typer.echo(QueryService(_repository(settings)).execute(plan).text)


@app.command("digest")
def digest(since_hours: int = typer.Option(24, "--since-hours", min=1)) -> None:
    """Generate an incremental digest from local opinions."""
    settings = Settings()
    configure_logging(settings.log_level)
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    typer.echo(DigestService(_repository(settings)).generate(since).text)


def _golden_records() -> list[dict[str, object]]:
    path = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "golden_articles.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _fetched_from_golden(record: dict[str, object]) -> FetchedArticle:
    paragraphs = [Paragraph(**paragraph) for paragraph in record["paragraphs"]]
    return FetchedArticle(
        title=str(record["title"]),
        url=str(record["url"]),
        source_name=str(record["source_name"]),
        author_name=str(record["author_name"]) if record.get("author_name") else None,
        published_at=datetime.fromisoformat(str(record["published_at"])),
        content="\n\n".join(paragraph.text for paragraph in paragraphs),
        paragraphs=paragraphs,
    )


def _run_eval(*, live: bool, settings: Settings) -> dict[str, int | float]:
    records = _golden_records()
    extractor = _live_extractor(settings) if live else GoldenFixtureExtractor(records)
    expected_total = sum(len(record["expected_opinions"]) for record in records)
    extracted_total = topic_matches = subject_matches = valid_evidence = hallucinations = 0

    with tempfile.TemporaryDirectory(prefix="kol-radar-eval-") as directory:
        repository = Repository(Path(directory) / "eval.db")
        service = IngestionService(repository, extractor)
        for record in records:
            fetched = _fetched_from_golden(record)
            result = service.ingest_fetched(fetched, provider_name="fixture")
            actual = repository.list_opinions_for_article(result.article_id)
            expected = list(record["expected_opinions"])
            extracted_total += len(actual)
            paragraph_by_location = {
                paragraph.location: re.sub(r"\s+", " ", paragraph.text).strip()
                for paragraph in fetched.paragraphs
            }
            for opinion in actual:
                excerpt = re.sub(r"\s+", " ", opinion.source_excerpt).strip()
                if excerpt in paragraph_by_location.get(opinion.source_location, ""):
                    valid_evidence += 1
                if not any(
                    opinion.topic.value == item["topic"]
                    and opinion.subject_key == item["expected_subject_key"]
                    for item in expected
                ):
                    hallucinations += 1
            for item in expected:
                if any(opinion.topic.value == item["topic"] for opinion in actual):
                    topic_matches += 1
                if any(
                    opinion.subject_key == item["expected_subject_key"]
                    for opinion in actual
                ):
                    subject_matches += 1

    return {
        "articles_total": len(records),
        "opinions_expected": expected_total,
        "opinions_extracted": extracted_total,
        "topic_accuracy": topic_matches / expected_total if expected_total else 1.0,
        "subject_accuracy": subject_matches / expected_total if expected_total else 1.0,
        "evidence_validity": valid_evidence / extracted_total if extracted_total else 1.0,
        "hallucination_count": hallucinations,
    }


@app.command("eval")
def evaluate(
    fixture: bool = typer.Option(False, "--fixture"),
    live: bool = typer.Option(False, "--live"),
) -> None:
    """Run the golden fixture eval, or live eval when explicitly requested."""
    if fixture and live:
        raise typer.BadParameter("Choose either --fixture or --live")
    settings = Settings()
    configure_logging(settings.log_level)
    metrics = _run_eval(live=live, settings=settings)
    for key, value in metrics.items():
        typer.echo(f"{key}={value}")


if __name__ == "__main__":
    app()
