"""
am_rest.py — REST client for Unity Asset Manager API.

All functions take a requests.Session as their first argument.
Auth is handled externally by am_init.get_session().
"""

from __future__ import annotations

import sys

import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# The shared VPC config module lives at the repo root (two levels up).
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.local_paths import assert_safe_local_path  # noqa: E402
from shared.unity_auth import vpc as _vpc  # noqa: E402
from shared.version import attribution_headers  # noqa: E402

from .signed_urls import open_transfer_session

# ---------------------------------------------------------------------------
# Base URLs
# ---------------------------------------------------------------------------

# On a private-cloud (VPC) deployment the same endpoint paths are served from
# the customer's host: https://{fqdn}{path_prefix}/assets/v1/... Public cloud
# is unchanged when UNITY_VPC_FQDN is unset.
_AM_BASE = _vpc.api_base(
    "https://services.api.unity.com/assets/v1",
    _vpc.assets_service_path().lstrip("/"),
)

# The dashboard entities gateway is a public-cloud-only service (it backs
# project archive/delete). Private cloud deployments manage projects through
# their own identity and org services instead, so this stays pinned to the
# public host and its callers refuse to run in VPC mode.
_USER_BASE = "https://services.unity.com"

# ---------------------------------------------------------------------------
# Timeouts and retries
# ---------------------------------------------------------------------------

# (connect, read) timeouts in seconds. Every REST call sets a timeout so a
# stalled connection can never hang the stdio MCP server indefinitely.
DEFAULT_TIMEOUT = (10, 120)
# Larger read timeout for bulk file byte transfer to/from signed blob URLs.
TRANSFER_TIMEOUT = (10, 600)

_RETRY_STATUSES = (429, 502, 503, 504)


def _mount_retries(session: requests.Session) -> None:
    """Mount a retry adapter on the session (idempotent).

    Automatic retries are restricted to idempotent GET/HEAD requests that fail
    with 429/502/503/504. Connection errors are retried for all methods because
    they occur before the request ever reaches the server. Non-idempotent
    POST/PUT/PATCH/DELETE responses are never retried.
    """
    if getattr(session, "_uap_retries_mounted", False):
        return
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=_RETRY_STATUSES,
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session._uap_retries_mounted = True  # type: ignore[attr-defined]


def _get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    _mount_retries(session)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return session.get(url, **kwargs)


def _post(session: requests.Session, url: str, **kwargs) -> requests.Response:
    _mount_retries(session)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return session.post(url, **kwargs)


def _patch(session: requests.Session, url: str, **kwargs) -> requests.Response:
    _mount_retries(session)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return session.patch(url, **kwargs)


def _put(session: requests.Session, url: str, **kwargs) -> requests.Response:
    _mount_retries(session)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return session.put(url, **kwargs)


def _delete(session: requests.Session, url: str, **kwargs) -> requests.Response:
    _mount_retries(session)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    return session.delete(url, **kwargs)


def _proj(project_id: str, *parts: str) -> str:
    base = f"{_AM_BASE}/projects/{project_id}"
    if parts:
        return base + "/" + "/".join(parts)
    return base


def _org(org_id: str, *parts: str) -> str:
    base = f"{_AM_BASE}/organizations/{org_id}"
    if parts:
        return base + "/" + "/".join(parts)
    return base


def _raise(resp: requests.Response) -> None:
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code} {resp.reason} — {detail}")


class FileHasNoBytes(RuntimeError):
    """A file entry exists but its upload never completed, so there is nothing to download.

    Distinct from a missing file: the asset, version, dataset and entry are all present. See
    download_file() and CloudFile.has_bytes.
    """


class SilentlyIgnoredFilter(ValueError):
    """A search filter key the API accepts and then ignores.

    Worse than a rejected one: the response is a 200 containing everything, so a caller that
    trusts it treats the whole project as a filtered result.
    """


# ---------------------------------------------------------------------------
# Return types — mirror the SDK object attribute interface so am_mcp_server.py
# can access .name, .id, .version, .is_frozen, etc. without changing call sites.
# ---------------------------------------------------------------------------

@dataclass
class Asset:
    name: str
    id: str
    version: str
    is_frozen: bool
    status: str = ""
    primary_type: str = ""
    description: str = ""
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    version_number: int = -1
    change_log: str = ""
    created: str = ""
    created_by: str = ""
    updated: str = ""
    updated_by: str = ""
    preview_file_url: str = ""
    status_flow_name: str = ""
    source_project_id: str = ""
    project_ids: list = field(default_factory=list)
    parent_frozen_sequence_number: int = -1
    frozen_sequence_number: int = -1


@dataclass
class FieldDefinition:
    key: str
    display_name: str
    field_type: str  # TEXT, NUMBER, BOOLEAN, SELECTION, TIMESTAMP, URL, USER
    accepted_values: list = field(default_factory=list)
    multiselection: bool = False
    status: str = ""  # Active | Deleted — deleted definitions may linger in lists


@dataclass
class Collection:
    name: str
    path: str
    description: str = ""


@dataclass
class Dataset:
    id: str
    name: str = ""
    dataset_type: str = ""


@dataclass
class CloudFile:
    id: str
    path: str
    size: int = 0
    description: str = ""
    tags: list = field(default_factory=list)
    user_checksum: str = ""
    # "Uploaded" = bytes are in storage; "Draft" = only the file ENTRY exists (step 1 of
    # the 3-step upload, abandoned). verified live: the two are
    # indistinguishable in a listing and in the dashboard, and a download-URL request for a
    # Draft file is 404/40242. See has_bytes.
    status: str = ""

    @property
    def has_bytes(self) -> bool:
        """True only when the file is known to be downloadable.

        Fails CLOSED on a missing/unknown status: an absent field is not evidence of
        uploaded bytes, and the cost of being wrong is a 404 mid-loop.
        """
        return self.status == "Uploaded"


@dataclass
class AssetReference:
    id: str
    is_valid: bool
    source_asset_id: str
    source_asset_version: str
    target_asset_id: str
    target_asset_version: str
    target_asset_label: str
    dependency_type: str = ""
    relative_path: str = ""
    metadata: dict = field(default_factory=dict)
    reference_type: str = ""


@dataclass
class Organization:
    id: str        # UUID — use for AM asset/collection endpoints
    name: str
    genesis_id: str = ""  # numeric string — use for list_projects


@dataclass
class Project:
    id: str
    name: str


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_asset(data: dict) -> Asset:
    return Asset(
        name=data.get("name", ""),
        id=data.get("assetId", data.get("id", "")),
        version=data.get("assetVersion", data.get("version", "")),
        is_frozen=data.get("isFrozen", False),
        status=data.get("status", ""),
        primary_type=data.get("primaryType", ""),
        description=data.get("description", "") or "",
        tags=data.get("tags", []),
        metadata=data.get("metadata", {}),
        version_number=int(data.get("versionNumber", -1) or -1),
        change_log=data.get("changeLog", "") or "",
        created=str(data.get("created", "") or ""),
        created_by=str(data.get("createdBy", "") or ""),
        updated=str(data.get("updated", "") or ""),
        updated_by=str(data.get("updatedBy", "") or ""),
        preview_file_url=data.get("previewFileUrl", "") or "",
        status_flow_name=data.get("statusFlowName", "") or "",
        source_project_id=data.get("sourceProjectId", "") or "",
        project_ids=data.get("projectIds", []) or [],
        parent_frozen_sequence_number=int(data.get("parentFrozenSequenceNumber", -1) or -1),
        frozen_sequence_number=int(data.get("frozenSequenceNumber", -1) or -1),
    )


