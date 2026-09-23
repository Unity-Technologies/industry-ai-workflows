"""
Private cloud (VPC) configuration for the Unity Asset Pipeline MCP servers
==========================================================================

Unity private cloud deployments serve the same Asset Manager / Pipeline
Automation REST APIs from the deployment's own host instead of the public
Unity Cloud hosts. Per Unity VPC deployment docs the mapping is a pure
rebase — same endpoint paths, different base:

    public  https://services.api.unity.com/assets/v1/...
    VPC     https://{fqdn}{path_prefix}/assets/v1/...

    public  https://automation.services.api.unity.com/v1/...
    VPC     https://{fqdn}{path_prefix}/automation/v1/...

Auth on VPC is the deployment's embedded Keycloak (realm ``unity``): a
standard OIDC PKCE flow against the discovery document at
``https://{fqdn}/auth/realms/unity/.well-known/openid-configuration`` using
the public client id ``dashboard``. The Keycloak access token is sent
directly as the Bearer credential — there is no Genesis→Services token
exchange on VPC (see pkce_auth.py).

Everything is driven by environment variables; when UNITY_VPC_FQDN is blank
(the default) every helper returns the public-cloud value and behavior is
byte-identical to a build without this module.

Env vars:
    UNITY_VPC_FQDN               fully qualified domain of the private cloud
                                 (blank = standard/public Unity Cloud)
    UNITY_VPC_OPENID_CONFIG_URL  explicit OIDC discovery URL (blank = derive
                                 from the FQDN per the Keycloak layout above)
    UNITY_VPC_PATH_PREFIX        optional path prefix the deployment serves
                                 its APIs under (slashes normalized; a known
                                 real-world value is ``backend``, verified
                                 2026-07-27 against a live VPC instance)
    UNITY_VPC_CLIENT_ID          OIDC public client id (default ``dashboard``)
    UNITY_VPC_AUTOMATION_PATH    service path of the Pipeline Automation API
                                 on the VPC host (blank = auto-detect: the
                                 API version varies by bundle release, so
                                 ``api/automation/v1`` is tried first and
                                 ``api/automation/v1alpha1`` is the fallback;
                                 set explicitly to pin a single path)
"""

from __future__ import annotations

import os
from typing import Mapping

ENV_FQDN = "UNITY_VPC_FQDN"
ENV_OPENID_CONFIG_URL = "UNITY_VPC_OPENID_CONFIG_URL"
ENV_PATH_PREFIX = "UNITY_VPC_PATH_PREFIX"
ENV_CLIENT_ID = "UNITY_VPC_CLIENT_ID"
ENV_AUTOMATION_PATH = "UNITY_VPC_AUTOMATION_PATH"
ENV_ASSETS_PATH = "UNITY_VPC_ASSETS_PATH"

# Per Unity VPC deployment docs: interactive login uses the public (no-secret)
# Keycloak client `dashboard`.
DEFAULT_CLIENT_ID = "dashboard"

# Service paths under the VPC host (after any UNITY_VPC_PATH_PREFIX).
#
# Pipeline Automation's API version varies by VPC bundle release —
# verified live: newer deployments serve public-parity
# `api/automation/v1`, while older ones serve `api/automation/v1alpha1`
# (verified live on a different bundle).
# With no explicit UNITY_VPC_AUTOMATION_PATH, callers should try
# the candidates in order (see automation_service_paths); the two are
# distinguishable because a wrong version gets a gateway-level plain-text 404
# instead of an API JSON error. Asset Manager answers at both `assets/v1` and
# `api/assets/v1`; the shorter form is the default. All overridable per
# deployment.
DEFAULT_AUTOMATION_PATH = "api/automation/v1"
LEGACY_AUTOMATION_PATH = "api/automation/v1alpha1"
DEFAULT_ASSETS_PATH = "assets/v1"


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _clean(value: str | None) -> str:
    return (value or "").strip()


