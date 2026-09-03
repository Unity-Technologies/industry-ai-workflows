#!/usr/bin/env python3
"""
Unity Asset Pipeline MCP uninstaller
====================================

Removes everything install.py created, and makes sure NO cached credentials
are left behind.

By default removes:
  - the venvs in the Claude Code plugin data directory
    (`~/.claude/plugins/data/uap-mcp-unity-asset-pipeline-marketplace/venvs/`,
    plus the bootstrap stamp/lock/log next to them) — note that uninstalling
    the plugin from Claude Code (`/plugin uninstall`) also deletes these
  - any whole plugin data directory left over from before the 0.6.0 rename,
    which nothing else reclaims
  - each MCP's legacy in-repo `.venv/` and its `.env`
  - the legacy generated repo-level `.mcp.json` and `install.log`
  - ALL cached auth token files (the unified `token.json` + its lock file,
    legacy `am_token.json` / `pa_token.json`, and anything else token-like)
    from the token cache directory — `$UAP_MCP_HOME` when set, otherwise
    `~/.uap_mcp` — plus the pre-0.6.0 `~/.amt_mcp` home, plus each directory
    itself once empty.

Token files contain live OAuth access/refresh tokens and are ALWAYS removed;
there is no flag to keep them. `.env` files may contain values you typed by
hand (e.g. the license server host — not secrets); pass `--keep-env`
to preserve them.

Always asks for confirmation; pass `--yes` to skip the prompt.

Usage
-----
    python uninstall.py                  # remove everything (with prompt)
    python uninstall.py --keep-env       # keep .env files
    python uninstall.py --tokens-only    # only clear cached auth tokens
    python uninstall.py --yes            # don't prompt (useful in CI)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from install import (
    REPO_ROOT,
    SPECS,
    default_data_dir,
    default_venv_parent,
    find_processes_using_path,
    kill_processes,
    legacy_data_dirs,
    venv_dir_for,
)


DEFAULT_TOKEN_DIR = Path.home() / ".uap_mcp"

# Cache homes from before the 0.6.0 rename. Swept alongside the current one:
# they hold live refresh tokens and sit outside everything else this script
# touches, so skipping them would strand credentials on disk while the summary
# below reported a clean state.
LEGACY_TOKEN_DIRS = (Path.home() / ".amt_mcp",)


def token_cache_dir() -> Path:
    """The token cache directory the MCP servers use: $UAP_MCP_HOME when set
    (or the pre-0.6.0 $AMT_MCP_HOME), otherwise ~/.uap_mcp."""
    custom = (os.environ.get("UAP_MCP_HOME") or os.environ.get("AMT_MCP_HOME") or "").strip()
    return Path(custom) if custom else DEFAULT_TOKEN_DIR


def token_cache_dirs() -> list[Path]:
    """Every directory that could hold cached credentials, current one first."""
    dirs = [token_cache_dir()]
    dirs.extend(d for d in LEGACY_TOKEN_DIRS if d not in dirs)
    return dirs


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


def _token_files(token_dir: Path) -> list[Path]:
    """All cached auth token files in the token cache directory.

    Matches the known bundles (am_token.json, pa_token.json) and anything
    else that looks like a token file, so nothing secret is left behind.
    """
    if not token_dir.is_dir():
        return []
    files: list[Path] = []
    for p in sorted(token_dir.iterdir()):
        if p.is_file() and "token" in p.name.lower():
            files.append(p)
    return files


def _planned_removals(*, keep_env: bool, tokens_only: bool) -> list[tuple[str, Path]]:
    """Build the list of (label, path) entries to remove. Order matters only
    for the confirmation prompt; deletion is sequential."""
    plan: list[tuple[str, Path]] = []

    if not tokens_only:
        # Venvs in the plugin data directory (the default install location).
        venv_parent = default_venv_parent()
        for spec in SPECS:
            venv = venv_dir_for(spec, venv_parent)
            if venv.exists():
                plan.append((f"{spec.code} venv (plugin data)", venv))
        for label, name in (
            ("bootstrap stamp", "stamp.json"),
            ("bootstrap stamp (tmp)", "stamp.json.tmp"),
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

    # Token files are ALWAYS removed — they hold live OAuth tokens.
    for token_dir in token_cache_dirs():
        for token_file in _token_files(token_dir):
            plan.append(("auth token cache", token_file))
        if token_dir.is_dir():
            planned_tokens = {p for label, p in plan if label == "auth token cache"}
            try:
                remaining = [p for p in token_dir.iterdir() if p not in planned_tokens]
            except OSError:
                remaining = [token_dir]  # can't enumerate — leave the dir alone
            if not remaining:
                plan.append(("token cache directory", token_dir))

    return plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Uninstall Unity Asset Pipeline MCP server venvs, env files, and cached auth tokens."
    )
    parser.add_argument(
        "--keep-env", action="store_true",
        help="Preserve per-MCP .env files (they hold non-secret settings such as "
             "the license server host). "
             "Cached auth token files are always removed regardless.",
    )
    parser.add_argument(
        "--tokens-only", action="store_true",
        help="Only clear cached auth tokens; leave venvs and .env files alone.",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Don't prompt for confirmation.")
    parser.add_argument(
        "--kill-stale", action="store_true",
        help="Terminate any python processes still holding a target venv open "
             "before removing it. Required when an MCP server is still running "
             "from a prior session.",
    )
    args = parser.parse_args()

    plan = _planned_removals(keep_env=args.keep_env, tokens_only=args.tokens_only)

    print(f"Unity Asset Pipeline MCP uninstaller | repo root: {REPO_ROOT}")
    print(f"Token cache directory: {token_cache_dir()}")
    if not plan:
        print("Nothing to remove. Exiting.")
        return 0

    print("\nWill remove:")
    for label, path in plan:
        print(f"  - {label}: {path}")
    if args.keep_env and not args.tokens_only:
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

    leftover_tokens = [f for d in token_cache_dirs() for f in _token_files(d)]
    if leftover_tokens:
        print("\n! Token files still present (remove these manually — they contain")
        print("  live OAuth tokens):")
        for p in leftover_tokens:
            print(f"    {p}")
    else:
        print("\nNo cached auth token files remain — clean state verified.")

    print(f"\nDone. {len(removed)} item(s) removed.")
    return 0 if not failed and not leftover_tokens else 1


if __name__ == "__main__":
    sys.exit(main())
