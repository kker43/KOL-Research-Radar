from datetime import datetime, timezone

from kol_radar.domain import Opinion, Stance, SubjectType, Topic
from kol_radar.opinions.changes import ChangeType, detect_change


def make_opinion(
    *,
    stance: Stance = Stance.positive,
    thesis: str = "需求继续向上",
    topic: Topic = Topic.trend,
    author_id: int = 1,
    subject_key: str = "AI_CAPEX",
) -> Opinion:
    return Opinion(
        topic=topic,
        subject="AI Capex",
        raw_subject="AI Capex",
        subject_key=subject_key,
        subject_type=SubjectType.theme,
        stance=stance,
        thesis=thesis,
        rationale=[],
        published_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        source_article_id=1,
        author_id=author_id,
        source_excerpt="AI Capex 需求继续向上。",
        source_location="p1",
    )


def test_first_opinion_is_new():
    assert detect_change(None, make_opinion()).change_type == ChangeType.new


def test_positive_to_negative_is_reversal():
    previous = make_opinion(stance=Stance.positive, thesis="需求继续向上")
    current = make_opinion(stance=Stance.negative, thesis="需求已经转弱")

    assert detect_change(previous, current).change_type == ChangeType.reversal


def test_risk_neutral_to_deteriorating_is_strengthening():
    previous = make_opinion(topic=Topic.risk, stance=Stance.neutral)
    current = make_opinion(topic=Topic.risk, stance=Stance.deteriorating)

    assert detect_change(previous, current).change_type == ChangeType.strengthening


def test_risk_deteriorating_to_negative_is_strengthening():
    previous = make_opinion(topic=Topic.risk, stance=Stance.deteriorating)
    current = make_opinion(topic=Topic.risk, stance=Stance.negative)

    assert detect_change(previous, current).change_type == ChangeType.strengthening


def test_risk_negative_to_deteriorating_is_weakening():
    previous = make_opinion(topic=Topic.risk, stance=Stance.negative)
    current = make_opinion(topic=Topic.risk, stance=Stance.deteriorating)

    assert detect_change(previous, current).change_type == ChangeType.weakening


def test_different_identity_is_unclear():
    previous = make_opinion(author_id=2)
    current = make_opinion(author_id=1)

    assert detect_change(previous, current).change_type == ChangeType.unclear
