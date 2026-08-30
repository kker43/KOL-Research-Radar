# KOL Research Radar V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V1 local KOL research pipeline from article ingestion through evidence-grounded atomic opinions, SQLite persistence, Obsidian mirroring, local query, incremental digest, and a replaceable WeWe RSS-compatible feed provider.

**Architecture:** Keep one Python application with explicit module boundaries: provider → article → extractor → normalization → storage → query/export. SQLite is the machine source of truth; Obsidian is a one-way human-readable mirror. ArticleURLProvider must make the full product usable without WeWe RSS, while the WeWe adapter consumes its public JSON/RSS feed contract and remains replaceable because the upstream project is archived.

**Tech Stack:** Python 3.12+, `pydantic`, `pydantic-settings`, `typer`, `httpx`, `beautifulsoup4`, `openai`, standard-library `sqlite3`, `pytest`, `respx`.

**Spec:** `docs/PRD_V1.md`

## Global Constraints

- V1 scope is frozen; do not add Web UI, dashboard, vector DB, graph DB, complex RAG, multi-agent orchestration, trading execution, complex scheduler, or Obsidian bidirectional sync.
- Track only user-added Watchlist sources; no global KOL discovery.
- Initial lookback is configurable from 30–90 days and defaults to 60 days.
- Every article yields 0–5 atomic opinions; 0 is valid.
- An opinion may be persisted only when it contains a source excerpt and stable source location.
- `positioning` is allowed only when explicitly expressed by the author; never infer a position from a market view.
- SQLite is the machine source of truth. Obsidian is a one-way mirror and must not mutate unrelated user notes.
- Authentication secrets stay local and must never be written to Git, SQLite, Obsidian, or plaintext logs.
- Provider failures are isolated; one source failure must not fail the entire sync run.
- Article and Obsidian writes must be idempotent.
- The core application must remain usable through ArticleURLProvider even when the feed provider is unavailable.
- Use TDD for every task: failing test → minimal implementation → passing test → commit.

---

## Locked File Structure

```text
KOL-Research-Radar/
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
├── src/kol_radar/
│   ├── __init__.py
│   ├── config.py
│   ├── cli.py
│   ├── domain.py
│   ├── logging_config.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── article_url.py
│   │   └── wewe_feed.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── article_parser.py
│   │   └── service.py
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── openai_extractor.py
│   │   └── prompts.py
│   ├── normalization/
│   │   ├── __init__.py
│   │   └── subjects.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── schema.py
│   │   └── repository.py
│   ├── opinions/
│   │   ├── __init__.py
│   │   └── changes.py
│   ├── obsidian/
│   │   ├── __init__.py
│   │   └── exporter.py
│   └── query/
│       ├── __init__.py
│       ├── planner.py
│       ├── service.py
│       └── digest.py
├── tests/
│   ├── fixtures/
│   │   ├── article_sample.html
│   │   ├── wewe_feed_sample.json
│   │   └── golden_articles.json
│   ├── badcases/
│   │   └── README.md
│   ├── test_storage.py
│   ├── test_article_url_provider.py
│   ├── test_extraction.py
│   ├── test_ingestion.py
│   ├── test_subjects.py
│   ├── test_changes.py
│   ├── test_obsidian.py
│   ├── test_query.py
│   ├── test_digest.py
│   ├── test_wewe_feed.py
│   └── test_cli_smoke.py
└── KOL-Research/
    └── .gitkeep
```

Keep files focused. Do not introduce repositories, services, factories, base classes, or dependency-injection frameworks beyond the interfaces explicitly listed below.

---

### Task 1: Project foundation, configuration, domain models, and SQLite schema

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/kol_radar/__init__.py`
- Create: `src/kol_radar/config.py`
- Create: `src/kol_radar/domain.py`
- Create: `src/kol_radar/storage/schema.py`
- Create: `src/kol_radar/storage/repository.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Produces: `Settings`, `Topic`, `Stance`, `AuthorType`, `SubjectType`, `Source`, `Author`, `Article`, `Opinion`, `OpinionDraft`, `Repository`.
- Later tasks may assume `Repository(db_path: Path)` initializes schema automatically.

- [ ] **Step 1: Add packaging and dependencies**

Create `pyproject.toml` with Python `>=3.12`, editable package under `src`, CLI entry point `kol = "kol_radar.cli:app"`, and dependencies:

