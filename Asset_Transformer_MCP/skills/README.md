# Asset Transformer skills

Authoring guides for writing Asset Transformer (pxz) code. Claude Code
auto-discovers them when this plugin is installed.

| I want to… | Skill |
|---|---|
| Write pxz code for the **`run_python`** tool (in-process, `pxz` global, stateful scene) | **`at-scripting`** |
| Look up any **pxz function or class signature** | `at-scripting/pxz-api-reference.md` — the authoritative reference. If it is not listed there, it does not exist in this SDK version. |
| Write the Python **`script` body of a pipeline "Execute custom script" action** (argparse, `/workspace` paths, no Asset Manager write) | **`at-upa-scripting`** |

```
at-upa-scripting ──► at-scripting/pxz-api-reference.md
 (custom-script body)      (authoritative pxz API)
```

`at-upa-scripting` describes a Unity Pipeline Automation action but ships here,
with the pxz reference it depends on. A skill cannot link to a file in another
plugin — Claude Code refuses component paths that leave the plugin root — so
splitting the pair would break that reference.

## Skills in the other plugins

These ship with their own plugins and are not installed with this one:

- **`pipeline-authoring`** — authoring the pipeline JSON around a custom-script
  step (schema, action IDs, pickers, fan-out). Ships with `upa-mcp`.
- **`asset-manager-authoring`** — publishing, versioning and organizing assets.
  Ships with `uam-mcp`. This is the destination for the "then push it to Asset
  Manager" handoff that the skills here defer to.


## Maintenance

`at-scripting/pxz-api-reference.md` is generated from the pxz SDK's `.pyi`
stubs and carries a `pxz-verified-version` marker — when the Asset Transformer
SDK is bumped, re-verify the reference against the new stubs and update the
marker so the documented API surface matches the installed SDK.
