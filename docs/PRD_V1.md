# KOL Research Radar — V1 PRD

**Status:** Scope Frozen  
**Baseline date:** 2026-08-30  
**Purpose:** Codex implementation baseline  

## 1. 产品目标

构建一个面向个人投资研究的 **KOL Research Radar**。

系统持续跟踪用户明确加入 Watchlist 的微信公众号，将公众号文章转化为结构化投资观点，并形成可长期积累、可查询、可比较、可追踪观点变化的本地知识库。

V1 的核心价值不是“总结公众号文章”，而是回答：

- 最近 KOL 怎么看市场？
- 当前主要机会在哪里？
- 当前主要风险在哪里？
- 机会是在增强还是减弱？
- 风险是在扩大还是收敛？
- 市场趋势正在如何变化？
- 哪些 KOL 明确表达了仓位或风险暴露观点？
- 某个 KOL 对同一对象的观点是否发生变化？
- 多个 KOL 对同一个市场问题有哪些共识和分歧？

---

## 2. V1 核心原则

V1 只完成一个最小长期闭环：

```text
Watchlist
    ↓
文章发现
    ↓
首次回溯 + 增量同步
    ↓
正文获取
    ↓
文章结构化
    ↓
Opinion 抽取
    ↓
观点变化检测
    ↓
SQLite
    ↓
Obsidian
    ↓
Query / Daily Digest
```

优先级：

> 能稳定工作 > 功能完整  
> 数据可信 > 字段丰富  
> 简单基础设施 > 复杂架构  
> 可验证 > “看起来智能”

V1 强制控 Scope。任何不是闭环必需的能力进入 V1.1+。

---

## 3. V1 用户流程

### 3.1 添加公众号

用户提供：

- 一个公众号名称；
- 或该公众号任意一篇文章 URL。

系统将该公众号加入 Watchlist。

V1 不负责全网自动寻找新的 KOL。

### 3.2 首次同步

公众号首次加入 Watchlist 后，默认回溯最近 60 天文章。

配置允许 30–90 天，例如：

```env
INITIAL_LOOKBACK_DAYS=60
```

完成首次同步后，以后只拉取新增文章。

### 3.3 日常同步

```text
Watchlist
↓
检查新增文章
↓
跳过已有文章
↓
下载新增正文
↓
抽取 Opinion
↓
写 SQLite
↓
写 Obsidian
↓
生成 Incremental Digest
```

禁止每次查询重新抓取全部公众号。

---

## 4. 内容源设计

### 4.1 Source Provider

文章采集必须通过独立 Provider 接口。

```text
SourceProvider
├── WeWeRSSProvider
└── ArticleURLProvider
```

后续微信数据源变化时，只替换 Provider，不修改 Opinion、Storage、Query 等模块。

### 4.2 WeWeRSSProvider

V1 主数据源。

V1 自动监控以 WeWe 已存在且已知的 `feed_id` 为输入；公众号名称只作为展示元数据，不能代替 `feed_id`。KOL Radar 不调用 WeWe 管理接口自动创建订阅。

负责：

- 获取 Watchlist 公众号文章列表；
- 获取文章基本信息；
- 获取历史文章；
- 获取新增文章；
- 获取正文或可进一步解析的 URL。

首次部署允许人工扫码登录微信/微信读书。

认证失效时允许再次人工认证。

认证信息必须：

- 只保存在本机；
- 不进入 Git；
- 不进入 SQLite；
- 不进入 Obsidian；
- 不记录在日志明文中。

### 4.3 ArticleURLProvider

Fallback。

用户可以直接提交 `https://mp.weixin.qq.com/...`。

系统读取该文章并进入正常 `Article → Opinion Pipeline`。

直接 URL 只表示单篇补录，不会自动建立该公众号的后续监控；持续发现仍需配置已知 WeWe `feed_id`。

主要用于：

- 单篇补录；
- WeWe RSS 获取失败；
- 某篇文章未被正常同步。

---

## 5. 核心数据模型

保持四个主要实体：

```text
Source
Author
Article
Opinion
```

### 5.1 Source

表示内容来源，例如微信公众号。

建议字段：

```text
id
name
provider
external_id
status
created_at
last_synced_at
```