```toml
[project]
name = "kol-research-radar"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2.8,<3",
  "pydantic-settings>=2.4,<3",
  "typer>=0.12,<1",
  "httpx>=0.27,<1",
  "beautifulsoup4>=4.12,<5",
  "openai>=1.40,<3",
]

[project.optional-dependencies]
dev = ["pytest>=8,<9", "respx>=0.21,<1"]

[project.scripts]
kol = "kol_radar.cli:app"

[build-system]
requires = ["setuptools>=72"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

Create `.env.example`:

```env
KOL_DB_PATH=./data/kol_radar.db
INITIAL_LOOKBACK_DAYS=60
OBSIDIAN_VAULT_PATH=
WEWE_RSS_BASE_URL=http://localhost:4000
OPENAI_API_KEY=
OPENAI_MODEL=
LOG_LEVEL=INFO
```

Create `.gitignore` including `.env`, `data/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, and local WeWe/auth files.

- [ ] **Step 2: Write failing storage/domain tests**

Create `tests/test_storage.py` with these assertions:

```python
from datetime import datetime, timezone
from pathlib import Path

from kol_radar.domain import Article, Author, AuthorType, Opinion, Source, Stance, SubjectType, Topic
from kol_radar.storage.repository import Repository


def test_repository_round_trip_and_article_idempotency(tmp_path: Path):
    repo = Repository(tmp_path / "radar.db")
    source = repo.upsert_source(Source(name="Test Source", provider="article_url", external_id="test-source"))
    author = repo.upsert_author(Author(name="Test Author", author_type=AuthorType.person))
    article = Article(
        source_id=source.id,
        author_id=author.id,
        title="AI capex is still rising",
        url="https://mp.weixin.qq.com/s/test",
        published_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        content="AI capex remains strong.",
        content_hash="hash-1",
    )

    first = repo.upsert_article(article)
    second = repo.upsert_article(article)

    assert first.id == second.id
    assert len(repo.list_articles()) == 1

    opinion = repo.insert_opinion(Opinion(
        topic=Topic.trend,
        subject="AI Capex",
        raw_subject="AI capex",
        subject_key="AI_CAPEX",
        subject_type=SubjectType.theme,
        stance=Stance.positive,
        thesis="AI capex remains in an uptrend.",
        rationale=["Cloud demand remains strong."],
        published_at=article.published_at,
        source_article_id=first.id,
        author_id=author.id,
        source_excerpt="AI capex remains strong.",
        source_location="p1",
    ))
    assert opinion.id is not None
    assert repo.list_opinions(subject_key="AI_CAPEX")[0].thesis == "AI capex remains in an uptrend."
```

- [ ] **Step 3: Run the test and verify failure**

Run:

```bash
python -m pip install -e '.[dev]'
pytest tests/test_storage.py -v
```

Expected: FAIL because `kol_radar.domain` and `Repository` do not exist.

- [ ] **Step 4: Implement domain models, settings, and schema minimally**

`domain.py` must define string enums with exactly these values:

```python
class Topic(str, Enum):
    market_view = "market_view"
    opportunity = "opportunity"
    risk = "risk"
    risk_reward = "risk_reward"
    positioning = "positioning"
    trend = "trend"

class Stance(str, Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"
    improving = "improving"
    deteriorating = "deteriorating"
    mixed = "mixed"
    unclear = "unclear"

class AuthorType(str, Enum):
    person = "person"
    organization = "organization"
    unknown = "unknown"

class SubjectType(str, Enum):
    market = "market"
    asset = "asset"
    industry = "industry"
    company = "company"
    theme = "theme"
    other = "other"
```

Use Pydantic models. IDs are `int | None` before persistence. `OpinionDraft` contains the extractor-facing fields (`topic`, `raw_subject`, `thesis`, `stance`, `rationale`, `source_excerpt`, `source_location`) and enforces `1 <= len(source_excerpt)` and max 5 drafts at the response-envelope level later.

`config.py` must define `Settings(BaseSettings)` with:

```python
kol_db_path: Path = Path("./data/kol_radar.db")
initial_lookback_days: int = 60
obsidian_vault_path: Path | None = None
wewe_rss_base_url: str = "http://localhost:4000"
openai_api_key: str | None = None
openai_model: str | None = None
log_level: str = "INFO"
```

Validate `initial_lookback_days` is 30–90.

`schema.py` must create only these tables: `sources`, `authors`, `articles`, `opinions`, `sync_runs`. Use UNIQUE constraints on `sources(provider, external_id)`, `articles(url)`, `articles(content_hash)`, and `opinions(source_article_id, topic, subject_key, thesis)`.

`Repository` must use parameterized `sqlite3` statements and expose:

```python
upsert_source(source: Source) -> Source
upsert_author(author: Author) -> Author
upsert_article(article: Article) -> Article
insert_opinion(opinion: Opinion) -> Opinion
list_articles() -> list[Article]
list_opinions(*, topic: Topic | None = None, subject_key: str | None = None,
              author_id: int | None = None, since: datetime | None = None) -> list[Opinion]
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
pytest tests/test_storage.py -v
```

Expected: PASS.

Commit:

