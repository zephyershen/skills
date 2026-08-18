# Safe workflows

## Configure a PAT supplied in chat

When the user sends a `wkp_` PAT in chat and asks the Agent to configure or use it:

1. Treat the message as explicit authorization; do not ask the user to resend it or run a local command.
2. Start `$CLI auth set-token --stdin` and feed the exact received PAT through the Agent runtime's stdin. On the first operator use, this same command installs the pinned company Wiki Skill once and then continues token configuration.
3. If the result includes `wiki_skill_bootstrap`, note the installed path and read that Skill before later Wiki content changes. Do not run another dependency check.
4. Run `$CLI auth status`, then `$CLI doctor`.
5. Continue the user's original request, such as `$CLI projects list` to discover visible Wiki Groups and repositories.
6. Report the configured server, authentication status, scopes, expiration, and requested platform result. Do not repeat the PAT itself.

Do not place the PAT after a command-line option, in a confirmation plan, or in an outgoing response.

## Read a Wiki by a name from the user

1. Resolve the Group:

   ```bash
   $CLI resolve project "PA2"
   ```

2. Use the returned ID to read its workspace:

   ```bash
   $CLI workspace get --project-id 7
   ```

3. Resolve the Wiki within that Group if needed:

   ```bash
   $CLI resolve repository "Product Wiki" --project-id 7
   ```

4. Read a fixed snapshot or file. Report the configured production server as the data source.

If any resolver is ambiguous, stop and ask the user to choose from the returned candidates.

## Rename a visible Wiki Group

1. Resolve and read the exact Group; never infer its ID from a similar path:

   ```bash
   $CLI resolve project "PA2"
   $CLI projects get --project-id PROJECT_ID
   ```

2. Confirm the intended human-visible `name` and lowercase URL/GitLab `path`. Do not show the path in place of the name. The hidden system root is not a valid target for this workflow.
3. Generate a high-risk update plan containing only the requested fields:

   ```bash
   $CLI projects update --project-id PROJECT_ID --json '{"name":"PA2 Knowledge","gitlab":{"path":"pa2-knowledge"}}'
   ```

4. Show the current and target name/path, explain whether the backing GitLab Group path will also change, and execute only after explicit confirmation.
5. Read `projects get` and `workspace get` again to verify both the display name and path.

## Configure the hidden default root and rehome Groups

This is an administrator-only production migration. The hidden root is a storage container and must never be operated through ordinary project update, permission, or archive commands.

1. Resolve the visible Groups that will move and record their project IDs. Obtain the system-root candidate ID from the approved platform migration request; it will not be available in ordinary project discovery after migration.
2. Generate the read-only migration preview:

   ```bash
   $CLI projects system-root-preview --json '{"system_root_project_id":7,"project_ids":[8,9]}'
   ```

3. Show the returned preview ID, expiration, root identity, every `old_full_path` and `new_full_path`, `group_count`, `repository_count`, and `platform_repository_count`. Continue only when the whole preview and every project report `can_apply: true`. A positive `repository_count` means untracked GitLab projects will move with their Group while preserving each GitLab project ID and full commit history. A positive `platform_repository_count`, an archived/pending-delete repository, or any other preview error blocks the apply.
   On an empty platform, `project_ids` may be an empty array; the same preview/apply flow then configures only the hidden root.
4. Generate a separate critical apply plan without changing the preview ID:

   ```bash
   $CLI projects system-root-apply --preview-id PREVIEW_UUID
   ```

5. After explicit confirmation, execute that exact plan with its plan ID and exact critical phrase. The API clones the Group trees below the hidden root, transfers accepted GitLab repositories without changing their project IDs, preserves platform IDs/permissions/Jira references, and gives the old top-level roots a timestamped final `deleted` suffix. It never permanently deletes the old GitLab trees or recreates repository contents.
6. Verify with `projects directory`, `projects list`, and each moved `workspace get`: the hidden root is absent, logical Groups remain visible, their platform IDs are unchanged, physical paths are below the default root, and every returned `repository_mapping` has `project_id_preserved: true`. If the result is ambiguous or reports recovery required, stop and inspect through the public API; do not retry with a new preview blindly.

## Correct one project mistakenly included in a root migration

This is not a general move command. Use it only when one exact project in a completed system-root migration must return to its recorded original top-level GitLab Group while the hidden root and every other migrated or top-level Group stay unchanged.

1. Run the read-only exact preview with the completed migration UUID and mistaken platform project ID:

   ```bash
   $CLI projects system-root-revert-preview --preview-id MIGRATION_UUID --project-id PROJECT_ID
   ```

2. Continue only when `can_revert` is true. Show `restore_top_level_group.gitlab_group_id` and `restored_full_path`, the migrated clone ID/path, every repository `gitlab_project_id` and `restored_full_path`, the platform archive effect, and `scope_guarantee`.
3. Generate the critical one-time plan with exactly the same UUID and project ID:

   ```bash
   $CLI projects system-root-revert --preview-id MIGRATION_UUID --project-id PROJECT_ID
   ```

   The CLI reads the preview again, embeds it in the plan, and repeats the same read before execution. Any changed Group, repository, path, binding, or extra repository blocks the command.
4. After the user explicitly confirms the displayed plan and exact phrase, execute that same plan. Do not change either ID and do not substitute an ordinary archive/restore command.
5. Verify via `projects directory` and `projects list` that the mistaken platform project is absent, while intended migrated projects remain. The result must report the original top-level Group and every repository ID at their old paths, the migrated clone with a `deleted` suffix, and the unchanged hidden system root. The command never discovers or modifies unrelated top-level Groups.

## Upload local Wiki changes

