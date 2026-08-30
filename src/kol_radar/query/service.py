from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from kol_radar.domain import Opinion
from kol_radar.normalization.subjects import normalize_subject
from kol_radar.opinions.changes import detect_change
from kol_radar.query.planner import QueryKind, QueryPlan
from kol_radar.storage.repository import Repository


@dataclass(frozen=True)
class QueryResult:
    kind: QueryKind
    records: list[dict[str, object]]
    text: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class QueryService:
    def __init__(
        self, repository: Repository, *, clock: Callable[[], datetime] = _utc_now
    ):
        self.repository = repository
        self.clock = clock

    def execute(self, plan: QueryPlan) -> QueryResult:
        since = self.clock() - timedelta(days=plan.since_days)
        if plan.kind == QueryKind.recent_by_topic:
            opinions = self.repository.list_opinions(topic=plan.topic, since=since)
            return self._opinion_result(plan.kind, opinions)
        if plan.kind == QueryKind.author_subject_history:
            return self._author_subject_history(plan, since)
        if plan.kind == QueryKind.subject_change:
            return self._subject_changes(plan, since)
        return self._cross_kol_compare(plan, since)

    def _author_subject_history(
        self, plan: QueryPlan, since: datetime
    ) -> QueryResult:
        if not plan.author_name or not plan.subject:
            return QueryResult(plan.kind, [], "No matching local opinions.")
        author = self.repository.find_author_by_name(plan.author_name)
        if author is None or author.id is None:
            return QueryResult(plan.kind, [], "No matching local opinions.")
        subject_key = normalize_subject(plan.subject).key
        opinions = self.repository.list_opinions(
            author_id=author.id, subject_key=subject_key, since=since
        )
        return self._opinion_result(plan.kind, opinions)

    def _subject_changes(self, plan: QueryPlan, since: datetime) -> QueryResult:
        if not plan.subject:
            return QueryResult(plan.kind, [], "No matching local opinions.")
        subject_key = normalize_subject(plan.subject).key
        opinions = self.repository.list_opinions(
            topic=plan.topic, subject_key=subject_key, since=since
        )
        latest: dict[tuple[int, object], Opinion] = {}
        for opinion in opinions:
            latest.setdefault((opinion.author_id, opinion.topic), opinion)

        records: list[dict[str, object]] = []
        for opinion in latest.values():
            previous = None
            if opinion.published_at is not None:
                previous = self.repository.get_previous_opinion(
                    opinion.author_id,
                    opinion.subject_key,
                    opinion.topic,
                    opinion.published_at,
                )
            record = self._record(opinion)
            record["change_type"] = detect_change(previous, opinion).change_type.value
            records.append(record)
        return QueryResult(plan.kind, records, self._render(records))

    def _cross_kol_compare(self, plan: QueryPlan, since: datetime) -> QueryResult:
        if not plan.subject:
            return QueryResult(plan.kind, [], "No matching local opinions.")
        subject_key = normalize_subject(plan.subject).key
        opinions = self.repository.list_opinions(subject_key=subject_key, since=since)
        latest: dict[int, Opinion] = {}
        for opinion in opinions:
            latest.setdefault(opinion.author_id, opinion)
        records = [self._record(opinion) for opinion in latest.values()]
        stances = {
            str(record["stance"])
            for record in records
            if record["stance"] != "unclear"
        }
        if len(records) < 2:
            label = "insufficient"
        else:
            label = "consensus" if len(stances) == 1 else "divergence"
        text = f"{label}\n{self._render(records)}" if records else "No matching local opinions."
        return QueryResult(plan.kind, records, text)

    def _opinion_result(
        self, kind: QueryKind, opinions: list[Opinion]
    ) -> QueryResult:
        records = [self._record(opinion) for opinion in opinions]
        return QueryResult(kind, records, self._render(records))

    def _record(self, opinion: Opinion) -> dict[str, object]:
        author = self.repository.get_author(opinion.author_id)
        return {
            "published_at": opinion.published_at,
            "author_id": opinion.author_id,
            "author_name": author.name if author else f"author:{opinion.author_id}",
            "topic": opinion.topic.value,
            "subject": opinion.subject,
            "subject_key": opinion.subject_key,
            "stance": opinion.stance.value,
            "thesis": opinion.thesis,
        }

    @staticmethod
    def _render(records: list[dict[str, object]]) -> str:
        if not records:
            return "No matching local opinions."
        lines = []
        for record in records:
            published_at = record["published_at"]
            date = published_at.date().isoformat() if isinstance(published_at, datetime) else "undated"
            change = (
                f" change={record['change_type']}" if "change_type" in record else ""
            )
            lines.append(
                f"{date} | {record['author_name']} | {record['topic']} | "
                f"{record['subject']} | {record['stance']}{change} | {record['thesis']}"
            )
        return "\n".join(lines)
