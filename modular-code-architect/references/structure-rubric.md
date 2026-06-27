# Structure Rubric

Use this rubric when reviewing, generating, or refactoring a project for modularity and future maintenance.

## Quality Gates

1. Directory names explain product capabilities.
   - Good: `checkout`, `billing`, `projects`, `editor`, `auth`.
   - Weak: `misc`, `utils`, `stuff`, `new`, `components` as the only organizing idea.
2. Each module has a clear owner responsibility.
   - It is obvious what belongs in the module.
   - It is obvious what should stay outside the module.
3. Dependencies flow inward or sideways in predictable ways.
   - UI or delivery code may call use cases/services.
   - Use cases/services may call repositories/adapters.
   - Domain logic should not import routes, pages, controllers, or UI components.
4. Shared code is earned.
   - Shared helpers solve repeated needs across modules.
   - One-off helpers stay local until reuse is real.
5. Change points are isolated.
   - External providers, storage, network APIs, and model calls live behind small adapters.
   - Product rules do not leak into low-level transport or database code.
6. Files tell one coherent story.
   - The main export appears before private details.
   - Helpers are ordered by usage.
   - Large files are split by responsibility, not by arbitrary line count.
7. Tests protect behavior at useful boundaries.
   - Feature behavior, service contracts, adapters, and data transforms are covered when risky.
   - Tests do not depend on private helper ordering or unrelated directory trivia.

## Common Smells And Fixes

| Smell | Likely problem | Better move |
| --- | --- | --- |
| `utils` keeps growing | No module ownership | Move helpers beside the feature that owns them; keep only cross-module helpers shared |
| Page or route file has most logic | Delivery layer became the app | Extract validation, orchestration, and provider calls into feature/service modules |
| One change touches many unrelated folders | Capability is split by technical layer only | Group capability-specific files together where the framework allows it |
| Everything imports everything | No dependency direction | Introduce module public APIs and move external calls behind adapters |
| Abstract base classes everywhere | Premature abstraction | Replace with plain functions or small interfaces only at real change boundaries |
| Duplicate provider logic | Missing adapter boundary | Create one adapter/service for the provider and inject or configure variants |
| Huge component/service file | Mixed responsibilities | Split rendering, state, data access, validation, and transformations |
| Tests break after moving private helpers | Tests know too much | Test public module behavior or contracts instead |

## Refactor Slicing Pattern

1. Choose one capability or dependency boundary.
2. Create the target module folder with a narrow public entrypoint if useful.
3. Move pure helpers first because they are easiest to verify.
4. Move stateful or external calls behind adapters/services.
5. Update callers one group at a time.
6. Run targeted checks after each meaningful slice.
7. Delete obsolete wrappers only after all imports are migrated.

## Output Standard

When this skill is used, final responses should name:

- The module structure created or changed.
- The behavior that stayed the same or changed.
- The validation performed.
- Any assumption that affects future product or code decisions.
