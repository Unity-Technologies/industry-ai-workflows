# Action IDs: discover, don't hardcode

`actionId` strings look stable but are **deployment-specific**. Always discover
them in the target org before authoring a pipeline; treat any ID written in a
doc (including this one) as an example to verify, not a constant to copy.

Why copying IDs breaks:

- **Duplicate app registrations.** Orgs can see more than one registration of
  the same Unity app. On public cloud there are two "Unity Asset Transformer"
  apps: `f83a90ce-…` has only a **Draft** 1.1.1 version — a pipeline
  referencing it can never be set to Available (error code 53) — while
  `9dadfc21-…` carries the Available versions. Nothing in the actionId warns
  you which registration you picked.
- **Slugs differ per deployment.** The same action carries different name
  slugs: public cloud serves
  `…-<version>-Execute-custom-script---Requires-Unity-Industry`, a private-cloud
  (VPC) deployment served `…-1.2.1-Execute-custom-script` (verified live on
  1.2.1; the 1.3.x slug on VPC has not been re-checked).
  A copied public-cloud ID 400s on VPC and vice versa.
- **Versions advance.** The `<version>` embedded in the ID must be an app
  version that is Available in *that org*, and old versions get retired.

## How to discover the right actionId

`actionId` format: `<app-uuid>-<app-version>-<Action-Name-slug>`.

Using the Pipeline Automation MCP tools:

1. `list_apps` — find the app by name (e.g. "Unity Asset Transformer",
   "Unity Asset Manager"). If the same name appears twice, keep both ids for
   step 2.
2. `list_app_versions` for each candidate app id — keep only versions whose
   `lifecycle.lifecycleStatus` is **`Available`** (Draft versions cannot back
   an Available pipeline), preferring the newest.
3. Read the `actions` array on that app version — each entry carries the
   exact `actionId` plus its `inputParameters` / `outputParameters` schema.
   `get_app_action` returns the same detail for a single action.
4. Use the discovered `actionId` verbatim in the step's `action.actionId`.

## IDs observed on public cloud (examples, verified live)

The example pipelines in `examples/` validate against this table. These were
correct on public Unity Cloud when last verified — re-discover before use, per
the procedure above.

| Action | actionId |
|---|---|
| Get asset (Asset Manager) | `ad7cbc97-36d5-46ac-99fc-89ea88025b26-1.1.2-Get-asset` |
| Create asset (Asset Manager) | `ad7cbc97-36d5-46ac-99fc-89ea88025b26-1.1.2-Create-asset` |
| Add file (Asset Manager) | `ad7cbc97-36d5-46ac-99fc-89ea88025b26-1.1.2-Add-file` |
| Execute custom script (Asset Transformer) | `9dadfc21-2cd6-4dff-a31e-7a64967579c9-1.3.1-Execute-custom-script---Requires-Unity-Industry` |

> **Do not use** the other Asset Transformer registration
> (`f83a90ce-12a9-4efd-918f-fddc0f1680d3`, action
> `…-1.1.1-Execute-custom-script-v2025-3`): its only version is Draft, so
> pipelines referencing it can never become Available (error code 53).

**Default `configurationId` for AT steps:** `21a311c6-da72-488a-9688-374824e1c751` —
the platform-global "Linux Micro" profile (1 vCPU / 4Gi RAM / 8Gi disk; verified
present and identical in every org, including VPC deployments). For heavier jobs
list the org's profiles via
`GET /organizations/{orgId}/configurations/profiles` and pick a bigger SKU.

---

The parameter tables below describe the action *families*; they have been
stable across app versions. The authoritative schema for a specific version is
the `inputParameters` / `outputParameters` on the discovered app version.

## Get asset

Downloads an asset's files into the workspace (default `/workspace/input`).

| Key | Required | Description |
|---|---|---|
| `projectId` | Yes | Project the asset belongs to |
| `assetId` | Yes | Asset to download |
| `assetVersionId` | No | Specific version; latest if omitted |
| `datasetDescriptor` | No | Dataset within the asset version |
| `Files` | No | Specific files to download; all if omitted |
| `downloadDirectory` | No | Local path (default `/workspace/input`) |
| `downloadDependencies` | No | `true` / `false` |

## Execute custom script

Runs an Asset Transformer Python script (see the `at-upa-scripting` skill for the
script body itself).

