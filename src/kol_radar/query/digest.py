from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kol_radar.domain import Opinion, Topic
from kol_radar.opinions.changes import ChangeType, detect_change
from kol_radar.storage.repository import Repository


@dataclass(frozen=True)
class DigestResult:
    since: datetime
    sections: dict[str, list[str]]
    text: str
    opinions: list[Opinion]


class DigestService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def generate(self, since: datetime) -> DigestResult:
        opinions = self._deduplicated(self.repository.list_opinions(since=since))
        sections: dict[str, list[str]] = {}
        if opinions:
            sections["New Important Opinions"] = [
                self._opinion_line(opinion) for opinion in opinions
            ]

        changes = []
        for opinion in opinions:
            previous = None
            if opinion.published_at is not None:
                previous = self.repository.get_previous_opinion(
                    opinion.author_id,
                    opinion.subject_key,
                    opinion.topic,
                    opinion.published_at,
                )
            change = detect_change(previous, opinion)
            if change.change_type in {
                ChangeType.strengthening,
                ChangeType.weakening,
                ChangeType.reversal,
            }:
                changes.append(
                    f"{change.change_type.value}: {self._opinion_line(opinion)}"
                )
        if changes:
            sections["Opinion Changes"] = changes

        topic_sections = {
            Topic.opportunity: "Opportunities",
            Topic.risk: "Risks",
            Topic.positioning: "Positioning",
        }
        for topic, title in topic_sections.items():
            entries = [
                self._opinion_line(opinion)
                for opinion in opinions
                if opinion.topic == topic
            ]
            if entries:
                sections[title] = entries

        comparisons = self._consensus_or_divergence(opinions)
        if comparisons:
            sections["Consensus / Divergence"] = comparisons

        lines = ["# Daily Incremental Digest", ""]
        for title, entries in sections.items():
            lines.extend([f"## {title}", ""])
            lines.extend(f"- {entry}" for entry in entries)
            lines.append("")
        return DigestResult(since, sections, "\n".join(lines).rstrip(), opinions)

    @staticmethod
    def _deduplicated(opinions: list[Opinion]) -> list[Opinion]:
        seen: set[tuple[int, str, Topic, str]] = set()
        result = []
        for opinion in opinions:
            key = (
                opinion.author_id,
                opinion.subject_key,
                opinion.topic,
                opinion.thesis,
            )
            if key not in seen:
                seen.add(key)
                result.append(opinion)
        return result

    def _opinion_line(self, opinion: Opinion) -> str:
        author = self.repository.get_author(opinion.author_id)
        author_name = author.name if author else f"author:{opinion.author_id}"
        return (
            f"{author_name} | {opinion.topic.value} | {opinion.subject} | "
            f"{opinion.stance.value} | {opinion.thesis}"
        )

    def _consensus_or_divergence(self, opinions: list[Opinion]) -> list[str]:
        groups: dict[tuple[str, Topic], dict[int, Opinion]] = {}
        for opinion in opinions:
            groups.setdefault((opinion.subject_key, opinion.topic), {}).setdefault(
                opinion.author_id, opinion
            )

        results = []
        for (subject_key, topic), by_author in groups.items():
            if len(by_author) < 2:
                continue
            stances = {
                opinion.stance.value
                for opinion in by_author.values()
                if opinion.stance.value != "unclear"
            }
            label = "consensus" if len(stances) == 1 else "divergence"
            details = []
            for opinion in by_author.values():
                author = self.repository.get_author(opinion.author_id)
                name = author.name if author else f"author:{opinion.author_id}"
                details.append(f"{name}={opinion.stance.value}")
            results.append(
                f"{subject_key} / {topic.value}: {label} ({'; '.join(details)})"
            )
        return results