### 5.2 Author

表示实际作者、分析师、研究员或机构。

必须满足：

> Source ≠ Author

因为一个公众号可以有多个作者，一个作者未来也可能出现在多个来源。

建议字段：

```text
id
name
author_type
created_at
```

其中：

```text
author_type = person | organization | unknown
```

如果文章无法确认作者：

```text
author = Source
author_type = organization
```

### 5.3 Article

建议字段：

```text
id
source_id
title
url
published_at
author_id
content
content_hash
fetched_at
processed_at
```

`content_hash` 用于幂等和去重。

同一篇文章不得：

- 重复下载；
- 重复调用 LLM；
- 重复创建 Opinion；
- 重复生成 Obsidian 文件。

---

## 6. Opinion 数据模型

V1 强制保持简单。

每篇 Article 允许产生：

```text
0–5 Atomic Opinions
```

允许没有 Opinion；不允许为了填充数据库强制制造观点。

### 6.1 V1 主 Schema

```text
Opinion
├── topic
├── subject
├── thesis
├── stance
├── rationale[]
├── published_at
├── source_article_id
└── author_id
```

不再为 V1 增加主业务字段。

---

## 7. Topic 定义

Topic 不是行业分类，而是：

> 这个观点正在回答什么投资决策问题？

V1 固定枚举：

```text
market_view
opportunity
risk
risk_reward
positioning
trend
```

### market_view

整体怎么看市场。

示例：当前流动性仍然支持风险资产。

### opportunity

机会在哪里。

示例：当前存储景气度仍然处于上升周期。

### risk

主要风险是什么。

示例：AI 高估值股票正在形成较大的回撤风险。

### risk_reward

机会与风险之间的关系如何变化。

示例：当前继续追高 AI 龙头的赔率明显下降。

### positioning

作者明确提出的仓位、风险暴露、资产配置、进攻/防守等观点。

硬规则：

> 只有作者明确表达时才能生成 positioning Opinion。

禁止模型根据其他市场观点自行推导仓位建议。

### trend

趋势正在如何变化。

示例：AI 基础设施需求仍然保持向上趋势。

---

## 8. Subject

Subject 表示观点所针对的实际对象。

例如：

```text
美股
纳斯达克
NVDA
英伟达
AI Capex
HBM
DRAM
PCB
铜箔
10Y UST
美元
黄金
```

V1 不建设知识图谱，只做基础归一化。

### 8.1 内部 Subject Metadata

业务层仍只展示 `subject`。

内部允许保存：

```text
raw_subject
subject_key
subject_type
```

例如：

```text
raw_subject = 英伟达
subject = 英伟达
subject_key = NVDA
subject_type = company
```

`英伟达 / NVIDIA / NVDA` 应尽量映射到同一个 `subject_key`。

V1 `subject_type`：

```text
market
asset
industry
company
theme
other
```

不做复杂实体知识库。

---

## 9. Stance

V1 使用：

```text
positive
negative
neutral
improving
deteriorating
mixed
unclear
```

避免简单把所有投资观点压缩成 Bullish / Bearish。

例如：

```text
topic = risk
stance = deteriorating
```

意味着风险正在变大。

---

## 10. Opinion 抽取规则

每条 Opinion 必须满足：

> 一个 Opinion = 一个核心判断。

禁止：

- 一句话拆出大量碎片 Opinion；
- 把文章摘要直接当 Opinion；
- 将作者未表达的判断推断为作者观点。

每篇最多 5 条，没有明确投资判断允许 0 条。

---

## 11. Evidence Trace

V1 强制要求每条 Opinion 内部保存：

```text
source_excerpt
source_location
```

### source_excerpt

支撑该 Opinion 的原文片段。

### source_location

原文对应段落或其他稳定定位方式。

硬规则：

> 没有可定位原文依据的 Opinion，不允许入库。

Evidence Trace 默认不进入普通用户输出，主要用于：Audit、Eval、Debug、Badcase 修复。

---

## 12. LLM 原则

Opinion Extractor 必须遵循：

```text
明确表达 > 合理推测
NULL > 猜测
少抽 > 错抽
```

禁止模型补全：

