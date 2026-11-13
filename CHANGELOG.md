# Changelog

## 0.7.4 — 2026-11-13

Asset Transformer (`uat-mcp`) moves to 0.7.3. Asset Manager (`uam-mcp`) and
Pipeline Automation (`upa-mcp`) move to 0.7.4.

All three plugins have new dependency versions and Asset Transformer moves to
the 2026.5 SDK, so each plugin rebuilds its environment automatically at the
start of your first session after updating. For Asset Transformer that
includes downloading the SDK again, which takes several minutes.

### Added

- **Pipeline Automation: stopping jobs and Project Service workers** (51 → 57
  tools). `stop_job` and `stop_project_job` call the API's stop route, which is
  separate from terminate. `start_worker`, `stop_worker`,
  `stop_project_service` and `send_project_service_command` manage Project
  Service workers. They are project-scoped and need the Automation Admin role,
  and the API marks the command route as temporary.
- **Pipeline Automation: `jobPipelineUid`** on approving and resuming job steps
  and on step logs (org and project variants), plus `startLine` on step logs.
  Use `jobPipelineUid` when a step runs inside several pipeline-reference
  invocations, which otherwise returns a 409.
- **Asset Manager: project features and dataset checks** (55 → 59 tools):
  `list_features`, `add_project_features`, `remove_project_features` and
  `check_dataset_in_asset`.
- **Asset Transformer: seven optimisation tools** (35 → 42 tools):
  `remove_hidden_geometry` (deletes parts and polygons no outside viewpoint
  can see), `decimate_to_budget` (shares a total triangle budget across parts
  by visible size, with optional name weights, and reports whether it stayed
  within budget), `cleanup_mesh`, `fix_normals_uv`, `list_materials`,
  `assign_material` and `instance_similar_parts`.
- **Asset Transformer: new options.** `decimate_target(triangle_count=...)` for
  an absolute target, `merge_occurrences(by_material=True)` for one part per
  material, and `import_file(prefer_load_mesh=True)` to load stored meshes
  instead of re-tessellating.
- **`at-scripting`: optimisation recipes** (`optimisation-recipes.md`):
  per-part budgets, LOD chains, perforated plates, world-space centring,
  inside-out rims, what baking transfers, and hidden geometry. Each recipe is
  marked as verified against a licensed SDK or as guidance. A new "Tools vs.
  `run_python`" section maps each tool to its SDK calls.
- **`pipeline-authoring`: Creo View (`.pvz`) input.** The Asset Transformer
  SDK cannot import `.pvz` directly. The skill shows how to convert it first
  with `python3wine` inside an "Execute custom script" step on version 1.3.x.
- **`COPILOT_SETUP.md`: a manual setup guide for GitHub Copilot** (VS Code and
  Copilot CLI). `copilot plugin install` installs the plugins but the servers
  do not start under Copilot, so the guide registers them by hand.

### Changed

- **Asset Transformer: Pixyz SDK 2026.5** (`pxz==2026.5.0.0`) on Windows, Linux
  and macOS. The API reference in `at-scripting` is re-checked against it.
- **`pipeline-authoring`: "Execute custom script" defaults to 1.3.1.** Every
  1.2.x version of the action is now archived on public cloud, so the example
  action ID and pipelines move to the latest available version.
- **Dependencies.** All three servers now use `mcp` 2.3.0, `pydantic` 2.14.3,
  `httpx2` 2.16.0, `PyJWT` 2.15.1 and `cryptography` 50.0.2; Asset Transformer
  also takes `pillow` 13.0.0.
- **Converted outputs become new, referenced assets.** The
  `asset-manager-authoring`, `pipeline-authoring` and `at-upa-scripting` skills
  now say to publish a converted file (a GLB from CAD, an optimised LOD) as a
  new asset that the source references as `Converted`, instead of adding it to
  a custom dataset on the source asset. `pipeline-authoring` documents the
  `Create asset` action's `source*` and `referenceType` inputs.

### Fixed

