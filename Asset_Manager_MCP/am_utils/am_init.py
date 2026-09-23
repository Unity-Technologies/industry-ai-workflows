"""
Auth bootstrap for the Asset Manager MCP server.

Thin re-export over this plugin's own auth package (am_utils/unity_auth).

The Pipeline Automation plugin ships an independent copy of that package. The
two plugins install separately and never import each other; they share exactly
one thing — the on-disk token cache (~/.uap_mcp/token.json, or
$UAP_MCP_HOME/token.json), which is resolved from the user's home directory and
carries no plugin identity. So one browser-based PKCE login still authenticates
both Asset Manager and Pipeline Automation, and logging out signs out both.
"""

from __future__ import annotations

from .unity_auth import (
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