def vpc_fqdn(env: Mapping[str, str] | None = None) -> str:
    """The configured private-cloud host, normalized to a bare FQDN.

    Lenient about the value users paste in: a scheme prefix and trailing
    slashes are stripped. Blank means standard/public Unity Cloud."""
    raw = _clean(_env(env).get(ENV_FQDN))
    lowered = raw.lower()
    for scheme in ("https://", "http://"):
        if lowered.startswith(scheme):
            raw = raw[len(scheme):]
            break
    return raw.strip().strip("/")


def is_vpc(env: Mapping[str, str] | None = None) -> bool:
    """True when a private-cloud FQDN is configured."""
    return bool(vpc_fqdn(env))


def path_prefix(env: Mapping[str, str] | None = None) -> str:
    """The optional VPC path prefix, normalized to '' or '/prefix' (single
    leading slash, no trailing slash) regardless of how it was written."""
    raw = _clean(_env(env).get(ENV_PATH_PREFIX)).strip("/")
    return f"/{raw}" if raw else ""


def client_id(env: Mapping[str, str] | None = None) -> str:
    """The OIDC public client id used for the VPC browser login."""
    return _clean(_env(env).get(ENV_CLIENT_ID)) or DEFAULT_CLIENT_ID


def openid_config_url(env: Mapping[str, str] | None = None) -> str:
    """The OIDC discovery URL for the VPC's embedded Keycloak.

    An explicit UNITY_VPC_OPENID_CONFIG_URL wins; otherwise derive the
    standard location per Unity VPC deployment docs (realm ``unity``).
    The derived form is verified live. Empty string when
    not in VPC mode and no explicit URL is set."""
    e = _env(env)
    explicit = _clean(e.get(ENV_OPENID_CONFIG_URL))
    if explicit:
        return explicit
    fqdn = vpc_fqdn(e)
    if not fqdn:
        return ""
    return f"https://{fqdn}/auth/realms/unity/.well-known/openid-configuration"


def automation_service_path(env: Mapping[str, str] | None = None) -> str:
    """The preferred Pipeline Automation service path on the VPC host,
    normalized to a single leading slash (default ``/api/automation/v1``)."""
    return automation_service_paths(env)[0]


def automation_service_paths(env: Mapping[str, str] | None = None) -> list[str]:
    """Candidate Pipeline Automation service paths, in preference order.

    An explicit UNITY_VPC_AUTOMATION_PATH is authoritative (single
    candidate); otherwise public-parity ``v1`` first, then the older
    bundles' ``v1alpha1``."""
    raw = _clean(_env(env).get(ENV_AUTOMATION_PATH)).strip("/")
    if raw:
        return [f"/{raw}"]
    return [f"/{DEFAULT_AUTOMATION_PATH}", f"/{LEGACY_AUTOMATION_PATH}"]


def assets_service_path(env: Mapping[str, str] | None = None) -> str:
    """The Asset Manager service path on the VPC host, normalized to a single
    leading slash (default ``/assets/v1``)."""
    raw = _clean(_env(env).get(ENV_ASSETS_PATH)).strip("/") or DEFAULT_ASSETS_PATH
    return f"/{raw}"


def api_base(
    public_default: str,
    vpc_service_path: str,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return the API base URL for the current deployment.

    Public cloud (UNITY_VPC_FQDN blank): returns ``public_default``
    byte-identical — zero behavior change.

    VPC: rebases onto ``https://{fqdn}{path_prefix}{vpc_service_path}``
    per Unity VPC deployment docs (same endpoint paths, different host and
    optional prefix)."""
    e = _env(env)
    fqdn = vpc_fqdn(e)
    if not fqdn:
        return public_default
    service = _clean(vpc_service_path).strip("/")
    suffix = f"/{service}" if service else ""
    return f"https://{fqdn}{path_prefix(e)}{suffix}"