- 作者未表达的仓位；
- 作者未表达的置信度；
- 作者未表达的时间周期；
- 作者未表达的风险；
- 作者未表达的催化剂。

V1 不实现：

```text
confidence
horizon
catalyst
risk_details
opinion_type
```

这些进入 V1.1 Backlog。

---

## 13. Opinion Change Detection

V1 不做 0–100 分数。

只比较：

```text
同一 Author
+
同一 Subject
+
同一 Topic
```

按时间排序。

输出：

```text
new
strengthening
weakening
reversal
unchanged
unclear
```

例如：

```text
Author A
Subject = AI高估值股
Topic = risk

08-01 neutral
08-15 deteriorating
08-28 negative
```

可以识别为 `strengthening`，即风险观点正在增强。

---

## 14. Persistence

V1 使用：

```text
SQLite + Markdown
```

禁止引入 PostgreSQL、Elasticsearch、Vector DB、Graph DB，除非未来出现明确需求。

---

## 15. SQLite

SQLite 是 **Machine Source of Truth**。

负责：

- 去重；
- 查询；
- Opinion 时间序列；
- Digest；
- Change Detection；
- 状态管理。

建议最小表：

```text
sources
authors
articles
opinions
sync_runs
```

可以根据实现需要增加简单 mapping 表，但禁止过度建模。

---

## 16. Obsidian

Obsidian 是 **Human-readable Knowledge Mirror**，不是数据库 Source of Truth。

### 16.1 开发目录

项目自身首先使用：

```text
KOL-Research/
```

作为独立测试知识库。

不得默认写入真实个人 Vault。

### 16.2 真实 Vault

通过：

```env
OBSIDIAN_VAULT_PATH=/path/to/vault
```

显式配置。

只有配置存在时才允许同步真实 Vault。

### 16.3 Obsidian 原则

V1 单向写入。

Agent：

- 可以创建自己的文件；
- 可以更新自己创建的文件。

禁止：

- 修改用户其他已有笔记；
- 删除用户其他笔记；
- 双向同步整个 Vault。

同步必须幂等。

---

## 17. Obsidian 目录结构

推荐：

```text
KOL-Research/
├── Sources/
├── Articles/
│   ├── <SourceName>/
│   └── ...
├── Authors/
├── Daily/
└── README.md
```

V1 不要求建立复杂 Topic Graph。

### 17.1 Article Note 示例

```markdown
---
article_id: xxx
source: xxx
author: xxx
published_at: 2026-08-30
url: xxx
---

# 标题

## Opinions

### Opinion 1

Topic: risk

Subject: 美股科技股

Stance: deteriorating

Thesis:
高估值科技股回撤风险正在增加。

Rationale:
- ...
- ...

## Source

原始正文或清洗正文。
```

---

## 18. Query

V1 不做 Web UI。

使用：

```text
CLI
```

以及可供 Agent 调用的 Python Service/API Interface。

### 18.1 CLI 示例

```bash
kol watchlist list
kol watchlist add <url>
kol sync
kol sync --source <source>
kol query "最近30天最大的风险是什么"
kol query "最近谁开始看多存储"
kol query "过去两个月某KOL怎么看美股"
kol digest --since 24h
```

CLI 的具体参数可以根据工程实现微调，核心能力不得变化。

---

## 19. Query Strategy

用户查询时：

```text
Query
↓
SQLite / Local Knowledge Base
↓
判断 freshness
```

正常情况下直接查询本地数据。

禁止：

```text
用户问一次
→ 重新抓全部 Watchlist
```

需要最新数据时，由显式 `sync` 完成增量更新。

V1 暂不实现复杂自动 freshness 推理。

---

## 20. Daily Incremental Digest

V1 同时支持：

```text
按需 Query + Daily Incremental Digest
```

Digest 只处理自上次 Digest 之后新增的数据，不得重复分析完整历史库。

输出重点：

### 新的重要观点

只输出有研究意义的新 Opinion。

### 观点变化

例如：某 KOL 对 AI Capex 从 `positive → deteriorating`。

### 新增机会

聚合 `topic = opportunity`。

### 新增风险

聚合 `topic = risk`。

### 新的仓位观点

只有明确 `positioning` Opinion。

