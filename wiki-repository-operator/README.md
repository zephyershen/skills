# Wiki Repository Operator Skill

Production-ready Agent Skill and dependency-free Python CLI for the Wiki Repository platform. It lets Codex, Claude Code, Devin, and other Agent Skills-compatible tools use the same authenticated platform actions as the web UI.

Default server: `http://10.40.2.178:4004`. The default is intentionally committed for this internal-network deployment; credentials are never committed.

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

Clone this repository to a location available to the Agent, then copy or symlink the whole `wiki-repository-operator` directory. Do not copy only `SKILL.md`; the scripts and references are part of the Skill.

Claude Code personal skills live at `~/.claude/skills/<name>/SKILL.md`, and project skills at `.claude/skills/<name>/SKILL.md`, according to [Claude Code's official Skills documentation](https://code.claude.com/docs/en/skills).

```bash
ln -s /path/to/skills/wiki-repository-operator ~/.claude/skills/wiki-repository-operator
```

Devin recommends `.agents/skills/<name>/SKILL.md` in a connected repository and also recognizes several tool-specific skill directories, according to [Devin's official Skills documentation](https://docs.devin.ai/product-guides/skills).

```bash
mkdir -p .agents/skills
cp -R /path/to/skills/wiki-repository-operator .agents/skills/
```

For Codex, place the directory in the local Codex skills folder:

```bash
ln -s /path/to/skills/wiki-repository-operator ~/.codex/skills/wiki-repository-operator
```

The bundle follows the open Agent Skills `SKILL.md` structure described in [OpenAI's official Skills guide](https://developers.openai.com/api/docs/guides/tools-skills).

## Bootstrap

The Agent host must be able to reach `10.40.2.178:4004`.

```bash
python3 scripts/wiki_platform.py doctor
python3 scripts/wiki_platform.py auth set-token --stdin
python3 scripts/wiki_platform.py auth status
```

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
