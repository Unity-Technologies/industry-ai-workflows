---
name: pipeline-authoring
description: Authoring reference for Unity Pipeline Automation pipeline JSON definitions. Use when creating, updating, or debugging pipelines via the Pipeline Automation MCP (`create_pipeline`, `create_pipeline_version`, `update_pipeline_version`, and the `_project_` variants) — covers the pipeline schema, Asset Manager picker metadata, known action IDs, template/fan-out syntax, and HTTP 400 gotchas.
---

# Pipeline Authoring — Format Reference

This skill is the source of truth for the JSON shape accepted by the Unity Pipeline Automation v1 API (and exposed by the Pipeline Automation MCP server in this repo). Most fields are not discoverable from the tool schema alone — picker metadata, action IDs, and several "looks fine but returns HTTP 400" traps live here.

For the REST API behind the MCP tools — endpoint routes, job/step response schemas, status enums, list filters, log formats, and error semantics — see **`automation-api.md`** next to this file.

## Top-level structure

```json
{
  "name": "My Pipeline",
  "description": "20–256 character description of what the pipeline does.",
  "version": "1.0.0",
  "tags": ["tag-a", "tag-b"],
  "inputParameters": [ /* see Input Parameters */ ],
  "outputParameters": [ /* see Output Parameters */ ],
  "secrets": [ /* see Secrets */ ],
  "storages": [ /* see Storages */ ],
  "steps": [ /* see Steps */ ],
  "metadata": { "key": "value" }
}
```

**Constraints**
- `name`: 2–57 chars, alphanumeric / hyphens / spaces
- `description`: 20–256 chars
- `version`: semver (`MAJOR.MINOR.PATCH`)

---

## Input Parameters

Each entry defines a value the caller must (or may) supply when triggering the pipeline.

| Field | Notes |
|---|---|
| `name` | Machine name; used in `{{inputParameters.name}}` references |
| `displayName` | Human-readable label shown in the UI |
| `type` | `String` (only observed type) |
| `required` | `true` / `false` |
| `isList` | `true` for multi-value params (e.g. a list of files) |
| `metadata.picker` | Optional UI picker hint (see Pickers below) |

### Standard Asset Manager fields (hardcoded — copy verbatim)

The `projectId`, `assetId`, and `assetVersionId` fields have fixed canonical definitions. Always use these exact objects — do not change names, descriptions, types, or picker metadata.

**projectId**
```json
{
  "name": "projectId",
  "displayName": "Project",
  "type": "String",
  "description": "The project containing the asset to process.",
  "required": true,
  "isList": false,
  "metadata": {
    "picker": "assetManagerProjectPicker"
  }
}
```

**assetId**
```json
{
  "name": "assetId",
  "displayName": "Asset",
  "type": "String",
  "description": "The asset containing the files to process.",
  "required": true,
  "isList": false,
  "metadata": {
    "picker": "assetManagerAssetPicker",
    "projectField": "projectId"
  }
}
```

**assetVersionId**
```json
{
  "name": "assetVersionId",
  "displayName": "Asset Version",
  "type": "String",
  "description": "The asset version containing the files to process.",
  "required": true,
  "isList": false,
  "metadata": {
    "picker": "assetManagerVersionPicker",
    "projectField": "projectId",
    "assetField": "assetId"
  }
}
```

### Additional Asset Manager pickers

For optional dataset and file selection, add these after the three standard fields:

```json
[
  {
    "name": "datasetId",
    "displayName": "Dataset",
    "type": "String",
    "description": "The dataset containing the files to process.",
    "required": false,
    "isList": false,
    "metadata": {
      "picker": "assetManagerDatasetPicker",
      "projectField": "projectId",
      "assetField": "assetId",
      "versionField": "assetVersionId"
    }
  },
  {
    "name": "inputFiles",
    "displayName": "Files",
    "type": "String",
    "description": "The files to process. If no file is selected, all the files are included.",
    "required": false,
    "isList": true,
    "metadata": {
      "picker": "assetManagerFilePicker",
      "projectField": "projectId",
      "assetField": "assetId",
      "versionField": "assetVersionId",
      "datasetField": "datasetId"
    }
  }
]
```

### Picker reference

