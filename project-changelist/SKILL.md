---
name: project-changelist
description: Use when creating a new local project, making incremental code updates, fixing bugs, refactoring, or shipping a version and the work should be documented in a `changelist/` folder under the project so reviewers can quickly see what changed, why it changed, and how it was checked.
---

# Project Changelist

## Overview

This skill makes Codex keep a per-project `changelist/` folder up to date.
Use it whenever code or project structure changes should be documented for review, handoff, or release tracking.

## When To Use

Use this skill when:

- creating a new project, app, package, or service
- adding or removing features
- fixing bugs
- refactoring code or folders
- changing configuration, scripts, or dependencies
- preparing work that someone else will review later

Do not use this skill when:

- the user explicitly says not to create changelist notes
- the task is read-only and no project files are being changed
- the project already has a required changelog format and the user asked to follow that format instead

## Project Root Rule

- Put the `changelist/` folder inside the project root that is being changed.
- If `changelist/` already exists, update it instead of creating a second folder.
- In a monorepo, use the specific app or package directory being modified unless the repo already uses one shared project-level `changelist/` folder.

## Workflow

1. Identify the project root being changed.
2. Ensure `<project>/changelist/` exists.
3. Create one markdown entry for the current work batch.
4. Make the code changes.
5. Update the same entry so it matches the final result.
6. Before finishing, verify that the changelist entry reflects the actual diff and validation status.

## Helper Script

Use the bundled helper script to create a changelist file skeleton:

```bash
python3 /root/.codex/skills/project-changelist/scripts/init_changelist_entry.py \
  --project /path/to/project \
  --title "short change title" \
  [--version v0.3.0] \
  [--type update]
```

The script will:

- create `<project>/changelist/` if needed
- create a markdown file with a stable name
- prefill the standard review template
- avoid overwriting an existing file by adding `-2`, `-3`, and so on

## Naming Rules

- If a version is known, prefer `<version>-<slug>.md`.
- Otherwise use `<date>-<slug>.md` with `YYYY-MM-DD`.
- Keep the slug short, lowercase, and hyphenated.
- Use one file per work batch, not one file per touched file.

## Required Sections

Every changelist entry should include:

- what part of the project changed
- why the change was needed
- the main code or config updates
- the important files or folders involved
- any behavior impact
- validation that was run, or a clear note that validation was not run
- known risks, open items, or follow-up work

## Writing Rules

- Keep it short and factual.
- Describe the real change, not only filenames.
- Prefer concrete statements such as `Added retry logic to API client`.
- Include commands for build, test, or lint when they matter.
- If work is partial, say what is still open.
- If no tests were run, say so directly.

## Suggested Template

```markdown
# <version-or-date> - <title>

- Date: <YYYY-MM-DD>
- Type: <create|update|fix|refactor|docs|release>
- Project: </absolute/path/to/project>

## Why
- ...

## What Changed
- ...

## Files Changed
- `path/to/file`
- `path/to/dir`

## Behavior Impact
- ...

## Validation
- `npm test`
- `pytest`
- Not run: <reason>

## Risks
- ...

## Follow-up
- ...
```

## Final Check

Before completing the task, make sure:

- the project contains a `changelist/` folder
- the current work batch has a markdown entry inside it
- the entry matches the final code state
- the validation section is honest
- the file is stored under the correct project root
