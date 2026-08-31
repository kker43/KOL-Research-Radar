from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Topic(str, Enum):
    market_view = "market_view"
    opportunity = "opportunity"
    risk = "risk"
    risk_reward = "risk_reward"
    positioning = "positioning"
    trend = "trend"


class Stance(str, Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"
    improving = "improving"
    deteriorating = "deteriorating"
    mixed = "mixed"
    unclear = "unclear"


class AuthorType(str, Enum):
    person = "person"
    organization = "organization"
    unknown = "unknown"


class SubjectType(str, Enum):
    market = "market"
    asset = "asset"
    industry = "industry"
    company = "company"
    theme = "theme"
    other = "other"


class Source(BaseModel):
    id: int | None = None
    name: str
    provider: str
    external_id: str
    status: str = "active"
    created_at: datetime = Field(default_factory=utc_now)
    last_synced_at: datetime | None = None


class Author(BaseModel):
    id: int | None = None
    name: str
    author_type: AuthorType = AuthorType.unknown
    created_at: datetime = Field(default_factory=utc_now)


class Article(BaseModel):
    id: int | None = None
    source_id: int
    title: str
    url: str
    published_at: datetime | None = None
    author_id: int
    content: str
    content_hash: str
    fetched_at: datetime = Field(default_factory=utc_now)
    processed_at: datetime | None = None


class OpinionDraft(BaseModel):
    topic: Topic
    raw_subject: str
    thesis: str
    stance: Stance
    rationale: list[str] = Field(default_factory=list)
    source_excerpt: str = Field(min_length=1)
    source_location: str = Field(min_length=1)


class Opinion(BaseModel):
    id: int | None = None
    topic: Topic
    subject: str
    raw_subject: str
    subject_key: str
    subject_type: SubjectType
    stance: Stance
    thesis: str
    rationale: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    source_article_id: int
    author_id: int
    source_excerpt: str = Field(min_length=1)
    source_location: str = Field(min_length=1)
