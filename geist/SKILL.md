---
name: geist
description: Use Vercel's Geist and Geistcn design system for React/Next.js UI work. Trigger when the user mentions Geist, Vercel design system, Geistcn, @vercel/geistcn, Vercel-style UI, Geist Sans/Mono, or asks to build/refactor components, dashboards, forms, developer tools, docs pages, or app screens using the current Geist component library and visual language. Includes an official-docs freshness workflow and local index updater.
---

# Geist

## Core Rule

Treat the official Geist docs as the source of truth. Geist changes over time, so verify current component names, imports, props, and best practices from `https://vercel.com/geist/introduction` or the specific component page before implementing anything that depends on exact API details.

## Freshness Workflow

1. For broad visual direction, read `references/usage.md`.
2. For current component navigation, read `references/geist-index.md` if it exists.
3. If the task depends on exact components, props, examples, or current availability, refresh the index:

```bash
python3 ~/.codex/skills/geist/scripts/update_geist_index.py --details
```

4. For a focused lookup, refresh only the relevant pages:

```bash
python3 ~/.codex/skills/geist/scripts/update_geist_index.py --slugs button,input,modal
```

5. If the script cannot reach the network, use the local index as a fallback and say the component data may be stale.

## Implementation Workflow

1. Inspect the target project first: framework, package manager, existing UI library, CSS setup, and whether `@vercel/geistcn` is already installed.
2. Use existing project patterns unless they conflict with Geist.
3. Prefer official Geistcn components when the project can use them. Verify the import path on the component page; current docs commonly use `@vercel/geistcn/components`.
4. Do not use old or unrelated packages such as `@geist-ui/react` unless the repo already depends on them and the user explicitly wants compatibility.
5. If Geist components are not installed and adding dependencies is appropriate, install with the repo's package manager. If adding packages is not appropriate, recreate the Geist visual language with local components and CSS, and clearly state that it is a Geist-style implementation rather than the official package.
6. Validate the result with the repo's normal lint/test/build commands. For visible UI changes, run a browser/screenshot check when the app can be launched locally.

## Design Priorities

- Build practical product UI: dense but readable, high-contrast, restrained, and scan-friendly.
- Use Geist Sans for general UI text and Geist Mono for code, ids, commands, metrics, timestamps, and technical labels when available.
- Prefer the official components for buttons, inputs, menus, modals, tabs, tables, tooltips, badges, toasts, and loading states.
- Keep wording direct and action-oriented. Use labels that name what will happen.
- Preserve accessibility: labels for inputs, keyboard-friendly focus states, `aria-label` for icon-only buttons, and clear disabled-state explanations.
- Avoid inventing props, variants, tokens, or component names. Check the official page first.

## References

- `references/usage.md`: compact guidance for using Geist in projects.
- `references/geist-index.md`: generated human-readable index of current docs.
- `references/geist-index.json`: generated machine-readable index.
- `scripts/update_geist_index.py`: refreshes the local index from official Geist docs.