### 共识与分歧

仅当多个 KOL 对相同 Subject 出现明显一致或冲突时输出。

重要性不足时不凑数。

---

## 21. 调度

V1 不建设复杂 Scheduler。

核心程序只提供：

```text
kol sync
kol digest
```

之后可以通过 cron、launchd、ChatGPT Automation 或其他 Scheduler 调用。

调度与核心业务解耦。

---

## 22. Error Handling

### Source failure

单个公众号失败：

- 不影响其他公众号同步；
- 记录失败状态；
- 下次允许重试。

### Article failure

文章正文无法读取：

```text
status = fetch_failed
```

不得创建虚假 Opinion。

### LLM failure

Schema 校验失败：

- retry；
- 超过最大 retry 后记录 failed；
- 不写不完整 Opinion。

### Obsidian failure

Obsidian 写入失败：

- SQLite 数据不得回滚；
- 下次可以重新同步 Markdown。

SQLite 优先级高于 Obsidian Mirror。

---

## 23. Logging

最小日志需要覆盖：

```text
sync start/end
source processed
articles discovered
articles new
articles skipped
articles failed
opinions extracted
opinions rejected
obsidian synced
errors
```

禁止记录 Cookie、Token、微信登录凭据、完整 Secret。

---

## 24. Eval

V1 必须包含最小 Eval，而不是只看代码是否能运行。

准备：

```text
10–20 篇人工确认文章
```

建立 Golden Dataset。

离线 `--fixture` 将人工确认的预期 Opinion 注入完整本地管线，用于 Fixture Pipeline Acceptance，不把结果表述为模型质量。只有 `--live` 才使用实际模型评估抽取效果；缺少 `OPENAI_API_KEY` 或 `OPENAI_MODEL` 时不得阻塞离线 V1 验收。

至少检查：

### Extraction Precision

抽出来的 Opinion 是否真的是作者观点。

### Evidence Validity

Opinion 是否真的有对应原文证据。

### Topic Accuracy

是否分到了正确业务 Topic。

### Subject Accuracy

是否识别正确对象。

### Hallucination Rate

是否生成作者根本没有表达的观点。

---

## 25. Badcase

建立：

```text
tests/badcases/
```

每次发现典型错误保存：

```text
原文
模型错误输出
期望结果
错误原因
```

后续优先通过 Prompt、Schema、Rule 修复。

禁止为了少数 Badcase 重构整个系统。

---

## 26. Definition of Done

### Source

- 能配置至少 3 个测试公众号；
- 能完成历史回溯；
- 能增量同步；
- 重跑不会重复入库。

### Article

- 正文能够正常保存；
- Article 有稳定 ID；
- content_hash 去重正常。

### Opinion

- 每篇 0–5 条；
- 所有 Opinion 有 Evidence Trace；
- 不明确的文章允许 0 条。

### Storage

- SQLite 可正常查询；
- Obsidian 可生成对应 Markdown；
- 重跑不产生重复笔记。

### Change

至少能演示 `同一 KOL + 同一 Subject + 同一 Topic` 的观点变化。

### Query

至少能回答：

1. 最近有哪些重要机会？
2. 最近有哪些重要风险？
3. 某 KOL 最近怎么看某个 Subject？
4. 某个观点最近是否发生变化？
5. 多个 KOL 对某个 Subject 有什么分歧？

### Digest

能够生成最近 24 小时增量 Digest。

### Quality

至少存在：

```text
Golden Dataset + Eval + Badcase
```

三类可验证证据。

---

## 27. Non-goals — V1 禁止实现

以下全部不属于 V1：

```text
全网自动发现 KOL
Web UI
Dashboard
复杂用户系统
Vector DB
Knowledge Graph
复杂 RAG
Multi-Agent
复杂 MCP Server
自动交易
自动生成买卖信号
自动修改仓位
0–100 Opinion Score
复杂 Confidence Score
完整 Entity Resolution
完整 Taxonomy
全文语义搜索平台
复杂推荐系统
Obsidian 双向同步
移动 App
复杂 Scheduler
Cloud SaaS
```

Codex 不得自行增加以上能力。

---

## 28. 建议技术栈

优先：

