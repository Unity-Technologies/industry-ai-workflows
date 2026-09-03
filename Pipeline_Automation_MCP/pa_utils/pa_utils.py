"""
Thin wrappers around the Unity Pipeline Automation REST API v1.

Base URL: https://automation.services.api.unity.com/v1 on public Unity Cloud.
On a private-cloud (VPC) deployment the service is served from the customer's
host instead, at an API version that varies by bundle release: newer bundles
serve public-parity `api/automation/v1`, older ones `api/automation/v1alpha1`.
With no explicit UNITY_VPC_AUTOMATION_PATH override, the request helpers
resolve the right one on the fly: a gateway-level 404 (plain-text "404 page
not found" — the request never reached the service, so a retry is safe for
any HTTP method) triggers one retry against the next candidate base, and the
first base that routes is locked in for the process.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# The shared VPC config module lives at the repo root (two levels up).
_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.unity_auth import vpc as _vpc  # noqa: E402

# Candidate bases in preference order. On public cloud (or with an explicit
# UNITY_VPC_AUTOMATION_PATH) this collapses to a single base and the fallback
# machinery below never engages.
_BASE_CANDIDATES: list[str] = []
for _path in _vpc.automation_service_paths():
    _base = _vpc.api_base("https://automation.services.api.unity.com/v1", _path.lstrip("/"))
    if _base not in _BASE_CANDIDATES:
        _BASE_CANDIDATES.append(_base)

BASE_URL = _BASE_CANDIDATES[0]
_base_locked = len(_BASE_CANDIDATES) == 1

# ---------------------------------------------------------------------------
# Timeouts and retries
# ---------------------------------------------------------------------------

# (connect, read) timeouts in seconds. Every REST call sets a timeout so a
# stalled connection can never hang the stdio MCP server indefinitely.
DEFAULT_TIMEOUT = (10, 120)

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


def _is_route_404(resp: requests.Response) -> bool:
    """True for a gateway-level "no such route" 404 (plain text), as opposed
    to an API-level 404 (JSON problem document for a missing resource)."""
    if resp.status_code != 404:
        return False
    try:
        return resp.text.strip().lower() == "404 page not found"
    except Exception:
        return False


def _request(method: str, session: requests.Session, url: str, **kwargs) -> requests.Response:
    """One HTTP request, with lazy automation-base resolution on VPC.

    Until a base is locked, a route-level 404 (the request never reached the
    service — safe to retry regardless of method) is retried once per
    remaining candidate base; the first base that routes becomes BASE_URL for
    the rest of the process."""
    global BASE_URL, _base_locked
    _mount_retries(session)
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    resp = getattr(session, method)(url, **kwargs)
    if _base_locked:
        return resp
    if not _is_route_404(resp):
        _base_locked = True
        return resp
    current = _BASE_CANDIDATES.index(BASE_URL)
    for candidate in _BASE_CANDIDATES[current + 1:]:
        retry = getattr(session, method)(url.replace(BASE_URL, candidate, 1), **kwargs)
        if not _is_route_404(retry):
            BASE_URL = candidate
            _base_locked = True
            return retry
    return resp  # every candidate route-404s: report against the preferred base


def _get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    return _request("get", session, url, **kwargs)


def _post(session: requests.Session, url: str, **kwargs) -> requests.Response:
    return _request("post", session, url, **kwargs)


def _patch(session: requests.Session, url: str, **kwargs) -> requests.Response:
    return _request("patch", session, url, **kwargs)


def _put(session: requests.Session, url: str, **kwargs) -> requests.Response:
    return _request("put", session, url, **kwargs)


def _delete(session: requests.Session, url: str, **kwargs) -> requests.Response:
    return _request("delete", session, url, **kwargs)


def _url(*parts: str) -> str:
    return "/".join([BASE_URL.rstrip("/")] + [p.strip("/") for p in parts])


def _raise(resp: requests.Response) -> None:
    """Raise with a readable message on non-2xx responses."""
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise RuntimeError(
            f"HTTP {resp.status_code} {resp.reason} — {detail}"
        )


# ---------------------------------------------------------------------------
# Pipelines (organisation-level)
# ---------------------------------------------------------------------------

def list_pipelines(
    session: requests.Session,
    org_id: str,
    owned: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if owned is not None:
        params["owned"] = owned
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session, _url("organizations", org_id, "pipelines"), params=params)
    _raise(resp)
    return resp.json()


def list_pipeline_versions(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session,
        _url("organizations", org_id, "pipelines", pipeline_id, "versions"),
        params=params,
    )
    _raise(resp)
    return resp.json()


def get_pipeline_version(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    pipeline_version: str,
) -> dict:
    resp = _get(session,
        _url("organizations", org_id, "pipelines", pipeline_id, "versions", pipeline_version)
    )
    _raise(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Apps and Actions
# ---------------------------------------------------------------------------

def list_apps(
    session: requests.Session,
    org_id: str,
    owned: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if owned is not None:
        params["owned"] = owned
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session, _url("organizations", org_id, "apps"), params=params)
    _raise(resp)
    return resp.json()


def list_app_versions(
    session: requests.Session,
    org_id: str,
    app_id: str,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session,
        _url("organizations", org_id, "apps", app_id, "versions"),
        params=params,
    )
    _raise(resp)
    return resp.json()


def get_app_version(
    session: requests.Session,
    org_id: str,
    app_id: str,
    app_version: str,
) -> dict:
    resp = _get(session,
        _url("organizations", org_id, "apps", app_id, "versions", app_version)
    )
    _raise(resp)
    return resp.json()


def get_app_action(
    session: requests.Session,
    org_id: str,
    app_id: str,
    app_version: str,
    action_id: str,
) -> dict:
    resp = _get(session,
        _url("organizations", org_id, "apps", app_id, "versions", app_version, "actions", action_id)
    )
    _raise(resp)
    return resp.json()


def validate_pipeline(session: requests.Session, org_id: str, definition: dict) -> None:
    """Validate a pipeline definition (TransientPipelineRequest) without creating a draft.

    204 = valid; an invalid definition raises with the ProblemDetails body, so
    authoring errors surface without burning a draft version.
    """
    resp = _post(session, _url("organizations", org_id, "pipelines", "validate"), json=definition)
    _raise(resp)


def trigger_transient_pipeline(
    session: requests.Session, org_id: str, definition: dict
) -> dict:
    """Trigger an inline pipeline definition (TransientPipelineRequest) without
    creating a pipeline or draft version. 201 returns the created job."""
    resp = _post(session, _url("organizations", org_id, "pipelines", "trigger"), json=definition)
    _raise(resp)
    return resp.json()


def trigger_pipeline(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    pipeline_version: str,
    inputs: dict | None = None,
    secrets: dict | None = None,
    job_priority: int | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if inputs:
        body["inputs"] = inputs
    if secrets:
        body["secrets"] = secrets
    if job_priority is not None:
        body["jobPriority"] = job_priority
    resp = _post(session,
        _url(
            "organizations", org_id, "pipelines", pipeline_id,
            "versions", pipeline_version, "trigger",
        ),
        json=body,
    )
    _raise(resp)
    return resp.json()


def create_pipeline(
    session: requests.Session,
    org_id: str,
    name: str,
    description: str,
    version: str,
    pipeline_id: str | None = None,
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    tags: list[str] | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> dict:
    body: dict[str, Any] = {"name": name, "description": description, "version": version}
    if pipeline_id:
        body["id"] = pipeline_id
    if input_parameters is not None:
        body["inputParameters"] = input_parameters
    if secrets is not None:
        body["secrets"] = secrets
    if output_parameters is not None:
        body["outputParameters"] = output_parameters
    if tags is not None:
        body["tags"] = tags
    if steps is not None:
        body["steps"] = steps
    if metadata is not None:
        body["metadata"] = metadata
    if storages is not None:
        body["storages"] = storages
    resp = _post(session, _url("organizations", org_id, "pipelines"), json=body)
    _raise(resp)
    return resp.json()


def update_pipeline(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if tags is not None:
        body["tags"] = tags
    resp = _patch(session, _url("organizations", org_id, "pipelines", pipeline_id), json=body)
    _raise(resp)
    return resp.json()


def create_pipeline_version(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    version: str | None = None,
    base_version: str | None = None,
    steps: list | None = None,
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if version:
        body["version"] = version
    if base_version:
        body["baseVersion"] = base_version
    if steps is not None:
        body["steps"] = steps
    if input_parameters is not None:
        body["inputParameters"] = input_parameters
    if secrets is not None:
        body["secrets"] = secrets
    if output_parameters is not None:
        body["outputParameters"] = output_parameters
    if metadata is not None:
        body["metadata"] = metadata
    if storages is not None:
        body["storages"] = storages
    resp = _post(session,
        _url("organizations", org_id, "pipelines", pipeline_id, "versions"), json=body
    )
    _raise(resp)
    return resp.json()


def update_pipeline_version(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    pipeline_version: str,
    input_parameters: list | None = None,
    output_parameters: list | None = None,
    secrets: list | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if input_parameters is not None:
        body["inputParameters"] = input_parameters
    if output_parameters is not None:
        body["outputParameters"] = output_parameters
    if secrets is not None:
        body["secrets"] = secrets
    if steps is not None:
        body["steps"] = steps
    if metadata is not None:
        body["metadata"] = metadata
    if storages is not None:
        body["storages"] = storages
    resp = _patch(session,
        _url("organizations", org_id, "pipelines", pipeline_id, "versions", pipeline_version),
        json=body,
    )
    _raise(resp)
    return resp.json()


def delete_draft_pipeline_version(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    pipeline_version: str,
) -> bool:
    resp = _delete(session,
        _url("organizations", org_id, "pipelines", pipeline_id, "versions", pipeline_version)
    )
    _raise(resp)
    return resp.status_code == 204


def publish_pipeline_version(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    pipeline_version: str,
    target_visibility: str,
) -> dict:
    resp = _post(session,
        _url(
            "organizations", org_id, "pipelines", pipeline_id,
            "versions", pipeline_version, "publish", target_visibility,
        )
    )
    _raise(resp)
    return resp.json()


def change_pipeline_status(
    session: requests.Session,
    org_id: str,
    pipeline_id: str,
    pipeline_version: str,
    lifecycle_status: str,
    archiving_date: str | None = None,
) -> dict:
    # verified live: the API takes the target status in the PATH
    # (POST .../status/{target}); the body-based POST .../status route the spec
    # suggests does not exist (404).
    body: dict[str, Any] = {}
    if archiving_date:
        body["archivingDate"] = archiving_date
    resp = _post(session,
        _url(
            "organizations", org_id, "pipelines", pipeline_id,
            "versions", pipeline_version, "status", lifecycle_status,
        ),
        json=body,
    )
    _raise(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Project Pipelines
# ---------------------------------------------------------------------------

def list_project_pipelines(
    session: requests.Session,
    org_id: str,
    project_id: str,
    owned: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if owned is not None:
        params["owned"] = owned
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session,
        _url("organizations", org_id, "projects", project_id, "pipelines"),
        params=params,
    )
    _raise(resp)
    return resp.json()


def list_project_pipeline_versions(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "pipelines", pipeline_id, "versions",
        ),
        params=params,
    )
    _raise(resp)
    return resp.json()


def get_project_pipeline_version(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    pipeline_version: str,
) -> dict:
    resp = _get(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "pipelines", pipeline_id, "versions", pipeline_version,
        )
    )
    _raise(resp)
    return resp.json()


def validate_project_pipeline(session: requests.Session, org_id: str, project_id: str, definition: dict) -> None:
    """Project-scoped variant of validate_pipeline."""
    resp = _post(session, _url("organizations", org_id, "projects", project_id, "pipelines", "validate"), json=definition)
    _raise(resp)


def trigger_transient_project_pipeline(
    session: requests.Session, org_id: str, project_id: str, definition: dict
) -> dict:
    """Project-scoped variant of trigger_transient_pipeline."""
    resp = _post(session, _url("organizations", org_id, "projects", project_id, "pipelines", "trigger"), json=definition)
    _raise(resp)
    return resp.json()


def trigger_project_pipeline(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    pipeline_version: str,
    inputs: dict | None = None,
    secrets: dict | None = None,
    job_priority: int | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if inputs:
        body["inputs"] = inputs
    if secrets:
        body["secrets"] = secrets
    if job_priority is not None:
        body["jobPriority"] = job_priority
    resp = _post(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "pipelines", pipeline_id, "versions", pipeline_version, "trigger",
        ),
        json=body,
    )
    _raise(resp)
    return resp.json()


def create_project_pipeline(
    session: requests.Session,
    org_id: str,
    project_id: str,
    name: str,
    description: str,
    version: str,
    pipeline_id: str | None = None,
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    tags: list[str] | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> dict:
    body: dict[str, Any] = {"name": name, "description": description, "version": version}
    if pipeline_id:
        body["id"] = pipeline_id
    if input_parameters is not None:
        body["inputParameters"] = input_parameters
    if secrets is not None:
        body["secrets"] = secrets
    if output_parameters is not None:
        body["outputParameters"] = output_parameters
    if tags is not None:
        body["tags"] = tags
    if steps is not None:
        body["steps"] = steps
    if metadata is not None:
        body["metadata"] = metadata
    if storages is not None:
        body["storages"] = storages
    resp = _post(session,
        _url("organizations", org_id, "projects", project_id, "pipelines"), json=body
    )
    _raise(resp)
    return resp.json()


def update_project_pipeline(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    if tags is not None:
        body["tags"] = tags
    resp = _patch(session,
        _url("organizations", org_id, "projects", project_id, "pipelines", pipeline_id),
        json=body,
    )
    _raise(resp)
    return resp.json()


def create_project_pipeline_version(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    version: str | None = None,
    base_version: str | None = None,
    steps: list | None = None,
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if version:
        body["version"] = version
    if base_version:
        body["baseVersion"] = base_version
    if steps is not None:
        body["steps"] = steps
    if input_parameters is not None:
        body["inputParameters"] = input_parameters
    if secrets is not None:
        body["secrets"] = secrets
    if output_parameters is not None:
        body["outputParameters"] = output_parameters
    if metadata is not None:
        body["metadata"] = metadata
    if storages is not None:
        body["storages"] = storages
    resp = _post(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "pipelines", pipeline_id, "versions",
        ),
        json=body,
    )
    _raise(resp)
    return resp.json()


def update_project_pipeline_version(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    pipeline_version: str,
    input_parameters: list | None = None,
    output_parameters: list | None = None,
    secrets: list | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if input_parameters is not None:
        body["inputParameters"] = input_parameters
    if output_parameters is not None:
        body["outputParameters"] = output_parameters
    if secrets is not None:
        body["secrets"] = secrets
    if steps is not None:
        body["steps"] = steps
    if metadata is not None:
        body["metadata"] = metadata
    if storages is not None:
        body["storages"] = storages
    resp = _patch(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "pipelines", pipeline_id, "versions", pipeline_version,
        ),
        json=body,
    )
    _raise(resp)
    return resp.json()


def delete_draft_project_pipeline_version(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    pipeline_version: str,
) -> bool:
    resp = _delete(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "pipelines", pipeline_id, "versions", pipeline_version,
        )
    )
    _raise(resp)
    return resp.status_code == 204


def change_project_pipeline_status(
    session: requests.Session,
    org_id: str,
    project_id: str,
    pipeline_id: str,
    pipeline_version: str,
    lifecycle_status: str,
    archiving_date: str | None = None,
) -> dict:
    # Target status goes in the PATH, same as change_pipeline_status.
    body: dict[str, Any] = {}
    if archiving_date:
        body["archivingDate"] = archiving_date
    resp = _post(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "pipelines", pipeline_id, "versions", pipeline_version, "status", lifecycle_status,
        ),
        json=body,
    )
    _raise(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Jobs (organisation-level)
# ---------------------------------------------------------------------------

def list_jobs(
    session: requests.Session,
    org_id: str,
    statuses: list[str] | None = None,
    pipeline_ids: list[str] | None = None,
    automation_ids: list[str] | None = None,
    order_by: str | None = None,
    order: str | None = None,
    inputs: dict | None = None,
    include_all_org_project_jobs: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if statuses:
        params["statuses"] = statuses
    if pipeline_ids:
        params["pipelineIds"] = pipeline_ids
    if automation_ids:
        params["automationIds"] = automation_ids
    if order_by:
        params["orderBy"] = order_by
    if order:
        params["order"] = order
    if inputs:
        # The `inputs` filter is an OpenAPI deepObject: each entry serializes
        # as an inputs[name]=value query parameter.
        for key, value in inputs.items():
            params[f"inputs[{key}]"] = value
    if include_all_org_project_jobs is not None:
        params["includeAllOrgProjectJobs"] = include_all_org_project_jobs
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session, _url("organizations", org_id, "jobs"), params=params)
    _raise(resp)
    return resp.json()


def get_job(session: requests.Session, org_id: str, job_id: str) -> dict:
    resp = _get(session, _url("organizations", org_id, "jobs", job_id))
    _raise(resp)
    return resp.json()


def get_job_stats(session: requests.Session, org_id: str) -> dict:
    resp = _get(session, _url("organizations", org_id, "job-stats"))
    _raise(resp)
    return resp.json()


def terminate_job(session: requests.Session, org_id: str, job_id: str) -> dict:
    resp = _put(session, _url("organizations", org_id, "jobs", job_id, "terminate"))
    _raise(resp)
    return resp.json()


def resume_job(
    session: requests.Session,
    org_id: str,
    job_id: str,
    step_id: str,
    parameters: dict | None = None,
) -> dict:
    # verified live: resume is step-scoped — PUT
    # .../jobs/{jobId}/steps/{stepId}/resume. The job-level
    # .../jobs/{jobId}/resume route does not exist (404).
    # parameters populates ResumeJobStepRequest for suspend steps that wait
    # for user-supplied input.
    body = {"parameters": parameters} if parameters else None
    resp = _put(session, _url("organizations", org_id, "jobs", job_id, "steps", step_id, "resume"), json=body)
    _raise(resp)
    return resp.json()


def approve_job_step(
    session: requests.Session,
    org_id: str,
    job_id: str,
    step_id: str,
    approved: bool,
    comment: str = "",
) -> dict:
    body: dict[str, Any] = {"approved": approved}
    if comment:
        body["comment"] = comment
    resp = _put(session,
        _url("organizations", org_id, "jobs", job_id, "steps", step_id, "approve"),
        json=body,
    )
    _raise(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Jobs (project-level)
# ---------------------------------------------------------------------------

def list_project_jobs(
    session: requests.Session,
    org_id: str,
    project_id: str,
    statuses: list[str] | None = None,
    pipeline_ids: list[str] | None = None,
    automation_ids: list[str] | None = None,
    order_by: str | None = None,
    order: str | None = None,
    inputs: dict | None = None,
    include_all_org_project_jobs: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if statuses:
        params["statuses"] = statuses
    if pipeline_ids:
        params["pipelineIds"] = pipeline_ids
    if automation_ids:
        params["automationIds"] = automation_ids
    if order_by:
        params["orderBy"] = order_by
    if order:
        params["order"] = order
    if inputs:
        # deepObject serialization: inputs[name]=value query parameters.
        for key, value in inputs.items():
            params[f"inputs[{key}]"] = value
    if include_all_org_project_jobs is not None:
        params["includeAllOrgProjectJobs"] = include_all_org_project_jobs
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session,
        _url("organizations", org_id, "projects", project_id, "jobs"),
        params=params,
    )
    _raise(resp)
    return resp.json()


def get_project_job(
    session: requests.Session, org_id: str, project_id: str, job_id: str
) -> dict:
    resp = _get(session,
        _url("organizations", org_id, "projects", project_id, "jobs", job_id)
    )
    _raise(resp)
    return resp.json()


def terminate_project_job(
    session: requests.Session, org_id: str, project_id: str, job_id: str
) -> dict:
    resp = _put(session,
        _url("organizations", org_id, "projects", project_id, "jobs", job_id, "terminate")
    )
    _raise(resp)
    return resp.json()


def resume_project_job(
    session: requests.Session,
    org_id: str,
    project_id: str,
    job_id: str,
    step_id: str,
    parameters: dict | None = None,
) -> dict:
    # Step-scoped, same as resume_job; parameters populates ResumeJobStepRequest.
    body = {"parameters": parameters} if parameters else None
    resp = _put(session,
        _url("organizations", org_id, "projects", project_id, "jobs", job_id, "steps", step_id, "resume"),
        json=body,
    )
    _raise(resp)
    return resp.json()


def approve_project_job_step(
    session: requests.Session,
    org_id: str,
    project_id: str,
    job_id: str,
    step_id: str,
    approved: bool,
    comment: str = "",
) -> dict:
    body: dict[str, Any] = {"approved": approved}
    if comment:
        body["comment"] = comment
    resp = _put(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "jobs", job_id, "steps", step_id, "approve",
        ),
        json=body,
    )
    _raise(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def get_job_step_logs(
    session: requests.Session, org_id: str, job_id: str, step_id: str
) -> Any:
    resp = _get(session,
        _url("organizations", org_id, "jobs", job_id, "steps", step_id, "logs")
    )
    _raise(resp)
    try:
        return resp.json()
    except Exception:
        return resp.text


def get_project_job_step_logs(
    session: requests.Session,
    org_id: str,
    project_id: str,
    job_id: str,
    step_id: str,
) -> Any:
    resp = _get(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "jobs", job_id, "steps", step_id, "logs",
        )
    )
    _raise(resp)
    try:
        return resp.json()
    except Exception:
        return resp.text


def get_job_logs(session: requests.Session, org_id: str, job_id: str) -> Any:
    # Spec: 200 returns a LogsDto JSON document (whole-job logs, all steps).
    resp = _get(session,
        _url("organizations", org_id, "jobs", job_id, "logs")
    )
    _raise(resp)
    try:
        return resp.json()
    except Exception:
        return resp.text


def get_project_job_logs(
    session: requests.Session,
    org_id: str,
    project_id: str,
    job_id: str,
) -> Any:
    resp = _get(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "jobs", job_id, "logs",
        )
    )
    _raise(resp)
    try:
        return resp.json()
    except Exception:
        return resp.text


# ---------------------------------------------------------------------------
# Automations (read-only)
# ---------------------------------------------------------------------------

def list_automations(
    session: requests.Session,
    org_id: str,
    include_fields: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if include_fields:
        params["includeFields"] = include_fields
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session, _url("organizations", org_id, "automations"), params=params)
    _raise(resp)
    return resp.json()


def get_automation(
    session: requests.Session,
    org_id: str,
    automation_id: str,
    include_fields: str | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if include_fields:
        params["includeFields"] = include_fields
    resp = _get(session,
        _url("organizations", org_id, "automations", automation_id),
        params=params,
    )
    _raise(resp)
    return resp.json()


def list_project_automations(
    session: requests.Session,
    org_id: str,
    project_id: str,
    include_fields: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if include_fields:
        params["includeFields"] = include_fields
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session,
        _url("organizations", org_id, "projects", project_id, "automations"),
        params=params,
    )
    _raise(resp)
    return resp.json()


def get_project_automation(
    session: requests.Session,
    org_id: str,
    project_id: str,
    automation_id: str,
    include_fields: str | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if include_fields:
        params["includeFields"] = include_fields
    resp = _get(session,
        _url(
            "organizations", org_id, "projects", project_id,
            "automations", automation_id,
        ),
        params=params,
    )
    _raise(resp)
    return resp.json()


# ---------------------------------------------------------------------------
# Pipeline templates
# ---------------------------------------------------------------------------

def list_pipeline_templates(
    session: requests.Session,
    org_id: str,
    app_ids: list[str] | None = None,
    tags: list[str] | None = None,
    metadata: list[str] | None = None,
    system_metadata: list[str] | None = None,
    used_with: list[str] | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    params: dict[str, Any] = {}
    if app_ids:
        params["appIds"] = app_ids
    if tags:
        params["tags"] = tags
    if metadata:
        params["metadata"] = metadata
    if system_metadata:
        params["systemMetadata"] = system_metadata
    if used_with:
        params["usedWith"] = used_with
    if offset is not None:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit
    resp = _get(session, _url("organizations", org_id, "pipeline-templates"), params=params)
    _raise(resp)
    return resp.json()


def get_pipeline_template(
    session: requests.Session,
    org_id: str,
    pipeline_template_id: str,
) -> dict:
    resp = _get(session,
        _url("organizations", org_id, "pipeline-templates", pipeline_template_id)
    )
    _raise(resp)
    return resp.json()
