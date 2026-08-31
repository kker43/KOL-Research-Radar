from pathlib import Path

from kol_radar.ingestion.article_parser import parse_wechat_article
from kol_radar.providers.article_url import ArticleURLProvider


def test_parse_wechat_article_extracts_metadata_and_stable_paragraph_locations():
    html = Path("tests/fixtures/article_sample.html").read_text()
    parsed = parse_wechat_article(html, "https://mp.weixin.qq.com/s/test")

    assert parsed.title == "测试文章"
    assert parsed.source_name == "测试公众号"
    assert parsed.paragraphs[0].location == "p1"
    assert parsed.paragraphs[1].location == "p2"
    assert "第一段" in parsed.content


def test_article_url_provider_fetches_and_parses(respx_mock):
    html = Path("tests/fixtures/article_sample.html").read_text()
    respx_mock.get("https://mp.weixin.qq.com/s/test").respond(200, text=html)

    provider = ArticleURLProvider()
    article = provider.fetch_url("https://mp.weixin.qq.com/s/test")

    assert article.source_name == "测试公众号"
    assert article.paragraphs[0].location == "p1"