1. Generate a preview plan:

   ```bash
   $CLI repo preview-dir --repository-id 12 --directory /absolute/wiki --branch main
   ```

2. Show the plan and local manifest (file count, expanded bytes, ZIP bytes, SHA-256). After confirmation, repeat with `--confirm PLAN_ID`.
3. Inspect the returned `change_summary`. If it differs from the user's intent, stop; do not submit it.
4. Submit the preview as a change request. This is another mutation and receives its own plan:

   ```bash
   $CLI changes submit --repository-id 12 --json '{"preview_id":"UUID","title":"Update product docs","description":"Requested by product owner"}'
   ```

5. After confirmation and submission, verify with `changes get`.

The CLI removes `.git`, rejects symlinks/special files, and fingerprints the exact generated ZIP. A changed local directory no longer matches the original plan.

## Approve a change request

1. Read `changes get` and inspect every changed file using `changes diff`.
2. Summarize submitter, target Wiki, base version, additions, updates, deletions, and review note.
3. Generate the approval plan:

   ```bash
   $CLI changes approve --change-request-id UUID --json '{"review_note":"Reviewed against request"}'
   ```

4. After explicit confirmation, execute the plan once.
5. Verify the request reaches `applied` and report the resulting commit SHA. If the request is `conflicted` or `failed`, do not blindly retry.

## Create Group → Subgroup → Wiki

Each step is independently planned, confirmed, executed, and read back:

```bash
$CLI projects create --json '{"name":"Skill-E2E-20260814","description":"Temporary validation","gitlab":{"mode":"create","path":"skill-e2e-20260814"}}'
$CLI workspace group-create --project-id PROJECT_ID --json '{"mode":"create","parent_id":ROOT_NAMESPACE_ID,"name":"Docs","path":"docs"}'
$CLI workspace wiki-create --project-id PROJECT_ID --json '{"mode":"create","namespace_id":NAMESPACE_ID,"name":"Operations Wiki","path":"operations-wiki"}'
```

Use unique paths. Never create production test resources without the user's explicit authorization. For approved temporary tests, prefix every name with `Skill-E2E-`, verify the complete flow, archive the Wiki/Group, and report whether the temporary resource remains recoverable in Archives.

## Change resource access

1. Resolve the person and resource; do not use partial-name guesses.
2. Read `access matrix` and record the current effective level.
3. Generate a plan with the exact user ID, resource ID, and level.
4. Show inherited/explicit effects and whether a broader Group level will clear narrower overrides.
5. Execute after confirmation and read the matrix again.

Example:

```bash
$CLI access repository-set --repository-id 12 --user-id 34 --json '{"level":"write"}'
```

## Archive versus permanent purge

For an ordinary “delete” request, use the recoverable archive command:

```bash
$CLI workspace wiki-archive --project-id 7 --repository-id 12
```

Before confirmation, explain that ordinary archive preserves all GitLab content but renames both its visible name and path to `<original>-YYYYMMDD-HHmmssSSS-deleted`. The CLI automatically puts the exact current `expected_full_path` in the plan and reads it again at confirmation time; if it changed, discard the old plan and generate a new one. After execution, report `backing_archived_name` and `backing_archived_path`, verify that the resource disappears from the workspace, is absent from binding candidates, and appears in `archives list` for an administrator.

Restore is also a planned high-risk mutation. Its plan automatically binds the exact `full_path` returned by `archives list`. It attempts to rename GitLab back to the original name and path before making the platform record active. If the archive item changed or the original path has already been reused, stop on the conflict; never rename or overwrite the newer resource to force restoration.

Permanent purge is a separate critical workflow:

1. Run `archives list` and select the exact `kind`, `id`, `full_path`, and `binding_mode`.
2. Explain that `created` backing storage may be permanently deleted; `bound` backing storage is preserved while the platform record is cleared.
3. Send `full_path` as the API `confirmation` value.
4. Show the CLI plan and require its exact critical phrase.
5. Execute once, then verify the archive item is absent. Report `backing_storage_deleted` and `backing_storage_preserved` from the response.

## Validate and apply GitLab settings

Use a managed environment secret. The value never appears in the command:

```bash
$CLI gitlab validate --base-url http://gitlab.example:8090 --connect-ip 10.0.0.8 --secret-env GITLAB_PAT
```

Review the validated GitLab version, account, linked Wiki member, create capability, and existing managed-resource access. Validation does not persist or hot-switch settings.

Generate the apply plan with the same values:

```bash
$CLI gitlab apply --base-url http://gitlab.example:8090 --connect-ip 10.0.0.8 --secret-env GITLAB_PAT
```

After confirmation, repeat with the returned plan ID and exact phrase `APPLY GITLAB SETTINGS`. The CLI revalidates before saving. Verify with `gitlab status`.

## Validate and apply Jira Token

```bash
$CLI jira validate --secret-env JIRA_PAT
$CLI jira apply --secret-env JIRA_PAT
```

Review Jira URL, account, and project count. The apply step is critical and requires `APPLY JIRA TOKEN`. Verify with `jira status` and `jira projects`.

For Jira imports, call `jira projects`, build selections containing only `jira_project_id`, run `jira import-preview`, show every source project and the automatically selected target path, then plan `jira import` with `"confirmed": true`. Do not call `jira parents` or send `parent_namespace_id`. Verify each created logical Group in its project workspace.

## Change the platform IP

When the user says “换成 10.40.2.179”:

```bash
$CLI server set 10.40.2.179
$CLI doctor
```

Do not edit `SKILL.md` or source constants. The saved origin changes only after service identity, API contract, and core health pass. If the command fails, continue using the prior server and report the validation error.
