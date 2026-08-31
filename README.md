# KOL Research Radar

KOL Research Radar 将用户明确加入 Watchlist 的微信公众号文章转换为带原文证据的 Atomic Opinions，并保存为可查询、可比较、可追踪变化的本地研究资产。

V1 Scope 已冻结。系统只实现这条本地闭环：

```text
Watchlist / Article URL
  → Article
  → 0–5 evidence-grounded Opinions
  → SQLite
  → Obsidian one-way mirror
  → Local Query / Incremental Digest
```

SQLite 是 Machine Source of Truth；Obsidian 是 Human-readable Mirror。V1 不包含 Web UI、Vector DB、Knowledge Graph、复杂 RAG、Multi-Agent、自动交易或复杂 Scheduler。

## Documents

- [`docs/PRD_V1.md`](docs/PRD_V1.md) — V1 唯一需求基线
- [`docs/superpowers/plans/2026-08-30-kol-research-radar-v1.md`](docs/superpowers/plans/2026-08-30-kol-research-radar-v1.md) — Implementation Plan 与验收标准

## Setup

需要 Python 3.12+：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

`.env`：

```env
KOL_DB_PATH=./data/kol_radar.db
INITIAL_LOOKBACK_DAYS=60
OBSIDIAN_VAULT_PATH=
WEWE_RSS_BASE_URL=http://localhost:4000
LLM_BACKEND=codex
OPENAI_API_KEY=
OPENAI_MODEL=
LOG_LEVEL=INFO
```

`INITIAL_LOOKBACK_DAYS` 只允许 30–90，默认 60。不要把 `.env` 或任何 Cookie、Token、API Key、微信认证文件提交到 Git。

### Default Codex backend

