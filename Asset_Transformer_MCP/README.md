# Asset Transformer MCP

MCP server that exposes Asset Transformer SDK (`pxz`) capabilities for CAD/3D processing.

Main entrypoint: `at_mcp_server.py`

## Prerequisites

- Python 3.12
- Access to an Asset Transformer **FlexLM floating license server** (node-locked/local license files are not supported by this server)
- Asset Transformer SDK (`pxz`) — installed from Unity's customer-accessible Pixyz package index (see Install)

## Install

The repo-level installer (`python install.py` from the repo root) handles everything
below automatically, including the `pxz` install. To set this server up manually,
run these commands from the `Asset_Transformer_MCP` folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install pxz --no-deps --extra-index-url https://unity3ddist.jfrog.io/artifactory/api/pypi/pixyz-pypi-prod-local/simple
pip install -r requirements.txt
```

The Pixyz package index above is available to customers — no Unity-internal
network or VPN access is required to install `pxz`.

## Configure

Copy `.env.example` to `.env` and set your license server details:

```powershell
Copy-Item .env.example .env
```

Then open `.env` and fill in your values:

```
AT_LICENSE_SERVER_HOST=<your-license-server-hostname>
AT_LICENSE_SERVER_PORT=27005
```

Optional settings (see `.env.example` for details):

```
AT_LICENSE_TOKENS=        # extra comma-separated Pixyz feature tokens (default: none)
AT_LICENSE_FAIL_FAST=1    # validate license availability at startup (default: off/lazy)
AT_MAX_CONCURRENT_JOBS=1  # cap on simultaneous heavy AT operations (default: 1, 0 = unlimited)
```

## License seat behaviour

Asset Transformer seats are limited and served by a FlexLM license server, so
this MCP is careful about when it holds one:

- **Lazy acquisition.** Starting the MCP server does NOT consume a license
  seat. A seat is only acquired the first time a tool that needs the `pxz` SDK
  actually runs. If `AT_LICENSE_SERVER_HOST` is not set, tools return a clear
  `No license server configured` error instead of touching any license.
- **Only what is needed.** Only the mandatory product token is acquired by
  default. Extra optional feature tokens can be requested with
  `AT_LICENSE_TOKENS` (comma-separated) if your workflow needs them.
- **Release semantics.** The seat is released automatically on clean server
  shutdown. You can also free it at any time without stopping the server with
  the `release_license` tool — note this clears the in-memory scene (the SDK
  has no way to drop the seat while keeping the session); the next tool call
  re-acquires a seat and starts from an empty scene. If the process is killed
  hard, the FlexLM server reclaims the seat after its own timeout.
- **Availability check.** The `check_license` tool reports whether the
  configured license server is reachable and a seat is available (host and
  port included in the output). The Pixyz SDK cannot query availability
  without acquiring, so if no seat is currently held the tool briefly acquires
  one and releases it again before returning.
- **Fail fast (optional).** Set `AT_LICENSE_FAIL_FAST=1` to validate license
  availability at startup (acquire + immediate release) and exit with a clear
  error if the server is unreachable — useful for CI or kiosk setups. Default
  is off: fully lazy.
- **Concurrency cap.** `AT_MAX_CONCURRENT_JOBS` (default `1`) limits how many
  heavy operations (import, prepare, optimise, export, render, bake) run at
  once so machines and license pools are not overwhelmed. Set `0` for
  unlimited.
- **Clear errors.** License failures during a tool call are returned as a
  normal JSON error envelope with the reason and the configured host/port —
  the server keeps running and retries lazily on the next call.

## MCP Client Setup

Point your MCP client at the venv Python and the server script. Example `.mcp.json`:

```json
{
  "mcpServers": {
    "asset_transformer": {
      "command": "C:\\path\\to\\Asset_Transformer_MCP\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\Asset_Transformer_MCP\\at_mcp_server.py"]
    }
  }
}
```

Replace `C:\\path\\to\\Asset_Transformer_MCP` with the actual path on your machine.

## Features

- CAD import and export (`import_file`, `export_scene`)
- Repair/tessellation and optimization (`prepare_cad`, `optimise_cad`, `run_pipeline`)
- Scene queries and editing (`get_scene_info`, `get_children`, `delete_occurrences`, `merge_occurrences`, `set_occurrence_visibility`)
- Search and filtering (`find_occurrences_by_name`, `find_occurrences_by_property`, `find_occurrences_by_size`, `batch_delete_by_query`)
- Visual outputs (`take_screenshot`, `take_screenshot_set`, `render_turntable_video`)
- Analysis and export (`get_scene_statistics`, `export_hierarchy_json`, `bake_ambient_occlusion`)
- License management (`check_license`, `release_license`)
- Guided MCP prompts (`optimise_model`, `review_model`, `inspect_scene`, `export_workflow`)

## Tool Groups

- `Scene`: `get_scene_info`, `get_children`, `get_occurrence_name`, `delete_occurrences`, `clear_scene`
- `I/O`: `list_cad_files`, `import_file`, `export_scene`
- `Prepare/Optimize`: `prepare_cad`, `optimise_cad`, `decimate_target`, `generate_lods`, `run_pipeline`
- `Query`: `find_occurrences_by_name`, `find_occurrences_by_property`, `find_occurrences_by_size`, `get_occurrence_info`
- `Edit`: `batch_delete_by_query`, `set_occurrence_visibility`, `merge_occurrences`
- `Render/Bake`: `take_screenshot`, `take_screenshot_set`, `render_turntable_video`, `bake_ambient_occlusion`
- `Stats/Export`: `polygon_count`, `get_aabb`, `get_scene_statistics`, `export_hierarchy_json`
- `License`: `check_license`, `release_license`
- `Advanced`: `run_python` (executes arbitrary Python in-process with `pxz` in scope)

## Example Workflow

1. `list_cad_files` to select a source model.
2. `run_pipeline` to import + prepare + optimize in one step.
3. `take_screenshot_set` for visual QA.
4. `get_scene_statistics` to verify triangle/vertex reduction.
5. `export_scene` to target format (`.glb`, `.fbx`, `.obj`, `.pxz`, `.step`).

## Notes

- `render_turntable_video` requires optional packages: `ImageIO`, `imageio-ffmpeg`, `pillow`.
- Screenshot tools can include base64 image payloads in the text response.
- `run_python` executes arbitrary Python in-process — only use it with trusted input.
- HTTP/SSE transport defaults to port 8766 (8765 is reserved for the Unity PKCE login callback used by the Asset Manager / Pipeline Automation MCPs).
