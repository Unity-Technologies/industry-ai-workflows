# Unity Pipeline Automation v1 — REST API Reference

Distilled reference for the Pipeline Automation v1 REST API, the service behind
the Pipeline Automation MCP server in this repo (`Pipeline_Automation_MCP/`).
The MCP tools hide the HTTP layer, so use this file for what the tool schemas
don't tell you: valid enum values, response shapes, filter parameters, and
error semantics. For the pipeline JSON *authoring* format (steps, pickers,
fan-out, template expressions) see `SKILL.md`; for verified action IDs see
`known-action-ids.md`.

- **Base URL:** `https://automation.services.api.unity.com/v1`
- **Auth:** Unity user token (Client) or Service Account (this plugin ships user-login only). Mutating operations
  (create/update/publish/delete, reading logs) require the **Automation
  Developer** role in the organization.
- All routes below are relative to the base URL. Every org-level route has a
  project-scoped twin nested under `/organizations/{organizationId}/projects/{projectId}/...`
  (the MCP `_project_` tool variants).

---

## Common conventions

### Pagination

List endpoints take `offset` (items to skip) and `limit` (max items) query
parameters and return:

```json
{ "offset": 0, "limit": 50, "total": 123, "results": [ ... ] }
```

There is no cursor; page by incrementing `offset` until `offset + len(results) >= total`.

### Error responses

Non-2xx responses use the RFC 7807 problem-details shape:

```json
{ "type": "...", "title": "...", "status": 400, "detail": "...", "instance": "..." }
```

The MCP wrappers surface this as `HTTP <status> <reason> — <detail JSON>`.

| Status | Typical meaning |
|---|---|
| `400` | Request body / parameter has the wrong format (schema violation, bad GUID, constraint breach — see the HTTP 400 gotchas in `SKILL.md`) |
| `401` | Not authenticated (token missing/expired — re-run `unity_login`) |
| `403` | Authenticated but no permission on the org/project/resource, or missing the Automation Developer role |
| `404` | Org, project, pipeline, version, job, or step id does not exist (also returned for ids you cannot see) |
| `409` | Conflict: version already exists, supplied id already in use, or a job state transition is not allowed from its current status |
| `500` | Unexpected server-side error |

---

## Pipelines

| Operation | Route | MCP tool |
|---|---|---|
| Create pipeline (+ first version) | `POST /organizations/{orgId}/pipelines` | `create_pipeline` |
| List pipelines | `GET /organizations/{orgId}/pipelines` | `list_pipelines` |
| Update pipeline (name/description/tags only) | `PATCH /organizations/{orgId}/pipelines/{pipelineId}` | `update_pipeline` |
| List versions | `GET /organizations/{orgId}/pipelines/{pipelineId}/versions` | `list_pipeline_versions` |
| Create version | `POST /organizations/{orgId}/pipelines/{pipelineId}/versions` | `create_pipeline_version` |
| Get version | `GET /organizations/{orgId}/pipelines/{pipelineId}/versions/{version}` | `get_pipeline_version` |
| Update draft version | `PATCH /organizations/{orgId}/pipelines/{pipelineId}/versions/{version}` | `update_pipeline_version` |
| Delete draft version | `DELETE .../versions/{version}` (204 on success) | `delete_draft_pipeline_version` |
| Trigger | `POST .../versions/{version}/trigger` | `trigger_pipeline` |
| Publish (change visibility) | `POST .../versions/{version}/publish/{targetVisibility}` | `publish_pipeline_version` |
| Change lifecycle status | `POST .../versions/{version}/status/{targetStatus}` | `change_pipeline_status` |

### Create pipeline — request body

| Field | Constraint |
|---|---|
| `name` (required) | 2–57 chars, `^[a-zA-Z0-9\- ]+$` (alphanumeric, hyphens, spaces) |
| `description` (required) | 20–256 chars |
| `version` (required) | `^\d+\.\d+\.\d+$` (semver string) |
| `id` | Optional pipeline id; must be a valid UUID. Already in use → `409`; invalid → `400` |
| `inputParameters`, `outputParameters`, `secrets`, `tags`, `steps`, `metadata`, `storages` | Optional arrays/objects; see `SKILL.md` for the step/parameter shapes |

Each step must define exactly one of `action`, `pipeline`, or `suspend`.
Returns `201` with the created **pipeline version** object (below).

### Create pipeline version — request body

Same optional fields as create, plus:

| Field | Notes |
|---|---|
| `version` | New semver; omit to let the service pick. Duplicate → `409` |
| `baseVersion` | Existing semver to copy from — fields you don't send are inherited from this version |

### Update pipeline version