def _parse_field_definition(data: dict) -> FieldDefinition:
    raw_type = data.get("type", data.get("fieldType", ""))
    return FieldDefinition(
        key=data.get("name", data.get("key", "")),
        display_name=data.get("displayName", data.get("display_name", "")),
        field_type=raw_type.upper() if raw_type else "",
        accepted_values=data.get("acceptedValues", data.get("accepted_values", [])) or [],
        # verified live: the API returns camelCase "multiSelection";
        # the old lowercase read meant every field parsed as single-select.
        multiselection=data.get("multiSelection", data.get("multiselection", False)),
        status=data.get("status", ""),
    )


def _parse_reference(data: dict) -> AssetReference:
    source = data.get("source", {})
    target = data.get("target", {})
    return AssetReference(
        id=data.get("referenceId", data.get("id", "")),
        is_valid=data.get("isValid", True),
        source_asset_id=source.get("assetId", data.get("sourceAssetId", "")),
        source_asset_version=source.get("assetVersion", data.get("sourceAssetVersion", "")),
        target_asset_id=target.get("assetId", data.get("targetAssetId", "")),
        target_asset_version=target.get("assetVersion", data.get("targetAssetVersion", "")),
        target_asset_label=target.get("labelName", data.get("targetAssetLabel", "")),
        dependency_type=data.get("dependencyType", ""),
        relative_path=data.get("relativePath", "") or "",
        metadata=data.get("metadata", {}) or {},
        reference_type=data.get("type", "") or "",
    )


# ---------------------------------------------------------------------------
# Search filters
#
# Three behaviours here are silent or misleading, all verified live
# against the live API. They are checked rather than documented because two of
# the three produce a 200.
# ---------------------------------------------------------------------------

# Keys the API accepts at the top level of a search body and then does nothing with. A
# `collectionPath` here returns 200 with EVERY asset in the project — not filtered, not an
# error — so a caller that trusts it reads the whole project as one collection's contents.
# There is no read-membership endpoint; keep collection membership in your own metadata.
_SILENTLY_IGNORED_FILTER_KEYS = frozenset({"collectionPath", "collectionPaths", "collection"})

# `wildcard` works on `name` and `tags` but is a 400 on any `metadata.<key>`. `prefix` works
# everywhere. Criterion support is per-field, and the API documents no such distinction.
_NO_WILDCARD_PREFIX = "metadata."


def _validate_search_filter(metadata_filter: dict[str, Any] | None) -> None:
    """Reject filter shapes the API mishandles, before they cost anyone a debugging session.

    ⚠️ Also worth knowing and NOT checkable here: criteria inside a single `includeQuery`
    combine with **AND, not OR**. A lookup written as "match the GUID or fall back to the
    path" silently returns nothing exactly when the two disagree — the case it was written
    for. Use separate calls for a union.
    """
    if not metadata_filter:
        return

    # Callers pass either bare criteria or a pre-wrapped {include,exclude}Query —
    # both produce the SAME wire request, so both guards must look inside the
    # wrappers AND at the top level, unconditionally. (A bare criterion sitting
    # next to an explicit includeQuery still gets sent; it must still be checked.)
    scopes = [metadata_filter] + [
        q for q in (metadata_filter.get("includeQuery"), metadata_filter.get("excludeQuery"))
        if isinstance(q, dict)
    ]
    for scope in scopes:
        ignored = _SILENTLY_IGNORED_FILTER_KEYS & set(scope)
        if ignored:
            raise SilentlyIgnoredFilter(
                f"Search filter key(s) {sorted(ignored)} are accepted by the API and then ignored: "
                f"the response is a 200 containing every asset in the project. There is no "
                f"read-membership endpoint for collections — record membership in asset metadata "
                f"and filter on that instead."
            )
        for key, criterion in scope.items():
            if not isinstance(criterion, dict):
                continue
            if key.startswith(_NO_WILDCARD_PREFIX) and criterion.get("type") == "wildcard":
                raise ValueError(
                    f"'wildcard' is not supported on {key!r} — the API returns 400. It works "
                    f"on 'name' and 'tags' only; criterion support is per-field. Use "
                    f"{{'type': 'prefix', ...}}, which works everywhere."
                )


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

def list_assets(
    session: requests.Session,
    org_id: str,
    project_id: str,
    metadata_filter: dict[str, Any] | None = None,
) -> list[Asset]:
    _validate_search_filter(metadata_filter)
    url = _proj(project_id, "assets", "search")
    results: list[Asset] = []
    pagination_token: str | None = None
    while True:
        pagination: dict[str, Any] = {"sortingField": "name", "limit": 100}
        if pagination_token:
            pagination["token"] = pagination_token
        body: dict[str, Any] = {
            "pagination": pagination,
            "includeFields": ["isFrozen", "status", "name", "description", "primaryType", "tags", "metadata"],
        }
        if metadata_filter:
            # The search endpoint expects criteria under filter.includeQuery
            # (see assets.AssetReadFilter in the Assets API spec). Wrap bare
            # criteria dicts so callers can pass e.g. {"name": {...}} directly.
            if "includeQuery" in metadata_filter or "excludeQuery" in metadata_filter:
                body["filter"] = metadata_filter
            else:
                body["filter"] = {"includeQuery": metadata_filter}
        resp = _post(session, url, json=body)
        _raise(resp)
        data = resp.json()
        items = data.get("assets", []) or []
        results.extend(_parse_asset(a) for a in items)
        pagination_token = data.get("next")
        if not pagination_token:
            break
    return results


def search_assets_by_name(session: requests.Session, org_id: str, project_id: str, name: str) -> Asset | None:
    """Return the best matching asset for a given name, preferring unfrozen drafts.

    Uses the search endpoint's server-side name criterion (exact, case-sensitive
    match — verified live: against the Assets API) so the lookup is
    O(1) requests instead of paging through every asset in the project.
    """
    name_filter = {
        "name": {"type": "exact-match", "value": name, "caseInsensitive": False},
    }
    assets = list_assets(session, org_id, project_id, metadata_filter=name_filter)
    # Re-check client-side to guarantee exact-match semantics stay identical
    # even if the server-side criterion behaviour ever changes.
    matches = [a for a in assets if a.name == name]
    if not matches:
        return None

    unfrozen = [a for a in matches if not a.is_frozen]
    frozen = [a for a in matches if a.is_frozen]
    if unfrozen:
        return unfrozen[-1]
    if frozen:
        return frozen[-1]
    return matches[-1]


def find_asset_by_id(session: requests.Session, org_id: str, project_id: str, asset_id: str) -> Asset | None:
    """Locate an asset by id via a server-side search (latest/pending versions only).

    Returns the first matching version (same ordering as list_assets) or None.
    """
    assets = list_assets(session, org_id, project_id, metadata_filter={"assetId": asset_id})
    return next((a for a in assets if a.id == asset_id), None)


# The GET asset-version endpoint returns on-demand fields ONLY when asked for
# via IncludeFields; without it the response omits description, changeLog, etc.
_GET_ASSET_INCLUDE_FIELDS = [
    "name", "description", "primaryType", "status", "isFrozen", "tags", "metadata",
    "versionNumber", "changeLog", "created", "createdBy", "updated", "updatedBy",
    "previewFileUrl", "statusFlowName", "frozenSequenceNumber", "parentFrozenSequenceNumber",
]