V1.1 默认使用本机已登录的 Codex CLI / ChatGPT 订阅完成 Opinion Extraction，不需要 `OPENAI_API_KEY`，也不会读取、复制或保存 Codex 登录凭据。先安装 [Codex CLI](https://developers.openai.com/codex/cli/)，再使用 ChatGPT 账户登录：

```bash
codex login
codex login status
```

`codex login status` 应显示通过 ChatGPT 登录。KOL Radar 会在一次性的空目录中以只读 sandbox 调用 Codex，并只接收符合现有 Opinion Schema 的结构化 JSON；SQLite 与 Obsidian 仍由 Python ingestion pipeline 在证据校验通过后写入。

如需显式改用原有 OpenAI API backend：

```env
LLM_BACKEND=openai
OPENAI_API_KEY=your-local-secret
OPENAI_MODEL=your-model
```

只有 `openai` backend 需要这两个 OpenAI 配置。不要将真实值提交到 Git。

## ArticleURLProvider quick start

默认 Codex backend 下，真实 URL ingestion 使用本机 ChatGPT 登录态，不需要 OpenAI API Key：

```bash
kol ingest-url 'https://mp.weixin.qq.com/s/example'
```

它会执行 Article → Opinion → SQLite → Obsidian。没有明确投资判断时允许生成 0 条 Opinion；缺少 `source_excerpt + source_location` 的 Opinion 会被拒绝。

离线、可复现的 fixture 验收不会访问网络：

```bash
KOL_DB_PATH=./data/demo.db kol ingest-url --fixture tests/fixtures/article_sample.html
```

## Watchlist and WeWe feed

WeWe 是外部、可替换依赖，不属于核心业务层。V1 的自动监控必须先在 WeWe RSS 中添加订阅，并复制已知 `feed_id`；公众号名称不是可用的发现标识：

```bash
kol watchlist add --name '公众号名称' --provider wewe --external-id MP_FEED_ID
kol watchlist list
kol sync
kol sync --source-id 1
```

KOL Radar 只读取公开 feed surface：

```text
/feeds/<feed-id>.json?limit=100&page=<page>
```

它不调用 WeWe admin API，也不自动请求 `update=true`。Provider 会逐页读取到 lookback cutoff；同步水位记录成功观察到的最新文章发布时间，并用 1 天 overlap 接住延迟出现的文章。单个 Source 或 Article 失败不会中止其他 Source；存在 Article 失败时不会推进该 Source 的 `last_synced_at`，以便下次重试。

直接添加文章 URL：

```bash
kol watchlist add --url 'https://mp.weixin.qq.com/s/example'
```

这只完成单篇补录，不承诺自动发现该公众号的新文章；自动增量发现需要后续配置 WeWe `feed_id`。

## Local Query

Query planner 将自然语言转换为四类固定计划，执行阶段只查询本地 SQLite，绝不会因为一次 Query 重新抓取公众号：

```bash
kol query '最近30天最大的风险是什么'
kol query '最近谁开始看多存储'
kol query '过去两个月某KOL怎么看美股'
kol query '多个KOL对AI Capex有什么分歧'
```

自然语言 planner 需要 OpenAI 配置。离线验收可使用确定性 fixture planner：

```bash
KOL_DB_PATH=./data/demo.db kol query --fixture '最近有哪些趋势'
```

## Incremental Digest

Digest 只读取 cutoff 之后的新 Opinion，并为每条当前观点最多查询一个历史观点用于变化检测：

```bash
kol digest --since-hours 24
```

只输出非空 section；只有同一 `Subject + Topic` 至少出现两个 Author 时才输出 Consensus / Divergence。

## Obsidian mirror

未配置 `OBSIDIAN_VAULT_PATH` 时，笔记写入仓库本地 `./KOL-Research`。配置真实 Vault 根目录后，写入 `<vault>/KOL-Research`；如果路径本身已以 `KOL-Research` 结尾，则直接使用。

Exporter 只创建或更新自己带有同一 `article_id` 的生成文件，不修改或删除用户其他笔记。相同 Article 重跑不会新增 Markdown 文件。

## Eval and tests

完整测试与确定性 Fixture Pipeline Acceptance：

```bash
pytest -q
kol eval --fixture
```

使用默认 Codex backend 运行 10 篇 Golden Dataset 的 Live Eval：

```bash
kol eval --live --backend codex
```

该命令使用 ChatGPT 套餐内的 Codex 用量，不产生 OpenAI API 调用；单元测试和 fixture Eval 都不会调用 Codex。若显式选择 API backend，则需要本机配置 `OPENAI_API_KEY` 与 `OPENAI_MODEL`：

```bash
kol eval --live --backend openai
```

`--fixture` 使用已确认的预期 Opinion 验证 Article → SQLite → Evidence 校验链路，不代表模型抽取质量；输出 `evaluation_mode=fixture_pipeline_acceptance`。`--live` 才调用配置的模型并输出 `evaluation_mode=live_model_eval`。两者都报告 `articles_total`、`opinions_expected`、`opinions_extracted`、`topic_accuracy`、`subject_accuracy`、`evidence_validity`、`hallucination_count`。典型错误按 [`tests/badcases/README.md`](tests/badcases/README.md) 记录并附回归测试。

## Security rules

- Secret 只保存在本机环境变量或外部服务配置中。
- Secret 不进入 Git、SQLite、Obsidian 或明文日志。
- 日志对 `api_key`、`authorization`、`cookie`、`token`、`auth_code` 值做脱敏。
- KOL Radar 对 WeWe 保持只读，不管理微信扫码、Cookie 或认证生命周期。

## Known limitations

- WeWe RSS 上游已归档，且历史上存在账号/IP 请求限制；适配器因此保持可替换，服务部署与扫码认证需在 WeWe 外部完成。
- 微信文章 HTML 结构变化可能导致 `ArticleFetchError`，需要更新确定性 parser fixture。
- V1 Subject normalization 只有小型固定别名表，未知 Subject 使用稳定本地 key，不做完整 Entity Resolution。
- Opinion extraction 默认依赖本机已通过 ChatGPT 登录的 Codex CLI；自然语言 Query planner 仍依赖显式配置的 OpenAI API backend。fixture 模式仅用于可复现验收。
- V1 只提供 `kol sync` / `kol digest`，调度交给 cron、launchd 或其他外部 Scheduler。
- 不提供全文语义搜索、自动 KOL 发现、交易建议或交易执行。
