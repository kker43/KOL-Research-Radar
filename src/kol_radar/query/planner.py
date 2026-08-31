from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from kol_radar.domain import Topic


class QueryKind(str, Enum):
    recent_by_topic = "recent_by_topic"
    author_subject_history = "author_subject_history"
    subject_change = "subject_change"
    cross_kol_compare = "cross_kol_compare"


class QueryPlan(BaseModel):
    kind: QueryKind
    topic: Topic | None = None
    subject: str | None = None
    author_name: str | None = None
    since_days: int = Field(default=30, ge=1)


PLANNER_PROMPT = """Convert the user query into exactly one V1 local query plan.
Allowed kinds: recent_by_topic, author_subject_history, subject_change, cross_kol_compare.
Do not answer the query. Do not request or fetch source articles.
Use since_days=30 unless the user gives a different period.
"""


class QueryPlanner:
    def __init__(self, client, model: str):
        self.client = client
        self.model = model

    def plan(self, text: str) -> QueryPlan:
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": PLANNER_PROMPT},
                {"role": "user", "content": text},
            ],
            text_format=QueryPlan,
        )
        if response.output_parsed is None:
            raise ValueError("Query planner returned no plan")
        return response.output_parsed