def get_asset(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str) -> Asset:
    url = _proj(project_id, "assets", asset_id, "versions", asset_version)
    resp = _get(session, url, params={"IncludeFields": _GET_ASSET_INCLUDE_FIELDS})
    _raise(resp)
    return _parse_asset(resp.json())


# ---------------------------------------------------------------------------
# Asset typing
# ---------------------------------------------------------------------------

# The real `primaryType` enum — verified live: probed value-by-value
# against the live API. Values confirmed REJECTED, so do not add them back on a
# hunch: "Model", "Mesh", "Texture", "Configuration", "Unity Scene", "Terrain",
# "Physics".
PRIMARY_TYPES: tuple[str, ...] = (
    "2D Asset",
    "3D Model",
    "Animation",
    "Asset",
    "Audio",
    "Document",
    "Environment",
    "Font",
    "Image",
    "Material",
    "Other",
    "Prefab",
    "Scene",
    "Script",
    "Shader",
    "Unity Editor",
    "Unity Package",
    "Video",
)

# Callers (and this server's own tool signatures) have always used unspaced names
# like "3DModel". Those are not valid API values, so they are mapped rather than
# rejected — otherwise fixing the bug would break every existing caller.
_PRIMARY_TYPE_ALIASES: dict[str, str] = {
    _key.replace(" ", "").lower(): _key for _key in PRIMARY_TYPES
}


def normalise_primary_type(value: str) -> str:
    """Map any accepted spelling onto a valid `primaryType`.

    Accepts the real spaced values ("3D Model") and the legacy unspaced ones
    ("3DModel", "2DAsset", "UnityEditor"), case-insensitively. Falls back to
    "Other" for anything unrecognised: a 400 from the create call is a worse
    outcome than an imprecise-but-visible type, and the caller's asset still
    lands.
    """
    if not value:
        return "Other"
    return _PRIMARY_TYPE_ALIASES.get(value.replace(" ", "").lower(), "Other")


def create_asset(
    session: requests.Session,
    org_id: str,
    project_id: str,
    name: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    asset_type: str = "3D Model",
    description: str = "",
    collections: list[str] | None = None,
    status_flow_id: str = "",
) -> Asset:
    """Create an asset.

    verified live: the API silently ignores a `type` field — the real
    field is `primaryType`, and it only accepts the spaced enum in PRIMARY_TYPES.
    Callers may still pass legacy unspaced names; they are normalised here.

    collections links the asset at create time (saves a separate call);
    status_flow_id assigns a status flow to the first version.
    """
    url = _proj(project_id, "assets")
    body: dict[str, Any] = {
        "name": name,
        # primaryType, NOT type — see the docstring above.
        "primaryType": normalise_primary_type(asset_type),
        "description": description,
        "tags": tags or [],
    }
    if collections:
        body["collections"] = collections
    if status_flow_id:
        body["statusFlowId"] = status_flow_id
    if metadata:
        body["metadata"] = metadata
    resp = _post(session, url, json=body)
    _raise(resp)
    return _parse_asset(resp.json())


def set_primary_type(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    asset_type: str,
) -> None:
    """Set `primaryType` on an UNFROZEN version.

    primaryType is set at create time and inherited by new versions, so a
    wrongly-typed asset keeps its type until something patches it here. A frozen
    version rejects the PATCH.
    """
    url = _proj(project_id, "assets", asset_id, "versions", asset_version)
    resp = _patch(session, url, json={"primaryType": normalise_primary_type(asset_type)})
    _raise(resp)


def freeze_asset_version(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    change_log: str = "",
    force: bool = True,
) -> None:
    """Submit (freeze) an asset version.

    force=True (forceFreeze) freezes immediately, cancelling any running
    transformations; force=False waits for them. change_log is recorded on the
    frozen version and shown in the dashboard's version history.
    """
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "submit")
    body: dict[str, Any] = {"forceFreeze": force}
    if change_log:
        body["changeLog"] = change_log
    resp = _post(session, url, json=body)
    _raise(resp)


def create_unfrozen_asset_version(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str, status_flow_id: str = "") -> Asset:
    url = _proj(project_id, "assets", asset_id, "versions")
    body: dict[str, Any] = {"parentAssetVersion": asset_version}
    if status_flow_id:
        body["statusFlowId"] = status_flow_id
    resp = _post(session, url, json=body)
    _raise(resp)
    data = resp.json()
    # Response only contains assetVersion (not assetId); inherit from parent
    if "assetId" not in data:
        data["assetId"] = asset_id
    return _parse_asset(data)


def delete_asset(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str) -> bool:
    """Delete a specific unfrozen asset version."""
    url = _proj(project_id, "assets", asset_id, "versions", asset_version)
    resp = _delete(session, url)
    _raise(resp)
    return True


def unlink_asset_from_project(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    trash: bool = False,
) -> bool:
    """Remove an asset and ALL its versions from a project.

    This is the correct way to delete an entire asset.
    Pass trash=True to soft-delete (recoverable); default is hard-delete.
    """
    url = _proj(project_id, "assets", asset_id, "unlink")
    params = {"trash": "true"} if trash else {}
    resp = _post(session, url, params=params)
    _raise(resp)
    return True


def update_asset(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    preview_file_path: str | None = None,
    update_even_if_frozen: bool = False,
) -> Asset:
    """Update mutable fields (name, description, tags, cover image) on an asset version.

    preview_file_path designates an already-uploaded file (by its in-asset path)
    as the asset's cover image. update_even_if_frozen allows editing a frozen
    version (the API supports it via a query flag; default off).
    """
    url = _proj(project_id, "assets", asset_id, "versions", asset_version)
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if tags is not None:
        body["tags"] = tags
    if preview_file_path is not None:
        body["previewFilePath"] = preview_file_path
    params = {"updateEvenIfFrozen": "true"} if update_even_if_frozen else None
    resp = _patch(session, url, params=params, json=body)
    _raise(resp)
    # PATCH returns 204 No Content on success; fetch the updated asset
    return get_asset(session, org_id, project_id, asset_id, asset_version)


def get_asset_reachable_statuses(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str) -> list[str]:
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "status", "reachable")
    resp = _get(session, url)
    _raise(resp)
    data = resp.json()
    if isinstance(data, list):
        return data
    return data.get("reachableStatuses", data.get("statuses", []))


def update_asset_status(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str, status: str) -> bool:
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "status", status)
    resp = _patch(session, url)
    _raise(resp)
    return True


# ---------------------------------------------------------------------------
# Status flows
# ---------------------------------------------------------------------------

def list_status_flows(session: requests.Session, org_id: str) -> list[dict]:
    """List the status flows defined in an organization (raw dicts)."""
    url = _org(org_id, "status")
    resp = _get(session, url)
    _raise(resp)
    data = resp.json()
    items = data.get("statusFlows", data.get("results", data)) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def assign_status_flow(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str, status_flow_id: str) -> None:
    """Assign a status flow to an (unfrozen) asset version."""
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "statusflows", status_flow_id, "assign")
    resp = _post(session, url)
    _raise(resp)


# ---------------------------------------------------------------------------
# Version listing, bulk reads, aggregations
# ---------------------------------------------------------------------------

