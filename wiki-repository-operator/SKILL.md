---
name: wiki-repository-operator
description: Use when an AI agent needs to query or safely operate the Wiki Repository platform through its authenticated public API, including Wiki Groups, Subgroups, Wiki repositories, files, downloads, search, grounded Q&A, change requests, reviews, personnel, resource permissions, archives, personal access tokens, GitLab settings, Jira settings, and Jira imports. Defaults to http://10.40.2.178:4004 and supports changing the server IP without editing the skill.
---

# Wiki Repository Operator

## Purpose

Use this skill when the user wants to view or operate the Wiki Repository platform through an Agent. Users may perform the same work in the web page or ask the Agent to perform it.

The bundled CLI is the execution boundary. Determine the directory containing this `SKILL.md`, call it `SKILL_DIR`, then run:

```bash
python3 "$SKILL_DIR/scripts/wiki_platform.py" <command>
```

Do not reimplement API calls with `curl` when the CLI supports the action.

## One-Time Wiki Skill Bootstrap

The first CLI command for each installed copy of this operator automatically ensures the company Wiki Skill is installed beside `wiki-repository-operator`. It uses the pinned internal package `global-skills/wiki@1.0.0` from `http://10.40.2.15:2323`.

- The completion marker is written only after a compatible Wiki Skill is present.
- Once the marker is complete, later operator commands must not inspect the Wiki Skill directory and must not contact SkillHub again.
- The marker binds the operator copy to the install path resolved on its first run; later commands must not switch to a different sibling merely because an environment override is absent.
- Do not add a manual dependency check before every user request. The CLI owns this first-use-only behavior.
- The first command still performs the user's requested command after installation. Its JSON result includes `wiki_skill_bootstrap` with the installed path; later results omit that field.
- If the first result contains `wiki_skill_bootstrap`, read the installed `SKILL.md` before adding, editing, deleting, normalizing, or uploading Wiki content. Treat it as supporting instructions inside this operator workflow; do not replace the active operator workflow merely to invoke a second Skill.
- A pre-existing incompatible directory named `wiki` is preserved and reported as a conflict rather than overwritten.

By default the Wiki Skill is installed as a sibling of this Skill, so the same placement works for Codex, Claude Code, Devin, and other Agent Skills-compatible environments. `WIKI_REPOSITORY_SKILLS_DIR` may explicitly select a different absolute skills directory. `WIKI_REPOSITORY_SKILLHUB_URL` may override the internal SkillHub origin before the first successful bootstrap.

## Production Boundary

- Default web/API entry: `http://10.40.2.178:4004`
- Public API base: `http://10.40.2.178:4004/api`
- Never use port `4003`; it is an internal loopback API port.
- Never use SSH, direct database access, direct GitLab access, or repository files for platform business operations.
- Never use the user's Webmanager password. The personal access token is created on the platform web page; the user may then send the `wkp_` PAT directly in chat for the Agent to configure.
- Production data must come from the configured platform API, not from source code, Wiki memory files, Git history, or cached examples.

## First Run

1. Do not run a separate Wiki Skill dependency check. The first CLI command installs it once and then continues that command.
2. If the user already supplied a `wkp_` PAT in the current conversation and asked the Agent to configure or use it, treat that as explicit authorization. Save it immediately through stdin; this may be the first CLI command and therefore also performs the one-time Wiki Skill bootstrap:

   ```bash
   python3 "$SKILL_DIR/scripts/wiki_platform.py" auth set-token --stdin
   ```

   When the PAT came from chat, feed that value to the CLI through the Agent runtime's stdin. An incoming user message is an allowed PAT transport for this internal deployment. Never put the PAT in a command argument or repeat it in an outgoing message, plan, documentation, command summary, or result.
3. If no PAT was supplied, run `doctor` to verify the server and ask the user to create a PAT in the web page under “个人访问令牌” with only the scopes needed by the task. Tell them they may send it in chat.
4. After saving a PAT, run `auth status`, then `doctor`, and continue the original request. For example, “查看我对哪些 Wiki 仓库有权限” continues with `projects list` and the relevant workspace/repository reads.

Read [Installation](references/installation.md) when installing for Codex, Claude Code, or Devin.

## Translate The User Request

Before calling a write operation, resolve the exact object and intended effect:

