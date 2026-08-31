from __future__ import annotations

import logging

from kol_radar.domain import OpinionDraft
from kol_radar.extraction.base import OpinionExtractionError
from kol_radar.extraction.prompts import SYSTEM_PROMPT, format_article
from kol_radar.extraction.validation import (
    OpinionExtractionResult,
    validate_opinion_evidence,
)
from kol_radar.providers.base import FetchedArticle


logger = logging.getLogger(__name__)


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
            raise OpinionExtractionError("structured opinion extraction returned no parsed result")

        accepted, self.last_rejected_count = validate_opinion_evidence(
            article, result.opinions
        )
        if self.last_rejected_count:
            logger.info("opinions_rejected count=%s", self.last_rejected_count)
        return accepted
