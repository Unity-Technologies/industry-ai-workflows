# Security

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report them to Unity through either channel:

- Email **security@unity3d.com**
- Submit through Unity's bug bounty programme: <https://bugcrowd.com/unity>

Unity's responsible-disclosure policy is at <https://unity.com/security>.

Please include:

- the affected component (Asset Manager, Asset Transformer, or Pipeline
  Automation MCP server, or the plugin bootstrap)
- which plugin, and its version — from that plugin's own
  `.claude-plugin/plugin.json` (they version independently)
- what an attacker can achieve, and the steps to reproduce it

## What runs where

Worth knowing when assessing a report — these servers are not a hosted
service:

- All three MCP servers run **locally**, as stdio subprocesses of your MCP
  client, under your own user account. There is no network listener by default,
  so the attack vector is **local**, not network: reaching a tool means already
  being able to run code on the machine, or being able to steer the agent that
  is driving it.
- Asset Manager and Pipeline Automation talk to Unity Cloud as **you**, using a
  browser OAuth (PKCE) login. Tokens are cached in your home directory
  (`~/.uap_mcp/token.json`) and never leave the machine except to Unity's token
  endpoint. The cache file and its directory are restricted to your account —
  mode `0600` on POSIX, an explicit owner-only ACL on Windows.
- Asset Transformer executes **arbitrary Python** on purpose: `run_python` and
  the pxz scripting tools are the feature, not a flaw. Anything driving these
  servers can run code as your user, so treat prompt input to an agent with the
  same care as a shell. Set `AT_DISABLE_RUN_PYTHON=1` to remove the tool
  entirely where that is not wanted.
- The non-default `--transport sse` / `--transport streamable-http` modes bind a
  local HTTP port. It has no authentication unless you set
  `AT_HTTP_BEARER_TOKEN`, so the server refuses to bind a non-loopback `--host`
  without one, and validates `Host`/`Origin` on every request so a web page in
  your browser cannot post to the port on your behalf.

## Trust boundary

Each plugin installs separately, so this boundary is now structural rather
than a caveat: a machine that never installs the Asset Transformer plugin never
has an arbitrary-code-execution tool registered at all.

The three plugins do not sit behind the same boundary, and that difference is
what decides whether something is a finding:

| | Asset Transformer | Asset Manager / Pipeline Automation |
|---|---|---|
| Runs code as you | **Yes, by design** (`run_python`) | No |
| Reaches Unity Cloud as you | No | Yes, with your cached token |
| Reads and writes local files | Yes (CAD in, exports out) | Yes (uploads, downloads) |

In Asset Transformer, a tool that writes a file it was asked to write is not an
escalation: the same server will run whatever Python you hand it. Findings that
amount to "this tool can touch a path outside a workspace" describe a capability
that server offers deliberately, and confining it while `run_python` is present
would be theatre.

Two things are still worth closing there, and are:

- **Persistence.** A write into somewhere *something else* executes —
  `~/.claude/` settings and hooks, an installed plugin's own files, a shell rc
  file, `site-packages`, an autostart folder — outlives the session and runs
  without anyone asking. Those destinations are refused.
- **Exfiltration.** Asset Manager and Pipeline Automation have no code
  execution, so a path that reads `~/.ssh/id_rsa` and PUTs it to cloud storage
  *is* a new capability, not a restatement of an existing one. Credential
  stores and credential-shaped filenames are refused as upload sources.

Beyond that, the same accident protection applies in both plugins that touch
the filesystem: an agent that
mistypes an export path onto a shell rc file breaks a machine with no attacker
involved, and that is the common case.

### What is in scope for a report

- Anything that lets a **remote** party act without local access or without
  the user's agent being involved.
- Anything that escapes the boundaries above: reading a credential store,
  writing to an auto-executed location, exfiltrating local files through the
  cloud APIs, or reaching `run_python` from a network listener.
- Token cache handling, the OAuth flow, and the signed-URL transfer paths.
- The install path: each plugin's `SessionStart` hook, `bootstrap.py`, and
  `install.py`.

### What is not

- `run_python` executing Python, and the pxz scripting tools running scene
  operations. That is the product.
- An agent being steered into a *legitimate* tool call by injected content,
  where the call does only what that tool is for. Prompt injection is real and
  in scope where it crosses one of the boundaries above; it is not a finding
  that an agent can be told to export a scene.
- Resource exhaustion on the user's own machine by their own agent (a huge CAD
  import, a long bake). `AT_MAX_CONCURRENT_JOBS` and `AT_MAX_IMPORT_BYTES` are
  there for shared and CI hosts, where it does affect other people.
- Vulnerabilities in the pxz SDK's native format parsers. Report those to Unity
  as Pixyz issues; the mitigation here is an SDK version bump.

## Hardening options

All default to off or permissive, because the defaults are tuned for one
developer on their own machine. On a shared host, a build agent, or CI, set
these — as environment variables, which is how an operator configures a fleet.

Two of them, `UAP_MCP_ALLOWED_ROOTS` and `AT_DISABLE_RUN_PYTHON`, are also
offered in the plugins' own settings (`/plugin configure`), because an
individual may reasonably want them on their own machine. The rest are
environment-only: they are operator controls, not per-user preferences.

| Variable | Effect |
|---|---|
| `UAP_MCP_ALLOWED_ROOTS` | Confine every local file the servers read or write to these directories (`;`-separated on Windows, `:` elsewhere). Credential stores and auto-executed locations are refused whether or not this is set. |
| `AT_DISABLE_RUN_PYTHON` | Do not register `run_python` at all. Every other Asset Transformer tool keeps working. |
| `AT_HTTP_BEARER_TOKEN` | Require this token on the HTTP/SSE transports, and permit a non-loopback `--host`. |
| `AT_MAX_IMPORT_BYTES` | Refuse CAD imports above this size. |
| `AT_MAX_CONCURRENT_JOBS` | Cap simultaneous heavy operations (default 1). |
| `AM_TRANSFER_HOST_SUFFIXES` | Restrict signed upload/download URLs to these host suffixes, on top of the always-on public-address check. |
| `UAP_MCP_HOME` | Relocate the token cache. Keep it inside your user profile; the servers warn if it is not. |

## Dependencies

Each server installs from a hash-pinned `requirements.lock`, generated from its
`requirements.txt` by `tools/lock_requirements.py` and installed with
`pip --require-hashes` against an explicit `--index-url`. This matters because
the `SessionStart` hook builds these environments automatically and detached, so
a substituted artifact would otherwise run as you with nothing on screen.

The pxz SDK is the exception: Unity publishes a wheel per platform and platform
releases lag each other, so a checked-in hash set would be wrong for two of the
three platforms at any given time. Its install is instead recorded — the
resolved wheel URL and SHA256 are printed by the Asset Transformer plugin's
`install.py` and land in
`bootstrap.log`.

If you are reporting a vulnerability in a third-party package rather than in
this code, say so — those are usually resolved by a version bump.