def list_asset_versions(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
) -> list[Asset]:
    """List ALL versions of an asset via versions/search.

    Asset search returns only Latest/Pending-labelled versions; this endpoint
    is the way to enumerate older frozen versions.
    """
    url = _proj(project_id, "assets", asset_id, "versions", "search")
    results: list[Asset] = []
    pagination_token: str | None = None
    while True:
        pagination: dict[str, Any] = {"sortingField": "versionNumber", "limit": 100}
        if pagination_token:
            pagination["token"] = pagination_token
        body: dict[str, Any] = {
            "pagination": pagination,
            "includeFields": [
                "isFrozen", "status", "name", "description", "primaryType",
                "tags", "metadata", "versionNumber", "changeLog",
            ],
        }
        resp = _post(session, url, json=body)
        _raise(resp)
        data = resp.json()
        items = data.get("assets", data.get("results", [])) or []
        results.extend(_parse_asset(a) for a in items)
        pagination_token = data.get("next")
        if not pagination_token:
            break
    return results


def search_assets_across_projects(
    session: requests.Session,
    org_id: str,
    project_ids: list[str] | None = None,
    metadata_filter: dict[str, Any] | None = None,
) -> list[Asset]:
    """Search assets across all (or selected) projects in the organization.

    org_id must be the numeric genesis id (org-level Assets route). Results
    carry source_project_id / project_ids so callers can tell where each asset
    lives. project_ids=None searches every project the user can access.
    """
    _validate_search_filter(metadata_filter)
    url = _org(org_id, "assets", "search")
    results: list[Asset] = []
    pagination_token: str | None = None
    while True:
        pagination: dict[str, Any] = {"sortingField": "name", "limit": 100}
        if pagination_token:
            pagination["token"] = pagination_token
        body: dict[str, Any] = {
            "pagination": pagination,
            "includeFields": [
                "isFrozen", "status", "name", "description", "primaryType",
                "tags", "metadata", "sourceProjectId", "projectIds",
            ],
        }
        if project_ids:
            body["projectIds"] = project_ids
        if metadata_filter:
            if "includeQuery" in metadata_filter or "excludeQuery" in metadata_filter:
                body["filter"] = metadata_filter
            else:
                body["filter"] = {"includeQuery": metadata_filter}
        resp = _post(session, url, json=body)
        _raise(resp)
        data = resp.json()
        items = data.get("assets", data.get("results", [])) or []
        results.extend(_parse_asset(a) for a in items)
        pagination_token = data.get("next")
        if not pagination_token:
            break
    return results


def get_bulk_assets(
    session: requests.Session,
    org_id: str,
    project_id: str,
    assets: list[dict],
    include_fields: list[str] | None = None,
) -> list[Asset]:
    """Bulk-hydrate assets in one call. Each entry: {"assetId": ..., "assetVersion": ...}."""
    url = _proj(project_id, "assets", "batch", "get")
    body: dict[str, Any] = {"assets": assets}
    if include_fields:
        body["includeFields"] = include_fields
    resp = _post(session, url, json=body)
    _raise(resp)
    data = resp.json()
    items = data.get("assets", data.get("results", [])) or []
    return [_parse_asset(a) for a in items]


def search_asset_aggregations(
    session: requests.Session,
    org_id: str,
    project_id: str,
    aggregate_by: str | list[str],
    metadata_filter: dict[str, Any] | None = None,
    max_items: int | None = None,
) -> list[dict]:
    """Group assets by a field and return {value, count} buckets (facet counts).

    aggregate_by examples: name, tags, labels, status, primaryType,
    metadata.{FIELD_NAME}, files.filePath.
    """
    _validate_search_filter(metadata_filter)
    url = _proj(project_id, "assets", "aggregations", "search")
    body: dict[str, Any] = {"aggregateBy": aggregate_by}
    if metadata_filter:
        if "includeQuery" in metadata_filter or "excludeQuery" in metadata_filter:
            body["filter"] = metadata_filter
        else:
            body["filter"] = {"includeQuery": metadata_filter}
    if max_items is not None:
        body["maximumNumberOfItems"] = max_items
    resp = _post(session, url, json=body)
    _raise(resp)
    data = resp.json()
    return data.get("aggregations", []) or []


# ---------------------------------------------------------------------------
# Trash and cross-project linking
# ---------------------------------------------------------------------------

def list_trashed_assets(session: requests.Session, org_id: str, project_id: str) -> list[Asset]:
    """Search the project's trash can (soft-deleted assets)."""
    url = _proj(project_id, "trash", "assets", "search")
    results: list[Asset] = []
    pagination_token: str | None = None
    while True:
        pagination: dict[str, Any] = {"sortingField": "name", "limit": 100}
        if pagination_token:
            pagination["token"] = pagination_token
        body: dict[str, Any] = {
            "pagination": pagination,
            "includeFields": ["isFrozen", "status", "name", "description", "primaryType", "tags"],
        }
        resp = _post(session, url, json=body)
        _raise(resp)
        data = resp.json()
        items = data.get("assets", data.get("results", [])) or []
        results.extend(_parse_asset(a) for a in items)
        pagination_token = data.get("next")
        if not pagination_token:
            break
    return results


def restore_assets(session: requests.Session, org_id: str, project_id: str, asset_ids: list[str]) -> None:
    """Restore trashed assets back into the project they were removed from."""
    url = _proj(project_id, "assets", "restore")
    resp = _post(session, url, json={"assetIds": asset_ids})
    _raise(resp)


def delete_assets_from_trash(session: requests.Session, org_id: str, project_id: str, asset_ids: list[str]) -> None:
    """PERMANENTLY delete specific assets from the trash can. Irreversible."""
    url = _proj(project_id, "trash", "assets")
    resp = _delete(session, url, json={"assetIds": asset_ids})
    _raise(resp)


def link_asset_to_project(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    destination_project_id: str,
    link_referenced_assets: bool | None = None,
) -> dict | None:
    """Link (share) an asset into another project in the same organization.

    With link_referenced_assets set, recursively-referenced assets are linked
    too and the API returns a detail structure (200); omitted, success is a
    bodyless 204 and this returns None.
    """
    url = _proj(project_id, "assets", asset_id, "link", "projects", destination_project_id)
    params = None
    if link_referenced_assets is not None:
        params = {"linkReferencedAssets": "true" if link_referenced_assets else "false"}
    resp = _post(session, url, params=params)
    _raise(resp)
    if resp.status_code == 200 and resp.content:
        return resp.json()
    return None


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def get_dataset_list(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str) -> list[Dataset]:
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "datasets")
    resp = _get(session, url)
    _raise(resp)
    data = resp.json()
    items = data.get("results", data.get("datasets", data)) if isinstance(data, dict) else data
    if not isinstance(items, list):
        items = []
    return [
        Dataset(
            id=d.get("datasetId", d.get("id", "")),
            name=d.get("name", ""),
            dataset_type=d.get("primaryType", d.get("datasetType", d.get("type", ""))),
        )
        for d in items
    ]


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def get_file_list(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str, dataset_id: str) -> list[CloudFile]:
    """List a dataset's files.

    ⚠️ Not every entry is downloadable — check `.has_bytes` before requesting a download URL.
    verified live: of three assets sharing one name in a small project, one had no
    files, one had a `Draft` file and only the third worked. Iterating a file list and fetching
    each entry blind WILL fail on real projects.

    ⚠️ Entries carry NO checksum of any kind (no md5, etag or sha) and `fileSize` is absent
    entirely on dashboard-uploaded files. Local/cloud equality is provable only from a hash the
    client recorded itself at push time.
    """
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "datasets", dataset_id, "files")
    results: list[CloudFile] = []
    token: str | None = None
    while True:
        params: dict[str, Any] = {"limit": 100}
        if token:
            params["token"] = token
        resp = _get(session, url, params=params)
        _raise(resp)
        data = resp.json()
        items = data.get("results", data.get("files", data)) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []
        results.extend(
            CloudFile(
                id=f.get("filePath", f.get("id", "")),
                path=f.get("filePath", f.get("path", f.get("name", ""))),
                size=f.get("fileSize", f.get("size", 0)),
                description=f.get("description", "") or "",
                tags=f.get("tags", []) or [],
                user_checksum=f.get("userChecksum", "") or "",
                status=f.get("status", "") or "",
            )
            for f in items
        )
        token = data.get("next") if isinstance(data, dict) else None
        if not token:
            break
    return results


