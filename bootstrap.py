#!/usr/bin/env python3
"""
Unity Asset Pipeline MCP plugin bootstrap (SessionStart hook entry point)
=========================================================================

Makes the plugin work straight from a GitHub install with zero manual setup
(beyond Python 3.12 being on the machine): on session start it ensures the
three MCP server venvs exist in the plugin's persistent data directory
($CLAUDE_PLUGIN_DATA, which survives plugin updates), building them in a
DETACHED background process on first run / after an update that changes the
dependency set.

Why detached instead of building inside the hook:
  - Claude Code launches the plugin's MCP servers independently of
    SessionStart hooks, so even a blocking build could not make the servers
    usable in the same session — they only come up on the next session.
  - The first build downloads the Asset Transformer SDK and can take longer
    than hook timeout budgets on slow networks; a background build never
    blocks or times out the session.

Everything printed to stdout by a SessionStart hook is added to Claude's
context, which this script uses to (a) tell Claude that setup is running in
the background and (b) surface Unity sign-in status (the standard Claude
Code /mcp OAuth flow only exists for remote HTTP servers, not local stdio
servers like these).

Modes:
    python bootstrap.py            # hook mode (fast; never blocks, never prompts)
    python bootstrap.py --build    # foreground build (run by the detached child)

Stdlib-only; runnable with any Python 3.8+ — it discovers a Python 3.12
interpreter for the venvs itself (via install.py's find_python312).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip() or Path(__file__).resolve().parent)

# install.py (same directory) owns the server specs and the venv build logic.
sys.path.insert(0, str(PLUGIN_ROOT))
import install  # noqa: E402

# A build lock older than this is considered crashed/stale and is replaced.
LOCK_STALE_SECONDS = 6 * 60 * 60

CONTEXT_PREFIX = "Unity Asset Pipeline MCP:"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def data_dir() -> Path:
    return install.default_data_dir()


def venv_parent() -> Path:
    return data_dir() / "venvs"


def lock_path() -> Path:
    return data_dir() / "bootstrap.lock"


def log_path() -> Path:
    return data_dir() / "bootstrap.log"


# ---------------------------------------------------------------------------
# Build lock (one background build at a time, across sessions)
# ---------------------------------------------------------------------------

def lock_is_active(path: Path | None = None, stale_seconds: float = LOCK_STALE_SECONDS) -> bool:
    """True when a non-stale build lock exists."""
    p = path if path is not None else lock_path()
    try:
        age = time.time() - p.stat().st_mtime
    except OSError:
        return False
    return age < stale_seconds


def acquire_lock(path: Path | None = None, stale_seconds: float = LOCK_STALE_SECONDS) -> bool:
    """Atomically create the lock file. Replaces a stale lock. Returns False
    when another live build holds it."""
    p = path if path is not None else lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"pid": os.getpid(), "started": time.time()})
    for _ in range(2):
        try:
            fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(payload)
            return True
        except FileExistsError:
            if lock_is_active(p, stale_seconds):
                return False
            try:
                p.unlink()  # stale — remove and retry once
            except OSError:
                return False
    return False


def release_lock(path: Path | None = None) -> None:
    try:
        (path if path is not None else lock_path()).unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Unity sign-in status (read-only peek at the shared token cache)
# ---------------------------------------------------------------------------

def signed_in() -> bool:
    """Best-effort check of the shared Unity token cache. Never imports the
    auth module (hook context: stdlib only, must stay fast); a cached bundle
    with a refresh token or an unexpired access token counts as signed in."""
    home = (os.environ.get("UAP_MCP_HOME") or os.environ.get("AMT_MCP_HOME") or "").strip()
    base = Path(home) if home else Path.home() / ".uap_mcp"
    if not home and not (base / "token.json").exists():
        # Pre-0.6.0 home. The servers adopt it on their first tool call
        # (pkce_auth._migrate_legacy_cache); until then, read it here so the
        # session-start line doesn't tell a signed-in user they're signed out.
        # Skipped when a home is configured — that means "use exactly this
        # cache", and pkce_auth applies the same rule.
        legacy = Path.home() / ".amt_mcp"
        if (legacy / "token.json").exists():
            base = legacy
    try:
        bundle = json.loads((base / "token.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(bundle, dict):
        return False
    try:
        expires_at = float(bundle.get("expires_at") or 0.0)
    except (TypeError, ValueError):
        expires_at = 0.0
    return bool(bundle.get("refresh_token")) or expires_at > time.time()


def auth_context_line() -> str | None:
    if signed_in():
        return None
    return (
        f"{CONTEXT_PREFIX} not signed in to Unity. Asset Manager and Pipeline "
        f"Automation tools will not work until the user signs in — before "
        f"calling their tools, ask the user, then run the unity_login tool "
        f"(it opens a browser sign-in)."
    )


# ---------------------------------------------------------------------------
# Detached background build
# ---------------------------------------------------------------------------

def spawn_detached_build(python: str) -> None:
    """Start `python bootstrap.py --build` fully detached: its own process
    group/session, no inherited stdio (an inherited stdout pipe would make
    Claude Code wait on the hook until the build finished)."""
    log_path().parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path(), "ab")
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": subprocess.STDOUT,
        "cwd": str(PLUGIN_ROOT),
        "close_fds": True,
    }
    if os.name == "nt":
        # CREATE_NO_WINDOW (not DETACHED_PROCESS): DETACHED_PROCESS drops the
        # parent console but lets the console-subsystem child allocate a brand
        # new VISIBLE console window, which surfaces pip's pxz download in a
        # terminal pop-up. CREATE_NO_WINDOW gives the child (and its pip
        # children, which inherit it) a hidden console instead.
        CREATE_NO_WINDOW = 0x08000000
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([python, str(PLUGIN_ROOT / "bootstrap.py"), "--build"], **kwargs)
    finally:
        log.close()


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def build_main() -> int:
    """Foreground build with the cross-session lock (the detached child)."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unity Asset Pipeline MCP bootstrap build starting", flush=True)
    if not acquire_lock():
        print("Another build is already running (lock held) — exiting.", flush=True)
        return 0
    try:
        if install.stamp_is_current(venv_parent()):
            print("Environments already up to date — nothing to do.", flush=True)
            return 0
        python = install.find_python312()
        if not python:
            print("ERROR: no Python 3.12 interpreter found — cannot build.", flush=True)
            return 1
        print(f"Using Python 3.12: {python}", flush=True)
        results = install.build_venvs(venv_parent(), base_python=python)
        ok = all(results.values())
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] build finished: "
              f"{'OK' if ok else 'FAILED ' + str(results)}", flush=True)
        return 0 if ok else 1
    finally:
        release_lock()


