# Skills

Authoring guides and references for the three Unity MCP servers in this repo
(Asset Manager, Asset Transformer, Pipeline Automation). Each skill is a
`SKILL.md` plus supporting references/examples; Claude Code auto-discovers them.

## Which skill do I use?

| I want to… | Skill |
|---|---|
| Write pxz code for the **AT MCP `run_python`** tool (in-process, `pxz` global, stateful scene) | **`at-scripting`** |
| Look up any **pxz function/class signature** | `at-scripting/pxz-api-reference.md` (the shared, authoritative reference) |
| Write the Python **`script` body of a pipeline "Execute custom script"** action (argparse, `/workspace`, no AM write) | **`at-upa-scripting`** |
| Author/debug a **Pipeline Automation pipeline JSON** (schema, pickers, action IDs, fan-out) | **`pipeline-authoring`** |
| **Publish/version/organize assets** in Asset Manager (create, upload, metadata, references, collections) | **`asset-manager-authoring`** |

## How they relate

```
pipeline-authoring ──► at-upa-scripting ──► at-scripting/pxz-api-reference.md
   (pipeline JSON)      (custom-script body)    (authoritative pxz API)
        │                      ▲                        ▲
        │ Create asset /       │ shares the API surface │
        ▼ Add file actions     └────────────────────────┘
 asset-manager-authoring ◄──── "push result to Asset Manager" handoff
   (Asset Manager MCP)         (from at-scripting, in-process)
```

- **`at-scripting`** owns `pxz-api-reference.md`; `at-upa-scripting` defers to it
  for the API surface and adds the pipeline-container conventions.
- The Asset Transformer → Asset Manager handoff has two forms:
  - **In-process** (`at-scripting`): AT writes a local file, then the Asset
    Manager MCP (`asset-manager-authoring`) publishes it.
  - **In a pipeline** (`at-upa-scripting`): chain the pipeline's `Create asset` /
    `Add file` actions (`pipeline-authoring`) — the script itself can't reach AM.

## Maintenance

`at-scripting/pxz-api-reference.md` is generated from the pxz SDK's `.pyi`
stubs and carries a `pxz-verified-version` marker — when the Asset Transformer
SDK is bumped, re-verify the reference against the new stubs and update the
marker so the documented API surface matches the installed SDK.
