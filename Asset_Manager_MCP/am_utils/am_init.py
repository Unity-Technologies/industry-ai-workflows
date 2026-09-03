"""
Auth bootstrap for the Asset Manager MCP server.

Thin re-export over the shared auth module (shared/unity_auth at the repo
root). All Unity Asset Pipeline MCP servers share one browser-based PKCE user
login and one token cache (~/.uap_mcp/token.json, or $UAP_MCP_HOME/token.json),
so signing
in once authenticates both Asset Manager and Pipeline Automation — and
logging out signs out both.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The server dirs live one level below the repo root; the plugin always runs
# them from the cloned repo, so this path is stable.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.unity_auth import (  # noqa: E402  (after sys.path insert)
    NotLoggedInError,
    auth_status_message,
    get_session,
    logout,
    pkce_auth,
    trigger_user_login,
)

__all__ = [
    "NotLoggedInError",
    "auth_status_message",
    "get_session",
    "logout",
    "pkce_auth",
    "trigger_user_login",
]
