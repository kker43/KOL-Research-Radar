from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from kol_radar.domain import Article, Author, Opinion, Source


def resolve_obsidian_root(
    configured_path: Path | None, *, project_root: Path | None = None
) -> Path:
    if configured_path is None:
        return (project_root or Path.cwd()) / "KOL-Research"
    path = Path(configured_path)
    return path if path.name == "KOL-Research" else path / "KOL-Research"


def _safe_segment(value: str, fallback: str) -> str:
    value = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", value, flags=re.UNICODE)
    value = value.strip("-_")
    return (value or fallback)[:100]


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_article(
    article: Article, source: Source, author: Author, opinions: list[Opinion]
) -> str:
    published_at = article.published_at.isoformat() if article.published_at else ""
    lines = [
        "---",
        f"article_id: {article.id}",
        f"source: {_yaml_string(source.name)}",
        f"author: {_yaml_string(author.name)}",
        f"published_at: {_yaml_string(published_at)}",
        f"url: {_yaml_string(article.url)}",
        "---",
        "",
        f"# {article.title}",
        "",
        "## Opinions",
    ]
    if not opinions:
        lines.extend(["", "No explicit investment opinion extracted."])
    for index, opinion in enumerate(opinions, start=1):
        lines.extend(
            [
                "",
                f"### Opinion {index}",
                "",
                f"Topic: {opinion.topic.value}",
                "",
                f"Subject: {opinion.subject}",
                "",
                f"Stance: {opinion.stance.value}",
                "",
                "Thesis:",
                opinion.thesis,
                "",
                "Rationale:",
            ]
        )
        lines.extend(f"- {item}" for item in opinion.rationale)
    lines.extend(["", "## Source", "", article.content, ""])
    return "\n".join(lines)


class ObsidianExporter:
    def __init__(self, root: Path):
        self.root = Path(root)

    def export_article(
        self,
        article: Article,
        source: Source,
        author: Author,
        opinions: list[Opinion],
    ) -> Path:
        if article.id is None:
            raise ValueError("Article must be persisted before export")

        root = self.root.resolve()
        source_directory = root / "Articles" / _safe_segment(source.name, "source")
        source_directory.mkdir(parents=True, exist_ok=True)
        date_prefix = article.published_at.date().isoformat() if article.published_at else "undated"
        filename = (
            f"{date_prefix}-{_safe_segment(article.title, 'article')}-{article.id}.md"
        )
        target = (source_directory / filename).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Generated Obsidian path escapes the configured root")

        if target.exists():
            existing = target.read_text(encoding="utf-8")
            marker = rf"^article_id:\s*{article.id}\s*$"
            if re.search(marker, existing, flags=re.MULTILINE) is None:
                raise ValueError("Refusing to overwrite a note not owned by KOL Radar")

        content = _render_article(article, source, author, opinions)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            temporary_path.replace(target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return target
