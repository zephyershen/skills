# LLM Wiki Templates

Use these templates only when the user asks for copy-paste text, or when a concrete wording helps.

Before using them, replace `<wiki_root>` with the real wiki root on the current machine.

## 1. Session Start

### Short

```text
知识库在 `<wiki_root>`。
先读 `<wiki_root>/AGENTS.md`，再读 `<wiki_root>/wiki/index.md` 和 `overview.md`；不够再看 `entities`、`concepts`、`sources`，最后才回 `raw`。
```

### Standard

```text
知识库在 `<wiki_root>`。

请先从 `<wiki_root>/AGENTS.md` 开始，
再按这套 llm-wiki-agent 的结构工作：

1. 先读 wiki/index.md
2. 再读 wiki/overview.md
3. 再读相关 entities
4. 再读相关 concepts
5. 不够再读 sources
6. 最后才回 raw

回答时优先基于 wiki，不要跳过现有结构直接猜。
如果这次结论有长期价值，请顺手建议应该回写到 entities、concepts 还是 syntheses。
```

## 2. Query

```text
先按 llm-wiki-agent 的读取顺序回答这个问题。
先读 `<wiki_root>/AGENTS.md`，再读 `<wiki_root>/wiki/index.md` 和 `overview.md`；然后读相关 `entities` 和 `concepts`；不够再回 `sources`，最后再回 `raw`。
```

## 3. Ingest

```text
把这份资料导入 llm-wiki-agent。
先归类到合适的 raw 来源包，再更新相关 source、entity、concept 页面，同时更新 overview、index 和 log。
```

## 4. Writeback

```text
把这次结论写回 llm-wiki-agent。
如果是项目长期事实，写到 entity；如果是跨项目说明，写到 concept；如果是一次完整答案，写到 synthesis。
```

## 5. Lint

```text
给这个 llm-wiki-agent 做一次 lint。
检查冲突结论、过期内容、缺失来源页、断掉的 wikilink、孤页、重复事实，以及应该拆分但还没拆分的页面。
```

## 6. Folder Meaning

```text
entities = 实体
concepts = 概念
sources = 来源
syntheses = 回写答案
```