| Key | Required | Description |
|---|---|---|
| `script` | Yes | Python source. Written to disk as a static artifact — template expressions are NOT resolved inside the script body. |
| `parameters` | No | CLI argument string appended after the script. Template expressions ARE resolved here. Read via `sys.argv` / argparse. |

> To inject a runtime value, put the `{{...}}` expression in `parameters`, not in
> `script`. Use `configurationId` `21a311c6-da72-488a-9688-374824e1c751`.

## Create asset

A converted output belongs in a new asset created by this action, with the
`source*` inputs set to the input asset and `referenceType: "Converted"`, not
in a custom dataset on the source asset.

| Key | Required | Description |
|---|---|---|
| `projectId` | Yes | Target project |
| `assetName` | Yes | Name for the new asset |
| `assetType` | No | Exact API spelling, e.g. `"3D Model"`, `"2D Asset"`. The action passes it straight to the API, so `"2D asset"` fails with 40203 (`Asset.PrimaryType` invalid). (The Asset Manager MCP normalises spellings; this action does not.) |
| `assetTags` | No | **Must be an array** (e.g. `["tag1"]`). A bare string returns HTTP 400 (code 55). |
| `collectionPath` | No | Collection to place the asset in |
| `sourceProjectId` / `sourceAssetId` / `sourceAssetVersionId` / `sourceDatasetDescriptor` | No | The asset this one was produced from; the source gets a reference to the new asset |
| `referenceType` | No | `Converted` (server default) or `Dependency` |

**Outputs:** `assetId`, `assetVersionId`, `datasetId`, `projectId`, `assetName`.

`Create asset` creates the `Source` and `Preview` datasets itself (a `ReferenceOutput` dataset may also appear), so no separate dataset step is needed: point a later `Add file` at `Preview` via `datasetDescriptor`.

## Add file

| Key | Required | Description |
|---|---|---|
| `projectId` | Yes | Project the asset belongs to |
| `assetId` | Yes | Asset to upload files into |
| `assetVersionId` | No | Specific version; uses current draft if omitted |
| `datasetDescriptor` | No | Dataset to upload into |
| `uploadDirectory` | No | Local directory whose contents are uploaded (default: all workspace files) |
| `freezeAsset` | No | `true` to freeze the asset version after upload |

## Creo View (.pvz) input — convert via Wine first

pxz cannot import `.pvz` directly: the PTC reader is Windows-only. AT images
that support it ship a Windows Pixyz under Wine, driven by one command:

```python
import subprocess
result = subprocess.run(
    ["python3wine", "/opt/exportcreo.py", input_pvz, output_pxz],
    capture_output=True, check=False,
)
ok = result.returncode in (0, 15)  # 15 is also success; still check the file exists
```

The `.pxz` it writes then imports normally (`io.importScene`).

**Use "Execute custom script" 1.3.x** (app `9dadfc21-…`, the latest Available
version; 1.3.1 as of 2026-11). The Asset Transformer team updated its image to
support the Wine emulator, so the conversion runs in the same script step as
the rest of the processing: call `python3wine`, then `io.importScene` the
`.pxz`. Wine may still log "wine32 is missing"; that warning is harmless.

History, in case you meet an older pipeline (public cloud):

| Runner | Result |
|---|---|
| "Execute custom script" 1.3.x | Supported (image updated for Wine) |
| "Execute custom script" 1.2.1–1.2.6, SDK 2026.3.1.1 | Broken (verified 2026-10-16): exit 3 and no output; JtOpenPlugin fails (`MSVCP140_ATOMIC_WAIT.dll` not found), then `signal received: 11`. All 1.2.x versions are now Archived |
| "Execute custom script" 1.2.0, SDK 2025.4.2.2 | Worked (exit 15, valid `.pxz`), but is now Archived |
| "Convert PVZ file to PXZ" action (`f83a90ce-…-1.1.1-Convert-PVZ-file-to-PXZ`) | Works, but its registration is Draft-only, so a pipeline using it can never be set to Available (error code 53). No longer needed |

A pipeline still pinned to a 1.2.x action id should move to the current 1.3.x
id (rediscover it with `list_app_versions`). If in-script Wine ever fails
again, a single `python3wine` call in a throwaway transient pipeline shows
whether the image regressed.