def upload_file(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    dataset_id: str,
    local_path: str,
    remote_path: str = "",
    description: str = "",
    tags: list[str] | None = None,
) -> None:
    """Upload a local file using the 3-step signed-URL process.

    remote_path sets the in-asset file path (e.g. "textures/wood.png") so
    directory structure survives the upload; the default flattens to the local
    file's basename. description/tags are recorded on the file entry.
    """
    # The caller chose this path and we are about to read the file and PUT its bytes to
    # cloud storage, from which they can be downloaded again. This server has no code
    # execution of its own, so an agent talked into "back up ~/.ssh/id_rsa" is a real
    # escalation rather than a restatement of one — see shared/local_paths.py.
    local_path = assert_safe_local_path(local_path, purpose="upload", mode="read")
    file_path = Path(local_path)
    target_path = (remote_path or file_path.name).replace("\\", "/").lstrip("/")
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "datasets", dataset_id, "files")

    # Step 1: create file entry — returns signed upload URL
    body: dict[str, Any] = {"filePath": target_path, "fileSize": file_path.stat().st_size}
    if description:
        body["description"] = description
    if tags:
        body["tags"] = tags
    resp = _post(session, url, json=body)
    _raise(resp)
    data = resp.json()
    upload_url = data.get("uploadUrl", data.get("signedUploadUrl", ""))
    if not upload_url:
        raise RuntimeError(
            f"File-entry response for '{target_path}' contained no signed upload URL "
            f"(keys: {sorted(data.keys())}) — cannot upload."
        )

    # The API chose this URL and we are about to send the file's BYTES to it, so validate
    # it first: https only, no embedded credentials, no host resolving inside the network.
    # See signed_urls.py — this is the SSRF sink static analysis flags as High. The session
    # comes back pinned to the address that was validated, so the name cannot resolve
    # somewhere else between the check and the connection.
    upload_url, transfer = open_transfer_session(upload_url, purpose="upload")

    # Step 2: PUT bytes directly to the signed blob URL (no session auth headers).
    # verified live: the signed URLs front Azure Blob storage behind
    # a Unity CNAME, so the x-ms-blob-type header is required even though the
    # host isn't *.blob.core.windows.net.
    with transfer, open(local_path, "rb") as f:
        put_resp = transfer.put(
            upload_url,
            data=f,
            headers={"x-ms-blob-type": "BlockBlob", **attribution_headers()},
            timeout=TRANSFER_TIMEOUT,
            # A validated URL that redirects somewhere internal defeats the validation.
            allow_redirects=False,
        )
    _raise(put_resp)

    # Step 3: finalize — filePath URL-encoded in path
    encoded = urllib.parse.quote(target_path, safe="")
    finalize_url = _proj(
        project_id, "assets", asset_id, "versions", asset_version,
        "datasets", dataset_id, "files", encoded, "finalize"
    )
    final_resp = _post(session, finalize_url)
    _raise(final_resp)


def download_file(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    dataset_id: str,
    file_id: str,
    dest_path: str,
) -> None:
    """Obtain a signed download URL and stream the file to dest_path.

    Raises FileHasNoBytes when the file entry exists but its bytes never landed — see
    get_file_list().
    """
    # Downloaded bytes are attacker-influenced (anyone who can upload an asset picks
    # them), so where they land matters: a write into an auto-loaded location is a
    # persistence primitive. Checked before the request, not after — see
    # shared/local_paths.py.
    dest_path = assert_safe_local_path(dest_path, purpose="download", mode="write")

    encoded = urllib.parse.quote(file_id, safe="")
    url = _proj(
        project_id, "assets", asset_id, "versions", asset_version,
        "datasets", dataset_id, "files", encoded, "download-url"
    )
    resp = _get(session, url)
    # verified live: a `Draft` file — one whose entry was created but whose upload
    # never finished — answers with 404/40242 "Dataset does not exist in storage". That message
    # sends the reader after the dataset, which is present and fine. Translate it, because the
    # difference between "this file is missing" and "this file was never uploaded" decides
    # whether the caller should skip the entry or go looking for a bug.
    if resp.status_code == 404:
        try:
            error_code = str(resp.json().get("code", ""))
        except Exception:
            error_code = ""
    else:
        error_code = ""
    if error_code == "40242":
        raise FileHasNoBytes(
            f"File '{file_id}' has no bytes in storage — its entry exists but the upload was "
            f"never finalized (status 'Draft'). Check CloudFile.has_bytes before downloading. "
            f"The API reports this as 404/40242 'Dataset does not exist in storage', which is "
            f"misleading: the dataset is fine."
        )
    _raise(resp)
    data = resp.json()
    # Same SSRF sink as the upload — see signed_urls.py. `file://` here would read an
    # arbitrary local file and write it to disk as the asset's contents.
    download_url, transfer = open_transfer_session(
        data.get("url", data.get("downloadUrl", data.get("signedUrl", ""))),
        purpose="download",
    )

    with transfer, transfer.get(
        download_url, stream=True, timeout=TRANSFER_TIMEOUT,
        headers=attribution_headers(), allow_redirects=False,
    ) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

def list_collections(session: requests.Session, org_id: str, project_id: str) -> list[Collection]:
    """List every collection in the project, with `path` reconstructed client-side.

    verified live: the response carries **no `path` field** — each entry is only
    `{name, description, parentPath}` — so `path` below is computed, not read. Reading a
    `path` key straight off the response yields an empty set, every level then looks absent,
    and the subsequent create 409s on collections that were there all along.
    """
    url = _proj(project_id, "collections")
    result: list[Collection] = []
    offset, limit = 0, 100
    while True:
        resp = _get(session, url, params={"offset": offset, "limit": limit})
        _raise(resp)
        data = resp.json()
        items = data.get("collections", data.get("results", data)) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []
        for c in items:
            name = c.get("name", "")
            parent = c.get("parentPath", "")
            path = f"{parent}/{name}" if parent else name
            result.append(Collection(name=name, path=path, description=c.get("description", "") or ""))
        if len(items) < limit:
            break
        offset += limit
    return result


