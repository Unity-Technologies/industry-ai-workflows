# Changelog

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