- **Asset Transformer: sub-part screenshots** rendered out of position, because
  the render dropped the parents' transforms.
- **Asset Transformer: `merge_occurrences`** skips parts with no triangles,
  cleans up emptied parents reliably, and returns `merged_occurrence_ids`.
- **Decimation selectors.** `decimateTarget` accepts only `triangleCount` and
  `ratio`. Any other key silently decimates the mesh to 0 triangles, so the
  tools use `triangleCount` only. The `ratio` value is a percentage: the
  `at-upa-scripting` example and a `SKILL.md` snippet passed a 0–1 fraction and
  kept 100× too few triangles.
- **SDK module names are case-sensitive:** the skills now use `"IO"`, not
  `"io"`, in `getModuleProperty` / `setModuleProperty` examples.
- **Asset Manager: `delete_project` when archiving is refused.** Unity's
  archive step can reject the plugin's sign-in with HTTP 401, even for an
  organization Owner, and a project must be archived before it can be
  deleted. `delete_project` now says plainly that nothing was deleted and
  links to the organization's project list in the Unity Cloud dashboard:
  archive the project there, then call `delete_project` again with
  `confirm=True`. A project that is already archived is deleted directly.
- **Asset Manager: documented errors.** `check_dataset_in_asset` rejects a
  dataset that is not in the asset with HTTP 400 code 40983, not 404.
  `add_project_features` explains that `MappedToUnityProject` can only be
  enabled on an empty project (HTTP 400 code 40760 "not empty"), so enable
  it right after `create_project`.

## 0.7.3 — 2026-09-25

Asset Manager (`uam-mcp`) and Pipeline Automation (`upa-mcp`) move to 0.7.3.
Asset Transformer (`uat-mcp`) has no changes and stays at 0.7.2, so
`/plugin update` does not offer it.

### Changed

- **Per-plugin attribution.** Asset Manager now sends
  `X-Unity-Cloud-Api-Source: uam_mcp@<version>` and `User-Agent: UAM_MCP/...`;
  Pipeline Automation sends `upa_mcp@<version>` and `UPA_MCP/...`. Both sent
  `uap_mcp` / `UAP_MCP` through 0.7.2, which left the calls they share (token
  refresh, OIDC discovery) unattributable to either plugin. Gateway queries
  should match all three values until older installs have updated. The
  `UAP_MCP_USER_AGENT` override, `UAP_MCP_HOME` and the shared `~/.uap_mcp`
  token cache are unchanged, so nobody is signed out.

## 0.7.2 — 2026-09-23

First release of **Industry AI Workflows**, a Claude Code plugin marketplace for
industry production workflows. It ships three Unity plugins, each installable on
its own — so if you publish assets but never touch CAD, you never download the
multi-gigabyte Pixyz SDK.

```text
/plugin marketplace add Unity-Technologies/industry-ai-workflows

/plugin install uam-mcp@industry-ai-workflows    # Unity Asset Manager
/plugin install uat-mcp@industry-ai-workflows    # Unity Asset Transformer
/plugin install upa-mcp@industry-ai-workflows    # Unity Pipeline Automation
```

Python 3.12 is the only machine prerequisite. Each plugin's first session builds
its own server environment in the background via a SessionStart hook; the server
comes up in the next session once that finishes. Asset Transformer's build
downloads the Pixyz SDK and takes several minutes — the other two are quick, and
they do not wait on it.

### Plugins

- **Unity Asset Manager** (`uam-mcp`, 55 tools) — organizations and projects,
  assets and versions, file upload and download, preview images, metadata and
  custom field definitions, references and dependency vocabularies, collections,
  labels, status flows, trash and restore, and cross-project search. Ships the
  `asset-manager-authoring` skill.
- **Unity Asset Transformer** (`uat-mcp`, 35 tools) — CAD import, scene
  inspection and hierarchy traversal, mesh preparation and repair, decimation and
  LOD generation, UV and ambient-occlusion baking, screenshots and turntable
  renders, export, and arbitrary pxz scripting. Ships the `at-scripting` and
  `at-upa-scripting` skills. Requires a Pixyz licence seat.