| Picker | Purpose | Required metadata fields |
|---|---|---|
| `assetManagerProjectPicker` | Project selector | — |
| `assetManagerAssetPicker` | Asset selector | `"projectField": "projectId"` |
| `assetManagerVersionPicker` | Version selector | `"projectField"`, `"assetField"` |
| `assetManagerDatasetPicker` | Dataset selector | `"projectField"`, `"assetField"`, `"versionField"` |
| `assetManagerFilePicker` | File selector | `"projectField"`, `"assetField"`, `"versionField"`, `"datasetField"` |

---

## Steps

Steps are the execution units of a pipeline. All steps share these fields:

```json
{
  "id": "my-step",
  "name": "My Step",
  "continueOnFail": false,
  "timeout": 300,
  "dependencies": ["previous-step-id"]
}
```

| Field | Notes |
|---|---|
| `id` | Unique within the pipeline; used in dependency references and template expressions |
| `name` | Display name shown in the UI |
| `continueOnFail` | If `true`, the pipeline continues even if this step fails |
| `timeout` | Seconds before the step is force-killed (default `300`) |
| `dependencies` | List of step `id`s that must complete before this step runs; empty array = runs immediately |

### Step type: action

Runs a named action (e.g. an Asset Manager operation).

```json
{
  "id": "get-asset",
  "name": "Get asset",
  "action": {
    "actionId": "ad7cbc97-36d5-46ac-99fc-89ea88025b26-1.1.2-Get-asset",
    "inputParameters": {
      "projectId": "{{inputParameters.projectId}}",
      "assetId": "{{inputParameters.assetId}}",
      "assetVersionId": "{{inputParameters.assetVersionId}}",
      "datasetDescriptor": "{{inputParameters.datasetId}}",
      "Files": "{{inputParameters.inputFiles}}",
      "downloadDirectory": "/workspace/input",
      "downloadDependencies": true
    },
    "configurationId": "21a311c6-da72-488a-9688-374824e1c751"
  },
  "continueOnFail": false,
  "timeout": 300,
  "dependencies": ["init"]
}
```

| Field | Notes |
|---|---|
| `actionId` | Format: `<uuid>-<version>-<Action-Name>` |
| `inputParameters` | Key/value map; values can be literals or template expressions |
| `configurationId` | Optional; ties the action to a specific infrastructure configuration |

### Step type: suspend

Pauses the pipeline until a human approves or rejects via `approve_job_step`.

```json
{
  "id": "await-approval",
  "name": "Await Approval",
  "suspend": {},
  "continueOnFail": false,
  "timeout": 86400,
  "dependencies": ["get-asset"]
}
```

### Step type: pipeline (sub-pipeline)

Runs another pipeline as a nested step.

```json
{
  "id": "run-sub-pipeline",
  "name": "Run Sub-Pipeline",
  "pipeline": {
    "id": "<uuid>",
    "version": "1.0.0",
    "inputParameters": {
      "projectId": "{{inputParameters.projectId}}"
    }
  },
  "continueOnFail": false,
  "dependencies": ["get-asset"]
}
```

> **Critical:** The fields inside `pipeline` are `id` and `version` — NOT `pipelineId` / `pipelineVersion`. Using the wrong names causes HTTP 400.
> **Critical:** Pipeline reference steps **cannot have a `timeout` field**. Remove it entirely or the API returns HTTP 400.

### Fan-out for sub-pipeline steps

Use the top-level `fanOut` field to run a sub-pipeline once per item in a JSON array.

```json
{
  "id": "process-each-item",
  "name": "Process Each Item",
  "pipeline": {
    "id": "<sub-pipeline-uuid>",
    "version": "1.0.0",
    "inputParameters": {
      "projectId": "{{inputParameters.projectId}}",
      "itemName": "_OPENING_BRACKETS_item.name_CLOSING_BRACKETS_",
      "itemDir": "_OPENING_BRACKETS_item.glb_dir_CLOSING_BRACKETS_"
    }
  },
  "fanOut": {
    "loopThroughList": "{{steps.previous-step.outputParameters.customOutput}}",
    "maximumParallelCount": 5
  },
  "continueOnFail": false,
  "dependencies": ["previous-step"]
}
```