def create_collection(
    session: requests.Session,
    org_id: str,
    project_id: str,
    collection_name: str,
    parent_path: str = "",
    description: str = "",
    exists_ok: bool = True,
) -> bool:
    """Create one collection LEVEL. Returns True if it was created, False if it existed.

    verified live: a slash inside `name` is a `400 / 40403` — only `parentPath`
    may nest. Passing "Robot/Textures" here does not create a hierarchy, it fails, so the
    check below turns an opaque validation error into an instruction. Use
    ensure_collection_path() for a deep path. A BACKSLASH is a legal name character —
    verified live: the API answers 200 and records the literal name — so only
    "/" is refused here. (ensure_collection_path still normalizes "\\" to "/" as a
    Windows-path convenience; a literal-backslash name must go through this function.)

    verified live: creating a collection that already exists is `409 / 40413`.
    With exists_ok (the default) that is treated as success, which is what almost every
    caller wants: a push plans several assets against one snapshot of the hierarchy, so the
    same level is legitimately requested more than once inside a single operation.
    """
    if "/" in collection_name:
        raise ValueError(
            f"Collection name {collection_name!r} contains a path separator. The API rejects "
            f"this with 400/40403 — only parentPath may nest. Use "
            f"ensure_collection_path(session, org_id, project_id, {collection_name!r}) to "
            f"create each level in turn."
        )
    url = _proj(project_id, "collections")
    body = {
        "name": collection_name,
        "parentPath": parent_path,
        # verified live: the API rejects empty/whitespace
        # descriptions (40403 validation error) — fall back to the collection
        # name when none was supplied.
        "description": description.strip() or collection_name,
    }
    resp = _post(session, url, json=body)
    if exists_ok and resp.status_code == 409:
        return False
    _raise(resp)
    return True


def ensure_collection_path(session: requests.Session, org_id: str, project_id: str, collection_path: str) -> str:
    """Create every level of a nested collection path, idempotently. Returns the full path.

    Exists because the API offers no way to create a hierarchy in one call: `name` may not
    contain a separator, so "Robot/Textures" has to become two requests, each naming its
    parent. Safe to call repeatedly — existing levels 409 and are treated as present.
    """
    parts = [p for p in collection_path.replace("\\", "/").split("/") if p]
    built = ""
    for part in parts:
        create_collection(session, org_id, project_id, part, parent_path=built, exists_ok=True)
        built = f"{built}/{part}" if built else part
    return built


def update_collection(session: requests.Session, org_id: str, project_id: str, collection_path: str, name: str = "", description: str = "") -> None:
    """Rename and/or re-describe a collection ('%' is not allowed in names)."""
    encoded = urllib.parse.quote(collection_path, safe="")
    url = _proj(project_id, "collections", encoded)
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    resp = _patch(session, url, json=body)
    _raise(resp)


def move_collection(session: requests.Session, org_id: str, project_id: str, collection_path: str, destination_parent_path: str) -> str:
    """Move a collection under a new parent (same project only); returns the new path."""
    encoded = urllib.parse.quote(collection_path, safe="")
    url = _proj(project_id, "collections", encoded, "move")
    resp = _patch(session, url, json={"destinationParentPath": destination_parent_path})
    _raise(resp)
    try:
        return resp.json().get("path", "")
    except Exception:
        return ""


def delete_collection(session: requests.Session, org_id: str, project_id: str, collection_path: str) -> bool:
    encoded = urllib.parse.quote(collection_path, safe="")
    url = _proj(project_id, "collections", encoded)
    resp = _delete(session, url)
    _raise(resp)
    return True


def link_asset_to_collection(session: requests.Session, org_id: str, project_id: str, collection_path: str, asset_id: str) -> None:
    encoded = urllib.parse.quote(collection_path, safe="")
    url = _proj(project_id, "collections", encoded, "assets")
    resp = _post(session, url, json={"assetIds": [asset_id]})
    _raise(resp)


def unlink_asset_from_collection(session: requests.Session, org_id: str, project_id: str, collection_path: str, asset_id: str) -> None:
    """Remove an asset from a collection.

    ⚠️ **This is a PATCH, not a DELETE** — verified live. Link and unlink post the
    same body to the same URL and differ only by verb; a DELETE there is a 404, which reads
    like a missing collection rather than a wrong method. Do not "fix" this to a DELETE for
    symmetry with link_asset_to_collection.

    ⚠️ There is no read-membership endpoint, and the search index lags a membership change by
    ~2-3s. Never reconcile membership against a search result — you will unlink assets from
    collections they just joined. Track what you linked.
    """
    encoded = urllib.parse.quote(collection_path, safe="")
    url = _proj(project_id, "collections", encoded, "assets")
    resp = _patch(session, url, json={"assetIds": [asset_id]})
    _raise(resp)


# ---------------------------------------------------------------------------
# References — at asset level (no version in path)
# ---------------------------------------------------------------------------

def add_asset_reference(
    session: requests.Session,
    org_id: str,
    project_id: str,
    source_asset_id: str,
    source_asset_version: str,
    target_asset_id: str,
    target_asset_version: str = "",
    target_label: str = "",
    dependency_type: str = "",
    relative_path: str = "",
    metadata: dict | None = None,
) -> AssetReference:
    url = _proj(project_id, "assets", source_asset_id, "references")
    target: dict[str, Any] = {"assetId": target_asset_id}
    if target_asset_version:
        target["assetVersion"] = target_asset_version
    if target_label:
        target["labelName"] = target_label
    body: dict[str, Any] = {
        "assetVersion": source_asset_version,
        "target": target,
    }
    if dependency_type:
        body["dependencyType"] = dependency_type
    if relative_path:
        body["relativePath"] = relative_path
    if metadata:
        body["metadata"] = metadata
    resp = _post(session, url, json=body)
    _raise(resp)
    data = resp.json()
    ref_id = data.get("referenceId", data.get("id", ""))
    # The create response contains only referenceId; re-fetch the reference so
    # the returned isValid / relativePath / metadata are server truth rather
    # than an echo of the caller's inputs.
    if ref_id:
        for ref in list_asset_references(session, org_id, project_id, source_asset_id, source_asset_version):
            if ref.id == ref_id:
                return ref
    return AssetReference(
        id=ref_id,
        is_valid=True,
        source_asset_id=source_asset_id,
        source_asset_version=source_asset_version,
        target_asset_id=target_asset_id,
        target_asset_version=target_asset_version,
        target_asset_label=target_label,
        dependency_type=dependency_type,
        relative_path=relative_path,
        metadata=metadata or {},
    )


def update_asset_reference(
    session: requests.Session,
    org_id: str,
    project_id: str,
    source_asset_id: str,
    reference_id: str,
    target_asset_version: str = "",
    target_label: str = "",
    dependency_type: str = "",
    relative_path: str = "",
    metadata: dict | None = None,
    metadata_to_remove: list[str] | None = None,
) -> None:
    """Update a reference in place — retarget to a version or a label, change
    dependencyType/relativePath, merge metadata, or remove metadata keys."""
    url = _proj(project_id, "assets", source_asset_id, "references", reference_id)
    target: dict[str, Any] = {}
    if target_asset_version:
        target["assetVersion"] = target_asset_version
    if target_label:
        target["labelName"] = target_label
    body: dict[str, Any] = {}
    if target:
        body["target"] = target
    if dependency_type:
        body["dependencyType"] = dependency_type
    if relative_path:
        body["relativePath"] = relative_path
    if metadata:
        body["metadata"] = metadata
    if metadata_to_remove:
        body["metadataToRemove"] = metadata_to_remove
    resp = _post(session, url, json=body)
    _raise(resp)