- Distinguish a top-level Wiki Group, a nested Subgroup, a Wiki repository, a personnel group, and a person.
- Prefer `resolve project`, `resolve repository`, or `resolve person` when the user gives a name instead of an ID.
- If resolution returns `ambiguous_object`, show the candidates and ask the user to choose. Never guess.
- When renaming a Wiki Group, read its current state first. Treat `name` as the human-visible label and `path` as the lowercase URL/GitLab path; show both current and target values plus the GitLab path impact before confirmation.
- For permissions, identify the target person, exact resource, and level (`none`, `read`, or `write`).
- For “删除”, determine whether the user means recoverable archive or permanent purge. Default to recoverable archive when not explicit.
- Recoverable Group/Subgroup/Wiki archive preserves GitLab content but renames the backing name and path with a Shanghai timestamp plus a final `deleted` suffix. Read the API response and report the archived backing name/path. These suffixed objects are hidden from normal binding candidates.
- Restore attempts to return the backing GitLab name and path to their originals. If the original path has been reused, report the conflict and do not bypass it or overwrite the newer resource.
- For content changes, generate an upload preview, inspect it, submit a change request, and let an authorized reviewer approve it.

## Confirmation Protocol

Read-only commands execute immediately. Every production mutation uses a two-step, one-time confirmation plan:

1. Run the command without `--confirm`. The CLI performs no mutation and exits with code `3`, returning `confirmation_required` and a sanitized plan.
2. Show the plan to the user: server, action, target, fields, risk, required scope, and impact.
3. Only after explicit confirmation, rerun the exact same command and parameters with `--confirm <PLAN_ID>`.
4. For critical actions, also pass the exact `confirmation_text` returned by the plan using `--confirm-text`.

Never invent a plan ID, skip the first step, reuse a plan, alter parameters after confirmation, or treat a failed mutation as safe to retry. Plans expire after 10 minutes and contain no credential values.

Archive and restore plans automatically read the current resource and bind `expected_full_path` into the plan. The confirmation attempt reads it again; a renamed, replaced, missing, or newly invisible target stops before mutation and requires a new plan.

After a successful mutation, use a read command to verify the resulting state and report both the change and verification.

## Secret Handling

- Platform PAT: the user may provide it directly in chat; immediately pass it through stdin on bootstrap, then use private local config. `WIKI_REPOSITORY_TOKEN` is also supported for managed Agent secrets.
- GitLab/Jira Token: use `--secret-stdin`, `--secret-env <NAME>`, or `--secret-file <PATH>` where the file mode is `600`.
- Never use `--json` for tokens, passwords, API keys, cookies, or secrets; the CLI rejects sensitive keys.
- Never repeat or print full tokens in Agent responses. Child PAT creation requires `--save-token <new-file>` and writes mode `600`; the token is never returned to stdout.
- Do not expose Wiki content from a `secrets` directory even if the current account can read it, unless the user explicitly requested that exact secret content and disclosure is appropriate.

Read [Security Model](references/security.md) before any permission, administrator, archive purge, or integration-setting action.

## Server Change

When the user says to use another IP, validate and save it without editing this skill:

```bash
python3 "$SKILL_DIR/scripts/wiki_platform.py" server set 10.40.2.179
```

A bare IP automatically uses `http://<IP>:4004`. A complete `http://` or `https://` URL is also accepted. The old server remains configured if discovery or health validation fails. `WIKI_REPOSITORY_URL` overrides saved configuration.

## Command Routing

- Use [Workflows](references/workflows.md) for exact, safe end-to-end examples.
- Use [Command Reference](references/api-actions.md) to select a command, scope, JSON body, and query parameters.
- Use `raw get /path` only for a new read-only endpoint not yet represented by a named command. It can never send a mutation.
- Run `doctor` when a request fails because of reachability, authentication, API-version, or scope uncertainty.
- A `token_scope_required` error means the PAT lacks the named scope. A 403 with the correct scope means the user's current role or resource authorization does not allow the action; do not bypass it.

## Response Rules

- Put the user-visible result first and reply in the user's language.
- For reads, state that data came from the configured production API and name the server.
- For writes, state exactly what changed, what the read-back verification showed, and whether backing GitLab storage was preserved or deleted.
- Never include passwords, full tokens, Authorization headers, cookies, encrypted credentials, or secret-file contents.
- If blocked, report the concrete server/API error and the required scope or missing user choice. Do not fall back to SSH, database changes, or web-password automation.
