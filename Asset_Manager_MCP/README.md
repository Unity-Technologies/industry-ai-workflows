# Asset Manager MCP

MCP server that exposes Unity Cloud Asset Manager capabilities for org, project, asset, collection, reference, and metadata management.

Main entrypoint: `am_mcp_server.py`

## Prerequisites

- Python 3.11+
- A Unity account (auth is a browser-based user login)
- Network access to `services.api.unity.com` and `services.unity.com`

No private package index required — the server uses the Unity Cloud REST API directly via `requests`.

## Install

Run from the `Asset_Manager_MCP` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Or use the repo-level installer (installs all three MCPs; requires Python 3.12):

```powershell
cd ..
python install.py
```

## Configure

No configuration file is required. Authentication is a browser-based Unity user
login (PKCE): the first time you use the server, call the `unity_login` tool; a
browser window opens for you to sign in with your Unity account. Tokens are
cached under `~/.uap_mcp/token.json` (or `$UAP_MCP_HOME/token.json`) and
refreshed automatically. The cache is shared with the Pipeline Automation MCP
server — one login authenticates both, and `unity_logout` on either signs out both.

Org/project scope is chosen per session: `list_organizations` → ask the user →
`set_default_organization`, then `list_projects` → `set_default_project` /
`set_default_project_by_name` (or `create_project`). Every tool also accepts
explicit `org_id` / `project_id` arguments.

## MCP Client Setup

Point your MCP client at the venv Python and the server script:

```json
{
  "mcpServers": {
    "asset_manager": {
      "command": "C:\\path\\to\\Asset_Manager_MCP\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\Asset_Manager_MCP\\am_mcp_server.py"]
    }
  }
}
```

Replace `C:\\path\\to\\Asset_Manager_MCP` with the actual path.

## Tools

### Org / Project

| Tool | Description |
|---|---|
| `list_organizations` | List all orgs visible to the authenticated identity (numbered list) |
| `set_default_organization` | Set the session's default org (by id or name) after asking the user |
| `list_projects` | List projects in an org |
| `create_project` | Create a new Asset Manager project |
| `delete_project` | Permanently delete a project (archive + delete; requires org Owner/Manager and `confirm=True`) |
| `set_default_project` | Set the default project ID for this server process |
| `set_default_project_by_name` | Set the default project by name |

### Asset Lifecycle