def list_asset_references(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    context: str = "BOTH",
) -> list[AssetReference]:
    url = _proj(project_id, "assets", asset_id, "references")
    results: list[AssetReference] = []
    offset, limit = 0, 100  # spec caps limit at 255
    while True:
        params: dict[str, Any] = {"assetVersion": asset_version, "offset": offset, "limit": limit}
        # Documented Context enum: Both | Source | Target | Downstream | Upstream.
        ctx = context.strip().capitalize() if context else ""
        if ctx and ctx != "Both":
            params["context"] = ctx
        resp = _get(session, url, params=params)
        _raise(resp)
        data = resp.json()
        items = data.get("references", data.get("results", data)) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []
        results.extend(_parse_reference(r) for r in items)
        if len(items) < limit:
            break
        offset += limit
    return results


def remove_asset_reference(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    reference_id: str,
) -> bool:
    url = _proj(project_id, "assets", asset_id, "references", reference_id)
    resp = _delete(session, url)
    _raise(resp)
    return True


# ---------------------------------------------------------------------------
# Labels — organizations define labels (system ones like "Latest"/"Pending"
# are auto-assigned and restricted; user labels are creatable and assignable
# to asset versions).
# ---------------------------------------------------------------------------

def list_labels(
    session: requests.Session,
    org_id: str,
    status: str = "",
    is_system_label: bool | None = None,
) -> list[dict]:
    """List the labels defined in an organization (raw dicts).

    status filters Active/Archived; is_system_label filters system vs user labels.
    """
    url = _org(org_id, "labels")
    params: dict[str, Any] = {}
    if status:
        params["status"] = status.strip().capitalize()
    if is_system_label is not None:
        params["isSystemLabel"] = "true" if is_system_label else "false"
    resp = _get(session, url, params=params or None)
    _raise(resp)
    data = resp.json()
    items = data.get("labels", data.get("results", data)) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def create_label(session: requests.Session, org_id: str, name: str, description: str, colour: str = "") -> str:
    """Create a user label in the organization; returns the label name."""
    url = _org(org_id, "labels")
    body: dict[str, Any] = {"name": name, "description": description}
    if colour:
        body["colour"] = colour
    resp = _post(session, url, json=body)
    _raise(resp)
    data = resp.json()
    return data.get("labelName", name)


def update_label(session: requests.Session, org_id: str, label_name: str, name: str = "", description: str = "", colour: str = "") -> None:
    """Update a non-system label's name/description/colour."""
    encoded = urllib.parse.quote(label_name, safe="")
    url = _org(org_id, "labels", encoded)
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    if colour:
        body["colour"] = colour
    resp = _patch(session, url, json=body)
    _raise(resp)


def archive_label(session: requests.Session, org_id: str, label_name: str) -> None:
    encoded = urllib.parse.quote(label_name, safe="")
    resp = _post(session, _org(org_id, "labels", encoded, "archive"))
    _raise(resp)


def unarchive_label(session: requests.Session, org_id: str, label_name: str) -> None:
    encoded = urllib.parse.quote(label_name, safe="")
    resp = _post(session, _org(org_id, "labels", encoded, "unarchive"))
    _raise(resp)


def assign_labels(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str, label_names: list[str]) -> None:
    """Assign labels to an asset version. Latest/Pending are restricted."""
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "labels", "assign")
    resp = _post(session, url, json={"labelNames": label_names})
    _raise(resp)


def unassign_labels(session: requests.Session, org_id: str, project_id: str, asset_id: str, asset_version: str, label_names: list[str]) -> None:
    """Unassign labels from an asset version. Latest/Pending are restricted."""
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "labels", "unassign")
    resp = _post(session, url, json={"labelNames": label_names})
    _raise(resp)


def get_asset_version_by_label(session: requests.Session, org_id: str, project_id: str, asset_id: str, label_name: str) -> Asset:
    """Resolve the asset version a label points at."""
    encoded = urllib.parse.quote(label_name, safe="")
    url = _proj(project_id, "assets", asset_id, "labels", encoded)
    resp = _get(session, url, params={"IncludeFields": _GET_ASSET_INCLUDE_FIELDS})
    _raise(resp)
    return _parse_asset(resp.json())


def list_asset_labels(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str = "",
) -> dict[str, list[str]]:
    """Return active and archived system labels for an asset.

    If asset_version is supplied, returns labels for that version only.
    Returns {"active": [...], "archived": [...]} with label name strings.
    """
    # Labels live at the asset level (not version level)
    url = _proj(project_id, "assets", asset_id, "labels")
    version_entries: list[dict] = []
    offset, limit = 0, 100  # spec caps limit at 1000
    while True:
        resp = _get(session, url, params={"offset": offset, "limit": limit})
        _raise(resp)
        data = resp.json()
        page = data.get("assetVersionLabels", []) or []
        version_entries.extend(page)
        if len(page) < limit:
            break
        offset += limit
    if asset_version:
        version_entries = [v for v in version_entries if v.get("assetVersion") == asset_version]
    active: list[str] = []
    archived: list[str] = []
    for entry in version_entries:
        active.extend(lbl["name"] for lbl in entry.get("labels", []))
        archived.extend(lbl["name"] for lbl in entry.get("archivedLabels", []))
    return {"active": active, "archived": archived}


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def update_asset_metadata(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    metadata: dict[str, Any],
) -> Asset:
    """Set or update custom metadata fields on an asset version (PATCH — merges into existing)."""
    url = _proj(project_id, "assets", asset_id, "versions", asset_version)
    resp = _patch(session, url, json={"metadata": metadata})
    _raise(resp)
    # PATCH returns 204 No Content on success; fetch the updated asset
    return get_asset(session, org_id, project_id, asset_id, asset_version)


def remove_asset_metadata_fields(
    session: requests.Session,
    org_id: str,
    project_id: str,
    asset_id: str,
    asset_version: str,
    field_names: list[str],
) -> None:
    """Remove custom metadata fields from an asset version.

    This is the documented removal mechanism (DELETE .../fields with the field
    names as query params) — a null value in the metadata PATCH is not it.
    """
    url = _proj(project_id, "assets", asset_id, "versions", asset_version, "fields")
    resp = _delete(session, url, params={"metadata": field_names})
    _raise(resp)


def list_field_definitions(session: requests.Session, org_id: str) -> list[FieldDefinition]:
    """Return all custom metadata field definitions for the organisation."""
    url = _org(org_id, "templates", "fields")
    results: list[FieldDefinition] = []
    token: str | None = None
    while True:
        # This endpoint's pagination params are PascalCase (Next/Limit) per the spec.
        params: dict[str, Any] = {"Limit": 1000}
        if token:
            params["Next"] = token
        resp = _get(session, url, params=params)
        _raise(resp)
        data = resp.json()
        items = data.get("fieldDefinitions", data.get("results", data)) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []
        results.extend(_parse_field_definition(f) for f in items)
        token = data.get("next") if isinstance(data, dict) else None
        if not token:
            break
    return results