```bash
git add pyproject.toml .env.example .gitignore src/kol_radar tests/test_storage.py
git commit -m "feat: add domain models and sqlite storage"
```

---

### Task 2: ArticleURLProvider and deterministic WeChat article parsing

**Files:**
- Create: `src/kol_radar/providers/base.py`
- Create: `src/kol_radar/providers/article_url.py`
- Create: `src/kol_radar/ingestion/article_parser.py`
- Create: `tests/fixtures/article_sample.html`
- Create: `tests/test_article_url_provider.py`

**Interfaces:**
- Produces: `DiscoveredArticle`, `FetchedArticle`, `SourceProvider`, `ArticleURLProvider.fetch_url(url: str) -> FetchedArticle`.
- Consumes: domain enums/models from Task 1.

- [ ] **Step 1: Write a realistic fixture and failing parser test**

`tests/fixtures/article_sample.html` must include `#activity-name`, `#js_name`, `#publish_time`, `#js_content`, and two `<p>` elements.

Create test:

```python
from pathlib import Path
from kol_radar.ingestion.article_parser import parse_wechat_article


def test_parse_wechat_article_extracts_metadata_and_stable_paragraph_locations():
    html = Path("tests/fixtures/article_sample.html").read_text()
    parsed = parse_wechat_article(html, "https://mp.weixin.qq.com/s/test")

    assert parsed.title == "测试文章"
    assert parsed.source_name == "测试公众号"
    assert parsed.paragraphs[0].location == "p1"
    assert parsed.paragraphs[1].location == "p2"
    assert "第一段" in parsed.content
```

- [ ] **Step 2: Run parser test and verify failure**

```bash
pytest tests/test_article_url_provider.py -v
```

Expected: FAIL because parser/provider do not exist.

- [ ] **Step 3: Implement provider contract and parser**

`providers/base.py`:

```python
@dataclass(frozen=True)
class DiscoveredArticle:
    external_id: str
    title: str
    url: str
    published_at: datetime | None
    author_name: str | None = None

@dataclass(frozen=True)
class FetchedArticle:
    title: str
    url: str
    source_name: str
    author_name: str | None
    published_at: datetime | None
    content: str
    paragraphs: list[Paragraph]

class SourceProvider(Protocol):
    def discover(self, source_external_id: str, since: datetime | None) -> list[DiscoveredArticle]: ...
    def fetch(self, article: DiscoveredArticle) -> FetchedArticle: ...
```

`article_parser.py` must normalize whitespace, retain paragraph order, and assign `p1`, `p2`, ... locations. Do not use OCR or browser automation.

`ArticleURLProvider.fetch_url` uses `httpx.Client(follow_redirects=True, timeout=20)` with a normal desktop User-Agent and parses returned HTML. Raise a typed `ArticleFetchError` for non-2xx or missing article content.

- [ ] **Step 4: Add HTTP mock test**

```python
def test_article_url_provider_fetches_and_parses(respx_mock):
    html = Path("tests/fixtures/article_sample.html").read_text()
    respx_mock.get("https://mp.weixin.qq.com/s/test").respond(200, text=html)
    provider = ArticleURLProvider()
    article = provider.fetch_url("https://mp.weixin.qq.com/s/test")
    assert article.source_name == "测试公众号"
    assert article.paragraphs[0].location == "p1"
```

Run:

```bash
pytest tests/test_article_url_provider.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kol_radar/providers src/kol_radar/ingestion/article_parser.py tests/fixtures/article_sample.html tests/test_article_url_provider.py
git commit -m "feat: add wechat article url ingestion"
```

---

### Task 3: Evidence-grounded OpinionExtractor with structured output

**Files:**
- Create: `src/kol_radar/extraction/base.py`
- Create: `src/kol_radar/extraction/prompts.py`
- Create: `src/kol_radar/extraction/openai_extractor.py`
- Create: `tests/test_extraction.py`
- Create: `tests/fixtures/golden_articles.json`

**Interfaces:**
- Produces: `OpinionExtractor.extract(article: FetchedArticle) -> list[OpinionDraft]` and `OpenAIOpinionExtractor`.
- Consumes: `FetchedArticle`, `OpinionDraft`, Topic/Stance enums.

- [ ] **Step 1: Write failing schema-guard tests**

```python
import pytest
from pydantic import ValidationError
from kol_radar.domain import OpinionDraft, Topic, Stance


def test_opinion_draft_requires_evidence():
    with pytest.raises(ValidationError):
        OpinionDraft(
            topic=Topic.risk,
            raw_subject="AI high valuation stocks",
            stance=Stance.deteriorating,
            thesis="Risk is rising.",
            rationale=["Crowding is rising."],
            source_excerpt="",
            source_location="p3",
        )


def test_positioning_requires_explicit_evidence_marker():
    draft = OpinionDraft(
        topic=Topic.positioning,
        raw_subject="US equities",
        stance=Stance.negative,
        thesis="Reduce equity exposure.",
        rationale=["Valuations are stretched."],
        source_excerpt="我会降低股票仓位。",
        source_location="p2",
    )
    assert "仓位" in draft.source_excerpt
```

