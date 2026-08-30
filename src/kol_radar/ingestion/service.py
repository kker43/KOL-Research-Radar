from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from kol_radar.domain import Article, Author, AuthorType, Opinion, Source
from kol_radar.extraction.base import OpinionExtractor
from kol_radar.normalization.subjects import normalize_subject
from kol_radar.providers.base import FetchedArticle, ProviderUnavailable, SourceProvider
from kol_radar.storage.repository import Repository


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    article_id: int
    source_id: int
    author_id: int
    opinions_count: int
    skipped_existing: bool


@dataclass(frozen=True)
class SyncResult:
    source_id: int
    discovered: int = 0
    new: int = 0
    skipped: int = 0
    failed: int = 0
    opinions: int = 0
    status: str = "success"
    error: str | None = None


def _normalized_content(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip()


def _source_external_id(source_name: str) -> str:
    digest = hashlib.sha256(source_name.casefold().encode("utf-8")).hexdigest()[:16]
    return f"article-url-{digest}"


class IngestionService:
    def __init__(self, repository: Repository, extractor: OpinionExtractor):
        self.repository = repository
        self.extractor = extractor

    def ingest_fetched(
        self,
        article: FetchedArticle,
        provider_name: str,
        external_source_id: str | None = None,
    ) -> IngestionResult:
        source = self.repository.upsert_source(
            Source(
                name=article.source_name,
                provider=provider_name,
                external_id=external_source_id or _source_external_id(article.source_name),
            )
        )
        if source.id is None:
            raise RuntimeError("Persisted source has no id")

        author = self.repository.upsert_author(
            Author(
                name=article.author_name or article.source_name,
                author_type=(
                    AuthorType.person if article.author_name else AuthorType.organization
                ),
            )
        )
        if author.id is None:
            raise RuntimeError("Persisted author has no id")

        normalized_content = _normalized_content(article.content)
        stored_article = self.repository.upsert_article(
            Article(
                source_id=source.id,
                author_id=author.id,
                title=article.title,
                url=article.url,
                published_at=article.published_at,
                content=article.content,
                content_hash=hashlib.sha256(
                    normalized_content.encode("utf-8")
                ).hexdigest(),
            )
        )
        if stored_article.id is None:
            raise RuntimeError("Persisted article has no id")
        if stored_article.processed_at is not None:
            logger.info("article_skipped article_id=%s", stored_article.id)
            return IngestionResult(
                article_id=stored_article.id,
                source_id=source.id,
                author_id=author.id,
                opinions_count=len(
                    self.repository.list_opinions_for_article(stored_article.id)
                ),
                skipped_existing=True,
            )

        drafts = self.extractor.extract(article)
        if len(drafts) > 5:
            raise ValueError("An article cannot produce more than 5 opinions")

        opinions_count = 0
        for draft in drafts:
            normalized_subject = normalize_subject(draft.raw_subject)
            self.repository.insert_opinion(
                Opinion(
                    topic=draft.topic,
                    subject=normalized_subject.display_name,
                    raw_subject=draft.raw_subject,
                    subject_key=normalized_subject.key,
                    subject_type=normalized_subject.subject_type,
                    stance=draft.stance,
                    thesis=draft.thesis,
                    rationale=draft.rationale,
                    published_at=article.published_at,
                    source_article_id=stored_article.id,
                    author_id=author.id,
                    source_excerpt=draft.source_excerpt,
                    source_location=draft.source_location,
                )
            )
            opinions_count += 1

        self.repository.mark_article_processed(stored_article.id)
        logger.info(
            "article_processed article_id=%s source_id=%s opinions_extracted=%s",
            stored_article.id,
            source.id,
            opinions_count,
        )
        return IngestionResult(
            article_id=stored_article.id,
            source_id=source.id,
            author_id=author.id,
            opinions_count=opinions_count,
            skipped_existing=False,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SyncService:
    def __init__(
        self,
        repository: Repository,
        ingestion_service: IngestionService,
        providers: dict[str, SourceProvider],
        *,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self.repository = repository
        self.ingestion_service = ingestion_service
        self.providers = providers
        self.clock = clock

    def sync_source(self, source_id: int, lookback_days: int) -> SyncResult:
        source = self.repository.get_source(source_id)
        if source is None:
            raise KeyError(f"Source {source_id} does not exist")
        started_at = self.clock()
        logger.info("sync_start source_id=%s", source_id)
        since = source.last_synced_at or started_at - timedelta(days=lookback_days)
        provider = self.providers.get(source.provider)
        if provider is None:
            return self._failed_source(source_id, started_at, "ProviderUnavailable")
        try:
            discovered_articles = provider.discover(source.external_id, since)
        except ProviderUnavailable as error:
            logger.warning(
                "sync_source_failed source_id=%s error_type=%s",
                source_id,
                type(error).__name__,
            )
            return self._failed_source(source_id, started_at, type(error).__name__)
        logger.info(
            "articles_discovered source_id=%s count=%s",
            source_id,
            len(discovered_articles),
        )

        new = skipped = failed = opinions = 0
        for discovered in discovered_articles:
            if self.repository.get_article_by_url(discovered.url) is not None:
                skipped += 1
                continue
            try:
                fetched = provider.fetch(discovered)
                result = self.ingestion_service.ingest_fetched(
                    fetched,
                    provider_name=source.provider,
                    external_source_id=source.external_id,
                )
                if result.skipped_existing:
                    skipped += 1
                else:
                    new += 1
                    opinions += result.opinions_count
            except Exception as error:
                failed += 1
                logger.warning(
                    "article_failed source_id=%s error_type=%s",
                    source_id,
                    type(error).__name__,
                )

        completed_at = self.clock()
        if failed == 0:
            self.repository.update_source_last_synced(source_id, completed_at)
        result = SyncResult(
            source_id=source_id,
            discovered=len(discovered_articles),
            new=new,
            skipped=skipped,
            failed=failed,
            opinions=opinions,
            status="success" if failed == 0 else "partial",
        )
        self.repository.record_sync_run(result, started_at, completed_at)
        logger.info(
            "sync_end source_id=%s status=%s new=%s skipped=%s failed=%s opinions=%s",
            source_id,
            result.status,
            result.new,
            result.skipped,
            result.failed,
            result.opinions,
        )
        return result

    def sync_all(self, lookback_days: int) -> list[SyncResult]:
        return [
            self.sync_source(source.id, lookback_days)
            for source in self.repository.list_sources()
            if source.id is not None
        ]

    def _failed_source(
        self, source_id: int, started_at: datetime, error: str
    ) -> SyncResult:
        completed_at = self.clock()
        result = SyncResult(source_id=source_id, status="failed", error=error)
        self.repository.record_sync_run(result, started_at, completed_at)
        return result
