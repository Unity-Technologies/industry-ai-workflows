---
name: at-upa-scripting
description: Authoring guide for the Python script body that goes into the Unity Pipeline Automation "Execute custom script" action (Asset Transformer). Use when writing or debugging the `script` field of an AT custom-script step — covers argparse-driven entry points, scripts that assume the pxz SDK is already initialized by the UPA runtime, the no-Asset-Manager-write rule (chain an AM action instead), and CAD prep / tessellation / optimization / export patterns. NOT for authoring the surrounding pipeline JSON (see `pipeline-authoring`) and NOT for the local Asset Transformer MCP tools (those run in-process).
---

# Asset Transformer Scripts for UPA — Authoring Guide

This skill is the source of truth for the Python that goes into the `script` field of the Unity Pipeline Automation **Execute custom script** action (Asset Transformer). The script is uploaded verbatim and executed inside a managed AT container, so the conventions are different from both the local Asset Transformer MCP and a normal Python program.

## Execution context — what UPA gives you

The AT custom script action runs in a managed container that has already:
- Initialized the Asset Transformer SDK (`pxz`)
- Activated the license
- Set up the Python environment

**Do not include any of the following in scripts:**
- `pxz.core.initialize(...)` or equivalent SDK init calls
- License server configuration
- Environment / path setup

Assume `pxz` is importable and ready to call. If a script fails on init, the runtime — not the script — needs fixing.

**No local AT license?** This remote path is also the fallback when the user has no Asset Transformer license seat: author and syntax-check the script locally (plain Python compile — no pxz needed), then execute it here. Tell the user that local execution via the AT MCP requires a seat, and that for full local capabilities they should contact their Unity account representative or sales: <https://unity.com/contact-us?reason=Speak+to+Sales&step=3&topic=Industrial+Solutions>

## Argparse is the only input channel

The pipeline passes inputs to the script via the `parameters` field of the action (template expressions are resolved here, not inside `script`). Those values arrive as `sys.argv`, so scripts MUST parse them with `argparse`:

```python
import argparse

def process_asset(input_path: str, output_path: str) -> None:
    # Asset Transformer operations here
    pass

def main() -> None:
    parser = argparse.ArgumentParser(description="Asset Transformer pipeline script")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    process_asset(args.input, args.output)

if __name__ == "__main__":
    main()
```

Notes:
- The Run command surfaced to the user in the UPA UI is **just the args** — no `python` prefix, no script path. UPA wraps invocation.
- Do not read inputs from environment variables or interactive prompts. argparse only.
- Workspace paths follow UPA conventions: input artifacts arrive under `/workspace/input`, outputs go under `/workspace/output` (or wherever the surrounding pipeline expects them).

## You cannot write to Asset Manager from this action

The AT custom script action has no Asset Manager credentials. If a workflow needs to push the resulting file back into Asset Manager, **chain an Asset Manager `Add file` (or `Create asset`) action** as a downstream step in the pipeline JSON — do not try to call AM APIs from inside the script.

When advising a user whose script needs to publish output, point them at the AM action; do not fabricate AM calls inside the script body.

## Script structure

Every script should follow this layout:

1. Imports
2. Function definitions (one per logical operation)
3. `main()` with argparse
4. `if __name__ == "__main__": main()` guard

Keep functions small and named after what they do (`import_cad`, `prepare_for_tessellation`, `optimize_mesh`, `export_glb`). Side effects belong inside the functions, not at module top level — top-level work runs at import time and breaks composition.

## CAD pipeline best practices

- Preserve assembly hierarchies when possible (downstream consumers often rely on them)
- Strip construction geometry, hidden nodes, and authoring-only metadata before export
- Tune tessellation to the *target use case* — real-time viewers tolerate coarser settings than engineering review
- Use instancing for repeated components rather than duplicating mesh data
- Keep node names stable across runs so downstream pipelines can address them

## Performance best practices

For large assemblies, prefer approaches that:
- Reduce polygon count during tessellation rather than after
- Merge or instance repeated components
- Remove unused nodes early in the pipeline (cheaper than carrying them through every stage)
- Avoid repeated traversal of large hierarchies — gather what you need in one pass
- Limit memory-heavy operations (full-scene bakes, redundant copies)

