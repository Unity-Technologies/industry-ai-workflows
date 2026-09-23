# Pipeline Automation MCP

MCP server that exposes the [Unity Pipeline Automation REST API v1](https://services.docs.unity.com/automation/v1/) as AI-callable tools.

Covers the full pipeline lifecycle — create, version, trigger, monitor jobs, approve suspended steps, and retrieve logs — at both the organisation and project level.

---

> Part of the **Industry AI Workflows** Claude Code plugin marketplace. This
> plugin installs on its own — you do not need the other Unity plugins.
>
> ```text
> /plugin marketplace add Unity-Technologies/industry-ai-workflows
> /plugin install upa-mcp@industry-ai-workflows
> ```
>
> That is the whole install: the plugin's SessionStart hook builds this server's
> environment in the background on first use, and the server comes up in the next
> session. Everything below is the manual route, for non-Claude MCP clients or
> development.

## Prerequisites

- Python 3.11+
- A Unity account with the **Automation Developer** role (or equivalent read access for read-only tools); auth is a browser-based user login
- Network access to `automation.services.api.unity.com`

---

## Installation

This plugin's own installer is what the SessionStart hook runs:

```powershell
python install.py              # builds into this plugin's Claude Code data dir
python install.py --in-repo    # or build .venv here, for local development
```

To set the server up by hand instead, run these from the
`Pipeline_Automation_MCP` folder:

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
```

---

## Configuration

No configuration file is required. Authentication is a browser-based Unity user
login (PKCE): the first time you use the server, call the `unity_login` tool; a
browser window opens for you to sign in with your Unity account. Tokens are
cached under `~/.uap_mcp/token.json` (or `$UAP_MCP_HOME/token.json`) and
refreshed automatically. The cache is shared with the Asset Manager MCP server —
one login authenticates both, and `unity_logout` on either signs out both.

Org/project scope is chosen per session: discover organizations via the Asset
Manager MCP's `list_organizations`, then call `set_default_organization` and
`set_default_project` here (every tool also accepts explicit `org_id` /
`project_id` arguments).

> Never commit `.env` to source control.

---

## Starting the Server

```bash
python pa_mcp_server.py
```

The server runs over **stdio** by default, which is what Claude Desktop and most MCP clients expect.

---

## Tools Reference

### Organisation-Level Pipeline Tools

| Tool | Description |
|---|---|
| `create_pipeline` | Create a new pipeline and return its first draft version. Requires `name`, `description`, and `version`. Optionally supply steps, parameters, secrets, tags, and metadata. |
| `update_pipeline` | Update a pipeline's name, description, or tags. |
| `list_pipelines` | List all pipelines accessible to the organisation (owned and public). Supports `owned`, `offset`, and `limit` filters. |
| `list_pipeline_versions` | List all versions of a specific pipeline. |
| `get_pipeline_version` | Get full details of a pipeline version — steps, parameters, lifecycle status, and visibility. |
| `create_pipeline_version` | Create a new version of an existing pipeline, optionally based on an existing version. |
| `update_pipeline_version` | Update a draft pipeline version (steps, parameters, secrets, metadata). Only Draft versions can be edited. |
| `delete_draft_pipeline_version` | Permanently delete a Draft pipeline version that is not in use. |
| `publish_pipeline_version` | Change a pipeline version's visibility to `Private`, `Public`, or `Unlisted`. |
| `trigger_pipeline` | Trigger a pipeline run and return the created job. Accepts `inputs`, `secrets`, and `job_priority`. |
| `change_pipeline_status` | Change a pipeline version's lifecycle status (`Draft`, `Available`, `Deprecated`, `Archived`). |

---

### Project-Level Pipeline Tools

Identical in capability to the organisation-level tools but scoped to a specific project via `project_id`.

| Tool | Description |
|---|---|
| `create_project_pipeline` | Create a new project-level pipeline. |
| `update_project_pipeline` | Update a project pipeline's name, description, or tags. |
| `list_project_pipelines` | List all pipelines available within a project. |
| `list_project_pipeline_versions` | List all versions of a specific project pipeline. |
| `get_project_pipeline_version` | Get full details of a project pipeline version. |
| `create_project_pipeline_version` | Create a new version of a project pipeline. |
| `update_project_pipeline_version` | Update a draft project pipeline version. |
| `delete_draft_project_pipeline_version` | Delete a draft project pipeline version. |
| `trigger_project_pipeline` | Trigger a project pipeline and return the created job. |
| `change_project_pipeline_status` | Change the lifecycle status of a project pipeline version. |

---

### Organisation-Level Job Tools

| Tool | Description |
|---|---|
| `list_jobs` | List pipeline jobs for the organisation. Filter by `statuses`, `pipeline_ids`, sort with `order_by` / `order`, and paginate with `offset` / `limit`. Valid statuses: `Queued`, `Pending`, `Running`, `Succeeded`, `Failed`, `Error`, `Terminated`, `Suspended`, `Unknown`. |
| `get_job` | Get full details of a job including per-step status, inputs, outputs, and timing. |
| `get_job_stats` | Get running job count, queued job count, and the concurrency limit for the organisation. |
| `terminate_job` | Cancel a running or queued job. |
| `resume_job` | Resume a suspended job. |
| `approve_job_step` | Approve or reject a suspended step in a job. Supply `approved` (bool) and an optional `comment`. |

---

### Project-Level Job Tools

| Tool | Description |
|---|---|
| `list_project_jobs` | List pipeline jobs for a specific project with the same filtering options as `list_jobs`. |
| `get_project_job` | Get full details of a project job. |
| `terminate_project_job` | Cancel a running or queued project job. |
| `resume_project_job` | Resume a suspended project job. |
| `approve_project_job_step` | Approve or reject a suspended step in a project job. |

---

### Log Tools

| Tool | Description |
|---|---|
| `get_job_step_logs` | Retrieve logs for a specific step in an organisation-level job. |
| `get_project_job_step_logs` | Retrieve logs for a specific step in a project-level job. |

---

### App / Action Discovery Tools

| Tool | Description |
|---|---|
| `list_apps` | List the automation apps available to the organisation. |
| `list_app_versions` | List the versions of an app. |
| `get_app_version` | Get an app version, including its action definitions. |
| `get_app_action` | Get one action's definition — the authoritative input/output parameter list for a step's `actionId`. |

---

### Session & Auth Tools

| Tool | Description |
|---|---|
| `set_default_organization` | Set the session's default org (numeric genesis id — discover via the Asset Manager MCP's `list_organizations`). |
| `set_default_project` | Set the session's default project id. |
| `unity_login` | Trigger a browser-based PKCE login (shared with Asset Manager). |
| `unity_logout` | Clear the shared cached tokens — signs out both servers. |
| `unity_auth_status` | Report whether authenticated calls will succeed. |

---

## Common Patterns

**Trigger a pipeline and poll until complete:**

1. Call `trigger_pipeline` (or `trigger_project_pipeline`) → note the returned `id` (job ID).
2. Call `get_job` (or `get_project_job`) with that job ID to check `status`.
3. If `status` is `Suspended`, call `approve_job_step` to unblock it.
4. Once `status` is `Succeeded` or `Failed`, call `get_job_step_logs` for per-step output.

**Check organisation capacity before triggering:**

Call `get_job_stats` to see `runningJobs`, `queuedJobs`, and `concurrencyLimit` before submitting a high-volume batch.

---