def legacy_data_notice() -> str:
    """One-shot heads-up about an unused environment directory left on disk.

    The data directory is keyed on the plugin id, so a directory belonging to a
    differently-named install is not referenced by anything here and
    `/plugin uninstall` on this id won't touch it. Told once (guarded by a
    marker file), because a directory this large is worth reclaiming but not
    worth nagging about.
    """
    marker = data_dir() / "legacy-notice.done"
    if marker.exists():
        return ""
    try:
        stale = install.legacy_data_dirs()
    except Exception:
        return ""
    if not stale:
        return ""
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("shown\n", encoding="utf-8")
    except OSError:
        pass  # can't mark it — a repeat notice beats losing the message
    paths = ", ".join(str(p) for p in stale)
    return (
        f"{CONTEXT_PREFIX} an unused server environment directory is taking up "
        f"several GB and can be deleted: {paths}. If the user wants it gone, "
        f"offer to run `python uninstall.py` from a checkout (it sweeps these). "
        f"If they also still have the `amt-mcp` plugin installed, it and its "
        f"marketplace entry can be removed with `/plugin uninstall amt-mcp` and "
        f"`/plugin marketplace remove amt-mcp-marketplace`."
    )


def hook_main() -> int:
    """SessionStart hook mode: fast, silent on the happy path, never blocks.

    stdout becomes Claude context — print only what Claude should know."""
    notice = legacy_data_notice()
    if notice:
        print(notice)
    if install.stamp_is_current(venv_parent()):
        line = auth_context_line()
        if line:
            print(line)
        return 0

    if lock_is_active():
        print(
            f"{CONTEXT_PREFIX} first-time environment setup is still running in "
            f"the background (it downloads the Asset Transformer SDK and can "
            f"take several minutes). The Unity MCP servers will be available "
            f"in a NEW session once it finishes. Progress log: {log_path()}"
        )
        line = auth_context_line()
        if line:
            print(line)
        return 0

    python = install.find_python312()
    if not python:
        print(
            f"{CONTEXT_PREFIX} Python 3.12 was not found on this machine, so the "
            f"plugin's MCP server environments cannot be built. Tell the user to "
            f"install Python 3.12 (https://www.python.org/downloads/ — on Windows "
            f"`winget install Python.Python.3.12`) and then start a new Claude "
            f"Code session."
        )
        return 0

    spawn_detached_build(python)
    print(
        f"{CONTEXT_PREFIX} building the MCP server environments in the "
        f"background (first run or plugin update; downloads the Asset "
        f"Transformer SDK and may take several minutes). The Unity MCP servers "
        f"(asset_manager, asset_transformer, pipeline_automation) will be "
        f"available in a NEW session once it finishes — if the user asks about "
        f"them now, explain this. Progress log: {log_path()}"
    )
    line = auth_context_line()
    if line:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if "--build" in args:
            return build_main()
        return hook_main()
    except Exception as exc:  # noqa: BLE001 — a hook must fail soft, with context
        if "--build" in args:
            raise
        print(f"{CONTEXT_PREFIX} bootstrap check failed ({exc.__class__.__name__}: {exc}). "
              f"MCP servers may be unavailable; running `python install.py` in the "
              f"plugin repo is the manual fallback.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
