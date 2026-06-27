---
name: wiki
description: Use when the user wants to query, ingest, explain, lint, or write back to a local personal LLM Wiki, or when a new session should start from the wiki using the right workflow template automatically.
---

# Wiki

## Overview

This skill standardizes how Codex works with a local personal `llm-wiki-agent` style wiki at `<wiki_root>`.
Use it to choose the right workflow automatically for querying, importing new material, writing conclusions back, running lint checks, or giving the user a reusable opening prompt for other AI tools.

## Quick Rules

- Resolve the wiki root before doing anything else
- Read [references/wiki-location.md](references/wiki-location.md) before resolving the wiki root
- If the user explicitly gives a wiki path, use that path for the current request; only update `references/wiki-location.md` when the user asks to persist it
- If `references/wiki-location.md` defines an active path, use it before auto-discovery
- If the user does not give a path, look for a usable root in this order:
  1. the active path in `references/wiki-location.md`, if present and valid
  2. current workspace directory that contains `AGENTS.md` and `wiki/index.md`
  3. a nearby `memory/` or `wiki/` directory that contains `AGENTS.md` and `wiki/index.md`
  4. a user home directory location that contains `AGENTS.md` and `wiki/index.md`
- A configured active path may point either to `<wiki_root>` or to the content directory `<wiki_root>/wiki`; prefer a path with `AGENTS.md` and `wiki/index.md` as `<wiki_root>`, otherwise if it has `index.md` and `overview.md`, treat it as `<wiki_dir>` and use its parent as `<wiki_root>` when the parent has `AGENTS.md`
- Treat concrete paths only as examples, not fixed truth
- Canonical rules file: `<wiki_root>/AGENTS.md`
- Always start from `wiki/index.md`
- Read `wiki/overview.md` right after `wiki/index.md`
- Read `entities/` and `concepts/` before drilling into `sources/`
- Read `sources/` only when the wiki is not enough
- Read `raw/` last
- Prefer Chinese explanations, but keep code paths, commands, logs, and identifiers in original language
- If the user does not explicitly ask to see a template, apply the workflow silently
- If you only find an older flat memory folder and it does not have `AGENTS.md` plus `wiki/index.md`, do not pretend it is this wiki format; first inspect its existing file style and then either work in that style or ask whether to migrate it

## Workflow Decision Tree

Choose one workflow based on user intent:

1. **Session start**
   Use when the user starts a new conversation and wants the AI to work against the wiki correctly.
   Output or internally use the session-start template.

2. **Query**
   Use when the user asks a new question and wants an answer from the wiki.
   Read in this order:
   1. `AGENTS.md`
   2. `wiki/index.md`
   3. `wiki/overview.md`
   4. relevant `wiki/entities/*.md`
   5. relevant `wiki/concepts/*.md`
   6. relevant `wiki/sources/*.md` if needed
   7. `raw/` only if still necessary

3. **Ingest**
   Use when the user provides new material or asks to import/update the wiki.
   Workflow:
   1. place material in `raw/inbox/` if not already organized
   2. classify into the right `raw/...` bundle
   3. update affected `wiki/sources/*.md`
   4. update affected `wiki/entities/*.md`
   5. update affected `wiki/concepts/*.md`
   6. update `wiki/overview.md`
   7. update `wiki/index.md`
   8. update `wiki/log.md`

4. **Writeback**
   Use when the user wants to keep a useful conclusion from the current conversation.
   Store it by intent:
   - project-specific long-lived fact -> `wiki/entities/...`
   - cross-project explanation or reusable rule -> `wiki/concepts/...`
   - a saved answer / analysis -> `wiki/syntheses/...`

5. **Lint**
   Use when the user asks to health-check the wiki.
   Check for:
   - contradictory statements
   - stale conclusions
   - broken `[[wikilinks]]`
   - orphan pages
   - missing source pages
   - missing links
   - pages that should be split
   - facts duplicated in too many places

6. **Explain the system**
   Use when the user asks what the folders mean or how to use the wiki itself.
   Explain with the current human-friendly mapping:
   - `entities` = 实体
   - `concepts` = 概念
   - `sources` = 来源
   - `syntheses` = 回写答案

## Output Style

- Keep explanations simple and direct
- Use examples from the actual wiki when helpful
- Do not force template text into every answer
- When the user asks for a template, provide the shortest version that is sufficient
- When unsure which template fits best, prefer `query` over `session-start`, and prefer `writeback` over leaving useful conclusions only in chat

## References

Read [references/wiki-location.md](references/wiki-location.md) when:

- resolving the active wiki path
- changing the permanent wiki location

Read [references/templates.md](references/templates.md) when:

- the user asks for a copy-paste opening prompt
- the user wants a standard wording for query/ingest/writeback/lint
- you want a concrete template to follow internally before replying

## Stored Assumptions

- The wiki is local and private
- The active wiki root is `<wiki_root>`, resolved from the current machine and the configured active path
- The canonical structure is:
  - `wiki/entities`
  - `wiki/concepts`
  - `wiki/sources`
  - `wiki/syntheses`
- The main entry file is `<wiki_root>/wiki/index.md`
- The canonical workflow rules live in `<wiki_root>/AGENTS.md`
- Older or machine-specific paths can exist, but should never be assumed unless the current machine actually has them

## Do Not

- Do not bypass `wiki/index.md` without reason
- Do not ignore `wiki/overview.md` for cross-project questions
- Do not jump to `raw/` first for normal questions
- Do not keep using the old `guides / reports` model as the active structure
- Do not write back every trivial chat answer; only persist reusable knowledge
- Do not hardcode machine-specific wiki paths unless the user explicitly confirmed that exact path for the current machine
