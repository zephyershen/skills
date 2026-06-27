# Wiki Location

This file is the single place to set the configured local wiki path for this skill.
Do not treat any example path as a default. Set `active_wiki_path` only after the
user explicitly confirms the exact path for the current machine.

```yaml
active_wiki_path: null
```

Path rules:

- If `active_wiki_path` is `null` or empty, resolve the wiki from the user's
  explicit path for the current request, then from nearby workspace/home
  discovery rules in `SKILL.md`.
- If `active_wiki_path` contains `AGENTS.md` and `wiki/index.md`, treat it as `<wiki_root>`.
- If `active_wiki_path` contains `index.md` and `overview.md`, treat it as `<wiki_dir>`, and use its parent as `<wiki_root>` when that parent has `AGENTS.md`.
