# Installation and bootstrap

## Prerequisites

- Python 3.10 or newer; no third-party package is required.
- One-time network access from the Agent runtime to the company SkillHub at `http://10.40.2.15:2323`.
- Network access from the Agent runtime to `http://10.40.2.178:4004`.
- A Wiki Repository account already added as an enabled Wiki member.
- A `wkp_` personal access token created by that user in the web page.

The web login password is not an Agent credential and must not be placed in this Skill.

## Download from the company SkillHub

The SkillHub CLI defaults to localhost. Point it at the company server for both health checks and installation:

```bash
SKILLHUB_API_URL=http://10.40.2.15:2323 skillhub doctor --json
SKILLHUB_API_URL=http://10.40.2.15:2323 \
  skillhub install global-skills/wiki-repository-operator@1.2.0 --dir /path/to/downloads
```

The installed directory is `/path/to/downloads/global-skills/wiki-repository-operator/`. Move or symlink that complete directory to one of the Agent locations below; do not move only `SKILL.md`.

## Install the complete bundle

Keep the directory structure intact:

```text
wiki-repository-operator/
├── SKILL.md
├── scripts/wiki_platform.py
├── scripts/wiki_repository/
└── references/
```

Supported placements:

- Claude Code personal: `~/.claude/skills/wiki-repository-operator/`
- Claude Code project: `.claude/skills/wiki-repository-operator/`
- Devin recommended project location: `.agents/skills/wiki-repository-operator/`
- Codex user location: `~/.agents/skills/wiki-repository-operator/`

For Devin, commit the complete directory into a connected repository. For a shared Claude or Codex installation, symlink the complete directory from a centrally updated checkout.

## Automatic Wiki Skill dependency

The user installs only the currently published `global-skills/wiki-repository-operator@1.2.0`. The first CLI command performs this sequence before continuing the requested platform command:

1. Read the private bootstrap completion marker.
2. When the marker is absent, check the sibling `wiki/` directory once.
3. If missing, download the exact public package `global-skills/wiki@1.0.0` from the company SkillHub.
4. Verify SHA-256 `43837e035d6d58e3ea9d44c57d3fa9f077ce940fc3ffdee7a171b536b8e18678`, validate the archive, and install it atomically beside this Skill.
5. Write the completion marker only after the Wiki Skill is ready.
6. Continue the original command in the same invocation.

Later normal commands trust the completion marker and its first resolved install path; they do not recompute a different default path, inspect `wiki/`, or contact SkillHub. A failed first installation writes no completion marker, so the next invocation retries. An incompatible pre-existing `wiki/` directory is never overwritten.

The completion marker is kept in `${XDG_CONFIG_HOME:-~/.config}/wiki-repository-operator/settings.json`. `WIKI_REPOSITORY_SKILLS_DIR` can select another absolute destination before first use. `WIKI_REPOSITORY_SKILLHUB_URL` or the compatible `SKILLHUB_API_URL` can replace the company SkillHub root before first use.

## Create the first token

In the Wiki Repository web page:

1. Open Account → Personal Access Tokens.
2. Name the token after the Agent and host, not after a person-only label.
3. Select the least scopes needed. “内容协作” is suitable for read/upload/change-request work; system operations require an administrator-owned token with explicitly selected management scopes.
4. Choose an expiration. Prefer a finite period for unattended Agent environments.
5. Send the token directly to the Agent in chat, or copy it into the Agent runtime's protected secret channel.

When the user sends a `wkp_` PAT in chat and asks the Agent to configure it, the Agent must perform the following commands itself. It must not ask the user to run them manually or resend the token:

Store and verify through stdin:

```bash
python3 "$SKILL_DIR/scripts/wiki_platform.py" auth set-token --stdin
python3 "$SKILL_DIR/scripts/wiki_platform.py" auth status
python3 "$SKILL_DIR/scripts/wiki_platform.py" doctor
```

The chat message is an allowed bootstrap transport in this internal deployment. The Agent feeds the received value to `auth set-token --stdin`, does not put it in a command-line argument, and does not repeat it in the result.

If this is the first operator command, `auth set-token --stdin` installs the Wiki Skill first and then continues to save and validate the PAT. The JSON response includes `wiki_skill_bootstrap` only for that first successful bootstrap.

For managed Agent secrets, set `WIKI_REPOSITORY_TOKEN`. The environment value takes precedence over the private token file.

## Configuration files

Default directory: `${XDG_CONFIG_HOME:-~/.config}/wiki-repository-operator`

- directory mode: `700`
- `settings.json`: mode `600`, contains only the server origin
- `token`: mode `600`, contains the platform PAT
- `plans/*.json`: mode `600`, contains short-lived redacted confirmation plans

Set `WIKI_REPOSITORY_CONFIG_DIR` to use another absolute config directory. Set `WIKI_REPOSITORY_URL` to manage the server externally; it overrides `server set`.

## Change IP or URL

```bash
python3 "$SKILL_DIR/scripts/wiki_platform.py" server set 10.40.2.179
```

Bare IP input becomes `http://10.40.2.179:4004`. Complete `http://` and `https://` roots are accepted. A root ending in `/api` is normalized automatically. User information, query strings, fragments, and other paths are rejected.

`server set` verifies `/service/meta`, `/api/openapi.json`, and `/api/health` before changing local configuration. Failed validation leaves the previous server unchanged.

## Upgrade

Update the Skill checkout, run the bundled tests, then run `doctor`:

```bash
python3 -m unittest discover -s "$SKILL_DIR/tests" -v
python3 "$SKILL_DIR/scripts/wiki_platform.py" doctor
```

Do not preserve a modified default IP by editing source. Use `server set` or `WIKI_REPOSITORY_URL`, so future upgrades remain clean.
