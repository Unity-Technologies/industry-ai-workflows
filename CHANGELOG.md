# Changelog

## 0.6.1 — 2026-09-03

### Security

Hardening from the pre-publication security review. Nothing here changes what
the tools do on a normal single-developer install; the new controls close paths
that only an attacker or a mistake takes, and the new environment variables are
opt-in lockdown for shared and CI hosts. See SECURITY.md for the trust boundary
these are drawn around.

- **Local paths are validated** (`shared/local_paths.py`). Every agent-supplied
  path — Asset Manager uploads and downloads, Asset Transformer exports,
  screenshots, renders, hierarchy JSON, recorder dumps, CAD imports and folder
  listings — is resolved for real and refused if it names a credential store
  (`~/.ssh`, `~/.aws`, the token cache, `*.pem`, `.env`, ...) or, for writes, a
  location something else auto-executes (`~/.claude/`, an installed plugin's
  files, `site-packages`, shell rc files, autostart folders). `Path.resolve()`
  replaces the `os.path.abspath` calls that never confined anything.
  `UAP_MCP_ALLOWED_ROOTS` optionally confines everything to named directories.
- **`run_python` can be switched off** with `AT_DISABLE_RUN_PYTHON=1` — the tool
  is not registered at all, so it never appears in `tools/list`. On by default:
  it is what the Asset Transformer is for.
- **CAD-derived strings are labelled as untrusted** in `get_children`,
  `get_occurrence_info` and both `find_occurrences_by_*` tools, so part names
  and metadata read out of an imported file are not mistaken for instructions.
- **The HTTP/SSE transports are hardened.** `Host` and `Origin` are now
  validated (mcp leaves this off by default), a non-loopback `--host` is refused
  unless `AT_HTTP_BEARER_TOKEN` is set, and when it is set the token is required
  on every request.
- **The signed-URL DNS-rebinding gap is closed.** `open_transfer_session`
  connects to the address that was validated, presenting the original hostname
  for SNI and `Host`, so the name is no longer resolved a second time at connect.
- **Dependencies install from hash-pinned locks.** `requirements.lock` per
  server, installed with
  `--require-hashes` against an explicit `--index-url`. The pxz wheel's URL and
  SHA256 are logged instead (per-platform releases lag, so a checked-in hash set
  would be wrong two-thirds of the time).
- **The token cache is owner-only on Windows too** — an explicit ACL, not just
  the `0600` mode that Windows ignores — and a `UAP_MCP_HOME` pointing outside
  the user profile now warns.
- `AT_MAX_IMPORT_BYTES` optionally caps CAD import size.

Note for existing installs: locking resolves Asset Manager's and Pipeline
Automation's declared ranges to today's versions, so the next rebuild moves them
from `mcp` 2.0.0 to 2.1.0 (both within the existing `>=2.0.0,<3` cap). Asset
Transformer is unaffected — its requirements were already exact pins. Both servers
were smoke-tested against the locked set.

## 0.6.0 — 2026-08-12

First public release of the Unity Asset Pipeline MCP toolkit: three MCP servers
that let an AI agent drive Unity's asset pipeline, plus the authoring skills
that teach it how.

**Experimental.** Tool names, parameters and behaviour may change between
releases.

### Servers

- **Asset Manager** (55 tools) — organizations and projects, assets and their
  versions, file upload and download, preview images, metadata and custom field
  definitions, references and dependency vocabularies, collections, labels,
  status flows, trash and restore, and cross-project search.
- **Asset Transformer** (35 tools) — CAD import, scene inspection and
  hierarchy traversal, mesh preparation and repair, decimation and LOD
  generation, UV and ambient-occlusion baking, screenshots and turntable
  renders, export, and arbitrary pxz scripting. Backed by the Pixyz SDK.
- **Pipeline Automation** (51 tools) — authoring and versioning pipelines,
  triggering and monitoring jobs, step approval and resume, logs and stats, and
  app/action discovery, at both organization and project scope.

### Skills

`asset-manager-authoring`, `at-scripting`, `at-upa-scripting` and
`pipeline-authoring` — reference material for publishing assets, writing pxz
scripts (locally and inside the "Execute custom script" pipeline action), and
authoring pipeline JSON.

### Install

A Claude Code plugin, installable straight from GitHub:

```text
/plugin marketplace add Unity-Technologies/unity-asset-pipeline-mcp
/plugin install uap-mcp@unity-asset-pipeline-marketplace
```

Python 3.12 is the only machine prerequisite. A `SessionStart` hook builds the
three server environments in the background on first run — including the Asset
Transformer SDK — into Claude Code's per-plugin data directory, so they survive
plugin updates. Manual pre-building (`python install.py`), a Windows setup
executable, and configuration for non-Claude MCP clients are all supported; see
the README.

### Authentication

One browser-based Unity user login (OAuth PKCE) shared by Asset Manager and
Pipeline Automation: signing in through either server's `unity_login`
authenticates both, and `unity_logout` signs out of both. Tokens are cached
locally under `~/.uap_mcp/token.json` and refreshed automatically; refresh is
serialized across processes so concurrent servers cannot invalidate a
single-use refresh token. A login is only discarded when Unity definitively
rejects it, so it survives being offline.

Asset Transformer authenticates separately, against a Pixyz license server.
Seats are acquired lazily on first use and released when idle, with a
configurable concurrency cap.

### Private cloud (VPC) — experimental

Setting `UNITY_VPC_FQDN` points Asset Manager and Pipeline Automation at a Unity
private cloud deployment and signs in against that deployment's own identity
service. Public cloud remains the default. Cached logins are tagged with the
deployment that issued them, so a token is never presented to a different one.
The Pipeline Automation API version is auto-detected, since deployments differ.
Three tools report clearly rather than failing where private cloud does not
serve the underlying route: `list_organizations`, `delete_project` and
`get_job_stats`.

### Notes

- Unity-bound requests carry `X-Unity-Cloud-Api-Source: uap_mcp@<version>` and a
  `User-Agent` identifying the tool version, calling agent and OS, so API
  traffic is attributable in Unity's server-side logs. Nothing is collected or
  transmitted client-side; `UAP_MCP_USER_AGENT` overrides the value, and setting
  it blank omits the header. On a private cloud the headers only ever reach the
  customer's own ingress.
- Signed blob URLs returned by the API are validated before use — HTTPS only, no
  embedded credentials, public addresses only, no redirects — so a
  server-supplied URL cannot be turned into a request against loopback, link-local
  metadata or a private network.
