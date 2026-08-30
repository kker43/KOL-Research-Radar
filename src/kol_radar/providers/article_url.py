from __future__ import annotations

import httpx

from kol_radar.ingestion.article_parser import parse_wechat_article
from kol_radar.providers.base import (
    ArticleFetchError,
    DiscoveredArticle,
    FetchedArticle,
)


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


class ArticleURLProvider:
    def fetch_url(self, url: str) -> FetchedArticle:
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=20,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as error:
            raise ArticleFetchError(f"Unable to fetch article: {url}") from error
        return parse_wechat_article(response.text, str(response.url))

    def fetch(self, article: DiscoveredArticle) -> FetchedArticle:
        return self.fetch_url(article.url)
