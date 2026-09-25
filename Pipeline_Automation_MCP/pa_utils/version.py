"""
Runtime identity for the Unity Pipeline Automation MCP server
=============================================================

Single source of truth for "who is this client" at runtime: reads the plugin
version from .claude-plugin/plugin.json (the same manifest the build tools
use) and derives the two attribution headers sent on every Unity-bound HTTP
request — X-Unity-Cloud-Api-Source ("upa_mcp@<version>", Unity's
"[source]@[version]" analytics-headers convention) and User-Agent — so API
traffic is attributable to this tool in Unity's server-side logs instead of
showing up as anonymous python-requests.

The User-Agent carries exactly three facts: the plugin version, the agent
driving the servers (the MCP client name from the initialize handshake —
e.g. claude-code, copilot; "unknown" until a tool call has revealed it),
and the OS family. Nothing here collects, stores, or transmits anything:
it is non-personal software metadata added to requests the servers already
make.

Switch: UAP_MCP_USER_AGENT replaces the computed value verbatim (e.g. to
tag a fleet); setting it to an empty string omits the header.

Every function is best-effort and never raises — a broken manifest yields
version "unknown" rather than a broken server.
"""

from __future__ import annotations

import os
import platform
import re
from functools import lru_cache
from pathlib import Path

# Fixed relative path to the manifest that owns this copy of the module.
# Correct in all three layouts: plugin cache, dev checkout, setup-exe
# extraction. Deliberately not an upward directory walk, which could find a
# different plugin's manifest.
#
# <pkg>/version.py -> <pkg> -> the plugin root, which holds this plugin's own
# .claude-plugin/plugin.json. Each plugin reports ITS OWN version.
#
# Getting this wrong is silent: plugin_version() catches everything and returns
# "unknown", so the attribution headers would degrade to upa_mcp@unknown with
# nothing failing. tests/test_user_agent.py pins it against the real manifest.
MANIFEST_PATH = Path(__file__).resolve().parents[1] / ".claude-plugin" / "plugin.json"

# Per plugin, not per marketplace: Asset Manager and Pipeline Automation make
# some of the same calls (token refresh, OIDC discovery), so a shared name
# would leave that traffic unattributable to either. Both sent "UAP_MCP" /
# "uap_mcp" through 0.7.2. ENV_USER_AGENT keeps the shared UAP_ prefix: it is
# user-facing config, like UAP_MCP_HOME.
PRODUCT = "UPA_MCP"
ENV_USER_AGENT = "UAP_MCP_USER_AGENT"

# Unity's cross-service attribution convention: the gateway logs capture
# this header so API traffic is attributable to the calling tool (the
# dashboard sends its own value the same way). The value must follow Unity's
# "[source]@[version]" format — see api_source().
API_SOURCE_HEADER = "X-Unity-Cloud-Api-Source"
API_SOURCE = "upa_mcp"

_VERSION_RE = re.compile(r"^[0-9A-Za-z._-]{1,32}$")
_MAX_UA_LENGTH = 200

# The MCP client name, cached once detected. Never cache the "unknown"
# fallback: outside a request context (e.g. during server startup) detection
# is impossible, but the very first tool call can still supply the real name.
_agent_cache: str | None = None


def _sanitize(value: str) -> str:
    """Reduce to a single line of visible ASCII safe to place in a header."""
    cleaned = "".join(ch if 0x20 <= ord(ch) <= 0x7E else " " for ch in value)
    return re.sub(r"\s+", " ", cleaned).strip()[:_MAX_UA_LENGTH]


@lru_cache(maxsize=1)
def plugin_version() -> str:
    """The plugin version from the manifest, or "unknown" (never raises)."""
    try:
        import json

        version = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("version")
        if isinstance(version, str) and _VERSION_RE.match(version):
            return version
    except Exception:
        pass
    return "unknown"


def set_agent(name: str | None) -> None:
    """Record the MCP client driving this server, from the clientInfo it sent
    in the initialize handshake.

    Pushed in rather than pulled: mcp 2.x threads the request context through
    handler arguments instead of a process-wide ContextVar, so there is no
    ambient place for the HTTP layer to read it from. `client_identity`
    registers a tool-call interceptor that calls this on the first tool call.

    Blank or unusable names are ignored, so a bad value can never displace a
    good one or get cached as if it were real.
    """
    global _agent_cache
    if _agent_cache is not None:
        return
    detected = _sanitize(str(name)) if name else ""
    if detected:
        _agent_cache = detected


def agent() -> str:
    """The MCP client driving this server (e.g. "claude-code"), or "unknown".

    Populated by `set_agent` on the first tool call and cached for the process
    (stdio servers serve exactly one client). Every Unity-bound call happens
    inside a tool call, so by the time attribution matters the real name is
    known; only traffic during server startup is attributed to "unknown".
    """
    return _agent_cache or "unknown"


def user_agent() -> str | None:
    """The User-Agent value to send, or None to send no header.

    Unset env -> computed "UPA_MCP/<version> (<agent>; <OS>)"; env set
    non-blank -> that value (sanitized); env set blank -> None.
    """
    override = os.environ.get(ENV_USER_AGENT)
    if override is not None:
        return _sanitize(override) or None
    try:
        system = platform.system() or "unknown"
    except Exception:
        system = "unknown"
    ua = f"{PRODUCT}/{plugin_version()} ({agent()}; {system})"
    return _sanitize(ua) or None


def api_source() -> str:
    """The api-source header value, "upa_mcp@<version>" — Unity's
    "[source]@[version]" analytics-headers format (a broken manifest yields
    "upa_mcp@unknown", matching the User-Agent fallback)."""
    return f"{API_SOURCE}@{plugin_version()}"


def attribution_headers() -> dict[str, str]:
    """The identifying headers for Unity-bound requests, as a one-line
    additive merge at every call site: the Unity gateway's api-source header
    ("upa_mcp@<version>"; captured by the gateway logs for attribution) plus
    the User-Agent, when not suppressed via UAP_MCP_USER_AGENT."""
    headers = {API_SOURCE_HEADER: api_source()}
    ua = user_agent()
    if ua:
        headers["User-Agent"] = ua
    return headers
