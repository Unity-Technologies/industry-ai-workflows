"""
Shared Unity Cloud auth for the Unity Asset Pipeline MCP servers
================================================================

One PKCE user login, one token cache (~/.uap_mcp/token.json, or
$UAP_MCP_HOME/token.json), shared by the Asset Manager and Pipeline
Automation MCP servers: signing in via either server's `unity_login` tool
authenticates both, and `unity_logout` on either signs out both.

The per-server packages (am_utils.am_init / pa_utils.pa_init) are thin
re-exports over this module, kept so `from am_utils import am_init` keeps
working for the servers.

Tools call get_session() per-request, which builds a fresh session whose
Bearer header reflects the latest (possibly just-refreshed) cached token.
"""

from __future__ import annotations

import requests

from . import pkce_auth
from .pkce_auth import NotLoggedInError  # noqa: F401  (re-exported for callers)
from ..version import attribution_headers


def auth_status_message() -> str | None:
    """None if get_session() will succeed; otherwise the user-facing message a
    tool should return in place of running."""
    if not pkce_auth.is_logged_in():
        return (
            "Not logged in to Unity Cloud. "
            "Call the `unity_login` tool to authenticate — a browser window will open "
            "so you can sign in with your Unity account."
        )
    return None


def get_session() -> requests.Session:
    """Return an authenticated session, refreshed if needed. Called per-request
    so token rotations are picked up transparently."""
    token = pkce_auth.get_access_token()  # may raise pkce_auth.NotLoggedInError
    session = requests.Session()
    session.headers.update(
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **attribution_headers(),
        }
    )
    return session


def trigger_user_login() -> None:
    """Drive the interactive PKCE flow. Opens a browser. Blocks until done."""
    pkce_auth.login()


def logout() -> None:
    """Clear the shared token cache — signs out both AM and PA."""
    pkce_auth.logout()