`PATCH` with any of `inputParameters`, `outputParameters`, `secrets`, `steps`,
`metadata`, `storages`. **Only versions in `Draft` status can be updated or
deleted.** Deleting also requires the version to be unused.

### List pipelines — query parameters

| Param | Notes |
|---|---|
| `owned` | `true` = only pipelines owned by the org; otherwise includes accessible public pipelines |
| `offset`, `limit` | Pagination |

Listing returns the **latest version** of each pipeline. When listing another
org's pipeline versions, only `Public` versions are visible.

### Pipeline version object (response shape)

```json
{
  "pipeline": {
    "id": "<uuid>", "name": "...", "description": "...", "tags": ["..."],
    "isUnityMade": false, "organizationId": "...", "projectId": "..."
  },
  "version": "1.0.0",
  "organizationId": "...",
  "certification": { "certified": false, "certifiedOn": "<iso8601>" },
  "lifecycle": { "lifecycleStatus": "Draft", "updatedOn": "<iso8601>", "archivingDate": "<iso8601>" },
  "visibility": { "visibilityLevel": "Private", "updatedOn": "<iso8601>" },
  "inputParameters": [ ... ],
  "outputParameters": [ ... ],
  "steps": [ ... ],
  "secrets": [ ... ],
  "metadata": { },
  "systemMetadata": { },
  "usedAppVersions": [ { "app": { ... }, "version": "...", "actions": [ ... ], "events": [ ... ] } ],
  "storages": [ { "type": "...", "name": "...", "cache": "None" } ]
}
```

`usedAppVersions` is filled in by the service: for each app referenced by the
steps it embeds the app version with its full action definitions — handy for
seeing what inputs an `actionId` actually accepts without a separate lookup.

### Input parameter definition (full field set)

| Field | Notes |
|---|---|
| `name` | Machine name used in `{{inputParameters.name}}` |
| `displayName` | UI label |
| `type` | Parameter type; `"String"` is what the platform actions use in practice |
| `description` | 20–256 chars (same constraint as pipeline descriptions) |
| `required` | boolean |
| `acceptedValues` | Optional array — restricts the value to an enumerated set |
| `regexPattern` | Optional validation regex applied to the supplied value |
| `defaultValue` | Optional default used when the caller omits the parameter |
| `metadata` | Arbitrary map; where the Asset Manager `picker` hints go (see `SKILL.md`) |
| `isList` | `true` for multi-value parameters |

Output parameter definitions use `name`, `displayName`, `type`, `description`,
and `value` (a template expression resolved when the job finishes).

### Lifecycle and visibility

- `lifecycleStatus` enum: **`Draft` → `Available` → `Deprecated` → `Archived`**.
  Allowed transitions: Draft → Available, Available → Deprecated. Only `Draft`
  versions are editable/deletable. `archivingDate` optionally schedules
  archiving.
- `visibilityLevel` enum: **`Private`**, **`Unlisted`**, **`Public`**.
  Change it via the publish route (`.../publish/{targetVisibility}`); only the
  owning organization can publish.

### Trigger — request body

```json
{
  "inputs":  { "paramName": "value" },
  "secrets": { "secretName": "value" },
  "jobPriority": 0
}
```

- `inputs` keys must match the version's `inputParameters` names; required
  params missing → `400`.
- `jobPriority`: integer, **zero is the highest priority**.
- Returns `201` with the created **job** object (see Jobs).

### One-shot trigger (unregistered pipeline)

`POST /organizations/{orgId}/pipelines/trigger` (and the project twin) runs a
pipeline definition without creating/registering it first. Body = `name`,
`description`, optional `tags`, `steps`, `metadata`, `jobPriority` (same
constraints as create). Returns the job. Not wrapped by an MCP tool.

---

## Jobs

| Operation | Route | MCP tool |
|---|---|---|
| List jobs | `GET /organizations/{orgId}/jobs` | `list_jobs` |
| Get job | `GET /organizations/{orgId}/jobs/{jobId}` | `get_job` |
| Job stream (SSE updates) | `GET /organizations/{orgId}/jobs/{jobId}/stream` | — |
| Terminate | `PUT /organizations/{orgId}/jobs/{jobId}/terminate` | `terminate_job` |
| Resume suspended step | `PUT /organizations/{orgId}/jobs/{jobId}/steps/{stepId}/resume` | `resume_job` |
| Approve/reject suspended step | `PUT /organizations/{orgId}/jobs/{jobId}/steps/{stepId}/approve` | `approve_job_step` |
| Org job stats | `GET /organizations/{orgId}/job-stats` | `get_job_stats` |

Project-scoped twins exist for all of these except `job-stats` (the org stats
endpoint already includes project jobs).

