#!/usr/bin/env python3
"""
Unity Pipeline Automation MCP installer
=======================================

Builds the venv for the Pipeline Automation MCP server: creates it and pip-installs this
server's dependencies from its hash-pinned requirements.lock.


The venv is built into THIS plugin's persistent data directory
(`~/.claude/plugins/data/<plugin-id>/venvs/{code}`) by default. The exact id
depends on how the marketplace was registered; the setup detects it — see
default_data_dir. That location survives plugin updates (Claude Code replaces a
plugin's cached source on every update, so venvs must not live inside the plugin
itself) and is exactly where this plugin's committed `mcp-servers.json` points,
so one config file works on every machine and OS.

Each plugin in the Industry AI Workflows marketplace installs independently and
owns its own copy of this script. Claude Code copies only a plugin's own subtree
into its cache, so a shared installer at the repo root would simply not exist on
an installed machine. The three copies are deliberate duplicates: keep them
structurally identical so they stay diffable, but they may diverge.

NOTE: when the plugin is installed through Claude Code, running this script is
OPTIONAL — the plugin's SessionStart hook (`bootstrap.py`) builds the same venv
automatically on first use. Run it manually to pre-build it, or for
standalone/dev setups.

Usage
-----
    python install.py                       # build the venv into the plugin data dir
    python install.py --recreate            # delete the existing venv first
    python install.py --python python3.12   # use this interpreter
    python install.py --venv-root DIR       # build under DIR instead (dev)
    python install.py --in-repo             # legacy layout: .venv inside this folder

Notes
-----
- This server accepts Python 3.11+, but the venv is currently built with
  3.12 because the venv stamp records the interpreter series and relaxing
  it would invalidate every existing stamp and force a rebuild. Widening
  to 3.11 is a deliberate, separate change.

- Signing in is browser-based and shared: one `unity_login` also
  authenticates the Unity Asset Manager plugin, because the token cache
  lives at ~/.uap_mcp/token.json and carries no plugin identity.
- The installer never deletes an existing venv unless `--recreate` is passed.
  Re-running is safe.
- Credentials and env vars are NOT configured here. Use the Claude Code
  plugin's userConfig prompt, or copy `.env.example` to `.env`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# This file lives at the plugin root, which is also the server folder. The
# spec below uses folder="." so every path expression that was written against
# a repo containing several server directories still resolves correctly.
PLUGIN_ROOT = Path(__file__).resolve().parent

# Kept as an alias so the shared body below reads the same in all three
# plugins' copies and stays diffable against them.
REPO_ROOT = PLUGIN_ROOT

# Candidate data-directory ids, in preference order. Observed empirically
# ($CLAUDE_PLUGIN_DATA in real hook/server runs): a GitHub- or local-
# MARKETPLACE-installed plugin gets `<plugin>-<marketplace>`; a plugin whose
# marketplace was registered from a plain DIRECTORY source gets
# `<plugin>-inline`. These constants are only the fallback for manual runs —
# inside hook and MCP-server processes Claude Code sets $CLAUDE_PLUGIN_DATA
# directly and that always wins (see default_data_dir).
PLUGIN_DATA_IDS = ("upa-mcp-industry-ai-workflows", "upa-mcp-inline")

# Data-directory ids from before the 0.6.0 rename, plus the mixed form a user
# lands on if they pull the renamed plugin while their locally registered
# marketplace still carries the old name. CLEANUP ONLY — deliberately not in
# PLUGIN_DATA_IDS, because default_data_dir() must never resolve *to* one of
# these: a renamed plugin would then keep building into the old directory.
LEGACY_PLUGIN_DATA_IDS = (
    # The single bundled plugin this one was split out of (0.6.x), and the
    # pre-0.6.0 names before that. Its venvs are multiple GB and nothing
    # reaches them any more.
    "uap-mcp-unity-asset-pipeline-marketplace",
    "uap-mcp-inline",
    "uap-mcp-amt-mcp-marketplace",
    "amt-mcp-amt-mcp-marketplace",
    "amt-mcp-inline",
)

# The venv is created with Python 3.12. This value also feeds the venv
# stamp, so changing it invalidates every existing stamp and forces a
# rebuild — widen it deliberately, not incidentally.
REQUIRED_PYTHON = (3, 12)

STAMP_SCHEMA = 1


@dataclass(frozen=True)
class McpSpec:
    code: str
    name: str
    folder: str
    server_script: str  # path inside folder, e.g. "am_mcp_server.py"
    mcp_key: str        # name used in the MCP config mcpServers map
    pre_install: tuple[tuple[str, ...], ...] = ()  # extra pip commands run before requirements.txt
    python_min: tuple[int, int] = (3, 11)
    python_max: tuple[int, int] | None = None  # inclusive upper bound (e.g. (3, 12))
    user_config_env: tuple[str, ...] = ()  # plugin userConfig values passed to the server as env vars
    needs_unity_auth: bool = False  # print a unity_login reminder after install
    needs_license_server: bool = False  # prompt for AT_LICENSE_SERVER_HOST after install


SPECS: list[McpSpec] = [
    McpSpec(
        code="PA",
        name="Pipeline Automation",
        folder=".",
        server_script="pa_mcp_server.py",
        mcp_key="pipeline_automation",
        python_min=(3, 11),
        needs_unity_auth=True,
        user_config_env=(
            "UNITY_VPC_FQDN",
            "UNITY_VPC_PATH_PREFIX",
            "UNITY_VPC_OPENID_CONFIG_URL",
            "UNITY_VPC_CLIENT_ID",
            "UNITY_VPC_AUTOMATION_PATH",
        ),
    ),
]


# ---------------------------------------------------------------------------
# Paths and layout
# ---------------------------------------------------------------------------

def default_data_dir() -> Path:
    """The plugin's persistent data directory.

    $CLAUDE_PLUGIN_DATA always wins when Claude Code provides it (hook /
    MCP-server processes). For manual runs (install.py, the setup exe) the id
    depends on how the marketplace was registered, so prefer whichever
    candidate directory already exists; otherwise default to the
    marketplace-install form (the GitHub-native route)."""
    env = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    if env:
        return Path(env)
    base = Path.home() / ".claude" / "plugins" / "data"
    for candidate in PLUGIN_DATA_IDS:
        if (base / candidate).exists():
            return base / candidate
    return base / PLUGIN_DATA_IDS[0]


def legacy_data_dirs() -> list[Path]:
    """Pre-rename data directories still present on this machine.

    These hold the old venvs — several GB, including the pxz-bearing Asset
    Transformer one — and nothing reaches them after the rename: Claude Code
    hands the plugin its new `$CLAUDE_PLUGIN_DATA`, and the plugin's own
    uninstall only removes the directory belonging to the id it was installed
    under. Surfaced so `uninstall.py` can sweep them and the SessionStart hook
    can offer cleanup once.

    Scanned next to the CURRENT data directory rather than under a hardcoded
    `~/.claude/plugins/data`: the sibling of wherever Claude Code actually put
    us is the only place a same-generation directory can be, and deriving it
    keeps a redirected $CLAUDE_PLUGIN_DATA (tests, bespoke installs) from
    reaching into the real home.
    """
    current = default_data_dir()
    base = current.parent
    return [
        base / candidate
        for candidate in LEGACY_PLUGIN_DATA_IDS
        if (base / candidate).is_dir() and (base / candidate) != current
    ]


def default_venv_parent() -> Path:
    return default_data_dir() / "venvs"


def venv_dir_for(spec: McpSpec, venv_parent: Path) -> Path:
    return venv_parent / spec.code


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_windows_style_launcher(venv_dir: Path) -> None:
    """Make `<venv>/Scripts/python.exe` work on POSIX too.

    The committed `mcp-servers.json` must contain ONE command path that works
    on every OS. Windows venvs already have `Scripts/python.exe`; on POSIX we
    add a `Scripts/python.exe` symlink to `bin/python` (fallback: a copy).
    CPython resolves the venv from the `pyvenv.cfg` next to the launcher's
    parent directory, so the interpreter still runs inside the venv.
    """
    if os.name == "nt":
        return
    scripts = venv_dir / "Scripts"
    target = venv_dir / "bin" / "python"
    link = scripts / "python.exe"
    if link.exists():
        return
    scripts.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(Path("..") / "bin" / "python")
    except OSError:
        shutil.copy2(target, link)


# ---------------------------------------------------------------------------
# Idempotence stamp
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"


def compute_stamp(root: Path = REPO_ROOT, specs: list[McpSpec] | None = None) -> dict:
    """Fingerprint of everything that would require (re)building the venvs:
    per-server requirements and lock, pre-install pip commands (includes the
    pxz pin and index), the venv Python major.minor, and the platform."""
    servers = {}
    for spec in specs if specs is not None else SPECS:
        servers[spec.code] = {
            "requirements_sha256": _sha256_file(root / spec.folder / "requirements.txt"),
            # The lock is what actually gets installed, so a regenerated lock has to
            # invalidate the stamp even when requirements.txt is untouched — a version
            # bump inside the declared ranges only shows up here.
            "lock_sha256": _sha256_file(root / spec.folder / "requirements.lock"),
            "pre_install": [list(cmd) for cmd in spec.pre_install],
        }
    return {
        "schema": STAMP_SCHEMA,
        "platform": sys.platform,
        "python": ".".join(map(str, REQUIRED_PYTHON)),
        "servers": servers,
    }


def stamp_path(venv_parent: Path) -> Path:
    """This plugin's build stamp.

    Named per server code, not a bare `stamp.json`. In the default layout each
    plugin owns its own $CLAUDE_PLUGIN_DATA so a shared name would be harmless,
    but `--venv-root` lets several plugins build into ONE directory (the
    non-Claude-client setup in the README tells you to do exactly that), and a
    shared name meant the second install silently overwrote the first's stamp.
    The first plugin then failed its currency check forever and rebuilt its
    venv on every session.
    """
    return venv_parent / f"stamp-{SPECS[0].code}.json"


def read_stamp(venv_parent: Path) -> dict | None:
    try:
        return json.loads(stamp_path(venv_parent).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_stamp(venv_parent: Path, stamp: dict) -> None:
    venv_parent.mkdir(parents=True, exist_ok=True)
    tmp = stamp_path(venv_parent).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, stamp_path(venv_parent))


def stamp_is_current(
    venv_parent: Path, root: Path = REPO_ROOT, specs: list[McpSpec] | None = None
) -> bool:
    """True when the stamp matches the current sources AND every venv python
    exists (a deleted/broken venv invalidates a matching stamp)."""
    use = specs if specs is not None else SPECS
    if read_stamp(venv_parent) != compute_stamp(root, use):
        return False
    return all(venv_python(venv_dir_for(s, venv_parent)).exists() for s in use)


# ---------------------------------------------------------------------------
# Interpreter discovery
# ---------------------------------------------------------------------------

def detect_interpreter_version(python: str) -> tuple[int, int]:
    out = subprocess.check_output(
        [python, "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
        text=True,
    ).strip().split()
    return int(out[0]), int(out[1])


def find_python312() -> str | None:
    """Locate a Python 3.12 interpreter (the version every venv needs)."""
    if sys.version_info[:2] == REQUIRED_PYTHON:
        return sys.executable
    probe = (
        "import sys; assert sys.version_info[:2] == (3, 12); print(sys.executable)"
    )
    for base in (["py", "-3.12"], ["python3.12"], ["python3"], ["python"]):
        try:
            out = subprocess.check_output(
                base + ["-c", probe], text=True, stderr=subprocess.DEVNULL
            ).strip()
            if out:
                return out
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            continue
    return None


# ---------------------------------------------------------------------------
# Process helpers (venvs held open by running MCP servers)
# ---------------------------------------------------------------------------

def find_processes_using_path(needle: Path) -> list[tuple[int, str]]:
    """Return (pid, command_line) for running processes whose command line
    references `needle`. Used to detect MCP server processes still holding a
    venv open, which causes shutil.rmtree to fail with PermissionError on Windows.

    Returns [] on platforms / shells where detection isn't available — better
    to proceed silently than block the install on a missing tool.
    """
    def _norm(s: str) -> str:
        sep = "\\" if os.name == "nt" else "/"
        s = s.lower()
        if os.name == "nt":
            s = s.replace("/", "\\")
        while sep * 2 in s:  # plugin launchers sometimes double a separator
            s = s.replace(sep * 2, sep)
        return s

    needle_str = _norm(str(needle))
    matches: list[tuple[int, str]] = []
    try:
        if os.name == "nt":
            # wmic is removed from recent Windows 11 builds — use CIM via
            # PowerShell instead. Tab-separated to survive commas in cmdlines.
            out = subprocess.check_output(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-CimInstance Win32_Process | "
                    "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }",
                ],
                text=True, stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                pid_s, _, cmdline = line.partition("\t")
                pid_s, cmdline = pid_s.strip(), cmdline.strip()
                if not pid_s.isdigit() or not cmdline:
                    continue
                if needle_str in _norm(cmdline):
                    matches.append((int(pid_s), cmdline))
        else:
            out = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
            for line in out.splitlines()[1:]:
                line = line.strip()
                if not line:
                    continue
                pid_s, _, args = line.partition(" ")
                if not pid_s.isdigit():
                    continue
                if needle_str in _norm(args):
                    matches.append((int(pid_s), args))
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []
    return matches


def kill_processes(pids: list[int]) -> None:
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               check=False, capture_output=True)
            else:
                os.kill(pid, 9)
        except OSError as exc:
            print(f"  ! could not kill PID {pid}: {exc}")


# ---------------------------------------------------------------------------
# Venv building
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=cwd)


def run_pip_audited(pip: list[str], args: list[str]) -> None:
    """Run a pip install and print what it actually fetched, with hashes.

    This server's dependencies install from a hash-pinned requirements.lock, so they
    are verified before any of them executes. This helper covers anything installed
    outside that path.

    `pip --report` records
    the resolved URL and the artifact's own hash for everything installed, so the
    filename and SHA256 of the wheel that ran on this machine end up in the install
    output — and, because the SessionStart build is detached, in bootstrap.log. If a
    tampered artifact is ever suspected, there is a record of what was installed instead
    of a shrug.
    """
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "install-report.json"
        run(pip + args + ["--report", str(report_path)])
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"  ! could not read the pip install report ({exc}) — install itself succeeded")
            return

    for item in report.get("install", []):
        download = item.get("download_info") or {}
        url = download.get("url", "?")
        hashes = (download.get("archive_info") or {}).get("hashes") or {}
        digest = hashes.get("sha256") or ",".join(f"{k}={v}" for k, v in hashes.items()) or "?"
        name = (item.get("metadata") or {}).get("name", "?")
        version = (item.get("metadata") or {}).get("version", "?")
        print(f"  provenance: {name}=={version} sha256={digest} from {url}")


def install_requirements(pip: list[str], spec: McpSpec) -> None:
    """Install a server's dependencies, preferring the hash-pinned lock file.

    Two things this closes, both from the same weakness: the SessionStart hook builds
    these venvs automatically, detached, on first run, so whatever pip resolves gets
    executed as the user with nothing on screen.

      * `--index-url` instead of pip's default: pin resolution to PyPI explicitly rather
        than to whatever index the ambient pip config happens to name.
      * `--require-hashes` against `requirements.lock`: if a name is ever hijacked, or an
        artifact is rebuilt under an existing version, the contents no longer match the
        recorded digest and pip refuses before any build backend runs. A pinned version
        alone does not do this — whoever owns the name publishes that version.

    `requirements.txt` stays the human-edited source of truth; the lock is generated from
    it by `tools/lock_requirements.py`. If the lock is missing we still install, without
    hashes, and say so — a stale checkout should not fail to start.
    """
    folder = REPO_ROOT / spec.folder
    lock = folder / "requirements.lock"
    requirements = folder / "requirements.txt"
    index = ["--index-url", "https://pypi.org/simple"]

    if lock.exists():
        run(pip + ["install", "--require-hashes", "-r", str(lock), *index])
        return
    if requirements.exists():
        print(
            f"  ! no requirements.lock in {spec.folder} — installing unverified from "
            f"requirements.txt. Regenerate with `python tools/lock_requirements.py`."
        )
        run(pip + ["install", "-r", str(requirements), *index])
        return
    print(f"  (no requirements.txt at {requirements})")


def smoke_test(spec: McpSpec, py: Path) -> bool:
    """Import the server module in the freshly-installed venv to catch broken
    installs (missing transitive deps, .dist-info without code, version conflicts).

    Returns True on clean import. Prints the captured stderr on failure.
    """
    server_path = REPO_ROOT / spec.folder / spec.server_script
    # Add the server's directory to sys.path[0] to mimic how Python resolves
    # imports when the launcher runs `python <abs>/server.py` — sibling modules
    # like `am_utils` are imported relative to the script directory.
    code = (
        "import sys, importlib.util\n"
        f"sys.path.insert(0, r'{server_path.parent}')\n"
        f"s = importlib.util.spec_from_file_location('m', r'{server_path}')\n"
        "m = importlib.util.module_from_spec(s)\n"
        "try:\n"
        "    s.loader.exec_module(m)\n"
        "except SystemExit:\n"
        "    pass\n"
    )
    print(f"  Smoke test: importing {spec.server_script} ...", flush=True)
    result = subprocess.run([str(py), "-c", code], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  [smoke ok] {spec.code} server imports cleanly.")
        return True
    print(f"  [SMOKE FAIL] {spec.code}: import of {spec.server_script} failed:")
    err = (result.stderr or "").strip() or "(no stderr)"
    print("    " + err.replace("\n", "\n    "))
    return False


def install_mcp(
    spec: McpSpec,
    *,
    base_python: str,
    venv: Path,
    recreate: bool = False,
    kill_stale: bool = False,
) -> bool:
    """Create/refresh one server's venv at `venv` and smoke-test it."""
    folder = REPO_ROOT / spec.folder
    py = venv_python(venv)

    print(f"\n=== {spec.code}: {spec.name} ({spec.folder}) ===", flush=True)
    print(f"  venv: {venv}")

    if not folder.exists():
        print(f"  ! {folder} does not exist. Skipping.")
        return False

    holders = find_processes_using_path(venv) if venv.exists() else []
    if holders:
        print(f"  ! {len(holders)} running process(es) reference this venv:")
        for pid, cmd in holders:
            short = cmd if len(cmd) <= 100 else cmd[:97] + "..."
            print(f"      PID {pid}: {short}")
        if kill_stale:
            print(f"  Killing {len(holders)} stale process(es) (--kill-stale).")
            kill_processes([pid for pid, _ in holders])
        elif recreate:
            print("  ! Cannot --recreate while venv is in use. "
                  "Quit Claude Code or re-run with --kill-stale.")
            return False
        else:
            print("  (Continuing without recreate; running processes will keep stale code "
                  "until restarted.)")

    base_version = detect_interpreter_version(base_python)
    if base_version < spec.python_min:
        print(
            f"  ! Python {'.'.join(map(str, spec.python_min))}+ required for {spec.name}; "
            f"got {'.'.join(map(str, base_version))} from `{base_python}`. Skipping."
        )
        return False
    if spec.python_max and base_version > spec.python_max:
        print(
            f"  ! Python {'.'.join(map(str, spec.python_max))} or earlier required for {spec.name}; "
            f"got {'.'.join(map(str, base_version))} from `{base_python}`. "
            f"Pass --python <python3.12-path> for this MCP. Skipping."
        )
        return False

    if venv.exists():
        if recreate:
            print(f"  Removing existing venv: {venv}")
            shutil.rmtree(venv)
        else:
            print(f"  venv already exists: {venv} (use --recreate to rebuild). Updating deps in place.")

    if not venv.exists():
        venv.parent.mkdir(parents=True, exist_ok=True)
        run([base_python, "-m", "venv", str(venv)])

    pip = [str(py), "-m", "pip"]
    run(pip + ["install", "--upgrade", "pip"])

    for cmd in spec.pre_install:
        run_pip_audited(pip, list(cmd))

    install_requirements(pip, spec)

    if not smoke_test(spec, py):
        print(f"  [FAIL] {spec.code} installed but smoke test failed. "
              f"Try `python install.py --recreate`.")
        return False

    ensure_windows_style_launcher(venv)
    print(f"  [ok] {spec.code} installed at {venv}")
    return True


