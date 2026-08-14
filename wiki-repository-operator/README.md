# Wiki Repository Operator Skill

Production-ready Agent Skill and dependency-free Python CLI for the Wiki Repository platform. It lets Codex, Claude Code, Devin, and other Agent Skills-compatible tools use the same authenticated platform actions as the web UI.

Default server: `http://10.40.2.178:4004`. The default is intentionally committed for this internal-network deployment; credentials are never committed.

Company distribution coordinate: `global-skills/wiki-repository-operator@1.1.0` on `http://10.40.2.15:2323`.

## What it covers

- Wiki Group, Subgroup, and Wiki discovery and management
- File trees, fixed-revision snapshots, secure ZIP download and extraction
- Search, knowledge graph, backlinks, grounded Q&A, and streaming Q&A
- Directory upload preview, change requests, approval, and rejection
- Personnel, personnel groups, resource permissions, and platform admins
- Archives, restore, and separately confirmed permanent purge
- Fine-grained personal access tokens
- GitLab and Jira validate-before-apply configuration flows
- Jira project import preview and execution

The CLI uses only Python's standard library. Python 3.10 or newer is required.

## Install

Download `global-skills/wiki-repository-operator@1.1.0` once from the company SkillHub, then place the complete `wiki-repository-operator` directory in a Skill location recognized by the Agent. Do not copy only `SKILL.md`; the scripts and references are part of the Skill.

Claude Code personal skills live at `~/.claude/skills/<name>/SKILL.md`, and project skills at `.claude/skills/<name>/SKILL.md`, according to [Claude Code's official Skills documentation](https://code.claude.com/docs/en/skills).

```bash
ln -s /path/to/skills/wiki-repository-operator ~/.claude/skills/wiki-repository-operator
```

Devin recommends `.agents/skills/<name>/SKILL.md` in a connected repository and also recognizes several tool-specific skill directories, according to [Devin's official Skills documentation](https://docs.devin.ai/product-guides/skills).

```bash
mkdir -p .agents/skills
cp -R /path/to/skills/wiki-repository-operator .agents/skills/
```

For Codex, place the directory in the user Agent Skills folder:

```bash
ln -s /path/to/skills/wiki-repository-operator ~/.agents/skills/wiki-repository-operator
```

The bundle follows the open Agent Skills `SKILL.md` structure described in [OpenAI's official Skills guide](https://learn.chatgpt.com/docs/build-skills).

## One-time Wiki Skill installation

Users install only `wiki-repository-operator`. On its first CLI command, the operator checks once for a compatible sibling `wiki` Skill. If missing, it downloads the pinned company package `global-skills/wiki@1.0.0` from `http://10.40.2.15:2323`, verifies its SHA-256, installs it atomically, records successful completion, and then continues the original command.

After successful completion, normal operator commands read only the saved completion marker. They do not inspect the Wiki Skill directory and do not contact SkillHub again. A different installed copy of the operator receives its own first-use bootstrap marker.

The private marker is stored in `${XDG_CONFIG_HOME:-~/.config}/wiki-repository-operator/settings.json`. Set `WIKI_REPOSITORY_SKILLS_DIR` before first use only when the Wiki Skill must go into a different absolute skills directory. Set `WIKI_REPOSITORY_SKILLHUB_URL` when the company SkillHub address changes.

## Bootstrap

On first use, the Agent host must be able to reach the company SkillHub at `10.40.2.15:2323` and the Wiki Repository platform at `10.40.2.178:4004`.

```bash
python3 scripts/wiki_platform.py auth set-token --stdin
python3 scripts/wiki_platform.py auth status
python3 scripts/wiki_platform.py doctor
```

The first command installs the Wiki Skill and then continues token configuration. No separate dependency command is required.

Create the first `wkp_` personal access token in the Wiki Repository web page. Paste it into stdin or pipe it from a protected secret manager. The CLI stores it under `${XDG_CONFIG_HOME:-~/.config}/wiki-repository-operator/token` with mode `600`.

For this internal deployment, the user may send the PAT directly to the Agent in chat. The Agent must treat that message as authorization to run `auth set-token --stdin` itself, verify with `auth status` and `doctor`, and report success without asking the user to execute a command. The Agent does not repeat the PAT in its reply.

Never place the token directly after a command-line option.

## Change the server

```bash
python3 scripts/wiki_platform.py server set 10.40.2.179
python3 scripts/wiki_platform.py server show
python3 scripts/wiki_platform.py doctor
```

A bare IP uses port `4004`. The new address is saved only after service identity, OpenAPI, and health validation pass. Set `WIKI_REPOSITORY_URL` when an Agent runtime should manage the address externally.

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

See [Installation](references/installation.md), [Workflows](references/workflows.md), [Command Reference](references/api-actions.md), and [Security Model](references/security.md).
