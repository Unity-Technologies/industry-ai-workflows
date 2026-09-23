---
description: Build or repair this plugin's Python environment. Use when the asset_manager MCP server is missing, failed to start, or its tools are unavailable — typically because the plugin was installed part-way through a session, so the SessionStart hook that normally builds it never ran.
---

# Set up the Unity Asset Manager MCP server

The server runs from a Python environment in this plugin's own data directory.
Normally the plugin's `SessionStart` hook builds it automatically. That hook
only fires when a session STARTS, so a plugin installed mid-session has no
environment until the next restart — and the server fails to start in the
meantime.

This command builds it now.

## Steps

1. Find this plugin's root — the directory containing `install.py`, alongside
   `am_mcp_server.py`. It is the installed plugin's cache directory, normally
   `~/.claude/plugins/cache/industry-ai-workflows/uam-mcp/<version>/`.

2. Run that plugin's own installer, with `CLAUDE_PLUGIN_DATA` pointing at its
   data directory so the environment and its stamp land where the MCP config
   expects:

   ```bash
   CLAUDE_PLUGIN_DATA="$HOME/.claude/plugins/data/uam-mcp-industry-ai-workflows"      python "<plugin root>/install.py" --non-interactive
   ```

   On Windows PowerShell:

   ```powershell
   $env:CLAUDE_PLUGIN_DATA = "$HOME\.claude\plugins\data\uam-mcp-industry-ai-workflows"
   python "<plugin root>\install.py" --non-interactive
   ```


3. Confirm it finished with `AM: OK` and that it wrote `stamp-AM.json`.
   The stamp matters: without it the next session treats the environment as
   stale and rebuilds the whole thing.

4. Bring the server up **without restarting**: open `/mcp` and **reconnect**
   it. That is what actually starts it.

   Do not rely on `/reload-plugins` here. It reloads plugin components, and the
   documentation says it covers plugin MCP servers, but in practice it has been
   seen not to bring one up — `/mcp` reconnect did. Claude Code's own install
   summary suggests `/reload-plugins`, so this is worth knowing. If neither
   works, a new session always will.

## Do not

- Do not hand-roll the environment with `python -m venv` and `pip install`.
  The installer verifies package hashes, runs a smoke test, and writes the
  stamp; a manual build skips all three and the next session rebuilds it.
- Do not install into a different directory. The `command` in this plugin's
  `mcp-servers.json` points at `$CLAUDE_PLUGIN_DATA/venvs/AM`, so an
  environment anywhere else is invisible to the server.
