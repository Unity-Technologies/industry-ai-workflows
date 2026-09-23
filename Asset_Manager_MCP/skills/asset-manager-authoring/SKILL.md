---
name: asset-manager-authoring
description: Usage guide for the Unity Asset Manager MCP — creating and versioning assets, uploading files and previews, metadata and field definitions, asset references (dependencies, relativePath, reference metadata), collections, and projects/orgs. Use when publishing or organizing assets in Asset Manager, and as the destination for the "then push it to Asset Manager" handoff that the at-scripting and at-upa-scripting skills defer to. NOT for the pipeline "Create asset"/"Add file" actions (see pipeline-authoring) and NOT for pxz scene work (see at-scripting).
---

# Asset Manager Authoring — MCP Usage Guide

Guide for driving the **Asset Manager MCP** (`Asset_Manager_MCP`) to publish and
organize assets in Unity Cloud. This is the endpoint both Asset Transformer skills
point at when they say "chain an Asset Manager action" / "push the result to
Asset Manager": once an AT workflow has produced a local file (GLB, FBX, etc.),
the tools here create the asset and upload it.

## Identity model — assets are addressed by name

Almost every tool takes **`asset_name`** as the primary handle, plus an
org/project scope. You rarely pass raw asset IDs:

- **Org / project scope** resolves in this order: explicit `org_id` / `project_id`
  args → `project_name` (resolved by name) → the session defaults set via
  `set_default_organization` / `set_default_project`.
- At the start of a session: `list_organizations` → ask the user → 
  `set_default_organization`, then `list_projects` → `set_default_project` (or
  `set_default_project_by_name`; offer `create_project` when none fits), then
  omit the scope on later calls.
- Discover scope with `list_organizations`, `list_projects`, `list_assets`.

## Authentication

The MCP authenticates the same way as Pipeline Automation:

- Run `unity_login` (browser PKCE) once; tokens are cached and refreshed automatically.
- Check state with `unity_auth_status`. If a call fails with an auth error, that's
  the first thing to verify — don't retry blindly.

## Core lifecycle — create, upload, freeze

The canonical publish flow:

1. **`create_asset`** — creates the asset, or a new uploadable version if it
   already exists. Returns the asset/version to upload into. `tags` must be a
   **list** (`["a", "b"]`). `asset_type` takes the dashboard's spaced values
   ("3D Model", "Prefab", "Scene", "Shader", ...; legacy unspaced spellings are
   mapped) — pick the specific type, and use `change_asset_type` to retype an
   existing asset. New assets default to "3D Model"; on a re-version, leaving
   it empty keeps the current type.
2. **`upload_files_to_asset`** — uploads local files to the current (unfrozen)
   version. `model_files` is a list of local paths. `freeze_after_upload=True`
   freezes in one step.
3. **`upload_preview_image_to_asset`** (optional) — uploads a thumbnail to the
   preview dataset. The asset must already exist with an unfrozen version.
4. **`freeze_asset`** — freezes the current version. **Freezing is required before
   a new version can be created.**
5. **`change_asset_status`** — advance the asset's status (e.g. to Published). If
   the requested status isn't directly reachable, the tool reports the reachable
   ones rather than forcing it. `get_asset_status` reads the current status and
   reachable transitions without changing anything.

Then **`get_asset_url`** returns the dashboard link — surface it to the user.

### New versions

To revise an existing asset: `create_new_draft_version` (or `create_asset` again
with the same name) → `upload_files_to_asset` → `freeze_asset`. You must freeze the
previous version before a new draft can be created.

### Bulk

- **`batch_upload_assets`** — create + upload many assets in one call.
- **`download_files_from_asset`** — pull an asset's files locally (e.g. to feed
  into an Asset Transformer `run_python` import).

## Metadata and field definitions

- **`update_asset_metadata`** — merges custom metadata fields into an asset
  (fields not supplied are left untouched).
- Custom fields must be **defined at the organization level first**. Manage them with
  `list_field_definitions`, `create_field_definition`, `delete_field_definition`.
  Setting metadata for an undefined field will not stick — define it first.
- **Labels** — `list_asset_labels` shows the labels on an asset's versions
  ("Latest"/"Pending" are system-assigned). User labels are fully manageable:
  `create_label` defines one at the org level, `assign_label`/`unassign_label`
  attach it to an asset's current version, `list_labels` shows the org's labels.
- **Finding assets** — `search_assets_across_projects` searches the whole org
  when you don't know which project holds an asset; `list_asset_versions` shows
  an asset's full version history including old frozen versions.
- **Deletion is recoverable by default** — `delete_asset` with
  `delete_all_versions=True` soft-deletes to the trash; `list_trashed_assets` +
  `restore_asset` bring things back. Pass `trash=False` only for a deliberate
  permanent removal.

## References (dependencies between assets)

Recently extended with `relativePath` and reference metadata — use them:

- **`add_asset_reference`** — link `source_asset_name` → `target_asset_name`
  within a project. Options:
  - `dependency_type` — the kind of dependency.
  - `target_label` — resolve the target by label.
  - `relative_path` — the path the source expects the target at (e.g. a texture's
    location relative to a model). Set this when the consumer needs the dependency
    laid out at a specific path.
  - `metadata` — arbitrary metadata on the reference itself.
  - The target version is **pinned to the current version by default**.
- **`list_asset_references`** — `context` = `source` | `target` | `both` (unrecognized values fall back to `both`).
- **`remove_asset_reference`** — drop a link.

## Collections

Organize assets into collection paths:
`list_collections`, `create_collection`, `delete_collection`,
`link_asset_to_collection`, `unlink_asset_from_collection`. `upload_files_to_asset`
and `batch_upload_assets` also accept a `collection_path` to place the asset on
upload.

## Projects & organizations

`list_organizations`, `list_projects`, `create_project`, `delete_project`,
`set_default_project`, `set_default_project_by_name`.

## The Asset Transformer → Asset Manager handoff

- **In-process (`at-scripting` / `run_python`):** the AT MCP writes a file to a
  local path; then call `create_asset` + `upload_files_to_asset` (this skill) to
  publish it. There is no direct "AT writes to AM" call — it's two steps.
- **In a pipeline (`at-upa-scripting`):** the custom-script action has no AM
  credentials, so you chain the pipeline's **`Create asset` / `Add file`** actions
  instead (see `pipeline-authoring`). That's a different mechanism from this MCP.

## Best practices

- Freeze a version before creating the next one; you can't upload into a frozen version.
- `tags` and other list-typed params must be arrays, not comma-strings.
- Define custom metadata fields before setting their values.
- Prefer resolving by name (`*_name`) and a session default project over threading
  IDs through every call — but pass explicit IDs when acting across projects.
- After publishing, return `get_asset_url` so the user can verify in the portal.
- Publishing an asset is outward-facing — confirm the target project with the user
  when it isn't already established in the conversation.

## Out of scope

- Pipeline `Create asset` / `Add file` **actions** and their parameters → see
  `pipeline-authoring` (`known-action-ids.md`). Those run inside a pipeline, not
  via this MCP.
- Writing/optimizing 3D scenes with pxz → see `at-scripting` (in-process) and
  `at-upa-scripting` (pipeline custom scripts).