| Tool | Description |
|---|---|
| `create_asset` | Create a new asset, or a new draft version if the asset already exists. Accepts `asset_type` (the dashboard's 18 types, e.g. "3D Model", "Prefab", "Scene"; legacy unspaced spellings are mapped), optional `metadata`, and re-applies tags/description/type on re-versions |
| `create_new_draft_version` | Explicitly create a new draft version for an existing asset |
| `update_asset` | Update name, description, or tags on an unfrozen asset version |
| `change_asset_type` | Change an existing asset's type (primaryType) without creating a version |
| `freeze_asset` | Lock a draft version (required before creating a new version or adding references). Accepts an optional `change_log` shown in the version history |
| `delete_asset` | Delete an unfrozen draft version, or remove the entire asset (`delete_all_versions=True`) — soft-deletes to the recoverable trash by default (`trash=False` for permanent). Accepts `asset_id` directly to avoid name ambiguity |
| `get_asset_status` | Read an asset's current status and the reachable transitions |
| `change_asset_status` | Transition an asset to a reachable workflow status |
| `assign_status_flow` | Assign an org status flow to an unfrozen version (`list_status_flows` shows the org's flows) |

### Upload / Download

| Tool | Description |
|---|---|
| `upload_files_to_asset` | Upload local files to the source dataset of an asset version |
| `upload_preview_image_to_asset` | Upload a preview image to the preview dataset |
| `download_files_from_asset` | Download all files from an asset's source dataset to a local folder |
| `batch_upload_assets` | Create and upload multiple assets in one call. Each entry supports `name`, `file`, `tags`, and `type`; a `default_asset_type` applies to entries without an explicit type |

### Asset Info

| Tool | Description |
|---|---|
| `get_asset` | Look up an asset by name — full details: type, status, description, tags, metadata, version number, change log, authorship, preview URL |
| `get_asset_url` | Get the Asset Manager dashboard URL for an asset |
| `list_assets` | List all assets in a project, including custom metadata. Supports `metadata_filter` |
| `search_assets_across_projects` | Search every project in the org at once — each match reports the project(s) it lives in |
| `list_asset_versions` | List ALL versions of an asset, including older frozen ones, with change logs |

### Trash & Sharing

| Tool | Description |
|---|---|
| `list_trashed_assets` | List soft-deleted assets in the project trash |
| `restore_asset` | Restore trashed assets back into the project |
| `link_asset_to_project` | Share an asset into another project in the same org (optionally with everything it references) |

### Collections

| Tool | Description |
|---|---|
| `list_collections` | List all collections in a project |
| `create_collection` | Create a top-level or nested collection (`parent_collection_path`) |
| `update_collection` | Rename or re-describe a collection |
| `move_collection` | Move a collection under a new parent |
| `delete_collection` | Delete a collection (assets are not deleted) |
| `link_asset_to_collection` | Add an asset to a collection |
| `unlink_asset_from_collection` | Remove an asset from a collection |

### References

| Tool | Description |
|---|---|
| `add_asset_reference` | Add a dependency reference from one asset to another |
| `list_asset_references` | List incoming, outgoing, or all references for an asset (incl. relativePath and reference metadata) |
| `update_asset_reference` | Update a reference in place — retarget to a version or label, change type/path/metadata |
| `remove_asset_reference` | Remove a specific reference |

### Metadata

| Tool | Description |
|---|---|
| `update_asset_metadata` | Set or update custom metadata fields on an asset version. Pass `null` as a value to remove that field |
| `list_field_definitions` | List all custom metadata field definitions for an org (incl. Active/Deleted status) |
| `create_field_definition` | Create a custom metadata field (TEXT, NUMBER, BOOLEAN, SELECTION, TIMESTAMP, URL, USER) |
| `update_field_definition` | Change a field's display name or accepted values (replace, add, or remove) without delete + recreate |
| `delete_field_definition` | Delete a custom metadata field definition |

### Labels

| Tool | Description |
|---|---|
| `list_asset_labels` | Show the labels on an asset's versions. "Latest" and "Pending" are system-assigned; user labels appear here too |
| `list_labels` | List the labels defined in the org (system and user) |
| `create_label` | Create a user label (name, description, optional colour) |
| `assign_label` / `unassign_label` | Attach or detach user labels on an asset's current version ("Latest"/"Pending" are restricted) |

### Auth

| Tool | Description |
|---|---|
| `unity_login` | Trigger a browser-based PKCE login |
| `unity_logout` | Clear the cached Unity user-login tokens |
| `unity_auth_status` | Report whether authenticated calls will succeed |
| `check_entitlements` | Report the user's Asset Manager license seats in an org (diagnoses 402 quota errors — orgs without seats get only the free 10 GB baseline) |

## Example Workflow

```
1. list_organizations          → pick your org
2. set_default_project_by_name → avoids passing IDs every call
3. create_asset                → creates a draft version (returns id + version)
4. upload_files_to_asset       → attach files; optionally freeze after upload
5. upload_preview_image_to_asset (optional)
6. update_asset_metadata       → set custom fields (e.g. source_format, lod_count)
7. add_asset_reference         → link related assets
8. link_asset_to_collection    → organise into a folder
9. freeze_asset                → lock the version when finalized
```

## Notes

- `delete_project` permanently deletes a project (archive + delete, the same flow as the dashboard). It requires org Owner/Manager and `confirm=True`; without confirm it returns a summary of what would be deleted.
- Field definitions are soft-deleted: a deleted key cannot be immediately reused (propagation delay).
- Frozen asset versions cannot be deleted individually; use `delete_asset(delete_all_versions=True)` to unlink the entire asset from the project.
- If upload errors mention encoding/charmap, rename local file paths to ASCII-only names and retry.
- "Latest" and "Pending" are system-assigned labels and cannot be attached or detached by hand; user-created labels (see the Labels section above) can.
