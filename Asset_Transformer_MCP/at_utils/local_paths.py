r"""
local_paths.py — validation for the local filesystem paths agents hand to tools.

Several tools take a destination or source path straight from the caller: Asset Manager
uploads `model_files` / `image_file` and downloads into `download_folder`; Asset
Transformer exports scenes, screenshots, videos, hierarchy JSON and recorder scripts to
`output_path`, and imports from `file_path`. The caller is an LLM agent, and the agent's
instructions can come from content it read rather than from the user — a skill document, a
CAD file's part names, an API response. So these paths are untrusted input, the same way
the signed URLs in `am_utils/signed_urls.py` are.

What this module is for, and what it is NOT for:

  NOT a sandbox for Asset Transformer. `run_python` executes arbitrary Python on purpose
  (see SECURITY.md); anything that can drive that server can already open any file the
  user can. Confining `output_path` there does not remove a capability that server
  deliberately offers, and pretending otherwise would be security theatre.

  IT IS about three real cases the exec capability does not cover:
    1. Asset Manager and Pipeline Automation offer no code execution at all. A path that
       reads `~/.ssh/id_rsa` and PUTs it to cloud storage moves a secret off the host to
       somewhere it can be fetched back later. That is a genuine escalation, not a
       restatement of an existing one.
    2. Writes into locations something else auto-executes — `~/.claude/settings.json` and
       its hooks, the plugin root, site-packages, shell rc files, autostart folders —
       convert "wrote a file" into "runs next session", in any of the three servers.
    3. Accidents. An agent that mistypes an export path onto a shell rc file breaks a
       developer's machine without any attacker involved, and that is the common case.

So: resolve the path for real, refuse the paths whose only plausible purpose is theft or
persistence, and otherwise get out of the way. `D:\work\out.glb` and `~/Downloads` must
keep working — an enforced single output root would break the product's normal use, which
is why `UAP_MCP_ALLOWED_ROOTS` exists but is unset by default. Operators who want hard
confinement (shared machines, CI) set it; everyone else gets the deny-list.

`Path.resolve()` rather than `os.path.abspath()`, because abspath only prefixes the
current working directory: it leaves `..` segments meaningful and never looks at symlinks,
so `out/../../../.bashrc` and a symlink pointing at `~/.ssh` both sail past it. resolve()
collapses the traversal and follows the links, and the deny check then sees where the
write actually lands.
"""

from __future__ import annotations

import os
from pathlib import Path

# Optional hard confinement: an os.pathsep-separated list of roots that every validated
# path must sit inside, e.g. `UAP_MCP_ALLOWED_ROOTS=D:\work;D:\scratch`.
#
# Empty by default ON PURPOSE — see the module docstring. Naming an explicit output root
# would break "export it to my Downloads folder", which is the ordinary request.
ALLOWED_ROOTS_ENV = "UAP_MCP_ALLOWED_ROOTS"

# The token cache home, mirroring shared.unity_auth.pkce_auth. Duplicated as plain strings
# rather than imported: this module is used by the Asset Transformer server, which has no
# Unity auth and must not grow a dependency on it.
_TOKEN_HOME_ENVS = ("UAP_MCP_HOME", "AMT_MCP_HOME")

# Directories whose contents are secrets. Denied for reads (exfiltration) and for writes
# (no tool has business rewriting them).
_SECRET_DIRS = (
    ".uap_mcp",          # our own token cache
    ".amt_mcp",          # pre-0.6.0 name
    ".ssh",
    ".aws",
    ".gnupg",
    ".kube",
    ".docker",
    ".azure",
    ".config/gcloud",
)

# Filenames and suffixes that carry credentials wherever they live.
_SECRET_NAMES = ("token.json", "credentials", "credentials.json", ".netrc", "_netrc", ".env")
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")
_SECRET_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")

# Write-only denials: locations something else loads or executes on its own. A write here
# is a persistence primitive, whatever the content.
_AUTOEXEC_DIRS = (
    ".claude",                            # settings.json + hooks — runs on session start
    ".config/autostart",
    ".config/systemd",
    "Library/LaunchAgents",
    "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup",
)
_AUTOEXEC_ABS_DIRS = ("/etc", "/usr/lib", "/usr/local/lib", "/Library/LaunchDaemons")
_AUTOEXEC_NAMES = (
    ".bashrc", ".bash_profile", ".bash_login", ".profile", ".zshrc", ".zprofile",
    ".zshenv", ".cshrc", ".kshrc", "sitecustomize.py", "usercustomize.py",
    "Microsoft.PowerShell_profile.ps1",
)
_AUTOEXEC_SUFFIXES = (".pth",)
# Any path component that means "Python imports from here".
_PACKAGE_DIRS = ("site-packages", "dist-packages")


class UnsafeLocalPath(RuntimeError):
    """A path failed validation. Always fatal — the path is never used."""


def _allowed_roots() -> tuple[Path, ...]:
    raw = os.environ.get(ALLOWED_ROOTS_ENV, "")
    roots = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(Path(part).expanduser().resolve())
    return tuple(roots)


