# Industry AI Workflows

> **Experimental** — these plugins are an experimental release. Tool names,
> parameters, prompts, and behavior may change between versions without a
> deprecation cycle, and features may appear or be removed as the project
> evolves. Don't build unattended production automation on it yet, and
> please report what works and what doesn't.

A Claude Code plugin marketplace for industry production workflows. Today it
ships three Unity plugins, each installable on its own:

| Plugin | What it does |
|---|---|
| `uam-mcp` | Unity Asset Manager — projects, assets, versions, files, metadata, references, collections |
| `uat-mcp` | CAD import, optimisation, rendering and export via the Asset Transformer (pxz) SDK |
| `upa-mcp` | Unity Pipeline Automation — pipelines, versions, jobs, logs |

Install only what you need. Asset Transformer is a large install (it downloads
the Pixyz SDK) and needs a licence seat; if you only publish assets, you never
have to pay for it.

## Repository Layout

- `Asset_Manager_MCP/`, `Asset_Transformer_MCP/`, `Pipeline_Automation_MCP/` — one plugin each
- `.claude-plugin/marketplace.json` — the marketplace manifest listing them
- inside each plugin: `.claude-plugin/plugin.json`, `mcp-servers.json`, `hooks/`,
  `bootstrap.py`, `install.py`, `uninstall.py`, its server code and its `skills/`

Each plugin is self-contained and imports nothing from the others — Claude Code
copies only a plugin's own subtree onto an installed machine. Asset Manager and
Pipeline Automation therefore ship independent copies of the Unity auth code.
They still share one sign-in, because the token cache lives in your home
directory and carries no plugin identity.

## Which MCP Should I Use?

| MCP | Primary Use | Backend |
| --- | --- | --- |
| Asset Manager | Manage Unity Cloud orgs/projects/assets/collections/references | Unity Cloud REST API |
| Asset Transformer | Process CAD/3D scenes and export optimized outputs | Asset Transformer SDK (`pxz`) |
| Pipeline Automation | Create, trigger, and monitor Unity automation pipelines and jobs | Unity Pipeline Automation REST API v1 |

