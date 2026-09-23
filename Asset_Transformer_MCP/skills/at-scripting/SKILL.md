---
name: at-scripting
description: Authoring guide and full API reference for writing Asset Transformer (pxz) Python scripts. Use when writing or debugging pxz code for the local Asset Transformer MCP `run_python` tool (in-process, `pxz` global, stateful scene, no argparse), and as the authoritative pxz API surface (pxz-api-reference.md) that other skills — including at-upa-scripting — defer to. Covers CAD import / repair / tessellation / decimation / UV / baking / export patterns and the integer-handle model. For the UPA "Execute custom script" container specifics (argparse, workspace paths, no Asset Manager write) see at-upa-scripting; for pipeline JSON see pipeline-authoring.
---

# Asset Transformer (pxz) Scripting — Authoring Guide

This skill is the source of truth for writing Python against the Asset Transformer SDK (`pxz`). It serves two audiences:

1. **The local Asset Transformer MCP `run_python` tool** — the primary target. Code runs *in-process* inside the running Pixyz session.
2. **Other skills** — notably `at-upa-scripting`, which layers UPA-container conventions (argparse, workspace paths, no-Asset-Manager-write) on top of this same API. Both defer to `pxz-api-reference.md` in this folder for the API surface.

The **API surface is documented in `pxz-api-reference.md` next to this file.** It is authoritative: if a function, class, parameter, or constant is not listed there, it does not exist in this SDK version — do not call it. See [Accuracy guardrails](#accuracy-guardrails).

## Execution context — the in-process `run_python` tool

The Asset Transformer MCP runs code like this:

```python
exec(compile(code, "<mcp_run_python>", "exec"), {"pxz": pxz})
```

So when you write a script for `run_python`:

- **`pxz` is already in scope** as a global. You do **not** `import pxz`. (You *may* still `from pxz import scene, algo, io, ...` for brevity, or just use `pxz.scene.*` — the module attributes are all reachable off the global.)
- **The SDK is already initialized and licensed.** Never call `pxz.initialize()`, `core.configureLicenseServer`, `core.checkLicense`, `core.needToken`, etc. If init is broken, the *server* is misconfigured — not your script.
- **The scene is stateful and persists across calls.** Each `run_python` (and every other AT MCP tool) operates on the *same* live session. A model you imported in one call is still there in the next. Do not assume an empty scene — call `pxz.scene.getRoot()` / `getChildren(root)` to see what's loaded, and `clear_scene` (or delete children of root) if you need a clean slate.
- **Only `pxz` is guaranteed in the globals.** The standard library is importable (`import math`, `os`, `json`, …), but there is no argparse-style input channel — inputs are literals in the code you write, or values you read from the live scene.
- **stdout is captured and returned.** `print(...)` is how you surface results (counts, ids, paths). Print the things the caller needs to see.

### `run_python` vs. the UPA custom-script action

| | `run_python` (this skill's default) | UPA "Execute custom script" (see `at-upa-scripting`) |
|---|---|---|
| `pxz` availability | global, pre-initialized | imported (`import pxz`), pre-initialized by runtime |
| Inputs | literals / live scene | `argparse` over `sys.argv` |
| Scene lifetime | **stateful** across tool calls | fresh per job |
| Entry point | bare statements run top-to-bottom | `main()` + `if __name__ == "__main__"` guard |
| File paths | wherever you point them | `/workspace/input`, `/workspace/output` |
| Write to Asset Manager | not this tool's job (chain an AM tool/action) | not possible (chain an AM action) |

When a user's script is clearly destined for a pipeline, switch to the `at-upa-scripting` conventions. When it's an interactive/one-off transformation against the live MCP session, use the in-process style below.

## No Asset Transformer license?

Local `run_python` (and every other AT MCP tool) consumes a Pixyz license seat. If `check_license` fails or no license server is configured, **do not stop** — fall back to remote execution:

1. **Author the script locally** using this skill's API reference as usual.
2. **Syntax-check it locally** with a plain Python compile (`compile(code, "<script>", "exec")` or `python -m py_compile`) — no pxz or license needed.
3. **Execute it remotely** via a Pipeline Automation "Execute custom script" step. Follow the `at-upa-scripting` conventions for the script body (argparse, `/workspace` paths, `main()` guard) and `pipeline-authoring` for the surrounding pipeline JSON.

Tell the user clearly about the trade-off: remote execution works without a seat, but local execution and fast local iteration require a license. To unlock full local capabilities they should contact their Unity account representative or sales: <https://unity.com/contact-us?reason=Speak+to+Sales&step=3&topic=Industrial+Solutions>

## The integer-handle model (read this once)

`pxz` has **no object model**. Every entity — occurrence, part, mesh, material, image, viewer, baking session, and every CAD BRep entity (body, face, edge, curve, surface) — is an opaque `int` id. There is no `scene.Node`, `scene.Material`, or `cad.Body` *object*.

- Get the root: `root = pxz.scene.getRoot()`.
- Most scene/algo functions take a **list** of occurrences, even for one: `pxz.algo.tessellate([root], ...)`.
- Real names use verbs on the module: `scene.getOccurrenceName(occ)`, `scene.deleteOccurrences([occ])`, `scene.getChildren(occ)`. There is **no** `scene.getName`, `scene.deleteNodes`, `node.name`.
- `io.exportScene(fileName, root=0)` infers format from the file **extension** — there is no `format=`/`binaryGLTF=`/`embedTextures=` keyword. Per-format tuning goes through `core.setModuleProperty("io", "<key>", "<value>")` *before* the export call.

## Script structure (in-process)

For `run_python`, prefer small, flat, top-to-bottom scripts that print what they did. You do not need argparse or a `main()` guard (though defining helper functions is fine and encouraged for anything non-trivial):

```python
# pxz is already global and initialized — no import, no initialize().
root = pxz.scene.getRoot()

# 1. Import a model into the live scene.
model = pxz.io.importScene(r"C:\models\bracket.step")

# 2. Prepare: repair + tessellate relative to the model's size.
pxz.algo.repairCAD([model], 0.1, True)
pxz.algo.tessellateRelativelyToAABB([model], maxSag=-1, sagRatio=0.005,
                                    maxLength=-1, maxAngle=20.0)
pxz.algo.repairMesh([model], 0.01, True, True)

# 3. Report and export.
tris = pxz.scene.getPolygonCount([model], asTriangleCount=True)
print(f"triangles after prep: {tris}")
pxz.io.exportScene(r"C:\out\bracket.glb", model)
```

Wrap genuinely multi-step, state-changing work in an undo/redo step so the session stays clean and reversible (the built-in AT MCP tools do this):

```python
pxz.core.startUndoRedoStep(stepName="run_python: decimate")
try:
    pxz.algo.decimateTarget([root], ["ratio", 0.5])
finally:
    pxz.core.endUndoRedoStep()
```

## Common workflows

Prefer adapting a vetted `examples/` script over generating from scratch. Current examples:

- `import-prepare-export.py` — in-process import → repair → tessellate (relative to AABB) → repair mesh → export GLB, with triangle-count reporting.
- `inspect-scene.py` — walk the live stateful scene, report per-occurrence names / triangle counts / AABB without mutating anything (safe to run first when you don't know what's loaded).

High-level building blocks (all detailed in `pxz-api-reference.md`):

- **Import / export:** `io.importScene`, `io.importFiles`, `io.exportScene` (extension-driven), `io.getImportFormats` / `io.getExportFormats`.
- **CAD prep:** `algo.repairCAD`, `algo.assembleCAD`, `algo.tessellate` / `algo.tessellateRelativelyToAABB`, `algo.repairMesh`.
- **Optimize:** `algo.decimate`, `algo.decimateTarget(occ, ["ratio", r])` / `(occ, ["polygonCount", n])`, `algo.removeHoles`, `algo.deletePatches`, `scene.mergePartOccurrences*`, `scene.convertSimilarPartOccurrencesToInstances*` (via `algo`), `algo.removeOccludedGeometries`.
- **UV:** `algo.automaticUVMapping`, `algo.unwrapUV`, `algo.repackUV`, `algo.mapUvOn*`.
- **Baking:** `algo.combineMaterials(occ, BakeOption(...))` for the high-level AO-into-materials path; `algo.beginBakingSession` + `algo.bake*Map` + `algo.endBakingSession` for explicit control.
- **Query / edit:** `scene.getChildren`, `scene.getPolygonCount`, `scene.getAABB`, `scene.findOccurrencesByProperty`, `scene.getFilteredOccurrences`, `scene.deleteOccurrences`, `scene.hide` / `show`.
- **Visuals:** `view.takeScreenshot` (offscreen viewer); `raytrace.renderImage` only when ray-traced quality is required.

## CAD pipeline best practices

- Preserve assembly hierarchies when downstream consumers rely on them.
- Strip construction geometry, hidden nodes, and authoring-only metadata before export.
- Tune tessellation to the *target use case* — real-time viewers tolerate coarser settings than engineering review. Prefer `tessellateRelativelyToAABB` (a `sagRatio` scales with model size) over a fixed `maxSag` when you don't know the model's scale.
- Instance repeated components (`convertSimilarPartOccurrencesToInstances*`) rather than duplicating mesh data.
- Keep occurrence names stable across runs so downstream steps can address them.

## Performance best practices

For large assemblies, prefer approaches that:

- Reduce polygon count during tessellation rather than after.
- Merge or instance repeated components.
- Remove unused nodes/occlusions early (cheaper than carrying them through every stage).
- Avoid repeated traversal of large hierarchies — gather what you need in one pass.
- Limit memory-heavy operations (full-scene bakes, redundant copies).

Because the scene is stateful in `run_python`, also: clean up after yourself (delete scratch occurrences, `core.endUndoRedoStep`) so later tool calls start from a predictable state.

When a chosen approach materially affects performance, add a one-line comment explaining why.

## Code style

- Python only. Clear variable names over clever ones.
- In `run_python` scripts, do **not** re-import or re-initialize `pxz`.
- Comments explain non-obvious SDK behavior, not what the code literally does.
- Prefer complete, runnable snippets over pseudocode unless the user explicitly asks for high-level design.
- When modifying a user's existing script, improve it in place — preserve their structure and naming. Don't rewrite a working script just to restyle it.

## Accuracy guardrails

The full pxz API surface is documented in `pxz-api-reference.md` next to this file. **If a function or class is not listed there, it does not exist in this SDK version.** Do not generate code that calls it — verify first, or tell the user the SDK doesn't support what they're asking for.

Specifically, do not invent:

- Classes, functions, parameters, or constants (the reference is authoritative).
- Object-style APIs like `scene.Node`, `scene.NodeType`, `scene.getName`, `scene.deleteNodes`, `cad.Body` objects — pxz uses **integer handles**, not objects. Real names: `scene.getOccurrenceName`, `scene.deleteOccurrences`, etc.
- Keyword arguments on `io.exportScene` — the real signature is `exportScene(fileName: str, root: int = 0)`. Format is inferred from extension; per-format options are set via `core.setModuleProperty("io", ...)` before the export call.

If something is uncertain or undocumented:

- Say so explicitly.
- Suggest the closest supported approach from the reference.
- If the SDK genuinely doesn't support what the user is asking for, say that and describe the closest workflow.

**Version.** The reference is verified against the installed **2026.4.0.0** stubs — the exact surface `run_python` executes against. Prefer functions confirmed in `pxz-api-reference.md`; when in doubt, probe the live SDK (`print([n for n in dir(pxz.algo) if "decimate" in n.lower()])`) before relying on a call.

Ground-truth source for the reference: the `*.pyi` type stubs shipped inside the installed `pxz` package. Re-extract the reference if the SDK is upgraded.

## Debugging checklist

When a script fails or behaves incorrectly, work through these in order:

1. **Scene state** — the session is stateful. Is the occurrence id you're using still valid? Did a prior call already delete/transform it? Print `scene.getChildren(scene.getRoot())` to see what's actually loaded.
2. **File paths** — is the input file present at the path you passed? For export, does the parent directory exist and is the extension a supported export format (`io.getExportFormats`)?
3. **SDK call shape** — wrong parameter name or type is the most common silent failure. Occurrence args are `list[int]`, not `int`. Check the signature in `pxz-api-reference.md`.
4. **Tessellation / prep settings** — wrong settings cause wildly wrong polygon counts or import errors. Use `tessellateRelativelyToAABB` when scale is unknown.
5. **Export format** — the destination format must support what's in the scene (instancing, materials, animation).

Identify the likely cause, explain *why* it fails, describe how to verify, then provide the corrected snippet.

## Out of scope

- The UPA "Execute custom script" container conventions (argparse, `/workspace` paths, no-AM-write, `main()` guard) → see `at-upa-scripting`, which uses this reference for the API surface.
- Pipeline JSON, action IDs, picker metadata, fan-out syntax → see `pipeline-authoring`.
- Writing back to Asset Manager → chain an Asset Manager MCP tool / pipeline action; the AT scripting layer does not push to AM.
