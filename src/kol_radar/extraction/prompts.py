from kol_radar.providers.base import FetchedArticle


SYSTEM_PROMPT = """You extract evidence-grounded investment opinions.

Return 0 to 5 atomic opinions.
Do not summarize the whole article as one opinion.
Only extract claims the author clearly expresses.
Every opinion must include an exact supporting excerpt and paragraph location from the supplied numbered paragraphs.
If no explicit investment judgment exists, return an empty list.
For topic=positioning, the source excerpt itself must explicitly mention position size, exposure, allocation, offense/defense, reducing/increasing risk, or equivalent wording. Never infer positioning from a bullish/bearish market view.
Do not invent confidence, horizon, catalyst, or risk fields.
"""


def format_article(article: FetchedArticle) -> str:
    paragraphs = "\n".join(
        f"[{paragraph.location}] {paragraph.text}" for paragraph in article.paragraphs
    )
    return f"Title: {article.title}\n\n{paragraphs}"