For Unity Editor and project tasks beyond these servers — installing Unity
Editor versions, adding build-support modules, opening Unity projects from the
terminal — there is the
[Unity CLI](https://docs.unity.com/en-us/unity-cli/use-unity-cli)
(experimental, like this plugin); the cloud servers' instructions point AI
agents at it, so an agent will offer to run it for you alongside this plugin.

## Prerequisites

- Windows, macOS, or Linux. The setup selects the right Asset Transformer
  (`pxz`) build for your platform automatically (the macOS build can trail the
  Windows/Linux version slightly).
- Python 3.12 installed on the machine (e.g. `winget install Python.Python.3.12`
  on Windows, or https://www.python.org/downloads/). Asset Manager and Pipeline
  Automation accept 3.11+, but Asset Transformer's dependencies are pinned for
  exactly 3.12, and the venvs are built with it. The setup discovers a
  3.12 interpreter itself (`py -3.12`, `python3.12`, ...).
- Network access to Unity's customer-accessible Pixyz package index for the `pxz`
  SDK (Asset Transformer only). It is installed automatically; to install
  manually:

  ```bash
  pip install pxz --no-deps --extra-index-url https://unity3ddist.jfrog.io/artifactory/api/pypi/pixyz-pypi-prod-local/simple
  ```

- A Unity account for Asset Manager and Pipeline Automation (browser-based user
  login via the `unity_login` tool).
- Asset Transformer license server/network access for Asset Transformer MCP.

## Quick Start (Claude Code plugin)

Register the marketplace once, then install whichever plugins you want —
inside Claude Code, run:

```text
/plugin marketplace add Unity-Technologies/industry-ai-workflows

/plugin install uam-mcp@industry-ai-workflows
/plugin install uat-mcp@industry-ai-workflows
/plugin install upa-mcp@industry-ai-workflows
```

Each plugin brings its own skills: `asset-manager-authoring` with Asset
Manager; `at-scripting` and `at-upa-scripting` with Asset Transformer;
`pipeline-authoring` with Pipeline Automation.

That's the whole install. The only machine prerequisite is Python 3.12 (see
Prerequisites above). The first session after installing builds each plugin's
server environment in the background via its SessionStart hook; the servers
come up in the next session once the build finishes. Asset Transformer's build
downloads the Pixyz SDK and can take several minutes — the others are quick,
and they no longer wait on it. The environments live in Claude Code's
per-plugin data directory, so they survive plugin updates.

### Alternative install routes

- **Windows setup exe**: download `IndustryAIWorkflows-Setup-<version>.exe`
  from the [latest release](https://github.com/Unity-Technologies/industry-ai-workflows/releases/latest),
  run it, and follow the prompts. It extracts the sources, pre-builds the server
  environments, and prints the two `/plugin` commands to finish. The executable
  is not code-signed, so Windows SmartScreen will warn on first run —
  **More info → Run anyway**.
- **Manual clone** (e.g. for development or air-gapped mirrors):

  ```text
  # 1. Clone the repo (Claude Code reads the plugin sources from disk).
  git clone https://github.com/Unity-Technologies/industry-ai-workflows.git

  # 2. Optional: pre-build the server environments instead of letting the
  #    plugin's first session do it. Each plugin has its own installer;
  #    run only the ones you want. Discovers a Python 3.12 automatically.
  cd industry-ai-workflows
  python Asset_Manager_MCP/install.py

  # 3. Inside Claude Code, register the local marketplace and install the plugin.
  /plugin marketplace add /absolute/path/to/industry-ai-workflows
  /plugin install uam-mcp@industry-ai-workflows
  /plugin install uat-mcp@industry-ai-workflows
  /plugin install upa-mcp@industry-ai-workflows
  ```

  After step 3, run Claude Code from the project directory you actually want to
  work in (not from `industry-ai-workflows/`). Don't move or rename the cloned folder — it is
  the marketplace source Claude Code updates from.

All routes build the same environments in the same place
(Claude Code's per-plugin data directory under `~/.claude/plugins/data/`), which the
committed `mcp-servers.json` points at on every OS.

When the plugin is enabled Claude Code will prompt you for the Asset Transformer
license settings (`AT_LICENSE_SERVER_HOST`, `AT_LICENSE_SERVER_PORT`, and optional
tuning values — defaults provided). These are passed to the server as environment
variables — no `.env` file required when using the plugin. You can also set them
non-interactively: `claude plugin install uat-mcp@industry-ai-workflows --config AT_LICENSE_SERVER_HOST=licenses.example.com`.

Settings are per plugin. If you run Asset Manager and Pipeline Automation
against a private cloud, set the same `UNITY_VPC_*` values in **both** — they
share one sign-in, and a token minted for one deployment is refused by the
other, which shows up as a permanent "not logged in" rather than an error.

Asset Manager and Pipeline Automation authenticate via a browser-based Unity user
login: the first time you use either server, call its `unity_login` tool and sign in
with your Unity account. Sessions surface this automatically — when you are signed
out, Claude is told at session start and will offer to run `unity_login` for you
(local stdio MCP servers cannot use Claude Code's `/mcp` OAuth panel; that flow
only exists for remote HTTP servers). Tokens are cached locally in a single shared cache
(`~/.uap_mcp/token.json`, or `$UAP_MCP_HOME/token.json`) and refreshed
automatically — logging in once via either server authenticates both.

There are no preset org/project settings: each session, the assistant lists your
organizations, asks which one to work in (`set_default_organization`), then does
the same for the project (`set_default_project`, offering `create_project` when
none fits). Every tool also accepts explicit `org_id` / `project_id` arguments.

### Running a single MCP server standalone

If you want to run one server outside the plugin (e.g. for development), each subfolder has
its own README and `.env.example`:

- `Asset_Manager_MCP/README.md`
- `Asset_Transformer_MCP/README.md`
- `Pipeline_Automation_MCP/README.md`

### Other MCP clients (Cursor, GitHub Copilot / VS Code, …)

These are standard stdio MCP servers — the Claude Code plugins are
just packaging. Any MCP-capable client can run them. Support for non-Claude
clients is experimental (the Claude Code plugins are the tested path), but the
recipe is always the same: **build the environment for each server you want,
then register an interpreter + script pair** in the client's MCP configuration.

**Step 1 — clone and build:**

```text
git clone https://github.com/Unity-Technologies/industry-ai-workflows.git
cd industry-ai-workflows

# Each plugin has its own installer — run only the ones you need.
python Asset_Manager_MCP/install.py       --venv-root <dir>
python Asset_Transformer_MCP/install.py   --venv-root <dir>
python Pipeline_Automation_MCP/install.py --venv-root <dir>
```

Needs Python 3.12 on the machine. `--venv-root` picks where the environments
(`AM/`, `AT/`, `PA/`) are built — with a non-Claude client choose somewhere
explicit, e.g. `--venv-root C:\mcp-venvs` (Windows) or `--venv-root ~/mcp-venvs`
(macOS/Linux). Point all three at the same directory to get the layout below.
Omitting it builds into that plugin's own Claude Code data directory, which
works even when Claude Code isn't installed — the build prints the exact paths
either way.

**Step 2 — register the servers.** Each server is one `command`/`args` pair:
the environment's Python running the server script from the clone.

| Server | `command` | `args` |
|---|---|---|
| Asset Manager | `<venvs>/AM/Scripts/python.exe` (Win) / `<venvs>/AM/bin/python` | `<repo>/Asset_Manager_MCP/am_mcp_server.py` |
| Asset Transformer | `<venvs>/AT/Scripts/python.exe` / `<venvs>/AT/bin/python` | `<repo>/Asset_Transformer_MCP/at_mcp_server.py` |
| Pipeline Automation | `<venvs>/PA/Scripts/python.exe` / `<venvs>/PA/bin/python` | `<repo>/Pipeline_Automation_MCP/pa_mcp_server.py` |

Use absolute paths in both fields. Settings the Claude Code plugin would
collect through its configuration UI go in each server's `env` block instead:
the Asset Transformer license server (`AT_LICENSE_SERVER_HOST` /
`AT_LICENSE_SERVER_PORT`) on the `asset_transformer` entry, and `UNITY_VPC_*`
(private cloud, see below) on `asset_manager` and `pipeline_automation` if you
use a VPC deployment.

**Cursor** — add to `~/.cursor/mcp.json` (all projects) or
`<project>/.cursor/mcp.json` (one project), then enable the servers under
*Settings → Cursor Settings → MCP*, where a green dot and a tool count show
each server came up:

```json
{
  "mcpServers": {
    "asset_manager": {
      "command": "C:/mcp-venvs/AM/Scripts/python.exe",
      "args": ["C:/repos/industry-ai-workflows/Asset_Manager_MCP/am_mcp_server.py"]
    },
    "asset_transformer": {
      "command": "C:/mcp-venvs/AT/Scripts/python.exe",
      "args": ["C:/repos/industry-ai-workflows/Asset_Transformer_MCP/at_mcp_server.py"],
      "env": {
        "AT_LICENSE_SERVER_HOST": "licenses.example.com",
        "AT_LICENSE_SERVER_PORT": "27005"
      }
    },
    "pipeline_automation": {
      "command": "C:/mcp-venvs/PA/Scripts/python.exe",
      "args": ["C:/repos/industry-ai-workflows/Pipeline_Automation_MCP/pa_mcp_server.py"]
    }
  }
}
```

The tools are used from Cursor's agent (Composer/chat in agent mode): ask for
something ("list my Unity organizations") and approve the tool calls it
proposes, or enable auto-run for the servers you trust.

**GitHub Copilot (VS Code)** — add to `.vscode/mcp.json` in your workspace,
or user-wide via the *MCP: Open User Configuration* command. Note the
slightly different schema (`servers`, plus a `type` field):

```json
{
  "servers": {
    "asset_manager": {
      "type": "stdio",
      "command": "C:/mcp-venvs/AM/Scripts/python.exe",
      "args": ["C:/repos/industry-ai-workflows/Asset_Manager_MCP/am_mcp_server.py"]
    },
    "asset_transformer": {
      "type": "stdio",
      "command": "C:/mcp-venvs/AT/Scripts/python.exe",
      "args": ["C:/repos/industry-ai-workflows/Asset_Transformer_MCP/at_mcp_server.py"],
      "env": {
        "AT_LICENSE_SERVER_HOST": "licenses.example.com",
        "AT_LICENSE_SERVER_PORT": "27005"
      }
    },
    "pipeline_automation": {
      "type": "stdio",
      "command": "C:/mcp-venvs/PA/Scripts/python.exe",
      "args": ["C:/repos/industry-ai-workflows/Pipeline_Automation_MCP/pa_mcp_server.py"]
    }
  }
}
```

VS Code shows a *Start* code-lens in the `mcp.json` editor and lists the
servers under *MCP: List Servers*. The tools are available to Copilot Chat in
**agent mode** — open the Tools picker in the chat input to confirm the Unity
tools are listed and enabled. If a server fails to start, *MCP: List Servers →
Show Output* has the server's stderr log.

**Verify and use** (any client):

- First conversation: ask the agent to call `unity_login` — it opens a
  browser for the Unity sign-in. The token cache (`~/.uap_mcp/token.json`) is
  shared machine-wide, so one login covers Asset Manager and Pipeline
  Automation in every client, and a login done in Claude Code carries over.
- There are no preset org/project defaults: start by asking the agent to list
  your organizations and set one (`set_default_organization`,
  `set_default_project`) — the same flow the Claude Code plugin walks through
  at session start.
- A quick no-credentials smoke test: `check_license` (Asset Transformer)
  and `unity_auth_status` (Asset Manager / Pipeline Automation) both answer
  without being signed in.
- The bundled authoring skills (`pipeline-authoring`, `at-scripting`,
  `at-upa-scripting`, `asset-manager-authoring`) and the session-start
  signed-out notice are Claude Code plugin features; other clients get the
  full tool set but not the skills. The `skills/` folder is plain markdown —
  in other clients you can paste the relevant guide into chat (or add it to
  the agent's context) when authoring pipelines or pxz scripts.

### Private cloud / VPC (experimental)

The plugin can talk to a Unity private cloud (VPC) deployment instead of public
Unity Cloud. Set these in the plugin settings (leave them all blank for public
Unity Cloud):

| Setting | Required | Description |
|---|---|---|
| `UNITY_VPC_FQDN` | Yes (VPC) | Your deployment's host, e.g. `private-cloud.example.com` |
| `UNITY_VPC_PATH_PREFIX` | Usually | Path prefix in front of the service paths — commonly `backend` |
| `UNITY_VPC_OPENID_CONFIG_URL` | No | Override for the OpenID discovery URL (default: `https://<host>/auth/realms/unity/.well-known/openid-configuration`) |
| `UNITY_VPC_CLIENT_ID` | No | OAuth client for the browser sign-in (default: `dashboard`) |
| `UNITY_VPC_ASSETS_PATH` | No | Asset Manager service path (default: `assets/v1`) |
| `UNITY_VPC_AUTOMATION_PATH` | No | Pipeline Automation service path (default: auto-detect `api/automation/v1`, then `api/automation/v1alpha1`) |

With `UNITY_VPC_FQDN` set, Asset Manager and Pipeline Automation call your
deployment (`https://<host>/<prefix>/assets/v1/...` and
`.../api/automation/v1...`)
and `unity_login` signs in against your deployment's own identity service
instead of Unity ID. Private clouds serve Pipeline Automation at an API
version that varies by bundle release (`api/automation/v1` on newer bundles,
`api/automation/v1alpha1` on older ones); the right one is detected
automatically on first use. Logins are tagged with the deployment they were issued
for, so a public-cloud token is never sent to a private cloud (or vice versa) —
switching between them requires signing in again. Asset Transformer is
unaffected (it runs locally against your Pixyz license server).

Two features are public-cloud only and report that clearly when used on a
private cloud: `delete_project` (it uses the public dashboard's entities
gateway) and Genesis-id resolution (private clouds identify organizations by
their own ids, which are used as supplied).

> **Experimental — the least exercised part of the toolkit.** Sign-in, reads,
> Asset Manager writes (asset create, upload/download, collections,
> freeze/version) and Pipeline Automation pipeline management
> (create/update/version/lifecycle) all work against a private cloud.
> Triggering, monitoring and approving jobs is the part not yet
> exercised there — treat it as unproven. Deployments vary in which automation
> API version they run, which is detected automatically (see above), but if
> yours serves either service somewhere unusual, set `UNITY_VPC_ASSETS_PATH` /
> `UNITY_VPC_AUTOMATION_PATH`. Please report what you find.

## Troubleshooting

- **"Python 3.12 not found" at session start** — install it
  (`winget install Python.Python.3.12` on Windows, python.org elsewhere) and
  start a new session. The plugin cannot install Python for you.
- **Unity MCP servers missing right after installing the plugin** — the first
  session builds the server environments in the background (several minutes;
  it downloads the Asset Transformer SDK). They connect in the next session
  once the build finishes. Progress log: `bootstrap.log` in the plugin's data
  directory (under `~/.claude/plugins/data/`).
- **Asset Transformer tools return "No license server configured" or license
  errors** — set `AT_LICENSE_SERVER_HOST` (and port) in the plugin settings
  (`/plugin configure uat-mcp@industry-ai-workflows`); the host must be a
  reachable FlexLM Pixyz license server with free seats (`check_license`
  reports availability). No license at all? You are not blocked: the agent
  can still author and syntax-check pxz scripts locally and run them in the
  cloud via Pipeline Automation's "Execute custom script" action — only
  local execution needs a seat. For full local capabilities, contact your
  Unity account representative or
  [sales](https://unity.com/contact-us?reason=Speak+to+Sales&step=3&topic=Industrial+Solutions).
- **"Not logged in to Unity Cloud"** — run the `unity_login` tool (opens a
  browser). One login covers both Asset Manager and Pipeline Automation.
- **"The cached login was for a different deployment"** — you switched between
  public Unity Cloud and a private cloud (or between two private clouds). Run
  `unity_login` again to sign in to the deployment now configured.
- **404s from Asset Manager or Pipeline Automation on a private cloud** — the
  service path is wrong for your deployment. Most deployments need
  `UNITY_VPC_PATH_PREFIX=backend`; for Pipeline Automation also try
  `UNITY_VPC_AUTOMATION_PATH`.

## Privacy

The only identifying information these plugins add to anything is two HTTP
headers on requests the servers already make to Unity Cloud:
`X-Unity-Cloud-Api-Source: <source>@<version>` (Unity's standard
`[source]@[version]` convention for naming the tool behind an API call:
`uam_mcp@<version>` from Asset Manager, `upa_mcp@<version>` from Pipeline
Automation) and the standard `User-Agent` header, e.g.
`UAM_MCP/0.7.3 (claude-code; Windows)` — tool name and version, the agent
driving it (the MCP client name your editor reports, e.g. Claude Code or
Copilot), and the OS family, so Unity can attribute API traffic to this
tool. Each plugin reports its own version, so Asset Manager and Pipeline
Automation can show different ones. No username, hostname, file path, or
asset/project name is added.
Support override: `UAP_MCP_USER_AGENT` replaces the value; setting it to an
empty string omits the header.

There is **no analytics or event pipeline**: these plugins never call any
analytics service, keep no usage logs, and login tokens never leave your
machine (`~/.uap_mcp/token.json`).

## License

Industry AI Workflows copyright © 2026 Unity Technologies.

Licensed under the
[Unity Terms of Service](https://unity.com/legal/terms-of-service) as an
Experimental / Evaluation Version — see [LICENSE.md](LICENSE.md). This is
source-available software, not an OSI open-source license.