| Field | Notes |
|---|---|
| `fanOut.loopThroughList` | Template expression resolving to a JSON array |
| `fanOut.maximumParallelCount` | Concurrent iterations — **must be 1–5** (HTTP 400 if outside this range) |

- Per-item values in `pipeline.inputParameters` use `_OPENING_BRACKETS_item.field_CLOSING_BRACKETS_` syntax (same as action fan-out)
- `fanOut` is a **top-level step field**, not nested inside `pipeline`
- Sub-pipeline fan-out steps still cannot have `timeout`

---

## Template expressions

Use `{{ }}` to reference values dynamically at runtime.

| Expression | Resolves to |
|---|---|
| `{{inputParameters.paramName}}` | A pipeline-level input parameter |
| `{{steps.step-id.outputParameters.outputName}}` | An output from a completed step |
| `{{steps.step-id.outputParameters.outputFile1Field2}}` | Specific field within a structured step output |

### Fan-out with `withParam`

Pass `withParam` to run a step once per item in a JSON array, running iterations in parallel.

```json
{
  "id": "process-each-file",
  "name": "Process Each File",
  "action": {
    "actionId": "<action-id>",
    "inputParameters": {
      "input1": "_OPENING_BRACKETS_item.sourceName_CLOSING_BRACKETS_",
      "withParam": "{{steps.find-files.outputParameters.outputFile1}}"
    }
  },
  "continueOnFail": false,
  "timeout": 300,
  "dependencies": ["find-files"]
}
```

- `withParam` value must be a JSON array (or a template resolving to one)
- Per-item values use the `_OPENING_BRACKETS_item.field_CLOSING_BRACKETS_` syntax (literal `{{ item.field }}` is escaped this way by the API)
- Use `"[1]"` as `withParam` to run a single-iteration fan-out (no parallelism, just satisfies the required field)

---

## Action IDs — discover them, don't hardcode

`actionId`s (`<app-uuid>-<app-version>-<Action-Name-slug>`) are
**deployment-specific**: orgs can see duplicate registrations of the same app
(one of which may only have Draft versions — pipelines referencing those can
never become Available, error 53), name slugs differ between public cloud and
private-cloud deployments, and the embedded app version must be Available in
the target org. Discover the ID in the org you're authoring for:

1. `list_apps` — find the app by name (keep all ids if the name appears twice)
2. `list_app_versions` — keep versions with `lifecycle.lifecycleStatus` =
   `Available`, prefer the newest
3. Read that version's `actions` array (or `get_app_action`) — it carries the
   exact `actionId` plus the input/output parameter schema
4. Use the discovered `actionId` verbatim

> **`known-action-ids.md`** next to this file has the full guidance, the IDs
> the example pipelines validate against (observed on public cloud —
> re-discover before use), and per-action parameter tables.

**Get asset — input parameters**

| Key | Required | Description |
|---|---|---|
| `projectId` | Yes | Project the asset belongs to |
| `assetId` | Yes | Asset to download |
| `assetVersionId` | No | Specific version; latest if omitted |
| `datasetDescriptor` | No | Dataset within the asset version |
| `Files` | No | Specific files to download; all if omitted |
| `downloadDirectory` | No | Local path (default `/workspace/input`) |
| `downloadDependencies` | No | `true` / `false` |

**Execute custom script — input parameters**

| Key | Required | Description |
|---|---|---|
| `script` | Yes | Python source code. Written as a static file artifact — template expressions are NOT resolved inside the script body. |
| `parameters` | No | Command-line argument string appended after the script path. Template expressions ARE resolved here. Access in-script via `sys.argv[1]`. |

> **Passing dynamic pipeline inputs to a script:** The `script` field is written to disk before execution, so `{{inputParameters.x}}` inside the script body is literal text — it will not be substituted. To inject a runtime value, put the template expression in `parameters` and read it from `sys.argv` in the script.
>
> ```json
> "inputParameters": {
>   "script": "import sys\nlevel = sys.argv[1]",
>   "parameters": "{{inputParameters.myParam}}"
> }
> ```

**Create asset — input parameters**