The second test does not attempt linguistic proof in Pydantic; it fixes the expected evidence semantics used by the prompt and later Eval.

- [ ] **Step 2: Implement extractor protocol and prompt contract**

`base.py`:

```python
class OpinionExtractor(Protocol):
    def extract(self, article: FetchedArticle) -> list[OpinionDraft]: ...
```

`prompts.py` must include these explicit instructions:

```text
Return 0 to 5 atomic opinions.
Do not summarize the whole article as one opinion.
Only extract claims the author clearly expresses.
Every opinion must include an exact supporting excerpt and paragraph location from the supplied numbered paragraphs.
If no explicit investment judgment exists, return an empty list.
For topic=positioning, the source excerpt itself must explicitly mention position size, exposure, allocation, offense/defense, reducing/increasing risk, or equivalent wording. Never infer positioning from a bullish/bearish market view.
Do not invent confidence, horizon, catalyst, or risk fields.
```

Send the article to the model as numbered paragraphs (`[p1] ...`).

- [ ] **Step 3: Implement OpenAI structured-output adapter**

Use one wrapper class only. It accepts an injected OpenAI client for tests:

```python
class OpenAIOpinionExtractor:
    def __init__(self, client, model: str): ...
    def extract(self, article: FetchedArticle) -> list[OpinionDraft]: ...
```

Define a Pydantic envelope:

```python
class OpinionExtractionResult(BaseModel):
    opinions: list[OpinionDraft] = Field(max_length=5)
```

Use OpenAI Structured Outputs / Pydantic parsing. Do not parse arbitrary JSON with regex. After parsing, verify every `source_location` exists in the article and every `source_excerpt` is a substring of the referenced paragraph after whitespace normalization. Reject invalid drafts rather than repairing evidence silently.

- [ ] **Step 4: Test post-validation without a live API**

Create a fake client response containing one valid opinion and one opinion whose excerpt is not in `p2`. Assert only the valid opinion is returned and an `opinions_rejected` count can be logged by callers.

Run:

```bash
pytest tests/test_extraction.py -v
```

Expected: PASS.

- [ ] **Step 5: Add minimal golden fixture and commit**

`golden_articles.json` contains at least 3 short fixture articles: one with a clear risk opinion, one with explicit positioning, one with no investable opinion. Store expected topic/subject/thesis intent and evidence paragraph.

Commit:

```bash
git add src/kol_radar/extraction tests/test_extraction.py tests/fixtures/golden_articles.json
git commit -m "feat: add evidence grounded opinion extraction"
```

---

### Task 4: Subject normalization and end-to-end Article → Opinion → SQLite ingestion

**Files:**
- Create: `src/kol_radar/normalization/subjects.py`
- Create: `src/kol_radar/ingestion/service.py`
- Create: `tests/test_subjects.py`
- Create: `tests/test_ingestion.py`

**Interfaces:**
- Produces: `normalize_subject(raw: str) -> NormalizedSubject`, `IngestionService.ingest_fetched(article: FetchedArticle, provider_name: str, external_source_id: str | None = None) -> IngestionResult`.
- Consumes: Repository, OpinionExtractor.

- [ ] **Step 1: Write failing normalization tests**

```python
from kol_radar.normalization.subjects import normalize_subject


def test_nvda_aliases_normalize_to_same_key():
    assert normalize_subject("英伟达").key == "NVDA"
    assert normalize_subject("NVIDIA").key == "NVDA"
    assert normalize_subject("NVDA").key == "NVDA"


def test_unknown_subject_gets_stable_key():
    result = normalize_subject("某新主题")
    assert result.display_name == "某新主题"
    assert result.key
```

V1 alias map must stay deliberately small: NVDA/NVIDIA/英伟达, HBM, DRAM, AI Capex, US equities/美股, Nasdaq/纳斯达克, 10Y UST/美债10年. Unknown subjects use a normalized uppercase slug/hash-safe key and type `other`.

- [ ] **Step 2: Write failing ingestion idempotency test**

Use a `FakeExtractor` returning one valid `OpinionDraft`.

```python
def test_ingest_same_article_twice_does_not_duplicate(tmp_path, fetched_article, fake_extractor):
    repo = Repository(tmp_path / "radar.db")
    service = IngestionService(repo, fake_extractor)
    first = service.ingest_fetched(fetched_article, provider_name="article_url")
    second = service.ingest_fetched(fetched_article, provider_name="article_url")
    assert first.article_id == second.article_id
    assert second.skipped_existing is True
    assert len(repo.list_opinions()) == 1
```