def build_venvs(
    venv_parent: Path,
    *,
    base_python: str,
    recreate: bool = False,
    kill_stale: bool = False,
    specs: list[McpSpec] | None = None,
) -> dict[str, bool]:
    """Build all server venvs under `venv_parent` (one per spec.code) and, on
    full success, write the idempotence stamp so `bootstrap.py` and re-runs
    can skip the work. Returns {spec.code: ok}."""
    use = specs if specs is not None else SPECS
    results: dict[str, bool] = {}
    for spec in use:
        try:
            ok = install_mcp(
                spec,
                base_python=base_python,
                venv=venv_dir_for(spec, venv_parent),
                recreate=recreate,
                kill_stale=kill_stale,
            )
        except subprocess.CalledProcessError as exc:
            print(f"  [FAIL] {spec.code} failed: {exc}")
            ok = False
        results[spec.code] = ok
    if all(results.values()):
        write_stamp(venv_parent, compute_stamp(REPO_ROOT, use))
        print(f"\nWrote stamp: {stamp_path(venv_parent)}")
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_base_python(cli_python: str | None) -> str:
    """Pick the interpreter used to create the venv.

    Pipeline Automation's venv is built with Python 3.12 (see REQUIRED_PYTHON).
    Refusing here beats building a venv this plugin's mcp-servers.json then
    points at but cannot run.
    """
    if cli_python:
        try:
            version = detect_interpreter_version(cli_python)
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            raise SystemExit(f"Could not run `{cli_python}` to detect its version: {exc}")
        if version != REQUIRED_PYTHON:
            need = ".".join(map(str, REQUIRED_PYTHON))
            raise SystemExit(
                f"Python {need} is required for this server's venv, but "
                f"`{cli_python}` is {'.'.join(map(str, version))}."
            )
        return cli_python

    found = find_python312()
    if not found:
        need = ".".join(map(str, REQUIRED_PYTHON))
        raise SystemExit(
            f"Python {need} is required but none was found on this machine.\n"
            f"Install it from https://www.python.org/downloads/ and re-run, or "
            f"point at one explicitly:\n"
            f"    python install.py --python <path-to-python3.12>"
        )
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the Unity Pipeline Automation MCP server venv.")
    parser.add_argument(
        "--python",
        default=None,
        help="Python 3.12 interpreter to use for creating venvs "
             "(default: auto-discover — this interpreter, `py -3.12`, `python3.12`, ...).",
    )
    parser.add_argument(
        "--venv-root",
        default=None,
        help="Directory to create the venv in. "
             f"Default: the Claude Code plugin data dir "
             f"({default_venv_parent()}).",
    )
    parser.add_argument(
        "--in-repo",
        action="store_true",
        help="Legacy/dev layout: create the venv as .venv inside this folder. "
             "Not used by the plugin.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete existing venvs before installing.",
    )
    parser.add_argument(
        "--kill-stale",
        action="store_true",
        help="Terminate any python processes still holding a target venv open "
             "before installing. Required to --recreate a venv whose MCP server "
             "is still running from a prior session.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip post-install prompts (e.g. the AT license-server prompt). Useful in CI.",
    )
    args = parser.parse_args()

    base_python = resolve_base_python(args.python)

    print(f"Unity Pipeline Automation MCP installer | plugin root: {PLUGIN_ROOT}")
    print(f"Base Python: {base_python}")

    results: dict[str, bool] = {}
    if args.in_repo:
        print("Layout: legacy in-repo (./.venv)")
        for spec in SPECS:
            try:
                ok = install_mcp(
                    spec,
                    base_python=base_python,
                    venv=REPO_ROOT / spec.folder / ".venv",
                    recreate=args.recreate,
                    kill_stale=args.kill_stale,
                )
            except subprocess.CalledProcessError as exc:
                print(f"  [FAIL] {spec.code} failed: {exc}")
                ok = False
            results[spec.code] = ok
    else:
        venv_parent = Path(args.venv_root).expanduser().resolve() if args.venv_root else default_venv_parent()
        print(f"Layout: shared venv root at {venv_parent}")
        results = build_venvs(
            venv_parent,
            base_python=base_python,
            recreate=args.recreate,
            kill_stale=args.kill_stale,
        )

    for spec in SPECS:
        if not results.get(spec.code):
            continue
        if spec.needs_unity_auth:
            print(f"  [note] {spec.name} uses browser-based Unity user login. "
                  "Run the `unity_login` MCP tool the first time you use the server.")

    print("\n=== Summary ===")
    for code, ok in results.items():
        status = "OK" if ok else "FAILED / SKIPPED"
        print(f"  {code}: {status}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
