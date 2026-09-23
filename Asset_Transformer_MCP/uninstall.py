#!/usr/bin/env python3
"""
Unity Asset Transformer MCP uninstaller
=======================================

Removes everything this plugin's install.py created.

By default removes:
  - the venv in this plugin's Claude Code data directory
    (`~/.claude/plugins/data/<plugin-id>/venvs/`, plus the bootstrap
    stamp/lock/log next to it) — note that uninstalling the plugin from Claude
    Code (`/plugin uninstall`) also deletes these
  - any whole plugin data directory left over from the previous bundled
    `uap-mcp` plugin, or from before the 0.6.0 rename, which nothing else
    reclaims
  - the legacy in-repo `.venv/` and `.env` beside this file

This plugin does NOT touch the Unity token cache. Asset Transformer has no
Unity sign-in — it authenticates against a Pixyz license server — and
~/.uap_mcp/token.json belongs to the Asset Manager and Pipeline Automation
plugins. Deleting it here would sign the user out of two plugins that are not
being uninstalled.

Each plugin in the Industry AI Workflows marketplace owns its own copy of this
script and removes only its own artifacts.

`.env` files may contain values you typed by hand (e.g. the license server
host — not secrets); pass `--keep-env` to preserve them.

Always asks for confirmation; pass `--yes` to skip the prompt.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# install.py sits beside this file and owns the server spec and the paths.
# Loaded by explicit path under a unique module name rather than
# `from install import ...`: every plugin in this marketplace ships its own
# install.py, and a bare import would bind whichever one happened to be on
# sys.path first. The sys.modules registration is required before
# exec_module, or the dataclass in install.py cannot resolve its own module.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "uap_install_asset_transformer", Path(__file__).resolve().parent / "install.py"
)
_install = importlib.util.module_from_spec(_spec)
sys.modules["uap_install_asset_transformer"] = _install
_spec.loader.exec_module(_install)

REPO_ROOT = _install.REPO_ROOT
SPECS = _install.SPECS
default_data_dir = _install.default_data_dir
default_venv_parent = _install.default_venv_parent
find_processes_using_path = _install.find_processes_using_path
kill_processes = _install.kill_processes
legacy_data_dirs = _install.legacy_data_dirs
venv_dir_for = _install.venv_dir_for
stamp_path = _install.stamp_path


def _confirm(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def _remove_path(path: Path, *, label: str) -> bool:
    """Delete a file or directory. Returns True if something was removed."""
    if not path.exists() and not path.is_symlink():
        return False
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True
    except OSError as e:
        print(f"  [FAIL]   {label}: {path} ({e})")
        return False


def _planned_removals(*, keep_env: bool) -> list[tuple[str, Path]]:
    """Build the list of (label, path) entries to remove. Order matters only
    for the confirmation prompt; deletion is sequential."""
    plan: list[tuple[str, Path]] = []

    if True:
        # Venvs in the plugin data directory (the default install location).
        venv_parent = default_venv_parent()
        for spec in SPECS:
            venv = venv_dir_for(spec, venv_parent)
            if venv.exists():
                plan.append((f"{spec.code} venv (plugin data)", venv))
        for label, name in (
            ("bootstrap stamp", stamp_path(venv_parent).name),
            ("bootstrap stamp (tmp)", stamp_path(venv_parent).name + ".tmp"),
        ):
            p = venv_parent / name
            if p.exists():
                plan.append((label, p))
        for label, name in (
            ("bootstrap lock", "bootstrap.lock"),
            ("bootstrap log", "bootstrap.log"),
        ):
            p = default_data_dir() / name
            if p.exists():
                plan.append((label, p))

        # Legacy in-repo venvs and per-MCP .env files.
        for spec in SPECS:
            folder = REPO_ROOT / spec.folder
            venv = folder / ".venv"
            if venv.exists():
                plan.append((f"{spec.code} venv (in-repo)", venv))
            if not keep_env:
                env = folder / ".env"
                if env.exists():
                    plan.append((f"{spec.code} .env", env))

        # Repo-level files a manual or in-repo dev install can leave behind.
        for label, path in (
            (".mcp.json (legacy generated)", REPO_ROOT / ".mcp.json"),
            ("install.log", REPO_ROOT / "install.log"),
        ):
            if path.exists():
                plan.append((label, path))

        # Whole data directories from before the 0.6.0 rename. The plugin id
        # composes into this path, so a renamed plugin never looks at the old
        # one again and `/plugin uninstall` only clears the id it was installed
        # under — leaving multiple GB of venvs (incl. the pxz-bearing AT one)
        # stranded unless swept here.
        for legacy_dir in legacy_data_dirs():
            plan.append(("plugin data directory (pre-0.6.0)", legacy_dir))

    return plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Uninstall the Unity Asset Transformer MCP server venv and env files."
    )
    parser.add_argument(
        "--keep-env", action="store_true",
        help="Preserve per-MCP .env files (they hold non-secret settings such as "
             "the license server host). "
             "This plugin never touches the Unity token cache.",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Don't prompt for confirmation.")
    parser.add_argument(
        "--kill-stale", action="store_true",
        help="Terminate any python processes still holding a target venv open "
             "before removing it. Required when an MCP server is still running "
             "from a prior session.",
    )
    args = parser.parse_args()

    plan = _planned_removals(keep_env=args.keep_env)

    print(f"Unity Asset Transformer MCP uninstaller | plugin root: {REPO_ROOT}")
    if not plan:
        print("Nothing to remove. Exiting.")
        return 0

    print("\nWill remove:")
    for label, path in plan:
        print(f"  - {label}: {path}")
    if args.keep_env:
        print("\n(--keep-env: .env files are preserved. They may contain license-server")
        print(" settings — not secrets. All cached auth token files are still removed.)")

    # Detect MCP server processes still using any venv we're about to remove.
    venv_paths = [p for label, p in plan if " venv (" in label]
    holders: list[tuple[int, str]] = []
    for venv in venv_paths:
        holders.extend(find_processes_using_path(venv))
    if holders:
        print(f"\n! {len(holders)} running process(es) still reference these venvs:")
        for pid, cmd in holders:
            short = cmd if len(cmd) <= 100 else cmd[:97] + "..."
            print(f"    PID {pid}: {short}")
        if not args.kill_stale:
            print("\nCannot remove a venv while it's in use. "
                  "Quit Claude Code or re-run with --kill-stale.")
            return 1

    if not _confirm("\nProceed?", assume_yes=args.yes):
        print("Aborted. Nothing removed.")
        return 1

    if holders and args.kill_stale:
        print(f"\nKilling {len(holders)} stale process(es) (--kill-stale).")
        kill_processes([pid for pid, _ in holders])

    print()
    removed: list[tuple[str, Path]] = []
    failed: list[tuple[str, Path]] = []
    for label, path in plan:
        if _remove_path(path, label=label):
            removed.append((label, path))
        elif path.exists():
            failed.append((label, path))

    print("=== Removal summary ===")
    if removed:
        for label, path in removed:
            print(f"  [removed] {label}: {path}")
    else:
        print("  (nothing was removed)")
    for label, path in failed:
        print(f"  [FAILED]  {label}: {path}  <- still present, remove manually")

    # No token-cache verification here, deliberately: Asset Transformer has no
    # Unity sign-in and never writes ~/.uap_mcp. Reporting on a cache this
    # plugin does not own would imply it had been cleared.

    print(f"\nDone. {len(removed)} item(s) removed.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
