"""
Standalone PKCE login for the Unity Asset Pipeline MCP servers
==============================================================

A pure-Python implementation of the Unity Cloud browser PKCE login flow.
This is the sole auth mechanism for the Asset
Manager and Pipeline Automation MCP servers — both share this module and a
single token cache, so one `unity_login` signs you in to both.

Flow:
1. Generate a code verifier + S256 challenge and a state value.
2. Spin up a one-shot HTTP server on the loopback to catch the OAuth redirect.
3. Open the system browser to Unity's authorize endpoint (proxied via
   services.api.unity.com so the redirect URI doesn't need per-client
   registration).
4. Exchange the returned authorization code for a Genesis access token.
5. Exchange the Genesis token for a Unity Services token (the one that the
   Unity Cloud APIs actually accept as a Bearer credential).
6. Cache the bundle (tokens + refresh + expiry) under ~/.uap_mcp/token.json
   (or $UAP_MCP_HOME/token.json) so subsequent runs reuse it until the
   refresh token can no longer be used.

Refresh: when the cached Unity Services token is within REFRESH_LEEWAY_SECONDS
of expiry, use the Genesis refresh_token to mint a new Genesis token, then
re-exchange for a new Services token. Refresh is serialized across processes
with a lock file so AM and PA (which share the cache) can't double-refresh and
invalidate a single-use refresh token. The cache is only cleared when Unity
definitively rejects the refresh (HTTP 400/401/403); transient network
failures leave the cache intact so the login survives being offline.

Migration: the first time the current token.json is missing, the freshest
pre-0.6.0 cache is adopted — either a per-server cache (am_token.json /
pa_token.json) or one from the previous ~/.amt_mcp home. Same-directory
legacy files are left for uninstall.py; a bundle adopted from the old home is
removed from it, since that directory is outside everything the uninstaller
sweeps.

Private cloud (VPC) mode
------------------------
When UNITY_VPC_FQDN is set (see shared/unity_auth/vpc.py) this module drives a
standard OIDC PKCE flow against the deployment's embedded Keycloak instead of
the public-cloud proxy flow, per Unity VPC deployment docs:

1. Fetch the discovery document (realm `unity`) for authorization_endpoint /
   token_endpoint.
2. Same S256 PKCE + loopback callback server as public mode, but the redirect
   URI is the loopback URL itself (registered for the public `dashboard`
   client) — no app-linking proxy hop.
3. Exchange the code at token_endpoint. The Keycloak access_token IS the Bearer
   credential for both the Assets and Automation APIs — there is NO
   Genesis -> Services token exchange on VPC.
4. Refresh with a standard `refresh_token` grant at token_endpoint, with the
   same Rejected (400/401/403 -> clear cache) / Unavailable (transport, 5xx ->
   keep cache) classification as public mode.

The cached bundle records its `mode` ("public"/"vpc") and, for VPC, the
`issuer` (FQDN), so a token minted for one deployment is never presented to
another: a mismatch reads as "not logged in". Cache files written before this
existed have no mode field and are treated as public.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

from . import vpc
from ..version import attribution_headers


# ---------------------------------------------------------------------------
# Config — mirrors the CONFIG block in the HTML sample
# ---------------------------------------------------------------------------

CLIENT_ID = "unity_cloud"
PROXY_LOGIN_REDIRECT_ROUTE = "services.api.unity.com/app-linking/v1/login/redirect/"
PROXY_LOGIN_COMPLETED_ROUTE = "services.api.unity.com/app-linking/v1/login/completed/"
LOGIN_URL = "https://api.unity.com/v1/oauth2/authorize"
TOKEN_URL = "https://services.api.unity.com/app-linking/v1/token"
TOKEN_EXCHANGE_URL = "https://services.api.unity.com/app-linking/v1/token/exchange"
APP_NAMESPACE = "com.unity.cloud"
TARGET_CLIENT_ID = "ads-publisher"  # required by the Genesis -> Services exchange

DEFAULT_REDIRECT_HOST = "localhost"
DEFAULT_REDIRECT_PORT = int(os.environ.get("UNITY_PKCE_REDIRECT_PORT", "8765"))
DEFAULT_REDIRECT_PATH = "/callback"

# Refresh slightly before the server says the token expires, to avoid races.
REFRESH_LEEWAY_SECONDS = 60

# How long to wait for the user to complete the browser login before giving up.
LOGIN_TIMEOUT_SECONDS = 300

# How long to wait for another process to finish a concurrent token refresh.
LOCK_TIMEOUT_SECONDS = 120

# Environment override for the cache home. The pre-0.6.0 name is still
# honoured so setups that export it keep working; the new one wins.
ENV_HOME = "UAP_MCP_HOME"
ENV_HOME_LEGACY = "AMT_MCP_HOME"

# Legacy per-server caches (pre-unification). Read once for migration only.
_LEGACY_CACHE_NAMES = ("am_token.json", "pa_token.json")

# Cache homes used before the uap_mcp rename. Unlike the per-server caches
# above — which live in the same directory uninstall.py cleans — these sit
# outside the current home, so an adopted bundle is removed from them rather
# than left behind as a stray live refresh token.
_LEGACY_TOKEN_DIRS = (Path.home() / ".amt_mcp",)

# Deployment modes a cached bundle can belong to.
MODE_PUBLIC = "public"
MODE_VPC = "vpc"

# OIDC scopes requested from the VPC's Keycloak. `openid` is required for the
# flow; `offline_access` is deliberately NOT requested because Keycloak gates it
# behind a role and already returns a normal refresh token for the
# authorization_code grant (verified against a live deployment).
VPC_SCOPES = "openid profile email"

# Discovery documents are small and stable for the life of a process.
_OPENID_CONFIG_CACHE: dict[str, dict] = {}


def current_mode() -> str:
    """"vpc" when a private-cloud FQDN is configured, else "public"."""
    return MODE_VPC if vpc.is_vpc() else MODE_PUBLIC


def current_issuer() -> str:
    """The private-cloud FQDN in VPC mode; empty string on public cloud."""
    return vpc.vpc_fqdn()


def deployment_label() -> str:
    """Human-readable description of the deployment tools are talking to."""
    fqdn = current_issuer()
    return f"Unity private cloud ({fqdn})" if fqdn else "Unity Cloud"


def token_home_env() -> str:
    """The configured cache home, or "" — new variable first, then the
    pre-0.6.0 one."""
    return (os.environ.get(ENV_HOME) or os.environ.get(ENV_HOME_LEGACY) or "").strip()


def _token_dir() -> Path:
    base = Path(token_home_env() or str(Path.home() / ".uap_mcp"))
    base.mkdir(parents=True, exist_ok=True)
    # Once per process, not per call: this runs on every cache read, lock and save, and
    # the Windows branch spawns `icacls`. The ACL does not drift while we hold it.
    if str(base) not in _HARDENED_DIRS:
        _HARDENED_DIRS.add(str(base))
        _restrict_to_owner(base)
        _warn_if_shared_location(base)
    return base


_HARDENED_DIRS: set[str] = set()
_WARNED_SHARED_HOME = False


def _warn_if_shared_location(base: Path) -> None:
    """Say something once if the cache has been moved outside the user's profile.

    The file protection below is applied either way, but a redirect to a location like
    `C:/ProgramData` or `/tmp` also means the *directory* was created with whatever
    permissions that parent grants, and anything already sitting there was not created by
    us. Not fatal: private-cloud operators legitimately relocate the cache, and refusing
    to start over a directory choice would be worse than saying so.
    """
    global _WARNED_SHARED_HOME
    if _WARNED_SHARED_HOME or not token_home_env():
        return
    try:
        resolved = base.resolve()
        home = Path.home().resolve()
        inside_profile = resolved == home or home in resolved.parents
    except OSError:
        inside_profile = False
    if not inside_profile:
        _WARNED_SHARED_HOME = True
        print(
            f"[unity-auth] warning: {ENV_HOME} points outside your user profile "
            f"({resolved}). Access is restricted to your account, but a shared parent "
            f"directory is a poor place for OAuth tokens — prefer the default "
            f"{Path.home() / '.uap_mcp'}.",
            file=sys.stderr,
        )


def _restrict_to_owner(target: Path) -> None:
    """Make `target` readable only by its owner, on Windows as well as POSIX.

    POSIX gets the mode directly. Windows ignores `chmod` for access control — the mode
    bits only toggle the read-only attribute — so the ACL has to be rewritten instead:
    `/inheritance:r` drops whatever the parent directory granted, and the single
    `/grant:r` puts the current user back. That matters because the previous code relied
    on `%USERPROFILE%` being per-user, an assumption `UAP_MCP_HOME` lets an operator
    invalidate by pointing the cache at a shared directory.

    Best-effort by design: a failure here must not stop a login. `icacls` rather than
    pywin32 because two of the three servers do not depend on pywin32 and a token cache
    is the wrong reason to add a native dependency to them.
    """
    if os.name != "nt":
        with suppress(OSError):
            target.chmod(0o700 if target.is_dir() else 0o600)
        return

    user = os.environ.get("USERNAME") or ""
    if not user:
        return
    domain = os.environ.get("USERDOMAIN") or ""
    principal = f"{domain}\\{user}" if domain else user
    with suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            ["icacls", str(target), "/inheritance:r", "/grant:r", f"{principal}:(F)"],
            capture_output=True,
            check=False,
            timeout=15,
        )


def _token_cache_path() -> Path:
    return _token_dir() / "token.json"


def _lock_path() -> Path:
    return _token_dir() / "token.json.lock"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class NotLoggedInError(Exception):
    """Raised when no usable login is available for a request (no cache, the
    cached login was rejected on refresh, or Unity was unreachable)."""


class TokenRefreshRejected(Exception):
    """The token endpoint definitively rejected our credentials (HTTP
    400/401/403). The cached refresh token is dead; re-login is required."""


class TokenRefreshUnavailable(Exception):
    """The token endpoint could not be used right now (network error, timeout,
    5xx). The cached refresh token may still be perfectly valid."""


# ---------------------------------------------------------------------------
# Cross-process lock — msvcrt on Windows, fcntl elsewhere
# ---------------------------------------------------------------------------

class _FileLock:
    """Small portable exclusive lock around a dedicated lock file. Used to
    serialize token refresh across the AM and PA server processes, which share
    a single cache (a Genesis refresh token is single-use: two concurrent
    refreshes would invalidate one process's result)."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT_SECONDS):
        self._path = path
        self._timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "_FileLock":
        # 0o600: owner-only on POSIX; effectively a no-op on Windows (see
        # _save_bundle for the same caveat).
        fd = os.open(str(self._path), os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self._timeout
        try:
            if os.name == "nt":
                import msvcrt

                while True:
                    try:
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                f"Timed out waiting for the token-cache lock ({self._path})."
                            )
                        time.sleep(0.2)
            else:
                import fcntl

                # Blocking flock — no portable timeout, but refreshes finish in
                # seconds so contention is short-lived.
                fcntl.flock(fd, fcntl.LOCK_EX)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        return self

    def __exit__(self, *exc) -> None:
        fd = self._fd
        self._fd = None
        if fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# Helpers — base64url, PKCE primitives
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_code_verifier() -> str:
    return _b64url(secrets.token_bytes(43))


def _generate_code_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _generate_state() -> str:
    return _b64url(secrets.token_bytes(43))


def _redirect_hint(redirect_uri: str) -> str:
    """Match the HTML sample: for http(s) URIs encode the URI itself, otherwise
    fall back to the app namespace. The Unity proxy uses this to route the
    final redirect back to the right place.

    The proxy only treats the hint as a base64-encoded URL when the original
    URI starts with `http://localhost` or `https://`. Anything else (including
    `http://127.0.0.1`) is interpreted as a custom URI scheme and the bounce
    back to loopback never happens — so callers must use `localhost`."""
    if redirect_uri.startswith("http://localhost") or redirect_uri.startswith("https://"):
        return base64.b64encode(redirect_uri.encode("utf-8")).decode("ascii")
    return APP_NAMESPACE


def _build_authenticate_url(state: str, code_challenge: str, redirect_uri: str) -> str:
    hint = _redirect_hint(redirect_uri)
    encoded_login = urllib.parse.quote(LOGIN_URL, safe="")
    base = f"https://{PROXY_LOGIN_REDIRECT_ROUTE}{hint}/{encoded_login}"
    params = urllib.parse.urlencode(
        {
            "client_id": CLIENT_ID,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "response_type": "code",
        }
    )
    return f"{base}?{params}"


def _constructed_redirect_uri(redirect_uri: str) -> str:
    """The redirect_uri value the token endpoint expects — not the actual
    callback URL, but the Unity proxy's 'completed' URL with the same hint."""
    hint = _redirect_hint(redirect_uri)
    return f"https://{PROXY_LOGIN_COMPLETED_ROUTE}{hint}/"


# ---------------------------------------------------------------------------
# Local callback server — single-shot
# ---------------------------------------------------------------------------

class _CallbackResult:
    def __init__(self) -> None:
        self.code: str | None = None
        self.state: str | None = None
        self.error: str | None = None
        self.event = threading.Event()


def _make_handler(result: _CallbackResult, expected_path: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence default stderr logging
            return

        def do_GET(self):  # noqa: N802 (required by BaseHTTPRequestHandler)
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            result.code = (qs.get("code") or [None])[0]
            result.state = (qs.get("state") or [None])[0]
            result.error = (qs.get("error") or [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            body = (
                "<html><body style='font-family:sans-serif;padding:32px'>"
                "<h2>Unity sign-in complete</h2>"
                "<p>You can close this tab and return to your terminal.</p>"
                "</body></html>"
            )
            self.wfile.write(body.encode("utf-8"))
            result.event.set()

    return Handler


def _wait_for_callback(host: str, port: int, path: str, timeout: float) -> _CallbackResult:
    result = _CallbackResult()
    try:
        server = HTTPServer((host, port), _make_handler(result, path))
    except OSError as e:
        raise RuntimeError(
            f"Port {port} on {host} is in use — set UNITY_PKCE_REDIRECT_PORT to a "
            f"free port and retry. ({e})"
        ) from e
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if not result.event.wait(timeout=timeout):
            raise TimeoutError(
                f"Timed out after {timeout:.0f}s waiting for the Unity login callback."
            )
        return result
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# Token bundle — what we cache to disk
# ---------------------------------------------------------------------------

@dataclass
class TokenBundle:
    services_token: str            # the Bearer token used for Unity Cloud API calls
    genesis_access_token: str      # public mode: upstream Genesis token; VPC: same as services_token
    refresh_token: str             # used to refresh (Genesis grant on public, Keycloak grant on VPC)
    id_token: str | None
    expires_at: float              # epoch seconds when the Services token should be considered stale
    # Which deployment this token was minted for. A bundle is only usable in a
    # matching deployment, so a token for one private cloud (or the public
    # cloud) is never presented to another. Files written before these fields
    # existed have no mode and are read as public.
    mode: str = MODE_PUBLIC
    issuer: str = ""               # VPC FQDN in vpc mode; empty on public cloud

    def to_json(self) -> dict:
        return {
            "services_token": self.services_token,
            "genesis_access_token": self.genesis_access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "expires_at": self.expires_at,
            "mode": self.mode,
            "issuer": self.issuer,
        }

    @staticmethod
    def from_json(data: dict) -> "TokenBundle":
        return TokenBundle(
            services_token=data["services_token"],
            genesis_access_token=data["genesis_access_token"],
            refresh_token=data["refresh_token"],
            id_token=data.get("id_token"),
            expires_at=float(data.get("expires_at", 0.0)),
            mode=data.get("mode") or MODE_PUBLIC,
            issuer=data.get("issuer") or "",
        )

    def needs_refresh(self) -> bool:
        return time.time() >= (self.expires_at - REFRESH_LEEWAY_SECONDS)

    def matches_deployment(self) -> bool:
        """True when this bundle belongs to the deployment configured right now."""
        if self.mode != current_mode():
            return False
        return self.mode != MODE_VPC or self.issuer == current_issuer()


def _read_bundle_file(path: Path) -> TokenBundle | None:
    try:
        return TokenBundle.from_json(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _legacy_cache_paths(target: Path) -> list[Path]:
    """Every pre-0.6.0 cache file that might hold a usable bundle.

    Two generations to cover: the per-server caches from before AM and PA
    shared one login (same directory as `target`), and the whole previous
    cache home from before the uap_mcp rename (a different directory).

    The previous *home* is only consulted when no home is configured. An
    explicit $UAP_MCP_HOME means "use exactly this cache" — reaching outside it
    would let an isolated cache adopt (and, below, delete) the real login.
    """
    paths = [target.parent / name for name in _LEGACY_CACHE_NAMES]
    if not token_home_env():
        for directory in _LEGACY_TOKEN_DIRS:
            if directory != target.parent:
                paths.append(directory / target.name)
                paths.extend(directory / name for name in _LEGACY_CACHE_NAMES)
    return paths


def _migrate_legacy_cache(target: Path) -> None:
    """One-time adoption of a pre-0.6.0 cache: when the current token.json is
    missing but an older one exists, copy the freshest into place.

    A bundle adopted from a previous cache *home* is then deleted, because that
    directory is outside everything uninstall.py sweeps and the file holds a
    live refresh token. Same-directory legacy names are left alone — those the
    uninstaller already removes.
    """
    candidates: list[tuple[float, Path]] = []
    for path in _legacy_cache_paths(target):
        try:
            if path.exists():
                candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    for _, path in sorted(candidates, key=lambda t: t[0], reverse=True):
        bundle = _read_bundle_file(path)
        if bundle is None:
            continue
        try:
            _save_bundle(bundle)
        except OSError:
            return  # couldn't adopt it — leave the original untouched
        if path.parent != target.parent:
            with suppress(OSError):
                path.unlink()
        return


def _load_bundle() -> TokenBundle | None:
    path = _token_cache_path()
    if not path.exists():
        _migrate_legacy_cache(path)
        if not path.exists():
            return None
    return _read_bundle_file(path)


def _save_bundle(bundle: TokenBundle) -> None:
    """Atomically persist the bundle: write to a temp file in the same
    directory, then os.replace over the real path so readers never see a
    partial file."""
    path = _token_cache_path()
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    # O_CREAT with mode 0o600 makes the file owner-only from the moment it exists on
    # POSIX. On Windows the mode only maps to the read-only bit and grants nothing, so
    # _restrict_to_owner below rewrites the ACL after the file is in place — the mode
    # alone was relying on %USERPROFILE% being per-user, which UAP_MCP_HOME can undo.
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(bundle.to_json(), indent=2))
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    os.replace(str(tmp), str(path))
    # After the replace, not before: os.replace onto an existing path keeps the
    # destination's ACL on Windows, so restricting the temp file would be discarded.
    _restrict_to_owner(path)


def _clear_bundle() -> None:
    path = _token_cache_path()
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Token exchange calls
# ---------------------------------------------------------------------------

def _classified_post(url: str, *, what: str, **kwargs) -> dict:
    """POST to a token endpoint, classifying failures:
    - transport error / timeout  -> TokenRefreshUnavailable
    - HTTP 400/401/403           -> TokenRefreshRejected (credentials are dead)
    - other non-2xx (5xx, ...)   -> TokenRefreshUnavailable (server-side blip)
    """
    kwargs["headers"] = {**attribution_headers(), **(kwargs.get("headers") or {})}
    try:
        resp = requests.post(url, timeout=30, **kwargs)
    except requests.RequestException as e:
        raise TokenRefreshUnavailable(f"{what}: could not reach Unity ({e})") from e
    if resp.status_code in (400, 401, 403):
        raise TokenRefreshRejected(f"{what}: HTTP {resp.status_code} — {resp.text}")
    if not resp.ok:
        raise TokenRefreshUnavailable(f"{what}: HTTP {resp.status_code} — {resp.text}")
    return resp.json()


def _exchange_code_for_genesis(code: str, verifier: str, redirect_uri: str) -> dict:
    return _classified_post(
        TOKEN_URL,
        what="Genesis token exchange failed",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": _constructed_redirect_uri(redirect_uri),
        },
    )


def _refresh_genesis(refresh_token: str) -> dict:
    return _classified_post(
        TOKEN_URL,
        what="Genesis refresh failed",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )


def _exchange_for_services(genesis_access_token: str) -> dict:
    return _classified_post(
        TOKEN_EXCHANGE_URL,
        what="Services token exchange failed",
        headers={"Content-Type": "application/json"},
        json={
            "accessToken": genesis_access_token,
            "grantType": "EXCHANGE_ACCESS_TOKEN",
            "targetClientId": TARGET_CLIENT_ID,
        },
    )


def _bundle_from_responses(genesis: dict, services: dict, prev_refresh: str | None = None) -> TokenBundle:
    expires_in = float(genesis.get("expires_in", 3600))  # genesis token expiry drives refresh cadence
    return TokenBundle(
        services_token=services["token"],
        genesis_access_token=genesis["access_token"],
        refresh_token=genesis.get("refresh_token") or prev_refresh or "",
        id_token=genesis.get("id_token"),
        expires_at=time.time() + expires_in,
        mode=MODE_PUBLIC,
    )


# ---------------------------------------------------------------------------
# VPC (private cloud): standard OIDC PKCE against the deployment's Keycloak
# ---------------------------------------------------------------------------

def _vpc_openid_config() -> dict:
    """Fetch (and process-cache) the VPC's OIDC discovery document."""
    url = vpc.openid_config_url()
    if not url:
        raise NotLoggedInError(
            f"Private cloud mode requires {vpc.ENV_FQDN} (and optionally "
            f"{vpc.ENV_OPENID_CONFIG_URL}) to be configured."
        )
    cached = _OPENID_CONFIG_CACHE.get(url)
    if cached is not None:
        return cached
    try:
        resp = requests.get(url, timeout=30, headers=attribution_headers())
    except requests.RequestException as e:
        raise TokenRefreshUnavailable(
            f"Could not reach the private cloud identity service at {url} ({e})"
        ) from e
    if not resp.ok:
        raise TokenRefreshUnavailable(
            f"Private cloud OIDC discovery failed: HTTP {resp.status_code} from {url}"
        )
    config = resp.json()
    for key in ("authorization_endpoint", "token_endpoint"):
        if not config.get(key):
            raise TokenRefreshUnavailable(
                f"Private cloud OIDC discovery document at {url} is missing '{key}'."
            )
    _OPENID_CONFIG_CACHE[url] = config
    return config


def _vpc_bundle_from_token_response(data: dict, prev_refresh: str | None = None) -> TokenBundle:
    """Build a bundle from a Keycloak token response.

    On VPC the access token IS the credential both APIs accept — there is no
    Genesis -> Services exchange, so services_token and genesis_access_token
    hold the same value.
    """
    access = data["access_token"]
    return TokenBundle(
        services_token=access,
        genesis_access_token=access,
        refresh_token=data.get("refresh_token") or prev_refresh or "",
        id_token=data.get("id_token"),
        expires_at=time.time() + float(data.get("expires_in", 3600)),
        mode=MODE_VPC,
        issuer=current_issuer(),
    )


def _vpc_login(open_browser: bool) -> TokenBundle:
    """Standard OIDC authorization-code + PKCE flow against the VPC Keycloak.

    The loopback URL is the real redirect_uri here (no app-linking proxy hop);
    it must be registered for the configured public client.
    """
    config = _vpc_openid_config()
    host = os.environ.get("UNITY_PKCE_REDIRECT_HOST", DEFAULT_REDIRECT_HOST)
    port = int(os.environ.get("UNITY_PKCE_REDIRECT_PORT", str(DEFAULT_REDIRECT_PORT)))
    path = os.environ.get("UNITY_PKCE_REDIRECT_PATH", DEFAULT_REDIRECT_PATH)
    redirect_uri = f"http://{host}:{port}{path}"

    verifier = _generate_code_verifier()
    state = _generate_state()
    params = urllib.parse.urlencode(
        {
            "client_id": vpc.client_id(),
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": VPC_SCOPES,
            "state": state,
            "code_challenge": _generate_code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    auth_url = f"{config['authorization_endpoint']}?{params}"
    if open_browser:
        webbrowser.open(auth_url, new=1, autoraise=True)

    cb = _wait_for_callback(host, port, path, timeout=LOGIN_TIMEOUT_SECONDS)
    if cb.error:
        raise RuntimeError(f"Private cloud sign-in returned an error: {cb.error}")
    if not cb.code or cb.state != state:
        raise RuntimeError("Private cloud callback was missing a code or returned a mismatched state.")

    data = _classified_post(
        config["token_endpoint"],
        what="Private cloud token exchange failed",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "client_id": vpc.client_id(),
            "code": cb.code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        },
    )
    return _vpc_bundle_from_token_response(data)


def _vpc_refresh(refresh_token: str) -> dict:
    """Standard OIDC refresh_token grant against the VPC Keycloak."""
    config = _vpc_openid_config()
    return _classified_post(
        config["token_endpoint"],
        what="Private cloud token refresh failed",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "client_id": vpc.client_id(),
            "refresh_token": refresh_token,
        },
    )


# ---------------------------------------------------------------------------
# Public API used by the init shims / the unity_login MCP tool
# ---------------------------------------------------------------------------

def is_logged_in() -> bool:
    """True if a cached token exists for the CURRENT deployment and we believe it
    can still be used (either fresh, or refreshable). We don't proactively
    refresh here — get_access_token() handles that on demand."""
    bundle = _load_bundle()
    return bundle is not None and bundle.matches_deployment()


def _usable_bundle() -> TokenBundle:
    """The cached bundle for the current deployment, or NotLoggedInError.

    A bundle minted for a different deployment (public vs a private cloud, or
    another private cloud) is never used — the user is told to sign in for the
    deployment now configured.
    """
    bundle = _load_bundle()
    if bundle is None:
        raise NotLoggedInError(
            "No cached Unity login. Call the `unity_login` MCP tool to sign in."
        )
    if not bundle.matches_deployment():
        where = (
            f"private cloud '{current_issuer()}'" if current_mode() == MODE_VPC
            else "the public Unity Cloud"
        )
        raise NotLoggedInError(
            f"The cached login was for a different deployment. Call the "
            f"`unity_login` MCP tool to sign in to {where}."
        )
    return bundle


def get_access_token() -> str:
    """Return a usable Unity Services Bearer token, refreshing if necessary.

    Raises NotLoggedInError if there's no cached login at all, if Unity
    rejected the cached refresh token (cache is cleared), or if Unity could
    not be reached to refresh (cache is preserved — retry later)."""
    bundle = _usable_bundle()
    if not (bundle.needs_refresh() and bundle.refresh_token):
        return bundle.services_token

    # Serialize the refresh across processes: AM and PA share this cache and a
    # refresh token is single-use, so concurrent refreshes would leave one
    # process holding an invalidated token.
    with _FileLock(_lock_path()):
        # Re-read: another process may have refreshed while we waited.
        bundle = _usable_bundle()
        if not (bundle.needs_refresh() and bundle.refresh_token):
            return bundle.services_token
        try:
            if current_mode() == MODE_VPC:
                bundle = _vpc_bundle_from_token_response(
                    _vpc_refresh(bundle.refresh_token), prev_refresh=bundle.refresh_token
                )
                _save_bundle(bundle)
                return bundle.services_token
            genesis = _refresh_genesis(bundle.refresh_token)
            services = _exchange_for_services(genesis["access_token"])
        except TokenRefreshRejected as e:
            # Definitive rejection: the refresh token is dead. Clear the cache
            # so the next unity_login starts cleanly.
            _clear_bundle()
            raise NotLoggedInError(
                f"Unity rejected the cached login during refresh ({e}). "
                "Call the `unity_login` MCP tool to sign in again."
            ) from e
        except TokenRefreshUnavailable as e:
            # Transient failure (offline, timeout, 5xx): the cached refresh
            # token is likely still valid — keep it and let the user retry.
            raise NotLoggedInError(
                "Could not reach Unity to refresh the login token — check your "
                f"connection and retry. The cached login was kept. ({e})"
            ) from e
        bundle = _bundle_from_responses(genesis, services, prev_refresh=bundle.refresh_token)
        _save_bundle(bundle)
        return bundle.services_token


def login(open_browser: bool = True) -> TokenBundle:
    """Drive the full PKCE flow end-to-end. Blocks until the user finishes
    signing in (or the timeout elapses). Caches the result and returns it.
    The cache is shared by the AM and PA MCP servers — one login covers both.

    In private-cloud mode this runs the OIDC flow against the deployment's
    Keycloak instead of the public-cloud proxy flow."""
    if current_mode() == MODE_VPC:
        bundle = _vpc_login(open_browser)
        _save_bundle(bundle)
        return bundle

    host = os.environ.get("UNITY_PKCE_REDIRECT_HOST", DEFAULT_REDIRECT_HOST)
    port = int(os.environ.get("UNITY_PKCE_REDIRECT_PORT", str(DEFAULT_REDIRECT_PORT)))
    path = os.environ.get("UNITY_PKCE_REDIRECT_PATH", DEFAULT_REDIRECT_PATH)
    redirect_uri = f"http://{host}:{port}{path}"

    verifier = _generate_code_verifier()
    challenge = _generate_code_challenge(verifier)
    state = _generate_state()
    auth_url = _build_authenticate_url(state, challenge, redirect_uri)

    if open_browser:
        webbrowser.open(auth_url, new=1, autoraise=True)

    cb = _wait_for_callback(host, port, path, timeout=LOGIN_TIMEOUT_SECONDS)
    if cb.error:
        raise RuntimeError(f"Unity returned an error in the callback: {cb.error}")
    if not cb.code or cb.state != state:
        raise RuntimeError("Callback was missing a code or returned a mismatched state.")

    genesis = _exchange_code_for_genesis(cb.code, verifier, redirect_uri)
    services = _exchange_for_services(genesis["access_token"])
    bundle = _bundle_from_responses(genesis, services)
    _save_bundle(bundle)
    return bundle


def logout() -> None:
    """Delete the shared token cache. Because AM and PA share it, this signs
    you out of both servers."""
    _clear_bundle()
