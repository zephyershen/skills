# Geist Usage Notes

Use this reference after the skill triggers and before coding a Geist-based UI.

## Source of Truth

- Official docs: `https://vercel.com/geist/introduction`
- Component pages follow `https://vercel.com/geist/<component-slug>`.
- Refresh the local index when exact component availability or API details matter:

```bash
python3 ~/.codex/skills/geist/scripts/update_geist_index.py --details
```

## Project Checks

Before editing a repo:

- Check `package.json` for `@vercel/geistcn`, `@vercel/geist`, `next`, `react`, Tailwind, and existing UI libraries.
- Check global CSS, font setup, and theme variables.
- Reuse the repo's existing component folder and import aliases.
- If another UI system is already deeply used, adapt the screen toward Geist visual language instead of mixing incompatible primitives everywhere.

## Current Package Clues

- Current Geist docs commonly import components from `@vercel/geistcn/components`.
- Verify icons, logos, fonts, and each component import from its official page before using them.
- Avoid `@geist-ui/react` for new work. That is not the current Vercel Geistcn component source.

## Visual Language

- Layout: tight spacing, clear hierarchy, low decoration, predictable controls.
- Color: neutral surfaces, strong foreground contrast, semantic accents for status and destructive actions.
- Typography: Geist Sans for UI, Geist Mono for technical strings.
- Shape: modest radii, crisp borders, compact controls.
- Motion: subtle and functional. Do not add decorative animation unless the product needs it.

## Common Mapping

- Primary action: `Button`.
- Secondary action: secondary button variant after verifying current prop name.
- Navigation action: link-styled component or official link button after verifying current docs.
- Forms: `Input`, `Textarea`, `Select`, `Checkbox`, `Radio`, `Switch`, `Fieldset`, validation text.
- App chrome: `Tabs`, `Menu`, `Breadcrumbs`, `Context Menu`, `Drawer`, `Sheet`, `Modal`.
- Feedback: `Toast`, `Note`, `Error`, `Error Card`, `Skeleton`, `Spinner`, `Loading Dots`.
- Data-heavy views: `Table`, `Badge`, `Status Dot`, `Pagination`, `Tooltip`, `Copy Button`.

## Quality Bar

- Do not invent component props.
- Do not leave placeholder copy.
- Use visible labels unless the control is icon-only.
- For icon-only buttons, include both the official icon-only prop if required by docs and an `aria-label`.
- Make disabled states understandable.
- Run lint/build/test commands available in the repo.
