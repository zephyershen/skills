# Command reference

All examples assume:

```bash
CLI="python3 $SKILL_DIR/scripts/wiki_platform.py"
```

The CLI emits one JSON object to stdout. Errors are JSON on stderr. Exit code `3` means a mutation plan is waiting for user confirmation; it does not mean the platform changed.

## Common input rules

- IDs use explicit options such as `--project-id`, `--repository-id`, `--namespace-id`, `--user-id`, `--change-request-id`, or `--id`.
- Query parameters use repeatable `--param KEY=VALUE`.
- Non-secret request bodies use `--json '{...}'` or `--json-file /path/body.json`.
- Secret values use only `--secret-stdin`, `--secret-env NAME`, or `--secret-file PATH`.
- Mutation confirmation adds `--confirm PLAN_ID`; critical actions also add `--confirm-text 'EXACT TEXT'`.

Use `--help` on any command for its exact required options.

## Service and identity

| Goal | Command |
|---|---|
| Full readiness check | `doctor` |
| Show server | `server show` |
| Change IP | `server set 10.40.2.179` |
| Restore default | `server reset` |
| Save bootstrap PAT | `auth set-token --stdin` |
| Verify PAT/profile | `auth status` |
| Remove stored PAT | `auth clear` |

## Tokens (`tokens:manage`)

- `tokens capabilities`
- `tokens list`
- `tokens create --json '{"name":"Claude Agent","scopes":["wiki:read","wiki:write"],"expires_in_days":90}' --save-token /secure/new.token`
- `tokens revoke --token-id UUID`

The `tokens create` response never prints the new token. The output file must not already exist.

## Discovery and workspace

- `projects list` (`wiki:read`)
- `projects explorer` (`wiki:read`)
- `projects directory` (`workspace:manage`)
- `projects get --project-id ID` (`wiki:read`)
- `projects create --json '{"name":"PA2","description":"Team Wiki","gitlab":{"mode":"create","path":"pa2"}}'` (`workspace:manage`)
- `projects update --project-id ID --json '{"description":"Updated"}'` (`workspace:manage`, high risk)
- `projects system-root-preview --json '{"system_root_project_id":7,"project_ids":[8,9]}'` (administrator-only migration preview)
- `projects system-root-apply --preview-id UUID` (critical; exact phrase comes from the plan)
- `workspace get --project-id ID --param reconcile=false` (`wiki:read`)
- `workspace group-candidates --project-id ID --param parent_id=NS_ID --param search=platform`
- `workspace wiki-candidates --project-id ID --param namespace_id=NS_ID`
- `workspace group-create --project-id ID --json '{"mode":"create","parent_id":NS_ID,"name":"Platforms","path":"platforms"}'`
- `workspace wiki-create --project-id ID --json '{"mode":"create","namespace_id":NS_ID,"name":"Product Wiki","path":"product-wiki"}'`
- `workspace wiki-archive --project-id ID --repository-id REPO_ID`
- `workspace group-archive --project-id ID --namespace-id NS_ID`

Ordinary archive keeps GitLab content but changes the backing name and path to a Shanghai timestamped `-deleted` identity. Before creating and consuming the confirmation plan, the CLI reads the selected resource and automatically binds its exact current `expected_full_path`; callers do not need to supply that field manually. A changed or missing target requires a new plan. The response returns the resulting backing name/path. Archived identities are omitted from Group/Subgroup/Wiki binding candidates. `archives restore` applies the same path binding, tries to reclaim the original GitLab name/path, and fails safely if either is no longer available.

Binding existing objects uses opaque references returned by candidate endpoints:

- logical Wiki Group: `{"gitlab":{"mode":"bind","group_reference":"default-root/full/path"}}` using a candidate returned by `gitlab namespaces`
- Subgroup: `{"mode":"bind","parent_id":NS_ID,"group_reference":"full/path"}`
- Wiki: `{"mode":"bind","namespace_id":NS_ID,"repository_reference":"full/path"}`

Before renaming a Wiki Group, read it with `projects get`. `name` is the human-visible label and `path` is the lowercase URL/GitLab path; do not display the path as the name. Show the current and target values for both fields and whether the backing GitLab Group path will change before asking for confirmation.

The hidden system root never appears in ordinary project discovery and cannot be read, renamed, archived, or granted to a person through normal commands. New logical Wiki Groups are always created directly below it; the request body has no parent selector. Configure or migrate it only through the dedicated preview/apply commands above. The preview must report `can_apply: true` for every project. `repository_count` is the number of untracked GitLab projects that will transfer with their original project IDs and history; `platform_repository_count` must be zero.

## Wiki content and changes

