from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class ArticleFetchError(RuntimeError):
    """Raised when an article cannot be fetched or parsed."""


class ProviderUnavailable(RuntimeError):
    """Raised when a source provider cannot serve a discovery request."""


@dataclass(frozen=True)
class Paragraph:
    location: str
    text: str


@dataclass(frozen=True)
class DiscoveredArticle:
    external_id: str
    title: str
    url: str
    published_at: datetime | None
    author_name: str | None = None


@dataclass(frozen=True)
class FetchedArticle:
    title: str
    url: str
    source_name: str
    author_name: str | None
    published_at: datetime | None
    content: str
    paragraphs: list[Paragraph]


class SourceProvider(Protocol):
    def discover(
        self, source_external_id: str, since: datetime | None
    ) -> list[DiscoveredArticle]: ...

    def fetch(self, article: DiscoveredArticle) -> FetchedArticle: ...