- [ ] **Step 3: Implement normalization and ingestion**

`IngestionService` must:

1. SHA-256 the normalized article content.
2. Upsert Source by `(provider, external_id)`; for URL ingestion use a deterministic source external id based on source name.
3. Upsert Author. If author missing, use the Source name with `AuthorType.organization`.
4. Upsert Article.
5. If the Article already has `processed_at`, return `skipped_existing=True` and do not call the extractor.
6. Extract 0–5 OpinionDrafts.
7. Normalize each subject.
8. Convert drafts to persisted Opinion records including trace fields.
9. Mark Article `processed_at` only after extraction completes successfully, including valid zero-opinion extraction.

Add repository methods needed for `get_article_by_url`, `article_has_opinions`, and `mark_article_processed`.

- [ ] **Step 4: Run focused tests**

```bash
pytest tests/test_subjects.py tests/test_ingestion.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kol_radar/normalization src/kol_radar/ingestion/service.py tests/test_subjects.py tests/test_ingestion.py
git commit -m "feat: add idempotent opinion ingestion pipeline"
```

---

### Task 5: Discrete opinion change detection

**Files:**
- Create: `src/kol_radar/opinions/changes.py`
- Create: `tests/test_changes.py`

**Interfaces:**
- Produces: `ChangeType`, `OpinionChange`, `detect_change(previous: Opinion | None, current: Opinion) -> OpinionChange`.
- Consumes: Opinion.

- [ ] **Step 1: Write failing change tests**

```python
from kol_radar.opinions.changes import ChangeType, detect_change


def test_first_opinion_is_new(opinion):
    assert detect_change(None, opinion).change_type == ChangeType.new


def test_positive_to_negative_is_reversal(make_opinion):
    prev = make_opinion(stance="positive", thesis="需求继续向上")
    curr = make_opinion(stance="negative", thesis="需求已经转弱")
    assert detect_change(prev, curr).change_type == ChangeType.reversal


def test_risk_neutral_to_deteriorating_is_strengthening(make_opinion):
    prev = make_opinion(topic="risk", stance="neutral")
    curr = make_opinion(topic="risk", stance="deteriorating")
    assert detect_change(prev, curr).change_type == ChangeType.strengthening
```

- [ ] **Step 2: Implement explicit stance transition rules**

`ChangeType` values are exactly:

```text
new
strengthening
weakening
reversal
unchanged
unclear
```

Only compare opinions with identical `author_id + subject_key + topic`; otherwise return `unclear` if called directly.

Use explicit transition maps, not an arbitrary 0–100 score. Treat direct positive↔negative as reversal. For `risk`, moving neutral→deteriorating or improving→deteriorating is strengthening; the inverse is weakening. For `opportunity`/`trend`, neutral→improving/positive is strengthening and positive→neutral/deteriorating is weakening. Identical stance plus highly similar normalized thesis text is unchanged; otherwise return unclear rather than inventing a direction.

- [ ] **Step 3: Add repository history lookup**

Expose:

```python
get_previous_opinion(author_id: int, subject_key: str, topic: Topic, before: datetime) -> Opinion | None
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_changes.py tests/test_storage.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kol_radar/opinions tests/test_changes.py src/kol_radar/storage/repository.py
git commit -m "feat: add discrete opinion change detection"
```

---

### Task 6: Obsidian one-way idempotent mirror

**Files:**
- Create: `src/kol_radar/obsidian/exporter.py`
- Create: `KOL-Research/.gitkeep`
- Create: `tests/test_obsidian.py`

**Interfaces:**
- Produces: `ObsidianExporter(root: Path).export_article(article, source, author, opinions) -> Path`.

- [ ] **Step 1: Write failing exporter test**

```python
def test_export_article_is_idempotent_and_scoped(tmp_path, article, source, author, opinions):
    root = tmp_path / "vault" / "KOL-Research"
    exporter = ObsidianExporter(root)
    first = exporter.export_article(article, source, author, opinions)
    original = first.read_text()
    second = exporter.export_article(article, source, author, opinions)
    assert first == second
    assert second.read_text() == original
    assert str(second).startswith(str(root))
    assert "article_id:" in original
    assert "## Opinions" in original
```

- [ ] **Step 2: Implement safe path rules**

All generated notes must live under `<root>/Articles/<sanitized-source>/`. Filename format:

```text
YYYY-MM-DD-<sanitized-title>-<article_id>.md
```

Use YAML front matter with `article_id`, `source`, `author`, `published_at`, and `url`. Include Opinion sections and cleaned Source content. Do not overwrite files outside the generated path. If the target exists and `article_id` matches, replace only that generated file atomically via temporary file + rename.