def create_field_definition(
    session: requests.Session,
    org_id: str,
    key: str,
    display_name: str,
    field_type: str,
    accepted_values: list[str] | None = None,
    multiselection: bool = False,
) -> FieldDefinition:
    """Create a custom metadata field definition at the organisation level.

    field_type must be one of: TEXT, NUMBER, BOOLEAN, SELECTION, TIMESTAMP, URL, USER.
    accepted_values is required (and only meaningful) when field_type is SELECTION.
    """
    url = _org(org_id, "templates", "fields")
    body: dict[str, Any] = {
        "name": key,
        "displayName": display_name,
        # Documented enum casing is PascalCase (Text, Selection, Timestamp, ...);
        # fully-uppercase input is normalised onto the documented form.
        "type": field_type.strip().capitalize() if field_type else field_type,
    }
    if accepted_values:
        body["acceptedValues"] = accepted_values
    if multiselection:
        # camelCase per the spec (assets.CreateFieldRequest.multiSelection);
        # see the live-verified note in _parse_field_definition.
        body["multiSelection"] = multiselection
    resp = _post(session, url, json=body)
    _raise(resp)
    try:
        return _parse_field_definition(resp.json())
    except Exception:
        return FieldDefinition(
            key=key,
            display_name=display_name,
            field_type=field_type,
            accepted_values=accepted_values or [],
            multiselection=multiselection,
        )


def update_field_definition(
    session: requests.Session,
    org_id: str,
    field_name: str,
    display_name: str = "",
    accepted_values: list[str] | None = None,
) -> None:
    """Update a field definition's display name and/or REPLACE its accepted values.

    Field type and field name cannot be changed. accepted_values overrides the
    whole list; use add/remove_accepted_values for incremental changes.
    """
    encoded = urllib.parse.quote(field_name, safe="")
    url = _org(org_id, "templates", "fields", encoded)
    body: dict[str, Any] = {}
    if display_name:
        body["displayName"] = display_name
    if accepted_values is not None:
        body["acceptedValues"] = accepted_values
    resp = _patch(session, url, json=body)
    _raise(resp)


def add_accepted_values(session: requests.Session, org_id: str, field_name: str, values: list[str]) -> None:
    """Add accepted values to a Selection field. Values go in the QUERY string, not the body."""
    encoded = urllib.parse.quote(field_name, safe="")
    url = _org(org_id, "templates", "fields", encoded, "accepted-values")
    resp = _post(session, url, params={"values": values})
    _raise(resp)


def remove_accepted_values(session: requests.Session, org_id: str, field_name: str, values: list[str]) -> None:
    """Remove accepted values from a Selection field. Values go in the QUERY string."""
    encoded = urllib.parse.quote(field_name, safe="")
    url = _org(org_id, "templates", "fields", encoded, "accepted-values")
    resp = _delete(session, url, params={"values": values})
    _raise(resp)


def delete_field_definition(session: requests.Session, org_id: str, field_name: str) -> bool:
    """Delete a metadata field definition from the organisation library.

    Note: deleted definitions may still appear in list_field_definitions responses.
    field_name is URL-encoded automatically.
    """
    encoded = urllib.parse.quote(field_name, safe="")
    url = _org(org_id, "templates", "fields", encoded)
    resp = _delete(session, url)
    _raise(resp)
    return True


# ---------------------------------------------------------------------------
# Organizations and projects (identity service)
# ---------------------------------------------------------------------------

def list_organizations(session: requests.Session) -> list[Organization]:
    url = f"{_USER_BASE}/api/unity/v3/users/me/organizations"
    results: list[Organization] = []
    limit = 50
    offset = 0
    while True:
        resp = _get(session, url, params={"limit": limit, "offset": offset})
        _raise(resp)
        data = resp.json()
        items = data.get("results", data.get("organizations", data)) if isinstance(data, dict) else data
        if not isinstance(items, list):
            break
        for o in items:
            results.append(Organization(
                id=o.get("id", ""),
                name=o.get("name", ""),
                genesis_id=str(o.get("genesisId", "")),
            ))
        if len(items) < limit:
            break
        offset += limit
    return results


def list_projects(session: requests.Session, org_id: str) -> list[Project]:
    # org_id here should be the numeric genesisId, not the UUID
    url = _org(org_id, "projects")
    results: list[Project] = []
    page = 1
    while True:
        resp = _get(session, url, params={"Limit": 50, "Page": page})
        _raise(resp)
        data = resp.json()
        items = data.get("projects", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            break
        page_items = [Project(
            id=p.get("id", p.get("projectId", p.get("guid", ""))),
            name=p.get("name", ""),
        ) for p in items]
        # The Limit/Page param names are unverified against any published spec
        # (identity API); if the server ignored them it would serve the same
        # page forever — stop when a page adds nothing new.
        seen_ids = {r.id for r in results}
        new_items = [p for p in page_items if p.id not in seen_ids]
        results.extend(new_items)
        if len(items) < 50 or not new_items:
            break
        page += 1
    return results


def get_entitlements(session: requests.Session, org_genesis_id: str) -> dict:
    """The signed-in user's Asset Manager entitlements in an org.

    org_genesis_id MUST be the numeric genesis id — the endpoint silently
    returns empty lists for a UUID (verified live). Response shape:
    {"entitlements": [...], "userSeats": [...], "validSeat": bool} where the
    lists hold seat product codes such as EDITION-IND (Industry), UCP-PRO
    (Pro), UCP-ENT (Enterprise). Empty lists mean the org/user has no Asset
    Manager seats: storage falls back to the free 10 GB baseline and file
    uploads may fail with HTTP 402 'Maximum quota reached'.
    """
    resp = _get(session, _org(org_genesis_id, "entitlements"))
    _raise(resp)
    return resp.json()


def create_project(session: requests.Session, org_id: str, name: str, metadata: dict | None = None) -> str:
    # org_id here must be the numeric genesisId, not the UUID (same as
    # list_projects — verified live: the UUID form returns 403
    # Forbidden).
    url = _org(org_id, "projects")
    body = {"name": name, "metadata": metadata or {}}
    resp = _post(session, url, json=body)
    _raise(resp)
    data = resp.json()
    return data.get("id", data.get("projectId", data.get("guid", "")))


# Unity "developer projects" gateway — the entities API behind the Unity Cloud
# dashboard. These are the same routes the dashboard's Archive/Delete project
# buttons call (verified live); they are NOT part of the documented
# public Assets API and may change without notice. All require the caller to be
# an Owner or Manager of the organization.
_UNITY_GATEWAY = "https://services.unity.com/api/unity"


def get_project_admin(session: requests.Session, project_id: str) -> dict:
    """Project metadata from the entities API, including `organizationId`
    (UUID), `organizationGenesisId` (numeric), and archive state."""
    resp = _get(session, f"{_UNITY_GATEWAY}/v1/projects/{project_id}")
    _raise(resp)
    return resp.json()


def archive_project(session: requests.Session, org_id: str, project_id: str) -> None:
    """Archive a project (dashboard 'Archive project'). org_id is the org UUID.
    Archiving is reversible from the dashboard's Archived tab and is required
    before delete_project."""
    resp = _put(
        session,
        f"{_UNITY_GATEWAY}/v1/organizations/{org_id}/projects/{project_id}/archive",
        json={},
    )
    _raise(resp)


def delete_project(session: requests.Session, org_genesis_id: str, project_id: str) -> None:
    """Permanently delete an ARCHIVED project (dashboard Archived tab →
    Delete). org_genesis_id is the numeric org id; project_id is the UUID.
    Irreversible — the API rejects projects that were not archived first."""
    resp = _delete(
        session,
        f"{_UNITY_GATEWAY}/v3/organizations/{org_genesis_id}/projects/{project_id}",
    )
    _raise(resp)