- **Unity Pipeline Automation** (`upa-mcp`, 51 tools) — authoring and versioning
  pipelines, triggering and monitoring jobs, step approval and resume, logs and
  stats, and app/action discovery, at both organization and project scope. Ships
  the `pipeline-authoring` skill.

### Authentication

One browser-based Unity user login (OAuth PKCE) shared by Asset Manager and
Pipeline Automation: signing in through either authenticates both, and
`unity_logout` signs out of both. The token cache lives at
`~/.uap_mcp/token.json`, resolved from your home directory with no plugin
identity in the path, which is what makes one login cover two separately
installed plugins. Refresh is serialized across processes, and a login is only
discarded when Unity definitively rejects it, so it survives being offline.

Asset Transformer authenticates separately, against a Pixyz licence server.
Seats are acquired lazily on first use and released when idle.

Settings are per plugin. If you use a private cloud, set the same `UNITY_VPC_*`
values in **both** Asset Manager and Pipeline Automation — they share one
sign-in, and a token minted for one deployment is refused by the other, which
shows up as a permanent "not logged in" rather than an error.

### Also in this release

- Each plugin ships a `setup` command — `/uam-mcp:setup`, `/uat-mcp:setup`,
  `/upa-mcp:setup` — that builds its environment on demand. The `SessionStart`
  hook that normally does this only fires when a session *starts*, so a plugin
  installed part-way through one has no environment until the next session.
  When a build finishes, open `/mcp` and **reconnect** that server — that is
  what starts it, and no restart is needed. `/reload-plugins` is suggested by
  Claude Code's own install summary but has been seen not to bring an MCP
  server up.
- Dependencies updated: `mcp` and `mcp-types` 2.2.0 across all three servers,
  plus `idna` 3.20, `pyjwt` 2.14.0, `python-dotenv` 1.2.3 and
  `typing-inspection` 0.4.4 in Asset Transformer.
- Asset Transformer's settings prompt asks for five things rather than eight.
  `AT_LICENSE_TOKENS`, `AT_LICENSE_FAIL_FAST` and `AT_MAX_IMPORT_BYTES` are
  still read from the environment — they are expert or shared-host options, not
  something to ask every user about. See SECURITY.md and `.env.example`.

### Notes

- **Experimental.** Tool names, parameters and behaviour may change between
  releases without a deprecation cycle.
- Plugins version independently, so an update to one does not show up as an
  update for the others.
- Unity-bound requests carry `X-Unity-Cloud-Api-Source: uap_mcp@<version>` and a
  `User-Agent` identifying the tool version, calling agent and OS, so API traffic
  is attributable in Unity's server-side logs. Each plugin reports its own
  version. Nothing is collected or transmitted client-side;
  `UAP_MCP_USER_AGENT` overrides the value, and setting it blank omits the header.
- Signed blob URLs returned by the API are validated before use — HTTPS only, no
  embedded credentials, public addresses only, no redirects — so a
  server-supplied URL cannot be turned into a request against loopback,
  link-local metadata or a private network.
- Local paths supplied by an agent are validated: credential stores are refused
  in both directions, and auto-executed locations are refused for writes.
  `UAP_MCP_ALLOWED_ROOTS` optionally confines file access to named directories.
- Dependencies install from hash-pinned lock files with `--require-hashes`.

### Private cloud (VPC) — experimental

Setting `UNITY_VPC_FQDN` points Asset Manager and Pipeline Automation at a Unity
private cloud deployment and signs in against that deployment's own identity
service. Public cloud remains the default. Cached logins are tagged with the
deployment that issued them, so a token is never presented to a different one.
The Pipeline Automation API version is auto-detected, since deployments differ.
Three tools report clearly rather than failing where private cloud does not serve
the underlying route: `list_organizations`, `delete_project` and `get_job_stats`.
