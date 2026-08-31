from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from kol_radar.domain import SubjectType


@dataclass(frozen=True)
class NormalizedSubject:
    display_name: str
    key: str
    subject_type: SubjectType


_ALIASES = {
    "nvda": NormalizedSubject("英伟达", "NVDA", SubjectType.company),
    "nvidia": NormalizedSubject("英伟达", "NVDA", SubjectType.company),
    "英伟达": NormalizedSubject("英伟达", "NVDA", SubjectType.company),
    "hbm": NormalizedSubject("HBM", "HBM", SubjectType.industry),
    "dram": NormalizedSubject("DRAM", "DRAM", SubjectType.industry),
    "ai capex": NormalizedSubject("AI Capex", "AI_CAPEX", SubjectType.theme),
    "美股": NormalizedSubject("美股", "US_EQUITIES", SubjectType.market),
    "us equities": NormalizedSubject("美股", "US_EQUITIES", SubjectType.market),
    "纳斯达克": NormalizedSubject("纳斯达克", "NASDAQ", SubjectType.market),
    "nasdaq": NormalizedSubject("纳斯达克", "NASDAQ", SubjectType.market),
    "10y ust": NormalizedSubject("10Y UST", "10Y_UST", SubjectType.asset),
    "美债10年": NormalizedSubject("10Y UST", "10Y_UST", SubjectType.asset),
}


def normalize_subject(raw: str) -> NormalizedSubject:
    display_name = re.sub(r"\s+", " ", raw).strip()
    alias = _ALIASES.get(display_name.casefold())
    if alias is not None:
        return alias

    ascii_slug = re.sub(r"[^A-Z0-9]+", "_", display_name.upper()).strip("_")
    if not ascii_slug:
        digest = hashlib.sha256(display_name.encode("utf-8")).hexdigest()[:12].upper()
        ascii_slug = f"OTHER_{digest}"
    return NormalizedSubject(display_name, ascii_slug, SubjectType.other)
