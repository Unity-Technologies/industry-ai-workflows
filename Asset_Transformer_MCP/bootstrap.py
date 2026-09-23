#!/usr/bin/env python3
"""
Unity Asset Transformer MCP plugin bootstrap (SessionStart hook entry point)
============================================================================

Makes this plugin work straight from a GitHub install with zero manual setup
(beyond Python being on the machine): on session start it ensures the
Asset Transformer MCP server's venv exists in the plugin's persistent data directory
($CLAUDE_PLUGIN_DATA, which survives plugin updates), building it in a DETACHED
background process on first run / after an update that changes the dependency
set.

Each plugin in the Industry AI Workflows marketplace owns its own copy of this
script and builds only its own venv into its own data directory. Claude Code
copies only a plugin's own subtree into its cache, so a shared bootstrap at the
repo root would not exist on an installed machine. One plugin's failed or slow
build can no longer hold up another's.

Why detached instead of building inside the hook:
  - Claude Code launches a plugin's MCP servers independently of SessionStart
    hooks, so even a blocking build could not make the server usable in the
    same session — it only comes up on the next session.
  - The first build downloads the Asset Transformer SDK (pxz) and can
    take longer than hook timeout budgets on slow networks; a background
    build never blocks or times out the session.

Everything printed to stdout by a SessionStart hook is added to Claude's
context, which this script uses to tell Claude that setup is running in the
background.

Modes:
    python bootstrap.py            # hook mode (fast; never blocks, never prompts)
    python bootstrap.py --build    # foreground build (run by the detached child)

Stdlib-only; runnable with any Python 3.8+ — it discovers a Python 3.12
interpreter for the venv itself (via install.py's find_python312).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip() or Path(__file__).resolve().parent)

# install.py sits beside this file and owns the server spec and the venv build
# logic. Loaded by explicit path under a unique module name rather than
# `import install`: every plugin in this marketplace ships its own install.py,
# and a bare import would bind whichever one happened to be on sys.path first —
# silently, and differently depending on how the process was started. The
# sys.modules registration is required before exec_module, or the dataclass in
# install.py cannot resolve its own module while being constructed.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "uap_install_asset_transformer", PLUGIN_ROOT / "install.py"
)
install = importlib.util.module_from_spec(_spec)
sys.modules["uap_install_asset_transformer"] = install
_spec.loader.exec_module(install)

# A build lock older than this is considered crashed/stale and is replaced.
LOCK_STALE_SECONDS = 6 * 60 * 60

CONTEXT_PREFIX = "Unity Asset Transformer MCP:"


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
    try:
        stale = install.legacy_data_dirs()
    except Exception:
        return ""
    # The marker goes INSIDE the directory being reported, not in this plugin's
    # own data dir. Every plugin in the marketplace sees the same stale
    # directory, so a per-plugin marker would tell the user about the same few
    # GB once per installed plugin. Whichever hook runs first claims it.
    stale = [d for d in stale if not (d / "legacy-notice.done").exists()]
    if not stale:
        return ""
    for d in stale:
        try:
            (d / "legacy-notice.done").write_text("shown\n", encoding="utf-8")
        except OSError:
            pass  # can't mark it — a repeat notice beats losing the message
    paths = ", ".join(str(p) for p in stale)
    return (
        f"{CONTEXT_PREFIX} an unused server environment directory is taking up "
        f"several GB and can be deleted: {paths}. It belongs to the previous "
        f"bundled `uap-mcp` plugin, which has been replaced by separate plugins "
        f"in the Industry AI Workflows marketplace. If the user wants it gone, "
        f"offer to run `python uninstall.py` from this plugin (it sweeps these). "
        f"If they still have `uap-mcp` installed it is now registering duplicate "
        f"copies of these same tools — recommend `/plugin uninstall uap-mcp` and "
        f"`/plugin marketplace remove unity-asset-pipeline-marketplace`. Their "
        f"Unity sign-in is NOT affected: it lives in ~/.uap_mcp and the new "
        f"plugins read the same cache."
    )


def hook_main() -> int:
    """SessionStart hook mode: fast, silent on the happy path, never blocks.

    stdout becomes Claude context — print only what Claude should know."""
    notice = legacy_data_notice()
    if notice:
        print(notice)
    if install.stamp_is_current(venv_parent()):
        return 0

    if lock_is_active():
        print(
            f"{CONTEXT_PREFIX} first-time environment setup is still running "
            f"in the background (it downloads the Asset Transformer SDK and can take several minutes). The asset_transformer MCP server will be "
            f"available in a NEW session once it finishes. "
            f"Progress log: {log_path()}"
        )
        return 0

    python = install.find_python312()
    if not python:
        print(
            f"{CONTEXT_PREFIX} Python 3.12 was not found on this machine, so this "
            f"plugin's MCP server environment cannot be built. Tell the user to "
            f"install Python 3.12 (https://www.python.org/downloads/ — on Windows "
            f"`winget install Python.Python.3.12`) and then start a new Claude "
            f"Code session."
        )
        return 0

    spawn_detached_build(python)
    print(
        f"{CONTEXT_PREFIX} building the MCP server environment in the "
        f"background (first run or plugin update (it downloads the Asset Transformer SDK and can take several minutes)). The asset_transformer MCP "
        f"server is not running yet. When the build finishes, open /mcp and "
        f"RECONNECT it — that is what brings it up; /reload-plugins does not "
        f"reliably start an MCP server. No restart needed, but the build has "
        f"to finish first. If the user asks about it now, explain this. "
        f"Progress log: {log_path()}"
    )
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
              f"This plugin's MCP server may be unavailable; running "
              f"`python install.py` from the plugin directory is the manual fallback.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
