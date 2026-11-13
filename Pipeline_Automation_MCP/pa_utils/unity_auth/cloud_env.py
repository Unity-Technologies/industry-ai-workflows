"""
Unity Cloud environment selection (production / staging)
========================================================

Public Unity Cloud runs as two environments that serve identical routes from
different hosts. Production is the default; staging is opt-in for testing
against Unity's pre-release services:

    role         production                       staging
    services     services.api.unity.com           staging.services.api.unity.com
    automation   automation.services.api.unity.com automation.staging.services.api.unity.com
    genesis      api.unity.com                    api-staging.unity.com
    gateway      services.unity.com               staging.services.unity.com
    dashboard    cloud.unity.com                  staging.cloud.unity.com

Unlike private cloud (see the vpc module beside this one), staging uses the same
sign-in flow as production — the Unity ID login proxied through app-linking,
then the Genesis -> Services token exchange — so only the hosts change.
Unauthenticated probes on 2026-10-09 got the same status from staging as from
production for the authorize, app-linking, Assets, Automation and gateway
routes; a signed-in end-to-end run has not been done yet.

A private cloud deployment (UNITY_VPC_FQDN) takes precedence: its hosts come
from the deployment, and this setting is ignored.

Env vars:
    UNITY_CLOUD_ENV   ``production`` (default; blank, ``prod`` also accepted)
                      or ``staging`` (``stg`` also accepted). Anything else is
                      refused rather than silently falling back to production,
                      so a typo can never send staging work to production.
"""

from __future__ import annotations

import os
from typing import Mapping

ENV_CLOUD_ENV = "UNITY_CLOUD_ENV"

PRODUCTION = "production"
STAGING = "staging"

_ALIASES = {
    "": PRODUCTION,
    "prod": PRODUCTION,
    "production": PRODUCTION,
    "stg": STAGING,
    "staging": STAGING,
}

# Host for each role, per environment. Every Unity-bound URL in this package is
# built from one of these, so adding an environment is a single new column.
_HOSTS: dict[str, dict[str, str]] = {
    PRODUCTION: {
        "services": "services.api.unity.com",
        "automation": "automation.services.api.unity.com",
        "genesis": "api.unity.com",
        "gateway": "services.unity.com",
        "dashboard": "cloud.unity.com",
    },
    STAGING: {
        "services": "staging.services.api.unity.com",
        "automation": "automation.staging.services.api.unity.com",
        "genesis": "api-staging.unity.com",
        "gateway": "staging.services.unity.com",
        "dashboard": "staging.cloud.unity.com",
    },
}


class UnknownCloudEnvironment(ValueError):
    """UNITY_CLOUD_ENV holds a value that names no known environment."""


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def cloud_env(env: Mapping[str, str] | None = None) -> str:
    """The selected environment: ``production`` (default) or ``staging``."""
    raw = (_env(env).get(ENV_CLOUD_ENV) or "").strip().lower()
    try:
        return _ALIASES[raw]
    except KeyError:
        raise UnknownCloudEnvironment(
            f"{ENV_CLOUD_ENV}={raw!r} is not a Unity Cloud environment. "
            f"Use 'production' (or leave it blank) or 'staging'."
        ) from None


def is_staging(env: Mapping[str, str] | None = None) -> bool:
    return cloud_env(env) == STAGING


def host(role: str, env: Mapping[str, str] | None = None) -> str:
    """The bare host serving ``role`` in the selected environment."""
    return _HOSTS[cloud_env(env)][role]


def url(role: str, path: str = "", env: Mapping[str, str] | None = None) -> str:
    """``https://<host for role><path>`` in the selected environment."""
    return f"https://{host(role, env)}{path}"
