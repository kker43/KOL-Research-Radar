from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from kol_radar.providers.article_url import ArticleURLProvider, USER_AGENT
from kol_radar.providers.base import (
    DiscoveredArticle,
    FetchedArticle,
    Paragraph,
    ProviderUnavailable,
)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class WeWeFeedProvider:
    def __init__(
        self, base_url: str, article_url_provider: ArticleURLProvider | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.article_url_provider = article_url_provider or ArticleURLProvider()
        self._items: dict[str, tuple[dict[str, object], str]] = {}

    def discover(
        self, source_external_id: str, since: datetime | None
    ) -> list[DiscoveredArticle]:
        url = f"{self.base_url}/feeds/{source_external_id}.json"
        try:
            with httpx.Client(
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.get(url, params={"limit": 100})
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderUnavailable("WeWe feed is unavailable") from error

        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProviderUnavailable("WeWe feed payload is invalid")
        feed_title = str(payload.get("title") or source_external_id)
        discovered = []
        for raw_item in payload["items"]:
            if not isinstance(raw_item, dict):
                continue
            item_id = str(raw_item.get("id") or "").strip()
            item_url = str(raw_item.get("url") or "").strip()
            title = str(raw_item.get("title") or "").strip()
            published_at = _parse_datetime(
                str(raw_item.get("date_published") or "")
            )
            if not item_id or not item_url or not title:
                continue
            if since is not None and (published_at is None or published_at < since):
                continue
            author_name = None
            authors = raw_item.get("authors")
            if isinstance(authors, list) and authors and isinstance(authors[0], dict):
                author_name = str(authors[0].get("name") or "").strip() or None
            article = DiscoveredArticle(
                external_id=item_id,
                title=title,
                url=item_url,
                published_at=published_at,
                author_name=author_name,
            )
            self._items[item_id] = (raw_item, feed_title)
            discovered.append(article)
        return discovered

    def fetch(self, article: DiscoveredArticle) -> FetchedArticle:
        cached = self._items.get(article.external_id)
        if cached is None:
            return self.article_url_provider.fetch(article)
        item, feed_title = cached
        paragraph_texts: list[str] = []
        content_html = item.get("content_html")
        if isinstance(content_html, str) and content_html.strip():
            soup = BeautifulSoup(content_html, "html.parser")
            paragraph_texts = [
                text
                for element in soup.find_all("p")
                if (text := _clean_text(element.get_text(" ", strip=True)))
            ]
            if not paragraph_texts:
                text = _clean_text(soup.get_text(" ", strip=True))
                paragraph_texts = [text] if text else []
        content_text = item.get("content_text")
        if not paragraph_texts and isinstance(content_text, str):
            paragraph_texts = [
                text
                for line in content_text.splitlines()
                if (text := _clean_text(line))
            ]
        if not paragraph_texts:
            return self.article_url_provider.fetch(article)
        paragraphs = [
            Paragraph(f"p{index}", text)
            for index, text in enumerate(paragraph_texts, start=1)
        ]
        return FetchedArticle(
            title=article.title,
            url=article.url,
            source_name=feed_title,
            author_name=article.author_name,
            published_at=article.published_at,
            content="\n\n".join(paragraph.text for paragraph in paragraphs),
            paragraphs=paragraphs,
        )
