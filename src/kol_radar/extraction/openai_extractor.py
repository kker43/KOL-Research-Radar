from __future__ import annotations

import re

from pydantic import BaseModel, Field

from kol_radar.domain import OpinionDraft
from kol_radar.extraction.prompts import SYSTEM_PROMPT, format_article
from kol_radar.providers.base import FetchedArticle


class OpinionExtractionResult(BaseModel):
    opinions: list[OpinionDraft] = Field(default_factory=list, max_length=5)


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class OpenAIOpinionExtractor:
    def __init__(self, client, model: str):
        self.client = client
        self.model = model
        self.last_rejected_count = 0

    def extract(self, article: FetchedArticle) -> list[OpinionDraft]:
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": format_article(article)},
            ],
            text_format=OpinionExtractionResult,
        )
        result = response.output_parsed
        if result is None:
            self.last_rejected_count = 0
            return []

        paragraph_by_location = {
            paragraph.location: _normalize_whitespace(paragraph.text)
            for paragraph in article.paragraphs
        }
        accepted: list[OpinionDraft] = []
        for draft in result.opinions:
            paragraph = paragraph_by_location.get(draft.source_location)
            excerpt = _normalize_whitespace(draft.source_excerpt)
            if paragraph is not None and excerpt in paragraph:
                accepted.append(draft)
        self.last_rejected_count = len(result.opinions) - len(accepted)
        return accepted