```text
Python 3.12+
SQLite
Pydantic
SQLAlchemy 或 sqlite3
httpx / requests
BeautifulSoup / readable parser
Typer
pytest
Markdown
```

LLM Provider 必须封装成简单接口，例如：

```python
OpinionExtractor.extract(article) -> list[Opinion]
```

不得把具体模型调用散落在业务代码中。

---

## 29. 推荐模块边界

```text
src/
├── providers/
│   ├── base.py
│   ├── wewe_rss.py
│   └── article_url.py
├── ingestion/
│   ├── sync.py
│   ├── article_fetcher.py
│   └── dedup.py
├── extraction/
│   ├── opinion_extractor.py
│   ├── schemas.py
│   └── prompts.py
├── normalization/
│   └── subjects.py
├── opinions/
│   └── change_detection.py
├── storage/
│   ├── db.py
│   ├── models.py
│   └── repository.py
├── obsidian/
│   └── exporter.py
├── query/
│   ├── service.py
│   └── digest.py
├── cli.py
└── config.py
```

该目录仅作为推荐。

如果 Codex 能在更简单的结构下保持模块边界清晰，可以适当简化。

不得因为追求目录结构而制造无意义抽象。

---

## 30. 架构硬边界

必须保证：

```text
Provider
   ↓
Article
   ↓
Extractor
   ↓
Opinion
   ↓
Storage
   ↓
Query / Obsidian
```

任何下层模块不得直接依赖具体微信实现。

例如：

- `OpinionExtractor` 不能知道 WeWe RSS 是否存在；
- `Query` 不能实时调用微信公众号；
- `Obsidian` 不能承担数据库职责。

---

## 31. V1 完成后的升级顺序

只有 V1 验收通过后才考虑。

### V1.1

```text
更好的 Subject Normalization
evidence[]
horizon
catalyst[]
risk[]
opinion_type
更丰富 Eval
```

### V1.2

```text
Topic / Subject 聚类
跨 KOL Consensus
更好的 Query
```

### V2

视真实使用价值决定是否加入：

```text
Investment Research Agent Integration
Semantic Search
Vector Index
Dashboard
Additional Sources
```

没有真实需求不得提前建设。

---

## 32. Codex Implementation Order

实现本项目时必须遵循以下顺序：

```text
1. 建立项目骨架
2. 建立数据库 Schema
3. 完成 ArticleURLProvider
4. 打通 Article → Opinion → SQLite
5. 完成 Opinion Evidence Trace
6. 完成 Subject 基础归一化
7. 完成 Change Detection
8. 完成 Obsidian Export
9. 完成 Query
10. 完成 Digest
11. 接入 WeWeRSSProvider
12. 加入 Eval / Badcase / Tests
13. 完成 README 与 setup
```

优先先用 `ArticleURLProvider` 打通闭环，再接 WeWe RSS。

避免一开始卡死在微信认证或第三方服务上。

---

## 33. Codex Exit Criteria

Codex 不得以“代码已创建”作为完成标准。

完成时必须提供：

```text
1. git diff / 文件变更摘要
2. pytest 结果
3. 一次真实或 fixture Article ingestion
4. SQLite 中对应 Article
5. 至少一条有 Evidence Trace 的 Opinion
6. 生成的 Obsidian Markdown
7. 一次 Query 示例
8. 一次 Digest 示例
9. 幂等重跑测试
10. Fixture Pipeline Acceptance 结果
11. Live Eval 结果（仅当已配置凭据）
12. 已知限制
```

如果其中任一核心流程未通过，V1 不视为完成。

---

## 34. Scope Freeze

本文件是 V1 唯一需求基线。

Codex 在实现期间：

- 不得自行增加 Non-goals 中能力；
- 不得为了未来扩展提前引入复杂基础设施；
- 不得在未出现明确 Badcase 前扩充 Opinion Schema；
- 不得把公众号 Provider 与 Opinion/Storage/Query 强耦合；
- 不得用“更高级的架构”替代本文定义的简单闭环。

若实现中发现 PRD 无法满足的真实阻塞，应记录为 `KNOWN_LIMITATION`，优先完成其余 V1 闭环，而不是扩 Scope。
