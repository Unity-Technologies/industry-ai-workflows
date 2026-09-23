"""
signed_urls.py — validation for the signed blob URLs Asset Manager hands us.

Both file-transfer paths in `am_rest.py` read a URL out of an API response body and
immediately use it: `download_file` GETs it, and `upload_file` PUTs the file's bytes to it.
That is a server-controlled value flowing into an outbound HTTP request: textbook SSRF.

It reads like a non-issue — "we trust Asset Manager" — and that misses where the payoff is.
The dangerous destinations are not on the public internet:

  127.0.0.1          local tooling. This MCP server runs on a developer machine alongside
                     services that bind loopback with no auth of their own, on the
                     assumption that only this machine can reach them.
  169.254.169.254    cloud instance metadata — the classic SSRF-to-credential-theft path,
                     and the reason this matters far more in CI than on a laptop.
  10./172.16./192.168.  internal services reachable from a corporate machine or a VPC runner.
  file://            turns "download an asset" into "read an arbitrary local file and write
                     it to disk as that asset's contents".

So: https only, no embedded credentials, and every address the host resolves to must be
public. Callers additionally pass `allow_redirects=False`, because a validated URL that 302s
to an internal host defeats the validation — safe to disable, since a signed storage URL
addresses the object directly (verified against a real 1.8 MB download).

NOT in scope: the private-cloud OpenID config URL in `am_utils/unity_auth/pkce_auth.py`. That
one is operator-configured rather than server-supplied, and in a private-cloud deployment it
is *legitimately* an internal host — applying this check there would break VPC mode.

The two-lookup problem, and how it is closed: validating the host and then handing the URL
to `requests` means the name is resolved twice, and a name that answers differently the
second time (DNS rebinding) would pass the check and then connect somewhere else. This was
previously recorded here as an accepted limitation on the grounds that pinning the address
breaks TLS — it does not. urllib3 takes the SNI name separately from the connection
address, so `open_transfer_session` dials the address that was actually validated while
still presenting the original hostname for SNI and the `Host` header; certificate
validation is unchanged. There is no second lookup left to race.

Callers should use `open_transfer_session` rather than `assert_safe_transfer_url` for that
reason: the validator alone leaves the resolve-again gap open, and having one entry point
that both checks and pins means a sink cannot get half of it by accident.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import urllib.parse

import requests
from requests.adapters import HTTPAdapter

# Optional tighter boundary: a comma-separated list of allowed host suffixes, e.g.
# `AM_TRANSFER_HOST_SUFFIXES=.unity.com,.blob.core.windows.net`.
#
# Empty by default ON PURPOSE. Signed URLs currently resolve to
# `assets.transformation.unity.com` — Unity fronts Azure Blob behind its own CNAME, which is
# why the `x-ms-blob-type` header is needed even though the host is not
# `*.blob.core.windows.net`. That CNAME has changed before, so a hardcoded allowlist would
# turn a platform-side CDN change into a total outage of every upload and download. The
# address check below has no such failure mode.
ALLOWLIST_ENV = "AM_TRANSFER_HOST_SUFFIXES"


class UnsafeTransferURL(RuntimeError):
    """A signed URL failed validation. Always fatal — the URL is never used."""


def _host_allowlist() -> tuple[str, ...]:
    raw = os.environ.get(ALLOWLIST_ENV, "")
    return tuple(s.strip().lower() for s in raw.split(",") if s.strip())


def _resolved_addresses(hostname: str) -> list:
    """Every address `hostname` resolves to.

    All of them, not just the first: a name returning one public and one private address
    would otherwise pass validation and then connect to the private one.
    """
    try:
        entries = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise UnsafeTransferURL(
            f"cannot resolve transfer host {hostname!r}: {e}"
        ) from e

    addresses = []
    for entry in entries:
        raw = entry[4][0]
        try:
            addresses.append(ipaddress.ip_address(raw))
        except ValueError:
            raise UnsafeTransferURL(
                f"transfer host {hostname!r} resolved to an unparseable address {raw!r}"
            ) from None
    if not addresses:
        raise UnsafeTransferURL(f"transfer host {hostname!r} resolved to nothing")
    return addresses


class _PinnedAddressAdapter(HTTPAdapter):
    """Connects to a pre-validated IP address, keeping the hostname for TLS and `Host`.

    The address swap happens in `send`, on the outgoing URL, so nothing above this layer
    has to know about it. `server_hostname` and `assert_hostname` carry the real name into
    the TLS handshake, which is why certificate verification still passes — the connection
    goes to an IP, the certificate is checked against the name.

    One address, not the whole resolved set: `getaddrinfo` returns them in the order the
    OS itself would have tried, so the first is the one an unpinned `requests` would have
    connected to. Retrying the rest would mean re-sending a request body that may already
    be partly consumed, which is worse than a clean connection error.
    """

    def __init__(self, hostname: str, address: str) -> None:
        self._hostname = hostname
        self._address = f"[{address}]" if ":" in address else address
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):  # noqa: ANN002, ANN003
        kwargs["server_hostname"] = self._hostname
        kwargs["assert_hostname"] = self._hostname
        return super().init_poolmanager(*args, **kwargs)

    def send(self, request, **kwargs):  # noqa: ANN001, ANN003
        parsed = urllib.parse.urlsplit(request.url)
        netloc = self._address if parsed.port is None else f"{self._address}:{parsed.port}"
        request.url = urllib.parse.urlunsplit(parsed._replace(netloc=netloc))
        request.headers["Host"] = parsed.netloc
        return super().send(request, **kwargs)


def open_transfer_session(
    url: str, purpose: str = "transfer"
) -> tuple[str, requests.Session]:
    """Validate a signed blob URL and return it with a session pinned to that address.

    Use this at every transfer sink. Close the session when done (it is a context
    manager), and keep `allow_redirects=False` on the request: a validated URL that 302s
    to an internal host defeats the validation, and the pinned address does not follow it.
    """
    url, addresses = _validate(url, purpose)
    session = requests.Session()
    session.mount(
        "https://",
        _PinnedAddressAdapter(urllib.parse.urlparse(url).hostname or "", str(addresses[0])),
    )
    return url, session


def assert_safe_transfer_url(url: str, purpose: str = "transfer") -> str:
    """Validate a signed blob URL, or raise `UnsafeTransferURL`.

    Returns the (stripped) URL. Prefer `open_transfer_session` at a sink — this leaves the
    resolve-again gap open, because whoever connects afterwards looks the name up again.
    """
    return _validate(url, purpose)[0]


def _validate(url: str, purpose: str) -> tuple[str, list]:
    """The checks themselves. Returns the stripped URL and the addresses it resolved to,
    so a caller can connect to exactly what was validated."""
    if not url or not url.strip():
        raise UnsafeTransferURL(f"no {purpose} URL was returned by the API")

    url = url.strip()
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme.lower() != "https":
        raise UnsafeTransferURL(
            f"{purpose} URL must use https, got {parsed.scheme or '<none>'!r}"
        )
    if parsed.username or parsed.password:
        raise UnsafeTransferURL(
            f"{purpose} URL must not embed credentials (they would reach the logs)"
        )

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeTransferURL(f"{purpose} URL has no host: {url[:80]!r}")

    allowlist = _host_allowlist()
    if allowlist and not any(
        hostname.lower() == suffix.lstrip(".") or hostname.lower().endswith(suffix)
        for suffix in allowlist
    ):
        raise UnsafeTransferURL(
            f"{purpose} host {hostname!r} is not permitted by {ALLOWLIST_ENV}"
        )

    addresses = _resolved_addresses(hostname)
    for address in addresses:
        # `is_global` is False for private, loopback, link-local, multicast, reserved and
        # unspecified ranges — one property rather than six hand-written comparisons, and it
        # covers the metadata endpoint without naming it.
        if not address.is_global:
            raise UnsafeTransferURL(
                f"{purpose} host {hostname!r} resolves to the non-public address "
                f"{address} — refusing. A signed storage URL should never point inside "
                f"the network."
            )
    return url, addresses