- [ ] **Step 3: Add default development root behavior**

When `OBSIDIAN_VAULT_PATH` is unset, CLI exports to repository-local `./KOL-Research`. When set, append `KOL-Research` to the configured vault path unless the configured path itself ends in `KOL-Research`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_obsidian.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kol_radar/obsidian KOL-Research/.gitkeep tests/test_obsidian.py
git commit -m "feat: add obsidian knowledge mirror"
```

---

### Task 7: Local query planner and deterministic query service

**Files:**
- Create: `src/kol_radar/query/planner.py`
- Create: `src/kol_radar/query/service.py`
- Create: `tests/test_query.py`

**Interfaces:**
- Produces: `QueryKind`, `QueryPlan`, `QueryPlanner.plan(text: str) -> QueryPlan`, `QueryService.execute(plan: QueryPlan) -> QueryResult`.
- Consumes: Repository and change detector.

- [ ] **Step 1: Define the only V1 query kinds**

```python
class QueryKind(str, Enum):
    recent_by_topic = "recent_by_topic"
    author_subject_history = "author_subject_history"
    subject_change = "subject_change"
    cross_kol_compare = "cross_kol_compare"
```

`QueryPlan` fields:

```python
kind: QueryKind
topic: Topic | None = None
subject: str | None = None
author_name: str | None = None
since_days: int = 30
```

- [ ] **Step 2: Write failing planner tests with a fake structured-output client**

Test these four inputs:

```text
最近30天最大的风险是什么
最近谁开始看多存储
过去两个月某KOL怎么看美股
多个KOL对AI Capex有什么分歧
```

The fake returns exact QueryPlan objects. The planner itself must be a thin LLM adapter using structured output; it must not execute SQL.

- [ ] **Step 3: Implement deterministic query execution**

`QueryService` may only query local SQLite. It must never call a SourceProvider.

Rules:

- `recent_by_topic`: return chronologically descending opinions filtered by topic and time.
- `author_subject_history`: resolve author by case-insensitive name and subject through `normalize_subject`, then return history.
- `subject_change`: group by author for normalized subject and compute the latest change against each author's previous same-topic opinion.
- `cross_kol_compare`: group latest opinions per author for subject, show stance/thesis, and label `consensus` only when all non-unclear stances are same; otherwise `divergence`.

Render a compact text result from records; do not add another free-form LLM synthesis call in V1.

- [ ] **Step 4: Run query tests**

```bash
pytest tests/test_query.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kol_radar/query/planner.py src/kol_radar/query/service.py tests/test_query.py
git commit -m "feat: add local opinion query service"
```

---

### Task 8: Incremental daily digest

**Files:**
- Create: `src/kol_radar/query/digest.py`
- Create: `tests/test_digest.py`

**Interfaces:**
- Produces: `DigestService.generate(since: datetime) -> DigestResult`.

- [ ] **Step 1: Write failing digest test**

Seed opinions before and after a cutoff. Assert the digest contains only post-cutoff records and the sections below only when non-empty:

```text
New Important Opinions
Opinion Changes
Opportunities
Risks
Positioning
Consensus / Divergence
```

No empty filler sections.

- [ ] **Step 2: Implement incremental selection**

Digest must query opinions by `published_at >= since` and may inspect one previous opinion per current record only for change detection. It must never rescan/re-extract article content.

V1 importance rule is deliberately simple: include all valid new atomic opinions, deduplicate identical `(author_id, subject_key, topic, thesis)` records, and sort newest first. Do not invent a numeric importance score.

- [ ] **Step 3: Implement consensus/divergence only when there are 2+ authors**

Group new opinions by `subject_key + topic`. Emit consensus/divergence only for groups with at least two distinct authors.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_digest.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/kol_radar/query/digest.py tests/test_digest.py
git commit -m "feat: add incremental daily digest"
```

---

### Task 9: Replaceable WeWe RSS-compatible feed provider and watchlist sync

**Files:**
- Create: `src/kol_radar/providers/wewe_feed.py`
- Create: `tests/fixtures/wewe_feed_sample.json`
- Create: `tests/test_wewe_feed.py`
- Modify: `src/kol_radar/ingestion/service.py`
- Modify: `src/kol_radar/storage/repository.py`

**Interfaces:**
- Produces: `WeWeFeedProvider(base_url: str)`, `SyncService.sync_source(source_id: int, lookback_days: int) -> SyncResult`.
- Consumes: WeWe feed endpoints only; never import or embed upstream WeWe source code.

**Provider risk note:** The upstream `cooderl/wewe-rss` repository was archived in May 2026 and historically enforced account/IP request limits. Therefore this adapter is non-core and must remain replaceable. Do not build WeWe deployment/auth internals into KOL Research Radar.

