from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

from kol_radar.domain import Opinion, Stance, Topic


class ChangeType(str, Enum):
    new = "new"
    strengthening = "strengthening"
    weakening = "weakening"
    reversal = "reversal"
    unchanged = "unchanged"
    unclear = "unclear"


@dataclass(frozen=True)
class OpinionChange:
    change_type: ChangeType
    previous: Opinion | None
    current: Opinion


_RISK_STRENGTHENING = {
    (Stance.neutral, Stance.deteriorating),
    (Stance.improving, Stance.deteriorating),
}
_RISK_WEAKENING = {(current, previous) for previous, current in _RISK_STRENGTHENING}
_OPPORTUNITY_STRENGTHENING = {
    (Stance.neutral, Stance.improving),
    (Stance.neutral, Stance.positive),
    (Stance.deteriorating, Stance.improving),
    (Stance.deteriorating, Stance.positive),
}
_OPPORTUNITY_WEAKENING = {
    (current, previous) for previous, current in _OPPORTUNITY_STRENGTHENING
}


def _normalized_thesis(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).casefold()


def detect_change(previous: Opinion | None, current: Opinion) -> OpinionChange:
    if previous is None:
        return OpinionChange(ChangeType.new, previous, current)
    if (
        previous.author_id != current.author_id
        or previous.subject_key != current.subject_key
        or previous.topic != current.topic
    ):
        return OpinionChange(ChangeType.unclear, previous, current)

    transition = (previous.stance, current.stance)
    if transition in {
        (Stance.positive, Stance.negative),
        (Stance.negative, Stance.positive),
    }:
        return OpinionChange(ChangeType.reversal, previous, current)
    if current.topic == Topic.risk:
        if transition in _RISK_STRENGTHENING:
            return OpinionChange(ChangeType.strengthening, previous, current)
        if transition in _RISK_WEAKENING:
            return OpinionChange(ChangeType.weakening, previous, current)
    if current.topic in {Topic.opportunity, Topic.trend}:
        if transition in _OPPORTUNITY_STRENGTHENING:
            return OpinionChange(ChangeType.strengthening, previous, current)
        if transition in _OPPORTUNITY_WEAKENING:
            return OpinionChange(ChangeType.weakening, previous, current)

    if previous.stance == current.stance:
        similarity = SequenceMatcher(
            None,
            _normalized_thesis(previous.thesis),
            _normalized_thesis(current.thesis),
        ).ratio()
        if similarity >= 0.85:
            return OpinionChange(ChangeType.unchanged, previous, current)
    return OpinionChange(ChangeType.unclear, previous, current)
