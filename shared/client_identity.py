"""
Client identification for the Unity MCP servers
===============================================

Records which MCP client is driving the server, so Unity-bound requests can be
attributed to a real agent name (claude-code, copilot, ...) instead of
"unknown". The name comes from the `clientInfo` the client sends in the MCP
initialize handshake.

Why an extension rather than a lookup: mcp 1.x exposed the live request through
a process-wide ContextVar (`mcp.server.lowlevel.server.request_ctx`), so the
HTTP layer could read the client name wherever it happened to be. mcp 2.x
threads the request context through handler arguments instead, and there is no
ambient equivalent. Reading it at the point of use is therefore impossible; the
name has to be pushed in from somewhere that legitimately holds a context.

A `tools/call` interceptor is that place. It sees every tool call, needs no
changes to the tool functions themselves, and preserves the original timing:
the first tool call reveals the client, and every Unity-bound request happens
inside a tool call.

Register it on the server that makes Unity-bound requests:

    from shared.client_identity import ClientIdentityExtension

    mcp = MCPServer(name=..., extensions=[ClientIdentityExtension()])
"""

from __future__ import annotations

from mcp.server.extension import (
    CallNext,
    CallToolRequestParams,
    Extension,
    HandlerResult,
    ServerRequestContext,
)

from .version import set_agent


class ClientIdentityExtension(Extension):
    """Observes `tools/call` to record the driving MCP client's name.

    Pure observer: it never short-circuits, never rewrites params, and never
    fails a tool call. `set_agent` caches the first usable name, so the lookup
    below stops costing anything after the first call.
    """

    identifier = "com.unity/client-identity"

    async def intercept_tool_call(
        self,
        params: CallToolRequestParams,
        ctx: ServerRequestContext,
        call_next: CallNext,
    ) -> HandlerResult:
        try:
            # `client_info`, snake_case: mcp 2.x renamed the 1.x `clientInfo`
            # field. Getting this wrong degrades silently to "unknown" rather
            # than raising, so it is asserted end-to-end against a live server
            # rather than trusted to fail loudly.
            set_agent(ctx.session.client_params.client_info.name)
        except Exception:
            # Attribution is best-effort metadata; a client that sent no
            # clientInfo, or an SDK-internal shape change, must never turn a
            # working tool call into a failure.
            pass
        return await call_next(ctx)