- [ ] **Step 1: Lock the feed contract in a fixture**

Use the public feed surface documented by WeWe: `/feeds/<feed-id>.json?limit=<n>`. Create a representative JSON Feed fixture containing `title`, `home_page_url`, and `items` with `id`, `url`, `title`, `date_published`, and HTML/text content.

Do not assume undocumented admin APIs for adding a subscription. V1 watchlist stores a known WeWe `feed_id`; initial WeWe subscription itself can be created through the WeWe UI using a shared article link.

- [ ] **Step 2: Write failing provider tests**

```python
def test_wewe_provider_discovers_articles_since_cutoff(respx_mock):
    respx_mock.get("http://localhost:4000/feeds/MP_TEST.json?limit=100").respond(
        200, json=json.loads(Path("tests/fixtures/wewe_feed_sample.json").read_text())
    )
    provider = WeWeFeedProvider("http://localhost:4000")
    found = provider.discover("MP_TEST", since=datetime(2026, 8, 1, tzinfo=timezone.utc))
    assert found
    assert all(a.published_at >= datetime(2026, 8, 1, tzinfo=timezone.utc) for a in found)
```

- [ ] **Step 3: Implement feed adapter**

`discover` requests `limit=100`, converts items to `DiscoveredArticle`, filters locally by `since`, and raises `ProviderUnavailable` on network/invalid-feed failures. `fetch` may use fulltext content from the item if available; otherwise delegate to ArticleURLProvider for the item's original URL.

Do not use `update=true` automatically in V1; let the WeWe service's own scheduler update feeds. This avoids consuming extra upstream calls and keeps KOL Radar read-only toward WeWe.

- [ ] **Step 4: Implement isolated source sync**

`SyncService.sync_source`:

1. Reads source by ID.
2. Uses `last_synced_at` if present; otherwise `now - lookback_days`.
3. Discovers articles.
4. For each item, skip known URLs; otherwise fetch + ingest.
5. Continue after individual article failures.
6. Update source `last_synced_at` only after discovery completes.
7. Record one `sync_runs` row with counts: discovered/new/skipped/failed/opinions.

Add `sync_all()` that loops sources and isolates `ProviderUnavailable` per source.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/test_wewe_feed.py tests/test_ingestion.py -v
```

Expected: PASS.

Commit:

```bash
git add src/kol_radar/providers/wewe_feed.py src/kol_radar/ingestion/service.py src/kol_radar/storage/repository.py tests/fixtures/wewe_feed_sample.json tests/test_wewe_feed.py
git commit -m "feat: add replaceable feed sync provider"
```

---

### Task 10: CLI, golden eval, badcases, README setup, and V1 acceptance

**Files:**
- Create: `src/kol_radar/cli.py`
- Create: `src/kol_radar/logging_config.py`
- Create: `tests/test_cli_smoke.py`
- Create: `tests/badcases/README.md`
- Modify: `README.md`

**Interfaces:**
- Produces user commands: `kol watchlist list`, `kol watchlist add`, `kol ingest-url`, `kol sync`, `kol query`, `kol digest`, `kol eval`.

- [ ] **Step 1: Write CLI smoke tests**

Using Typer `CliRunner`, test:

```text
kol --help
kol watchlist list
kol ingest-url --help
kol sync --help
kol query --help
kol digest --help
kol eval --help
```

All must exit 0 without requiring network access.

- [ ] **Step 2: Implement CLI with explicit dependency construction**

Commands:

```text
kol watchlist add --name <name> --provider wewe --external-id <feed_id>
kol watchlist add --url <mp.weixin.qq.com URL>
kol watchlist list
kol ingest-url <url>
kol sync [--source-id N]
kol query "<natural language>"
kol digest [--since-hours 24]
kol eval
```

Rules:

- `watchlist add --url` ingests the supplied article, then creates/updates its source entry; it does not promise automatic WeWe discovery unless a WeWe `external-id` is configured later.
- `ingest-url` must work independently of WeWe.
- `query` must use local DB only.
- `sync` must print per-source summary and continue after failures.
- `digest` defaults to 24 hours.
- Logging must redact values associated with `api_key`, `authorization`, `cookie`, `token`, and `auth_code` keys.

- [ ] **Step 3: Implement `kol eval` against golden fixtures**

For deterministic CI, `kol eval` supports `--fixture` and runs a `GoldenFixtureExtractor` that returns fixture-declared drafts. This validates the full persistence/evidence/eval harness without network.

When `OPENAI_API_KEY` and `OPENAI_MODEL` are present, `kol eval --live` runs the same golden articles through `OpenAIOpinionExtractor` and prints:

```text
articles_total
opinions_expected
opinions_extracted
topic_accuracy
subject_accuracy
evidence_validity
hallucination_count
```

Evaluation definitions:

- `topic_accuracy`: matched expected topic / expected opinions.
- `subject_accuracy`: normalized subject key matched / expected opinions.
- `evidence_validity`: accepted opinions with excerpt actually present at location / accepted opinions.
- `hallucination_count`: accepted opinions that cannot be matched to any expected opinion for that article by topic + subject key.

Do not add embeddings or semantic-scoring infrastructure in V1.

- [ ] **Step 4: Document badcase format and real setup**

`tests/badcases/README.md` template:

```markdown
# Badcase: <short name>