- `repo tree --repository-id ID --param ref=main`
- `repo snapshot --repository-id ID --param revision=COMMIT_OR_BRANCH`
- `repo file --repository-id ID --param path=docs/readme.md --param ref=main`
- `repo commits --repository-id ID --param page=1`
- `repo download --repository-id ID --revision COMMIT --output /new/path/wiki.zip`
- `repo extract --archive /path/wiki.zip --destination /new/directory`
- `repo sync --repository-id ID`
- `repo preview-dir --repository-id ID --directory /path/to/wiki --branch main`
- `changes submit --repository-id ID --json '{"preview_id":"UUID","title":"Update docs","description":"Reason"}'`
- `changes list --param status=pending_review --param limit=50`
- `changes get --change-request-id UUID`
- `changes diff --change-request-id UUID --param path=docs/readme.md`
- `changes approve --change-request-id UUID --json '{"review_note":"Reviewed"}'`
- `changes reject --change-request-id UUID --json '{"review_note":"Reason is required"}'`

## Knowledge (`wiki:read`)

- `knowledge graph --project-id ID`
- `knowledge backlinks --project-id ID --document-id DOC_ID`
- `knowledge search --project-id ID --param q=release --param repository_id=REPO_ID`
- `knowledge ask --project-id ID --json '{"question":"How is release approval handled?","repository_id":REPO_ID}'`
- `knowledge ask-stream --project-id ID --json '{"question":"..."}'`

Streaming output is JSON Lines: one object per SSE event followed by a completion summary.

## Personnel (`personnel:manage`)

- `people list`
- `people candidates --param page=1 --param page_size=20 --param search=alex`
- `people add --json '{"directory_user_ids":[12,13]}'`
- `people group-create --json '{"name":"QA","parent_id":null}'`
- `people group-update --id ID --json '{"name":"Platform QA","parent_id":PARENT_ID}'`
- `people group-delete --id ID`
- `people user-update --id USER_ID --json '{"personnel_group_id":GROUP_ID,"employee_role":"task_leader"}'`
- `people management-get --id USER_ID`
- `people management-set --id USER_ID --json-file /path/complete-profile-and-access.json`
- `people admin-grant --id USER_ID` (`admins:manage`, critical)
- `people admin-revoke --id USER_ID` (`admins:manage`, critical)

## Resource access (`access:manage`)

- `access matrix`
- `access project-set --project-id ID --user-id USER_ID --json '{"level":"write"}'`
- `access project-batch --project-id ID --json '{"user_ids":[2,3],"level":"read"}'`
- `access namespace-set --namespace-id ID --user-id USER_ID --json '{"level":"write"}'`
- `access namespace-batch --namespace-id ID --json '{"user_ids":[2,3],"level":"none"}'`
- `access repository-set --repository-id ID --user-id USER_ID --json '{"level":"write"}'`
- `access repository-batch --repository-id ID --json '{"user_ids":[2,3],"level":"read"}'`
- `access resource-manager --project-id ID --user-id USER_ID --json '{"enabled":true}'`

Always read `access matrix` first and verify it again after a permission write.

## Archives (`archives:manage`)

- `archives list`
- `archives restore --kind repository --id ID`
- `archives purge --kind repository --id ID --json '{"confirmation":"FULL_PATH_FROM_ARCHIVES_LIST"}'`

Permanent purge also requires the CLI critical phrase returned by the plan. Never derive `full_path` from a guessed name; use `archives list`.

## GitLab and Jira (`integrations:manage`)

- `gitlab status`
- `gitlab namespaces --param search=team`
- `gitlab validate --base-url http://gitlab.example --connect-ip 10.0.0.8 --secret-env GITLAB_PAT`
- `gitlab apply --base-url http://gitlab.example --connect-ip 10.0.0.8 --secret-env GITLAB_PAT`
- `jira status`
- `jira validate --secret-env JIRA_PAT`
- `jira apply --secret-env JIRA_PAT`
- `jira clear`
- `jira projects`
- `jira import-preview --json-file /path/jira-items.json`
- `jira import --json '{"items":[{"jira_project_id":"12618"}],"confirmed":true}'`

`gitlab apply` and `jira apply` validate the supplied credential before producing a mutation plan, validate it again before execution, and never include it in plan or output.

Jira imports always use the hidden default storage root. Do not call `jira parents` in a normal workflow and never send `parent_namespace_id`; that compatibility endpoint returns no selectable destinations.

## Name resolution

- `resolve project 'PA2'`
- `resolve repository 'Product Wiki' --project-id ID`
- `resolve person 'alex.hu'`

Exact case-insensitive names win, followed by prefixes, then substrings. Multiple equally ranked matches return `ambiguous_object`; require the user to choose.

## Forward-compatible reads

`raw get /new-read-endpoint --param key=value` is restricted to GET and relative `/api` paths. Never use it to emulate a write or to call an absolute URL.
