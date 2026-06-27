---
name: modular-code-architect
description: Plan, implement, or refactor code so it is modular, extensible, and easy to maintain. Use when Codex is asked to generate application code, add a feature, reorganize a project, reduce scattered logic, clarify directory structure, split code by feature/domain, define module boundaries, improve function/file order, or normalize an existing codebase for future iteration.
---

# Modular Code Architect

## Goal

Produce code that can keep growing without becoming a pile of unrelated patches. Treat "make it cleaner", "make it extensible", "organize the project", and similar vague requests as requests to define module boundaries, clear ownership, and safe change points.

## Default Workflow

1. Translate the user's wording into a concrete engineering objective before editing.
   - Separate the visible product result from the internal structure work.
   - If multiple user-visible outcomes are plausible, confirm the intended outcome first.
   - If only implementation details are unclear, choose defaults that match the existing project.
2. Inspect the current project shape before choosing a structure.
   - Prefer `rg --files`, package manifests, routing files, entrypoints, and nearby modules.
   - Identify the framework's required folders before proposing a custom structure.
   - Preserve established naming, import style, state management, and test patterns unless they are the source of the problem.
3. Define a small module map before writing substantial code.
   - Name each module by product capability or domain responsibility.
   - State what belongs inside it, what it exposes, and what it must not know about.
   - Keep routes/controllers/screens thin; move durable behavior into domain, service, or feature modules.
   - For UI flows with tabs, nested routes, or shared context panels, identify which component must stay mounted while inner content changes.
4. Implement by capability, not by scattered file type.
   - Group UI, state, validation, API calls, transforms, and tests close to the feature when the framework allows it.
   - Put truly shared code in shared/common areas only after at least two modules need it.
   - Hide external systems behind adapters or service functions so future changes stay local.
5. Validate behavior after restructuring.
   - Run the narrowest useful tests, type checks, linters, or build command available.
   - For refactors, avoid changing behavior unless the user explicitly asked for behavior changes.
   - Report assumptions, changed structure, and any checks that could not run.

## Structure Rules

- Prefer feature/domain folders over generic buckets when the app has clear business capabilities.
- Keep framework-mandated folders, but avoid letting route files, page files, or controllers become the real application.
- Keep one primary reason to change per file. Split files that mix unrelated UI, persistence, validation, business rules, and formatting.
- Use interfaces or ports only at real change boundaries: third-party services, storage, payment, auth, messaging, model providers, or multiple implementations.
- Avoid speculative abstraction. A module should make the next likely change simpler, not create ceremony for imaginary changes.
- Keep data contracts explicit at module boundaries with types, schemas, DTOs, request/response mappers, or equivalent local patterns.
- Keep dependency direction clear: feature UI can depend on feature logic; feature logic should not depend on UI; shared/domain code should not import app-specific screens or routes.
- For route-driven UI, do not confuse "shared component" with "shared lifecycle": a header/sidebar/context shell that should not reload across tabs belongs in a parent layout route, not as a wrapper imported by every child page.

## File And Function Order

Use local convention first. If the project has no clear convention, order files like this:

1. External imports.
2. Internal imports.
3. Public types, schemas, constants, and configuration used by the file's public API.
4. Main exported function, component, class, route handler, or service.
5. Supporting exported helpers.
6. Private helper functions in the order they are used.
7. Test-only builders or fixtures in test files.

Keep top-level code readable as a story: entrypoint first, orchestration next, low-level details last. Avoid forcing readers to jump across unrelated helper blocks.

## New Code Checklist

- Start with the smallest directory structure that can absorb the next obvious feature.
- Add a public module entrypoint only when it simplifies imports or matches existing practice.
- Give files names that explain responsibility: `pricing-service`, `checkout-form`, `user-repository`, `notification-adapter`, not vague names like `helpers2` or `manager`.
- Keep configuration separate from behavior when product variants, providers, or feature flags are expected.
- Add focused tests around module boundaries and important behavior. Do not write tests that only freeze the current internal layout.

## Refactor Checklist

- Map current behavior and entrypoints before moving code.
- Move one responsibility at a time; keep old public imports working until callers are migrated.
- Prefer extraction, relocation, and dependency inversion over broad rewrites.
- Remove dead duplicate paths only after confirming no callers remain.
- Update tests and imports as part of each slice so the project stays runnable.
- For page or route refactors, check mount/unmount boundaries and user-visible reload points before declaring the structure clean.

For larger restructures, reviews, or when deciding whether a proposed structure is good enough, read `references/structure-rubric.md`.