When a chosen approach materially affects performance, add a one-line comment explaining why.

## Code style

- Python only.
- Include all imports at the top.
- Clear variable names over clever ones.
- Comments explain non-obvious SDK behavior, not what the code literally does.
- Prefer complete, runnable snippets over pseudocode unless the user explicitly asks for high-level design.

When modifying a user's existing script, improve in place — preserve their structure and naming where possible. Don't rewrite a working script just to restyle it.

## Accuracy guardrails

The full pxz API surface is documented in **`../at-scripting/pxz-api-reference.md`** (the shared, authoritative reference; the `at-scripting` skill owns it and this skill defers to it). **If a function or class is not listed there, it does not exist in this SDK version.** Do not generate code that calls it — verify first, or tell the user the SDK doesn't support what they're asking for.

Specifically, do not invent:
- Classes, functions, parameters, or constants (the reference is authoritative)
- Pipeline features that don't exist
- AM / UPA APIs callable from inside the script
- Object-style APIs like `scene.Node`, `scene.NodeType`, `scene.getName`, `scene.deleteNodes` — pxz uses **integer occurrence handles**, not Node objects. Real names: `scene.getOccurrenceName`, `scene.deleteOccurrences`, etc.
- Keyword arguments on `io.exportScene` — the real signature is `exportScene(fileName: str, root: int = 0)`. Format is inferred from extension; per-format options are set via `core.setModuleProperty("io", ...)` before the export call.

If something is uncertain or undocumented:
- Say so explicitly
- Suggest the closest supported approach from the reference
- If the SDK genuinely doesn't support what the user is asking for, say that and describe the closest workflow — chaining a different action, doing the operation in a follow-up script, or restructuring the pipeline.

Ground-truth source for the reference: the `*.pyi` type stubs shipped inside the installed `pxz` package. Re-extract the shared reference (`../at-scripting/pxz-api-reference.md`) if the SDK is upgraded.

## Debugging checklist

When a script fails or behaves incorrectly, work through these in order:

1. **Argument handling** — is `argparse` receiving the values you expect? Print `args` early.
2. **File paths** — are the input files actually present at the path UPA passed in? Workspace conventions matter.
3. **SDK call shape** — wrong parameter name or type is the most common silent failure.
4. **Tessellation / prep settings** — wrong settings cause wildly wrong polygon counts and import errors.
5. **Export format** — the destination format must support what's in the scene (e.g. instancing, materials).

Identify the likely cause, explain *why* it fails, describe how to verify, then provide the corrected snippet.

## Out of scope

- The surrounding pipeline JSON, action IDs, picker metadata, fan-out syntax → see `pipeline-authoring`.
- Local Asset Transformer MCP tools / `run_python` (in-process, stateful scene, no argparse) → see the `at-scripting` skill (which also owns the shared pxz API reference) and the Asset Transformer MCP README.
- Writing back to Asset Manager from inside the script → not possible; chain an AM action instead.

## Examples

Vetted example scripts live in `examples/`. Currently:
- `import-tessellate-export-glb.py` — minimum viable CAD → GLB pipeline (import, tessellate relative to AABB, repair mesh, export).
- `import-decimate-export-glb.py` — import, tessellate at a `low`/`medium`/`high`/`custom` quality preset, decimate to a target triangle ratio, export. Demonstrates the `--quality` preset pattern with `--max-sag` / `--sag-ratio` / `--max-angle` overrides for `custom` mode.
- `bake-ao-and-export.py` — bake AO into materials via `algo.combineMaterials(..., BakeOption(textures=BakeMaps(ambientOcclusion=True, ...)), ...)` and export. The high-level path that handles both the bake and the material wiring; an exported GLB carries the AO in its material's `ao` slot.

Add new examples here as workflows are validated. Every example must use only calls present in the shared reference (`../at-scripting/pxz-api-reference.md`).

When a user asks for a common workflow, prefer adapting an existing example over generating from scratch.