| Key | Required | Description |
|---|---|---|
| `projectId` | Yes | Target project |
| `assetName` | Yes | Name for the new asset |
| `assetType` | No | e.g. `"3D Model"` |
| `assetTags` | No | **Must be an array** (e.g. `["tag1"]`). Passing a string causes HTTP 400 (code 55). |
| `collectionPath` | No | Collection to place the asset in |

**Create asset — output parameters**

| Key | Description |
|---|---|
| `assetId` | ID of the created asset |
| `assetVersionId` | Version ID of the created asset |
| `datasetId` | Primary dataset ID |
| `projectId` | Project the asset was created in |
| `assetName` | Name of the created asset |

**Add file — input parameters**

| Key | Required | Description |
|---|---|---|
| `projectId` | Yes | Project the asset belongs to |
| `assetId` | Yes | Asset to upload files into |
| `assetVersionId` | No | Specific version; uses current draft if omitted |
| `datasetDescriptor` | No | Dataset to upload into |
| `uploadDirectory` | No | Local directory whose contents are uploaded (default: all files in workspace) |
| `freezeAsset` | No | `true` to freeze the asset version after upload |

**Execute custom script — configurationId**

Use `21a311c6-da72-488a-9688-374824e1c751` (standard Asset Transformer infrastructure).

---

## Lifecycle & visibility

### Lifecycle status transitions

```
Draft → Available → Deprecated → Archived
```

- These are the API enum values (`lifecycleStatus`); the `Available` state is what the UI presents as an active/published version.
- Only `Draft` versions can be updated or deleted.
- Use `change_pipeline_status` / `change_project_pipeline_status` to advance.

### Visibility levels

| Value | Who can see |
|---|---|
| `Private` | Organisation members only |
| `Unlisted` | Anyone with the direct link |
| `Public` | Listed in the public pipeline catalogue |

---

## Minimal working example

```json
{
  "name": "My Asset Pipeline",
  "description": "Downloads an asset from Asset Manager and processes it.",
  "version": "1.0.0",
  "inputParameters": [
    {
      "name": "projectId",
      "displayName": "Project",
      "type": "String",
      "description": "The project containing the asset to process.",
      "required": true,
      "isList": false,
      "metadata": { "picker": "assetManagerProjectPicker" }
    },
    {
      "name": "assetId",
      "displayName": "Asset",
      "type": "String",
      "description": "The asset containing the files to process.",
      "required": true,
      "isList": false,
      "metadata": {
        "picker": "assetManagerAssetPicker",
        "projectField": "projectId"
      }
    },
    {
      "name": "assetVersionId",
      "displayName": "Asset Version",
      "type": "String",
      "description": "The asset version containing the files to process.",
      "required": true,
      "isList": false,
      "metadata": {
        "picker": "assetManagerVersionPicker",
        "projectField": "projectId",
        "assetField": "assetId"
      }
    }
  ],
  "steps": [
    {
      "id": "get-asset",
      "name": "Get asset",
      "action": {
        "actionId": "ad7cbc97-36d5-46ac-99fc-89ea88025b26-1.1.2-Get-asset",
        "inputParameters": {
          "projectId": "{{inputParameters.projectId}}",
          "assetId": "{{inputParameters.assetId}}",
          "assetVersionId": "{{inputParameters.assetVersionId}}",
          "downloadDirectory": "/workspace/input",
          "downloadDependencies": true
        },
        "configurationId": "21a311c6-da72-488a-9688-374824e1c751"
      },
      "continueOnFail": false,
      "timeout": 300,
      "dependencies": []
    }
  ]
}
```

---

## Examples

Vetted, end-to-end pipeline JSONs live in `examples/` (valid JSON, correct
constraints, only documented action IDs):

- `download-and-inspect.json` — minimal `Get asset` → `Execute custom script`
  (read-only scene stats to the job log).
- `optimize-and-republish.json` — full roundtrip: `Get asset` → `Execute custom
  script` (tessellate + decimate to GLB) → `Create asset` → `Add file`, showing
  how to pass a runtime value via `parameters` and how to wire `create-asset`
  outputs into a downstream `add-file` step.

Prefer adapting an example over authoring a pipeline from scratch. The Python
inside each `Execute custom script` step follows the `at-upa-scripting`
conventions (argparse, `/workspace` paths); the pxz API it calls is documented in
`../at-scripting/pxz-api-reference.md`.
