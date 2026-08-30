# KOL Research Radar

面向个人投资研究的微信公众号 / KOL 观点跟踪系统。

核心目标不是“总结公众号文章”，而是持续把 Watchlist 中的文章转化为可查询、可比较、可追踪变化的结构化投资观点资产。

## V1 Status

**Scope Frozen — PRD baseline established on 2026-08-30.**

V1 只实现最小长期闭环：

```text
Watchlist
  → 首次历史回溯 + 增量同步
  → Article
  → 0–5 Atomic Opinions
  → SQLite
  → Obsidian Mirror
  → Query / Daily Incremental Digest
```

设计原则：

- 能稳定工作 > 功能完整
- 数据可信 > 字段丰富
- 少字段、高可信、允许 NULL
- 没有原文证据的 Opinion 不入库
- SQLite 是 Machine Source of Truth
- Obsidian 是 Human-readable Knowledge Mirror
- Provider 与分析/存储/查询解耦
- V1 不扩 Scope

## Documents

- [`docs/PRD_V1.md`](docs/PRD_V1.md) — V1 产品需求与实现边界，当前唯一需求基线

## V1 Non-goals

V1 不实现：全网自动发现 KOL、Web UI、Dashboard、Vector DB、Knowledge Graph、复杂 RAG、Multi-Agent、自动交易、复杂 Scheduler、Obsidian 双向同步等。

开发必须以 `docs/PRD_V1.md` 的 Definition of Done 和 Exit Criteria 为完成标准，而不是以“代码已生成”为完成标准。
