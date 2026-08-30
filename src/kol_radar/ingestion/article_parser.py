from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from kol_radar.providers.base import ArticleFetchError, FetchedArticle, Paragraph


def _text(element) -> str:
    if element is None:
        return ""
    return re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()


def _published_at(text: str) -> datetime | None:
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, pattern)
            return parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        except ValueError:
            continue
    return None


def parse_wechat_article(html: str, url: str) -> FetchedArticle:
    soup = BeautifulSoup(html, "html.parser")
    content_element = soup.select_one("#js_content")
    if content_element is None:
        raise ArticleFetchError("WeChat article content is missing")

    paragraph_texts = [
        text
        for element in content_element.find_all("p")
        if (text := _text(element))
    ]
    if not paragraph_texts:
        fallback = _text(content_element)
        if fallback:
            paragraph_texts = [fallback]
    if not paragraph_texts:
        raise ArticleFetchError("WeChat article content is empty")

    paragraphs = [
        Paragraph(location=f"p{index}", text=text)
        for index, text in enumerate(paragraph_texts, start=1)
    ]
    title = _text(soup.select_one("#activity-name"))
    source_name = _text(soup.select_one("#js_name"))
    if not title or not source_name:
        raise ArticleFetchError("WeChat article metadata is incomplete")

    author_name = _text(soup.select_one("#js_author_name")) or None
    return FetchedArticle(
        title=title,
        url=url,
        source_name=source_name,
        author_name=author_name,
        published_at=_published_at(_text(soup.select_one("#publish_time"))),
        content="\n\n".join(paragraph.text for paragraph in paragraphs),
        paragraphs=paragraphs,
    )
