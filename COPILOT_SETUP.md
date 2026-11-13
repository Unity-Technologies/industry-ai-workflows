# Set up Unity Industry AI Workflows for GitHub Copilot

**For the person:** paste or attach this file in GitHub Copilot (VS Code agent
mode or Copilot CLI) and say *"Follow COPILOT_SETUP.md to set this up for me."*

**For the Copilot agent:** these are your instructions. Work through them in
order, run the commands yourself, and stop to ask the user only where it says
**ASK**. Use the shell commands that match the user's OS.

---

## What you are installing

[industry-ai-workflows](https://github.com/Unity-Technologies/industry-ai-workflows)
provides three independent MCP servers (stdio, Python) plus authoring skills:

| Server | Folder | What it does | Needs |
|---|---|---|---|
| `asset_manager` | `Asset_Manager_MCP` | Unity Asset Manager: assets, versions, files, metadata, collections, projects | Unity account (browser sign-in) |
| `pipeline_automation` | `Pipeline_Automation_MCP` | Unity Pipeline Automation: author, trigger and monitor pipelines | Unity account (browser sign-in) |
| `asset_transformer` | `Asset_Transformer_MCP` | Local CAD processing with the Pixyz / Asset Transformer SDK | Pixyz FlexLM license server; multi-GB SDK download |

The repo is packaged as a Claude Code plugin marketplace. **Do not use
`copilot plugin install` for these plugins.** It installs, but the servers do
not start under Copilot: the setup hook breaks under Windows PowerShell, the
server `command` path placeholder is not expanded, and plugin settings arrive
as literal `${user_config.*}` text, which switches the Unity servers into
private-cloud mode. Use the manual setup below instead.

## Step 0 — Ask the user what they need

**ASK** (one question, multiple choice): which servers do they want?
- Asset Manager
- Pipeline Automation
- Asset Transformer (only if they have a Pixyz license server)

If they choose Asset Transformer, **ASK** for the license server host name and
port (the port is usually `27005`).

If they mention a Unity **private cloud / VPC** deployment, **ASK** for its
values (see "Private cloud" at the end). Otherwise assume public Unity Cloud and
don't ask.

## Step 1 — Prerequisites

- **Git** must be on PATH.
- **Python 3.12** must be installed. Check with `py -3.12 --version` (Windows)
  or `python3.12 --version` (macOS/Linux). If it is missing, tell the user to
  install it from https://www.python.org/downloads/ (on Windows, tick "Add
  python.exe to PATH") and wait for them. Asset Transformer requires exactly
  3.12; the installers find a 3.12 interpreter on their own.

## Step 2 — Clone the repo

Use short paths. On Windows, deep folders can push venv DLL paths past the
path-length limit and break the build.

Windows (PowerShell):
```powershell
git clone https://github.com/Unity-Technologies/industry-ai-workflows.git "$HOME\industry-ai-workflows"
```

macOS / Linux:
```bash
git clone https://github.com/Unity-Technologies/industry-ai-workflows.git ~/industry-ai-workflows
```

From here on:
- `<repo>` = that clone folder
- `<venvs>` = `$HOME\mcp-venvs` (Windows) or `~/mcp-venvs` (macOS/Linux)

## Step 3 — Build one environment per chosen server

Run only the lines for the servers the user chose. Any `python` works to
launch the installer.

```text
python <repo>/Asset_Manager_MCP/install.py       --venv-root <venvs>
python <repo>/Pipeline_Automation_MCP/install.py --venv-root <venvs>
python <repo>/Asset_Transformer_MCP/install.py   --venv-root <venvs>
```

- Each run ends with a summary such as `AM: OK`. Treat anything else as a
  failure: show the user the output and retry once with `--recreate`.
- Asset Transformer downloads the Pixyz SDK (several GB) from Unity's package
  index and can take a long time. Run it in the background or tell the user to
  expect a wait.

This produces the following interpreters:

| Server | Windows | macOS / Linux |
|---|---|---|
| asset_manager | `<venvs>\AM\Scripts\python.exe` | `<venvs>/AM/bin/python` |
| pipeline_automation | `<venvs>\PA\Scripts\python.exe` | `<venvs>/PA/bin/python` |
| asset_transformer | `<venvs>\AT\Scripts\python.exe` | `<venvs>/AT/bin/python` |

## Step 4 — Register the MCP servers

Every server is the venv's Python running the server script from the clone.
**Use absolute, fully expanded paths**: no `~`, `$HOME` or `${...}`. Forward
slashes are fine on Windows. Include only the chosen servers. If the config
file already exists, merge into it and keep the user's other servers.

### Option A: VS Code (Copilot Chat agent mode)

Edit the user-level config (run the command **MCP: Open User Configuration**),
or `.vscode/mcp.json` to scope it to one workspace. Note that the top-level key
is `servers` and each entry has `"type": "stdio"`:

```json
{
  "servers": {
    "asset_manager": {
      "type": "stdio",
      "command": "C:/Users/<user>/mcp-venvs/AM/Scripts/python.exe",
      "args": ["C:/Users/<user>/industry-ai-workflows/Asset_Manager_MCP/am_mcp_server.py"]
    },
    "pipeline_automation": {
      "type": "stdio",
      "command": "C:/Users/<user>/mcp-venvs/PA/Scripts/python.exe",
      "args": ["C:/Users/<user>/industry-ai-workflows/Pipeline_Automation_MCP/pa_mcp_server.py"]
    },
    "asset_transformer": {
      "type": "stdio",
      "command": "C:/Users/<user>/mcp-venvs/AT/Scripts/python.exe",
      "args": ["C:/Users/<user>/industry-ai-workflows/Asset_Transformer_MCP/at_mcp_server.py"],
      "env": {
        "AT_LICENSE_SERVER_HOST": "<license host>",
        "AT_LICENSE_SERVER_PORT": "27005"
      }
    }
  }
}
```

Then start the servers: use the **Start** code-lens in the file, or run
**MCP: List Servers**. In the chat Tools picker, check that the Unity tools
appear and are enabled. If a server fails, **MCP: List Servers → Show Output**
shows its stderr.

### Option B: Copilot CLI

Edit `~/.copilot/mcp-config.json` (`%USERPROFILE%\.copilot\mcp-config.json` on
Windows). Note that the top-level key is `mcpServers` and each entry has
`"type": "local"` and `"tools": ["*"]`:

```json
{
  "mcpServers": {
    "asset_manager": {
      "type": "local",
      "tools": ["*"],
      "command": "C:/Users/<user>/mcp-venvs/AM/Scripts/python.exe",
      "args": ["C:/Users/<user>/industry-ai-workflows/Asset_Manager_MCP/am_mcp_server.py"]
    },
    "pipeline_automation": {
      "type": "local",
      "tools": ["*"],
      "command": "C:/Users/<user>/mcp-venvs/PA/Scripts/python.exe",
      "args": ["C:/Users/<user>/industry-ai-workflows/Pipeline_Automation_MCP/pa_mcp_server.py"]
    },
    "asset_transformer": {
      "type": "local",
      "tools": ["*"],
      "command": "C:/Users/<user>/mcp-venvs/AT/Scripts/python.exe",
      "args": ["C:/Users/<user>/industry-ai-workflows/Asset_Transformer_MCP/at_mcp_server.py"],
      "env": {
        "AT_LICENSE_SERVER_HOST": "<license host>",
        "AT_LICENSE_SERVER_PORT": "27005"
      }
    }
  }
}
```

`copilot mcp list` should now show the servers under "User servers". New
servers load when a new Copilot CLI session starts.

## Step 5 — Install the authoring skills

The skills are plain `SKILL.md` folders and work with Copilot Agent Skills
(VS Code agent mode, Copilot CLI and the Copilot cloud agent). Copy the folders
for the chosen servers into the user's personal skills folder,
`~/.copilot/skills/` (`%USERPROFILE%\.copilot\skills\` on Windows). To scope
them to one repo instead, use `.github/skills/`.

| Server chosen | Copy these folders |
|---|---|
| Asset Manager | `<repo>/Asset_Manager_MCP/skills/asset-manager-authoring` |
| Pipeline Automation | `<repo>/Pipeline_Automation_MCP/skills/pipeline-authoring` |
| Asset Transformer, or Pipeline Automation with custom Asset Transformer scripts | `<repo>/Asset_Transformer_MCP/skills/at-scripting` **and** `<repo>/Asset_Transformer_MCP/skills/at-upa-scripting` |

Copy whole folders, not just `SKILL.md`, because they include examples and API
references. Keep `at-scripting` and `at-upa-scripting` as sibling folders:
`at-upa-scripting` links to `../at-scripting/pxz-api-reference.md`.

## Step 6 — Restart and verify

1. **Restart.** Reload the VS Code window, or start a new Copilot CLI session.
2. **No-credentials check.** Call `unity_auth_status` on `asset_manager` or
   `pipeline_automation`. It should report "not signed in". For Asset
   Transformer, call `check_license`.
3. **Sign in.** Call `unity_login`. It opens a browser for the Unity sign-in
   and receives the result on `http://localhost:8765`, so that port must be
   free. One sign-in covers both Asset Manager and Pipeline Automation: the
   token is cached in `~/.uap_mcp/token.json`.
4. **Pick an organization.** Call `list_organizations` and show the user a
   numbered list. **ASK** which one to use, then call `set_default_organization`.
5. **Pick a project.** Call `list_projects`, **ASK** which one to use, then
   call `set_default_project`. There are no saved defaults, so repeat steps 4
   and 5 in each new session.

Then tell the user setup is done and suggest a first prompt, e.g. *"List the
assets in my project"* or *"Show my Pipeline Automation pipelines"*.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Server won't start / "cannot find the path specified" | `command` or `args` path is wrong or not absolute; check that the file exists |
| `DLL load failed ... filename or extension is too long` (Windows) | Rebuild with a shorter `--venv-root` (e.g. `C:\mcp-venvs`) |
| Unity tools reply "call unity_login" | Not signed in, or the session expired: call `unity_login` |
| "No organization selected" | Run Step 6.4–6.5 |
| Asset Transformer license error | Check `AT_LICENSE_SERVER_HOST`/`PORT` and network access to the license server |
| `unity_login` fails to open or complete | Port 8765 is in use or blocked; close whatever is using it and retry |

To update later: `git -C <repo> pull`, re-run the Step 3 installers for each
server, then restart.

## Private cloud / VPC (only if the user asked for it)

Add these to the `env` block of **both** `asset_manager` and
`pipeline_automation`, with identical values in each (a mismatch shows up as a
permanent "not signed in"):

| Variable | Required | Meaning |
|---|---|---|
| `UNITY_VPC_FQDN` | yes | Deployment host name, e.g. `unity.example.com` |
| `UNITY_VPC_PATH_PREFIX` | no | Path prefix in front of the services, if any |
| `UNITY_VPC_OPENID_CONFIG_URL` | no | OIDC discovery URL, if not the default |
| `UNITY_VPC_CLIENT_ID` | no | OIDC client id (default `dashboard`) |
| `UNITY_VPC_ASSETS_PATH` | no | `asset_manager` only, if the Assets API path differs |
| `UNITY_VPC_AUTOMATION_PATH` | no | `pipeline_automation` only, if the Automation API path differs |

For public Unity Cloud, leave every `UNITY_VPC_*` variable out entirely. Never
set one to placeholder text: any non-blank `UNITY_VPC_FQDN` switches the server
into private-cloud mode.
