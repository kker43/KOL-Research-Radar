from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from kol_radar.domain import Article, Author, AuthorType, Opinion, Source
from kol_radar.extraction.base import OpinionExtractor
from kol_radar.normalization.subjects import normalize_subject
from kol_radar.providers.base import FetchedArticle
from kol_radar.storage.repository import Repository


@dataclass(frozen=True)
class IngestionResult:
    article_id: int
    source_id: int
    author_id: int
    opinions_count: int
    skipped_existing: bool


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
        return IngestionResult(
            article_id=stored_article.id,
            source_id=source.id,
            author_id=author.id,
            opinions_count=opinions_count,
            skipped_existing=False,
        )
