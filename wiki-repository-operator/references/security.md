# Security model

## Trust boundary

The only supported production boundary is the platform's public reverse-proxy entry on port `4004`. The CLI must not connect to internal port `4003`, SSH, PostgreSQL, Docker sockets, or GitLab directly. Server-side role and resource checks remain authoritative even when a token contains the requested scope.

## Personal access token scopes

- `wiki:read`: discovery, files, downloads, search, Q&A, and change-request visibility
- `wiki:write`: sync, upload preview, and change-request submission; implies read
- `wiki:review`: approve or reject eligible change requests; implies read
- `workspace:manage`: create, bind, update, or archive Groups, Subgroups, and Wikis
- `access:manage`: resource grants and resource managers
- `personnel:manage`: members, personnel groups, employee roles, and personnel profiles
- `archives:manage`: list, restore, and permanently purge archives
- `integrations:manage`: GitLab/Jira settings and Jira imports
- `tokens:manage`: list, create, and revoke the owner's tokens
- `admins:manage`: grant or revoke platform administrators

A scope is necessary but never sufficient. The API rechecks current membership, employee role, platform-admin state, project grants, resource-manager state, and effective read/write access for every request. Disabling a Wiki member invalidates their PAT use. Delegated child tokens cannot exceed the parent token's scopes or expiration.

## Credential rules

- Never use the Webmanager password for Agent automation.
- An incoming user chat message is an allowed PAT bootstrap channel when the user intentionally supplies a `wkp_` value for configuration. Treat that message as explicit authorization to configure it immediately.
- Never pass full secrets in argv, JSON bodies accepted by generic commands, plan text, logs, or outgoing chat output. Do not repeat a chat-supplied PAT back to the user.
- Use stdin, a managed environment variable referenced by name, or a mode-`600` secret file.
- The CLI rejects symlinked token/config files and secret files readable by group or others.
- The local PAT file and confirmation plans are mode `600`; their directory is mode `700`.
- A created child PAT is written directly to a new mode-`600` file with exclusive creation and is never printed.
- Output redaction removes credential fields, `wkp_` values, and JWT-shaped strings.
- Authenticated HTTP requests never follow redirects, preventing bearer credentials from being forwarded to another URL.

An environment variable is convenient for Devin or CI secret management, but it remains present in the Agent process environment. Use the runtime's secret store and grant it only to the Agent that needs it.

## Mutation confirmation

Every platform mutation is blocked on first invocation. The CLI writes a one-time plan containing:

- target server
- operation and API path
- required scope and risk
- sanitized query/body fields
- expiration and a fingerprint of the exact operation

Plans never contain credential values. The second invocation must match the same server, path, body, query, and relevant local output path. A plan expires after ten minutes, is consumed before the request, and cannot be retried. Critical operations additionally require an exact phrase.

The CLI does not blindly retry any write request. If a network failure makes the outcome ambiguous, query the current state before planning another write.

## Risk levels

- `read`: no production mutation; retry is allowed only for GET and transient failures.
- `medium`: reversible or preview-oriented write; still requires a plan.
- `high`: resource, personnel, access, approval, archive, or credential-state change.
- `critical`: permanent purge, platform-admin change, or global integration change; requires an exact phrase.

Permanent archive purge has two confirmations: the API body `confirmation` must equal the archive's `full_path`, and the CLI requires `PERMANENTLY DELETE <kind> <id>`.

## Content handling

Read-only platform access filters any case-insensitive `secrets` directory from tree, file, and ZIP responses. Write-capable access may return such content; an Agent must still avoid disclosing it unless the user's exact request and context authorize disclosure.

Directory upload rejects symlinks and special files, removes every `.git` directory, limits inputs to 20,000 files and 200 MiB expanded, and fingerprints the generated ZIP before confirmation. ZIP extraction rejects traversal and symlink entries, writes into a new directory, and never overwrites an existing target.

## Audit attribution

The platform records the acting user, authentication type, and PAT identifier for audited mutations. It does not store the bearer token in audit metadata. Always verify a mutation through a follow-up read and report the observed result.
