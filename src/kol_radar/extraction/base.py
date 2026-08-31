from typing import Protocol

from kol_radar.domain import OpinionDraft
from kol_radar.providers.base import FetchedArticle


class OpinionExtractionError(RuntimeError):
    """The extractor could not produce a validated structured result."""


class OpinionExtractor(Protocol):
    def extract(self, article: FetchedArticle) -> list[OpinionDraft]: ...