### Job status enum

`Queued`, `Pending`, `Running`, `Succeeded`, `Failed`, `Error`, `Terminated`,
`Suspended`, `Unknown`

- `Suspended` = waiting on a `suspend` step (resume or approve it to continue).
- `Failed` = a step failed; `Error` = the platform hit an error running the job.
- Terminate/resume/approve return `409` when the job's current status does not
  allow that transition (e.g. terminating an already-finished job).

### List jobs — query parameters

| Param | Notes |
|---|---|
| `statuses` | Array of job statuses (enum above) to filter by |
| `pipelineIds` | Array of pipeline ids |
| `automationIds` | Array of automation ids (jobs started by a trigger/automation) |
| `orderBy` | `CreatedAt`, `StartedAt`, `FinishedAt`, `UpdatedAt`, `Progress`, `Status`, `Duration` |
| `order` | `Asc` / `Desc` |
| `inputs` | Map of input parameter name → value to filter by |
| `offset`, `limit` | Pagination |

### Job object

```json
{
  "id": "<uuid>",
  "pipeline": { "id": "<uuid>", "name": "...", "version": "1.0.0" },
  "status": "Running",
  "inputs":  { "...": "..." },
  "outputs": { "...": "..." },
  "errors": [ "..." ],
  "userId": "...", "serviceAccountId": "...",
  "organizationId": "...", "projectId": "...",
  "priority": 0,
  "automationId": "<uuid or null>",
  "createdAt": "...", "startedAt": "...", "finishedAt": "...", "updatedAt": "...",
  "queueTime": 0, "durationInSeconds": 0, "progress": 0,
  "steps": [ ... ]
}
```

List responses omit `steps`; `get_job` includes them.

### Job step object

```json
{
  "pipelineStepId": "my-step",
  "name": "My Step",
  "condition": { "statement": "...", "result": true },
  "inputParameters":  { "...": "..." },
  "outputParameters": { "...": "..." },
  "dependencies": [ "previous-step" ],
  "status": "Pending",
  "error": "...",
  "retryCount": 0,
  "progress": 0,
  "startedAt": "...", "finishedAt": "...",
  "configurationId": "<uuid>",
  "timeout": 300,
  "suspend": { "type": "...", "description": "...", "permissions": { "allowedUsers": [], "allowedGroups": [] }, "duration": "...", "allowUserToResume": true }
}
```

`pipelineStepId` is the step `id` from the pipeline JSON — it is the `step_id`
you pass to the logs / approve / resume endpoints. `outputParameters` here hold
the resolved runtime values (what `{{steps.<id>.outputParameters.<name>}}`
reads); inspect them when debugging template expressions.

### Approve / resume

- **Approve** body: `{ "approved": true|false, "comment": "optional" }` —
  `true` lets the pipeline continue past the suspend step, `false` rejects it.
- **Resume** body: `{ "parameters": { ... } }` (optional) — values handed to
  the resumed step. The route is step-scoped and the MCP `resume_job` /
  `resume_project_job` tools take both `job_id` and `step_id` (the suspended
  step's id from the job's `steps`).
- Both return `200` with `{ "status": "<new job status>" }`.

### Job stats

`GET /organizations/{orgId}/job-stats` →
`{ "runningJobs": 0, "queuedJobs": 0, "concurrencyLimit": 0 }`.
Includes project jobs. Use it to see whether jobs are stuck behind the org's
concurrency limit (jobs sit in `Queued` until a slot frees up).

---

## Logs

| Operation | Route | MCP tool |
|---|---|---|
| Step logs | `GET /organizations/{orgId}/jobs/{jobId}/steps/{stepId}/logs` | `get_job_step_logs` |
| Step logs (live SSE) | `GET .../steps/{stepId}/logs/sse` | — |
| Whole-job logs | `GET /organizations/{orgId}/jobs/{jobId}/logs` | — |

Requires the Automation Developer role (a `403` here with an otherwise-working
token usually means the role is missing).