def _token_home() -> Path | None:
    for env in _TOKEN_HOME_ENVS:
        value = (os.environ.get(env) or "").strip()
        if value:
            return Path(value).expanduser().resolve()
    return None


def _contains(parent: Path, child: Path) -> bool:
    """True if `child` is `parent` or sits underneath it."""
    try:
        return child == parent or parent in child.parents
    except (OSError, ValueError):
        return False


def _plugin_root() -> Path | None:
    """The installed plugin directory, if we are running as one.

    Denied wholesale: nothing a tool writes belongs inside an installed plugin, and the
    SessionStart hook runs code from there on every session.
    """
    env_root = (os.environ.get("CLAUDE_PLUGIN_ROOT") or "").strip()
    return Path(env_root).expanduser().resolve() if env_root else None


def _repo_autoexec_paths() -> tuple[Path, ...]:
    """The auto-executed entry points of a source checkout.

    Deliberately narrower than the whole repo: developers working in this checkout
    legitimately export scenes and dump recorder scripts into it, and `dump_recorded_script`
    writes `.py` files on purpose. Only the files something else runs by itself are closed.
    """
    # <pkg>/local_paths.py -> <pkg> -> the plugin root, which is where this
    # plugin's install.py, bootstrap.py, hooks/ and manifests live. Getting it
    # wrong silently stops guarding the real files.
    repo = Path(__file__).resolve().parents[1]
    return tuple(
        repo / name
        for name in ("bootstrap.py", "install.py", "uninstall.py", "hooks",
                     "mcp-servers.json", ".claude-plugin")
    )


def _reject(purpose: str, resolved: Path, reason: str) -> None:
    raise UnsafeLocalPath(
        f"refusing {purpose} at {resolved} — {reason}. Choose a path in your project or "
        f"working directory instead."
    )


def _check_secret(purpose: str, resolved: Path) -> None:
    home = Path.home()
    lowered = resolved.name.lower()

    if lowered in _SECRET_NAMES or lowered.endswith(_SECRET_SUFFIXES):
        _reject(purpose, resolved, "the filename identifies a credential or private key")
    if any(lowered.startswith(prefix) for prefix in _SECRET_PREFIXES):
        _reject(purpose, resolved, "the filename identifies an SSH private key")

    token_home = _token_home()
    if token_home is not None and _contains(token_home, resolved):
        _reject(purpose, resolved, "it is inside the Unity token cache")

    for rel in _SECRET_DIRS:
        if _contains((home / rel), resolved):
            _reject(purpose, resolved, f"it is inside the credential store {home / rel}")


def _check_autoexec(purpose: str, resolved: Path) -> None:
    home = Path.home()

    if set(resolved.parts) & set(_PACKAGE_DIRS):
        _reject(purpose, resolved, "Python imports code from this directory automatically")
    if resolved.name in _AUTOEXEC_NAMES or resolved.suffix in _AUTOEXEC_SUFFIXES:
        _reject(purpose, resolved, "this file is executed automatically by the shell or Python")

    for rel in _AUTOEXEC_DIRS:
        if _contains((home / rel), resolved):
            _reject(purpose, resolved, f"{home / rel} is loaded automatically at startup")
    for absolute in _AUTOEXEC_ABS_DIRS:
        if _contains(Path(absolute), resolved):
            _reject(purpose, resolved, f"{absolute} holds system startup configuration")
    plugin_root = _plugin_root()
    if plugin_root is not None and _contains(plugin_root, resolved):
        _reject(purpose, resolved, "it is inside the MCP plugin installation")
    for entry in _repo_autoexec_paths():
        if _contains(entry, resolved):
            _reject(purpose, resolved, f"{entry.name} is run automatically on session start")


def assert_safe_local_path(path: str, purpose: str = "access", mode: str = "read") -> str:
    """Validate an agent-supplied local path, or raise `UnsafeLocalPath`.

    `mode` is "read" for paths whose contents are consumed (upload sources, CAD imports)
    and "write" for destinations. Writes get the extra auto-execution denials on top of
    the credential ones. Returns the resolved absolute path as a string, so call sites can
    use the canonical form they were actually checked against rather than the raw input.
    """
    if mode not in ("read", "write"):
        raise ValueError(f"mode must be 'read' or 'write', got {mode!r}")
    if not path or not str(path).strip():
        raise UnsafeLocalPath(f"no path was given for {purpose}")

    raw = str(path).strip()
    try:
        resolved = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise UnsafeLocalPath(f"cannot resolve {purpose} path {raw!r}: {exc}") from exc

    _check_secret(purpose, resolved)
    if mode == "write":
        _check_autoexec(purpose, resolved)

    roots = _allowed_roots()
    if roots and not any(_contains(root, resolved) for root in roots):
        listed = ", ".join(str(r) for r in roots)
        _reject(purpose, resolved, f"{ALLOWED_ROOTS_ENV} confines this server to {listed}")

    return str(resolved)