## Article excerpt
...

## Wrong output
...

## Expected output
...

## Failure class
hallucination | wrong_topic | wrong_subject | bad_evidence | over_split | positioning_inference

## Fix
Prompt | schema | rule change, with regression test reference.
```

Update root README with:

1. Python setup and `pip install -e '.[dev]'`.
2. `.env` variables.
3. ArticleURLProvider quick start.
4. Self-hosted WeWe prerequisite and explicit note that WeWe is an external/replaceable dependency; use its UI to add公众号 via shared article link and copy/configure feed ID.
5. `OBSIDIAN_VAULT_PATH` behavior.
6. All CLI examples.
7. Security rules.
8. Current known limitations.

- [ ] **Step 5: Run the complete acceptance suite**

Run:

```bash
pytest -q
kol --help
kol eval --fixture
```

Expected:

- All tests PASS.
- Golden fixture eval has `evidence_validity = 1.0` and `hallucination_count = 0`.

Then execute one fixture-backed end-to-end demo in a temporary DB:

```bash
KOL_DB_PATH=./data/demo.db kol ingest-url --fixture tests/fixtures/article_sample.html
KOL_DB_PATH=./data/demo.db kol query --fixture "最近30天最大的风险是什么"
KOL_DB_PATH=./data/demo.db kol digest --since-hours 24
```

If the CLI implementation chooses a different explicit fixture flag shape, keep it documented and equivalent; do not silently hit the network during acceptance.

Verify manually or with a smoke assertion:

```text
1 Article exists in SQLite
>=1 evidence-backed Opinion exists for the opinion-bearing fixture
KOL-Research/ contains exactly one Markdown article note after two identical ingestion runs
Query prints local opinion data
Digest prints only incremental data
```

If OpenAI credentials are configured, additionally run:

```bash
kol eval --live
```

Record the live metrics in the implementation completion note; do not fail offline CI solely because secrets are absent.

- [ ] **Step 6: Final regression and scope check**

Run:

```bash
pytest -q
git status --short
git diff --stat HEAD~10..HEAD 2>/dev/null || git diff --stat
```

Confirm no V1 non-goal was introduced and no secret/config data is tracked.

- [ ] **Step 7: Commit**

```bash
git add src/kol_radar/cli.py src/kol_radar/logging_config.py tests/test_cli_smoke.py tests/badcases/README.md README.md
git commit -m "feat: complete KOL Research Radar v1"
```

---

# Cross-Task Acceptance Matrix

| PRD Requirement | Implementation Task |
|---|---|
| Watchlist only, no global discovery | 9, 10 |
| 30–90 day lookback, default 60 | 1, 9 |
| ArticleURL fallback | 2, 4, 10 |
| Replaceable WeWe feed provider | 2, 9 |
| Source / Author / Article / Opinion | 1 |
| 0–5 Atomic Opinions | 3 |
| Evidence required | 3, 4 |
| Positioning explicit only | 3 |
| Subject normalization | 4 |
| Idempotency | 1, 4, 6, 9 |
| Discrete change detection | 5 |
| SQLite source of truth | 1 |
| Obsidian one-way mirror | 6 |
| Local query | 7, 10 |
| Incremental digest | 8, 10 |
| Failure isolation | 2, 9 |
| Secret-safe logging | 10 |
| Golden eval + badcases | 3, 10 |
| No complex scheduler | 10 documents external scheduling only |

# Final Exit Criteria

The implementation is complete only when all of the following evidence is present in the final Codex report:

1. `git diff --stat` or commit/file-change summary.
2. `pytest -q` passing output.
3. One end-to-end ArticleURL/fixture ingestion.
4. SQLite row evidence for the Article.
5. At least one persisted Opinion with valid `source_excerpt + source_location`.
6. Generated Obsidian Markdown path and proof that rerun did not duplicate it.
7. One local query result.
8. One 24-hour incremental digest result.
9. Idempotent rerun test result.
10. Golden fixture Eval metrics.
11. Live Eval metrics if credentials were available; otherwise state clearly that live LLM eval was not run.
12. Known limitations, especially WeWe upstream archival/rate-limit risk.

Do not declare V1 complete merely because files were generated.