- Step logs return a JSON **array of strings** (one per log line).
- Whole-job logs return `{ "stepLogs": [ { "stepId": "...", "log": "..." } ] }`.
- `stepId` = the pipeline step id (`pipelineStepId` on the job's steps), not a
  separate runtime id.
- `404` means the job id or step id doesn't exist — check the step id against
  `get_job`'s `steps[].pipelineStepId`.

---

## Apps and Actions

Apps package the actions (and events) that pipeline steps invoke. You mostly
*read* these to discover valid `actionId`s and their input schemas.

| Operation | Route | MCP tool |
|---|---|---|
| List apps | `GET /organizations/{orgId}/apps` (query: `owned`, `offset`, `limit`) | `list_apps` |
| List app versions | `GET /organizations/{orgId}/apps/{appId}/versions` | `list_app_versions` |
| Get app version | `GET /organizations/{orgId}/apps/{appId}/versions/{appVersion}` | `get_app_version` |
| Get app action | `GET .../versions/{appVersion}/actions/{actionId}` | `get_app_action` |

- Listing apps returns the latest version of every app accessible to the org
  (its own plus public ones, e.g. the Unity-made Asset Manager and Asset
  Transformer apps — `systemMetadata.createdByUnity: true`).
- App versions have the same `lifecycle` (`Draft`/`Available`/`Deprecated`/`Archived`)
  and `visibility` (`Private`/`Unlisted`/`Public`) model as pipeline versions.
- App name: 2–64 chars; description: 20–256 chars; version: semver.

### Action definition object

Returned by `get_app_action` (and embedded in app versions / `usedAppVersions`):

| Field | Notes |
|---|---|
| `actionId` | The full id you put in a step's `action.actionId` (`<uuid>-<version>-<Action-Name>`) |
| `name`, `description` | Display info |
| `inputParameters` | Same schema as pipeline input parameters (`type`, `required`, `acceptedValues`, `regexPattern`, `defaultValue`, `isList`, ...) — **the authoritative list of keys a step may pass** |
| `outputParameters` | What `{{steps.<id>.outputParameters.<name>}}` can reference |
| `secrets` | Secret definitions the action expects |
| `requirements.configurationIds` | Infrastructure configurations the action can run on (candidates for the step's `configurationId`) |
| `requirements.entitlements` | Entitlements (licenses) the org must have to run the action |
| `timeout` | `{ "defaultValue": n, "minValue": n, "maxValue": n }` — bounds for the step `timeout` |
| `terminationGracePeriodSeconds` | Grace period before force-kill on terminate |
| `storages` | Named storages the action can use |

When a step returns `400` for an unknown input key or a value of the wrong
type, `get_app_action` for that `actionId` is the ground truth to check
against. Verified action IDs for this repo's use cases are cataloged in
`known-action-ids.md`.

### Configuration profiles

`GET /organizations/{orgId}/configurations/profiles` (optional `?appId=`) and
`.../profiles/{profileId}` list the infrastructure profiles (id, name, sku,
cpu/memory/gpu/storage) referenced by `configurationId`. Not wrapped by an MCP
tool; the standard Asset Transformer `configurationId` is in
`known-action-ids.md`.

---

## Automations (scheduled and webhook triggers)

Automations run a registered pipeline version automatically. They are not
wrapped by the MCP server but explain the `automationId` field on jobs and the
`automationIds` job filter.

| Operation | Route |
|---|---|
| Create | `POST /organizations/{orgId}/automations` |
| List / Get / Update / Delete | `GET`/`PATCH`/`DELETE` on `/organizations/{orgId}/automations[/{automationId}]` |
| Fire a webhook trigger | `POST /organizations/{orgId}/automations/{automationId}/webhook` |

Project-scoped twins exist under `/projects/{projectId}/automations`.

### Automation object

| Field | Notes |
|---|---|
| `name` (2–64 chars), `description` (20–256 chars) | Display info |
| `pipelineId`, `version` | The registered pipeline version to run |
| `inputs` (required, may be empty), `secrets` | Values passed to each triggered job |
| `trigger.triggerType` | `"Schedule"` with `trigger.schedule.cron` (cron expression), or event-based with `trigger.event` (`eventId`, `inputParameters`, `secrets`, `eventSecretToken`) |
| `botId` | Automation bot (a service-account identity, managed under `/organizations/{orgId}/bots`) that runs the jobs |
| `enabled`, `triggerCount` | Response-only state |

Posting any JSON payload to the webhook route fires an event-triggered
automation; the payload is mapped onto pipeline inputs via the app event's
`outputParameterMapping`, and webhook signatures can be verified via the
event's `signature` definition (e.g. HMAC-SHA256 header check).

---

## Route map for project-scoped variants

Every `_project_` MCP tool maps to the org route with
`/projects/{projectId}` inserted after the org segment, e.g.:

- `list_project_pipelines` → `GET /organizations/{orgId}/projects/{projectId}/pipelines`
- `trigger_project_pipeline` → `POST /organizations/{orgId}/projects/{projectId}/pipelines/{pipelineId}/versions/{version}/trigger`
- `get_project_job_step_logs` → `GET /organizations/{orgId}/projects/{projectId}/jobs/{jobId}/steps/{stepId}/logs`

Semantics, enums, and schemas are identical to the org-level endpoints.
Project pipelines/jobs are only visible through the project-scoped routes.
