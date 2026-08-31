from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from kol_radar.domain import OpinionDraft, Topic
from kol_radar.providers.base import FetchedArticle


class StructuredOpinionDraft(OpinionDraft):
    model_config = ConfigDict(extra="forbid")


class OpinionExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opinions: list[StructuredOpinionDraft] = Field(default_factory=list, max_length=5)


def strict_opinion_json_schema() -> dict[str, object]:
    return _make_schema_strict(OpinionExtractionResult.model_json_schema())


def _make_schema_strict(value):
    if isinstance(value, list):
        return [_make_schema_strict(item) for item in value]
    if not isinstance(value, dict):
        return value

    result = {
        key: _make_schema_strict(item)
        for key, item in value.items()
        if key != "default"
    }
    if result.get("type") == "object":
        properties = result.get("properties", {})
        result["additionalProperties"] = False
        result["required"] = list(properties)
    return result


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


_POSITIONING_MARKERS = re.compile(
    r"仓位|持仓|敞口|配置|加仓|减仓|增配|减配|空仓|满仓|重仓|轻仓|"
    r"进攻|防御|风险暴露|position|exposure|allocation|overweight|underweight|"
    r"risk[- ]on|risk[- ]off",
    re.IGNORECASE,
)


def validate_opinion_evidence(
    article: FetchedArticle, drafts: list[OpinionDraft]
) -> tuple[list[OpinionDraft], int]:
    paragraph_by_location = {
        paragraph.location: _normalize_whitespace(paragraph.text)
        for paragraph in article.paragraphs
    }
    accepted: list[OpinionDraft] = []
    for draft in drafts:
        paragraph = paragraph_by_location.get(draft.source_location)
        excerpt = _normalize_whitespace(draft.source_excerpt)
        if paragraph is None or excerpt not in paragraph:
            continue
        if draft.topic is Topic.positioning and not _POSITIONING_MARKERS.search(excerpt):
            continue
        accepted.append(draft)
    return accepted, len(drafts) - len(accepted)
