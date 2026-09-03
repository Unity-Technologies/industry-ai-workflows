"""
Pipeline_Automation_MCP Server
===============================

Exposes Unity Pipeline Automation REST API v1 operations as MCP tools.

Auth is a browser-based PKCE user login: run the `unity_login` tool first.
Tokens are cached on disk and refreshed on demand.

Org/project scope is chosen interactively per session: discover organizations
via the Asset Manager MCP's list_organizations, ask the user, then
set_default_organization / set_default_project here (every tool also accepts
explicit org_id / project_id arguments).

Start the server:
    python pa_mcp_server.py
"""

import functools
import json
import os

from dotenv import load_dotenv

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_SCRIPT_DIR, ".env"))

from mcp.server.mcpserver import MCPServer

from pa_utils import pa_init, pa_utils
from shared.client_identity import ClientIdentityExtension
from shared.unity_auth import vpc as _vpc

# The browser PKCE flow is deferred to the unity_login tool so the server can
# boot cleanly under marketplace install (no terminal, no browser pop-up at
# startup).

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = MCPServer(
    name="Pipeline_Automation_MCP",
    instructions=(
        "Unity Pipeline Automation MCP server. "
        "Exposes Pipeline Automation REST API v1 operations: authoring and "
        "versioning pipelines, triggering and monitoring jobs, step approval "
        "and logs, and app/action discovery. "
        "If the user mentions Unity or Unity workflows beyond these tools "
        "(e.g. installing Unity Editor versions, adding build-support modules, "
        "or opening Unity projects from the terminal), point them to the "
        "Unity CLI (https://docs.unity.com/en-us/unity-cli/use-unity-cli) "
        "and offer to run it for them alongside these tools."
    ),
    extensions=[ClientIdentityExtension()],
)

_ORG_ID = os.environ.get("UNITY_ORG_ID", "")
_PROJECT_ID = os.environ.get("UNITY_PROJECT_ID", "")


def _org(org_id: str) -> str:
    return org_id or _ORG_ID


def _proj(project_id: str) -> str:
    return project_id or _PROJECT_ID


@mcp.tool()
def set_default_organization(org_id: str) -> str:
    """Set the default organization for subsequent tool calls in this server process.

    Typical new-session flow: discover organizations with the Asset Manager
    MCP's `list_organizations` (or the Unity Cloud dashboard), ask the user
    which one to work in, then call this with its numeric (genesis) id.
    Follow up with set_default_project for project-scoped tools.
    """
    global _ORG_ID
    if not org_id.strip():
        return "Error: provide the organization's numeric (genesis) id."
    _ORG_ID = org_id.strip()
    return (
        f"Default organization set to '{_ORG_ID}'. Next: ask the user which "
        "project to use and call set_default_project (or pass project_id per call)."
    )


@mcp.tool()
def set_default_project(project_id: str) -> str:
    """Set the default project id for project-scoped tools in this server process.

    Ask the user which project to work in (the Asset Manager MCP's
    `list_projects` shows the org's projects; `create_project` there can make a
    new one if needed), then call this with the project id.
    """
    global _PROJECT_ID
    if not project_id.strip():
        return "Error: provide a project id."
    _PROJECT_ID = project_id.strip()
    return f"Default project set to '{_PROJECT_ID}'."


def _require_auth(func):
    """Decorator: short-circuit a tool when the current identity isn't usable.

    Returns the user-facing message (telling the caller to run unity_login)
    so the model can react, instead of the underlying HTTP layer throwing
    an opaque error mid-call."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        err = pa_init.auth_status_message()
        if err:
            return err
        return func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Pipeline tools – organisation level
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def create_pipeline(
    name: str,
    description: str,
    version: str,
    org_id: str = "",
    pipeline_id: str = "",
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    tags: list[str] | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> str:
    """Create a new organisation-level pipeline and return its first draft version.

    Args:
        name:              Pipeline name (2–57 chars, alphanumeric/hyphens/spaces).
        description:       Pipeline description (20–256 chars).
        version:           Initial version in semver format (e.g. "1.0.0").
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
        pipeline_id:       Optional UUID to assign as the pipeline ID.
        input_parameters:  List of input parameter definitions.
        secrets:           List of secret definitions.
        output_parameters: List of output parameter definitions.
        tags:              List of tag strings.
        steps:             List of step definitions (action, pipeline, or suspend).
        metadata:          Arbitrary metadata map attached to the pipeline version.
        storages:          List of pipeline storage definitions.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.create_pipeline(
            pa_init.get_session(), org, name, description, version,
            pipeline_id=pipeline_id or None,
            input_parameters=input_parameters,
            secrets=secrets,
            output_parameters=output_parameters,
            tags=tags,
            steps=steps,
            metadata=metadata,
            storages=storages,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error creating pipeline '{name}': {e}"


@mcp.tool()
@_require_auth
def update_pipeline(
    pipeline_id: str,
    org_id: str = "",
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update the basic information of an organisation-level pipeline (name, description, tags).

    This is independent of status or visibility and can only be called by the
    organisation the pipeline belongs to.

    Args:
        pipeline_id:  The pipeline unique identifier (UUID).
        org_id:       Organisation ID (falls back to the session default; see set_default_organization).
        name:         New pipeline name (2–57 chars, alphanumeric/hyphens/spaces).
        description:  New pipeline description (20–256 chars).
        tags:         New list of tag strings (replaces existing tags).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.update_pipeline(pa_init.get_session(), org, pipeline_id, name=name, description=description, tags=tags)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error updating pipeline '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def create_pipeline_version(
    pipeline_id: str,
    org_id: str = "",
    version: str = "",
    base_version: str = "",
    steps: list | None = None,
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> str:
    """Create a new version of an existing organisation-level pipeline.

    Args:
        pipeline_id:       The pipeline unique identifier (UUID).
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
        version:           New version number in semver format (e.g. "1.1.0").
        base_version:      Existing version to copy configuration from.
        steps:             List of step definitions for the new version.
        input_parameters:  List of input parameter definitions.
        secrets:           List of secret definitions.
        output_parameters: List of output parameter definitions.
        metadata:          Arbitrary metadata map.
        storages:          List of pipeline storage definitions.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.create_pipeline_version(
            pa_init.get_session(), org, pipeline_id,
            version=version or None,
            base_version=base_version or None,
            steps=steps,
            input_parameters=input_parameters,
            secrets=secrets,
            output_parameters=output_parameters,
            metadata=metadata,
            storages=storages,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error creating version for pipeline '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def validate_pipeline(
    definition: dict,
    org_id: str = "",
    project_id: str = "",
) -> str:
    """Validate a pipeline definition WITHOUT creating a pipeline or draft version.

    Use this to syntax-check a definition before create_pipeline /
    create_pipeline_version — validation errors surface here instead of
    burning a draft version on an HTTP 400.

    Args:
        definition: The full pipeline definition to validate. Required keys:
                    "name" (2-57 chars, alphanumeric/space/hyphen) and
                    "description" (20-256 chars). Optional: "tags", "steps"
                    (each step defines one of action/pipeline/suspend),
                    "metadata", "jobPriority".
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Optional project ID — pass to validate against the
                    project-scoped endpoint instead of the organisation one.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        if project_id:
            pa_utils.validate_project_pipeline(pa_init.get_session(), org, project_id, definition)
        else:
            pa_utils.validate_pipeline(pa_init.get_session(), org, definition)
        return json.dumps({"valid": True, "message": "Pipeline definition is valid."}, indent=2)
    except Exception as e:
        return json.dumps(
            {"valid": False, "message": f"Pipeline definition failed validation: {e}"},
            indent=2,
        )


@mcp.tool()
@_require_auth
def trigger_transient_pipeline(
    definition: dict,
    org_id: str = "",
    project_id: str = "",
) -> str:
    """Trigger an inline pipeline definition WITHOUT creating a pipeline or draft version.

    Runs the definition directly and returns the created job — nothing is
    persisted in the pipeline catalogue, so this is ideal for one-off runs and
    for iterating on a definition before committing it with create_pipeline.
    Call validate_pipeline on the definition first: validation errors surface
    there instead of failing the trigger.

    Args:
        definition: The full pipeline definition to run (same shape as
                    validate_pipeline). Required keys: "name" (2-57 chars,
                    alphanumeric/space/hyphen) and "description" (20-256 chars).
                    Optional: "tags", "steps" (each step defines one of
                    action/pipeline/suspend), "metadata", "jobPriority",
                    plus "inputs"/"secrets" values for the run.
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Optional project ID — pass to trigger against the
                    project-scoped endpoint instead of the organisation one.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        if project_id:
            result = pa_utils.trigger_transient_project_pipeline(
                pa_init.get_session(), org, project_id, definition
            )
        else:
            result = pa_utils.trigger_transient_pipeline(pa_init.get_session(), org, definition)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error triggering transient pipeline: {e}"


@mcp.tool()
@_require_auth
def update_pipeline_version(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
    input_parameters: list | None = None,
    output_parameters: list | None = None,
    secrets: list | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> str:
    """Update a draft pipeline version (only Draft status versions can be updated).

    Args:
        pipeline_id:       The pipeline unique identifier (UUID).
        pipeline_version:  Version string in semver format (e.g. "1.0.0").
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
        input_parameters:  Replacement list of input parameter definitions.
        output_parameters: Replacement list of output parameter definitions.
        secrets:           Replacement list of secret definitions.
        steps:             Replacement list of step definitions.
        metadata:          Replacement metadata map.
        storages:          Replacement list of pipeline storage definitions.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.update_pipeline_version(
            pa_init.get_session(), org, pipeline_id, pipeline_version,
            input_parameters=input_parameters,
            output_parameters=output_parameters,
            secrets=secrets,
            steps=steps,
            metadata=metadata,
            storages=storages,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error updating pipeline version '{pipeline_version}' for '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def delete_draft_pipeline_version(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
) -> str:
    """Delete a draft pipeline version.

    Only Draft versions that are not in use can be deleted.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        pa_utils.delete_draft_pipeline_version(pa_init.get_session(), org, pipeline_id, pipeline_version)
        return f"Pipeline version '{pipeline_version}' for pipeline '{pipeline_id}' deleted successfully."
    except Exception as e:
        return f"Error deleting pipeline version '{pipeline_version}' for '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def publish_pipeline_version(
    pipeline_id: str,
    pipeline_version: str,
    target_visibility: str,
    org_id: str = "",
) -> str:
    """Change the visibility of an organisation-level pipeline version.

    Args:
        pipeline_id:       The pipeline unique identifier (UUID).
        pipeline_version:  Version string in semver format (e.g. "1.0.0").
        target_visibility: Target visibility – Private, Public, or Unlisted.
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.publish_pipeline_version(
            pa_init.get_session(), org, pipeline_id, pipeline_version, target_visibility
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error publishing pipeline version '{pipeline_version}' for '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def list_pipelines(
    org_id: str = "",
    owned: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List all pipelines accessible by the organisation.

    Returns the latest version of each pipeline, including both pipelines
    created by the organisation and public pipelines.

    Args:
        org_id:  Organisation ID (falls back to the session default; see set_default_organization).
        owned:   True to return only pipelines owned by this org.
        offset:  Number of items to skip (pagination).
        limit:   Maximum number of items to return.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.list_pipelines(pa_init.get_session(), org, owned=owned, offset=offset, limit=limit)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing pipelines: {e}"


@mcp.tool()
@_require_auth
def list_pipeline_versions(
    pipeline_id: str,
    org_id: str = "",
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List all versions of a specific pipeline.

    Args:
        pipeline_id: The pipeline unique identifier (UUID).
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        offset:      Number of items to skip.
        limit:       Maximum number of items to return.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.list_pipeline_versions(pa_init.get_session(), org, pipeline_id, offset=offset, limit=limit)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing versions for pipeline '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def get_pipeline_version(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
) -> str:
    """Get full details of a specific pipeline version, including steps, parameters, and lifecycle.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_pipeline_version(pa_init.get_session(), org, pipeline_id, pipeline_version)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting pipeline version '{pipeline_version}' for '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def trigger_pipeline(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
    inputs: dict | None = None,
    secrets: dict | None = None,
    job_priority: int | None = None,
) -> str:
    """Trigger an organisation-level pipeline and return the created job.

    The pipeline must be accessible to the organisation triggering it.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
        inputs:           Map of input parameter names to values.
        secrets:          Map of secret names to values injected into the pipeline.
        job_priority:     Job priority – 0 is the highest priority.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.trigger_pipeline(
            pa_init.get_session(), org, pipeline_id, pipeline_version,
            inputs=inputs, secrets=secrets, job_priority=job_priority,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error triggering pipeline '{pipeline_id}' v{pipeline_version}: {e}"


@mcp.tool()
@_require_auth
def change_pipeline_status(
    pipeline_id: str,
    pipeline_version: str,
    lifecycle_status: str,
    org_id: str = "",
    archiving_date: str = "",
) -> str:
    """Change the lifecycle status of an organisation-level pipeline version.

    Valid lifecycle_status values: Draft, Available, Deprecated, Archived.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        lifecycle_status: Target lifecycle status.
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
        archiving_date:   UTC date-time (ISO 8601) used when requesting Deprecated status.
                          Defaults to 6 months from now if not specified.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.change_pipeline_status(
            pa_init.get_session(), org, pipeline_id, pipeline_version,
            lifecycle_status, archiving_date=archiving_date or None,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error changing status for pipeline '{pipeline_id}' v{pipeline_version}: {e}"


# ---------------------------------------------------------------------------
# Project Pipeline tools
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def create_project_pipeline(
    name: str,
    description: str,
    version: str,
    org_id: str = "",
    project_id: str = "",
    pipeline_id: str = "",
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    tags: list[str] | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> str:
    """Create a new project-level pipeline and return its first draft version.

    Args:
        name:              Pipeline name (2–57 chars, alphanumeric/hyphens/spaces).
        description:       Pipeline description (20–256 chars).
        version:           Initial version in semver format (e.g. "1.0.0").
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
        project_id:        Project ID (falls back to the session default; see set_default_project).
        pipeline_id:       Optional UUID to assign as the pipeline ID.
        input_parameters:  List of input parameter definitions.
        secrets:           List of secret definitions.
        output_parameters: List of output parameter definitions.
        tags:              List of tag strings.
        steps:             List of step definitions.
        metadata:          Arbitrary metadata map.
        storages:          List of pipeline storage definitions.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.create_project_pipeline(
            pa_init.get_session(), org, proj, name, description, version,
            pipeline_id=pipeline_id or None,
            input_parameters=input_parameters,
            secrets=secrets,
            output_parameters=output_parameters,
            tags=tags,
            steps=steps,
            metadata=metadata,
            storages=storages,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error creating project pipeline '{name}': {e}"


@mcp.tool()
@_require_auth
def update_project_pipeline(
    pipeline_id: str,
    org_id: str = "",
    project_id: str = "",
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update the basic information of a project-level pipeline (name, description, tags).

    Args:
        pipeline_id:  The pipeline unique identifier (UUID).
        org_id:       Organisation ID (falls back to the session default; see set_default_organization).
        project_id:   Project ID (falls back to the session default; see set_default_project).
        name:         New pipeline name (2–57 chars).
        description:  New pipeline description (20–256 chars).
        tags:         New list of tag strings.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.update_project_pipeline(
            pa_init.get_session(), org, proj, pipeline_id, name=name, description=description, tags=tags
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error updating project pipeline '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def create_project_pipeline_version(
    pipeline_id: str,
    org_id: str = "",
    project_id: str = "",
    version: str = "",
    base_version: str = "",
    steps: list | None = None,
    input_parameters: list | None = None,
    secrets: list | None = None,
    output_parameters: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> str:
    """Create a new version of an existing project-level pipeline.

    Args:
        pipeline_id:       The pipeline unique identifier (UUID).
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
        project_id:        Project ID (falls back to the session default; see set_default_project).
        version:           New version number in semver format (e.g. "1.1.0").
        base_version:      Existing version to copy configuration from.
        steps:             List of step definitions.
        input_parameters:  List of input parameter definitions.
        secrets:           List of secret definitions.
        output_parameters: List of output parameter definitions.
        metadata:          Arbitrary metadata map.
        storages:          List of pipeline storage definitions.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.create_project_pipeline_version(
            pa_init.get_session(), org, proj, pipeline_id,
            version=version or None,
            base_version=base_version or None,
            steps=steps,
            input_parameters=input_parameters,
            secrets=secrets,
            output_parameters=output_parameters,
            metadata=metadata,
            storages=storages,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error creating version for project pipeline '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def update_project_pipeline_version(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
    project_id: str = "",
    input_parameters: list | None = None,
    output_parameters: list | None = None,
    secrets: list | None = None,
    steps: list | None = None,
    metadata: dict | None = None,
    storages: list | None = None,
) -> str:
    """Update a draft project pipeline version (only Draft status versions can be updated).

    Args:
        pipeline_id:       The pipeline unique identifier (UUID).
        pipeline_version:  Version string in semver format (e.g. "1.0.0").
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
        project_id:        Project ID (falls back to the session default; see set_default_project).
        input_parameters:  Replacement list of input parameter definitions.
        output_parameters: Replacement list of output parameter definitions.
        secrets:           Replacement list of secret definitions.
        steps:             Replacement list of step definitions.
        metadata:          Replacement metadata map.
        storages:          Replacement list of pipeline storage definitions.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.update_project_pipeline_version(
            pa_init.get_session(), org, proj, pipeline_id, pipeline_version,
            input_parameters=input_parameters,
            output_parameters=output_parameters,
            secrets=secrets,
            steps=steps,
            metadata=metadata,
            storages=storages,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error updating project pipeline version '{pipeline_version}': {e}"


@mcp.tool()
@_require_auth
def delete_draft_project_pipeline_version(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
    project_id: str = "",
) -> str:
    """Delete a draft project pipeline version.

    Only Draft versions that are not in use can be deleted.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
        project_id:       Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        pa_utils.delete_draft_project_pipeline_version(
            pa_init.get_session(), org, proj, pipeline_id, pipeline_version
        )
        return f"Project pipeline version '{pipeline_version}' for pipeline '{pipeline_id}' deleted successfully."
    except Exception as e:
        return f"Error deleting project pipeline version '{pipeline_version}': {e}"


@mcp.tool()
@_require_auth
def list_project_pipelines(
    org_id: str = "",
    project_id: str = "",
    owned: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List all pipelines available within a specific project.

    Args:
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
        owned:       True to return only pipelines owned by this org.
        offset:      Number of items to skip.
        limit:       Maximum number of items to return.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.list_project_pipelines(pa_init.get_session(), org, proj, owned=owned, offset=offset, limit=limit)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing project pipelines: {e}"


@mcp.tool()
@_require_auth
def list_project_pipeline_versions(
    pipeline_id: str,
    org_id: str = "",
    project_id: str = "",
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List all versions of a specific project pipeline.

    Args:
        pipeline_id: The pipeline unique identifier (UUID).
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
        offset:      Number of items to skip.
        limit:       Maximum number of items to return.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.list_project_pipeline_versions(
            pa_init.get_session(), org, proj, pipeline_id, offset=offset, limit=limit
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing versions for project pipeline '{pipeline_id}': {e}"


@mcp.tool()
@_require_auth
def get_project_pipeline_version(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
    project_id: str = "",
) -> str:
    """Get full details of a specific project pipeline version.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
        project_id:       Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.get_project_pipeline_version(
            pa_init.get_session(), org, proj, pipeline_id, pipeline_version
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting project pipeline version '{pipeline_version}': {e}"


@mcp.tool()
@_require_auth
def trigger_project_pipeline(
    pipeline_id: str,
    pipeline_version: str,
    org_id: str = "",
    project_id: str = "",
    inputs: dict | None = None,
    secrets: dict | None = None,
    job_priority: int | None = None,
) -> str:
    """Trigger a project-level pipeline and return the created job.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
        project_id:       Project ID (falls back to the session default; see set_default_project).
        inputs:           Map of input parameter names to values.
        secrets:          Map of secret names to values injected into the pipeline.
        job_priority:     Job priority – 0 is the highest priority.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.trigger_project_pipeline(
            pa_init.get_session(), org, proj, pipeline_id, pipeline_version,
            inputs=inputs, secrets=secrets, job_priority=job_priority,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error triggering project pipeline '{pipeline_id}' v{pipeline_version}: {e}"


@mcp.tool()
@_require_auth
def change_project_pipeline_status(
    pipeline_id: str,
    pipeline_version: str,
    lifecycle_status: str,
    org_id: str = "",
    project_id: str = "",
    archiving_date: str = "",
) -> str:
    """Change the lifecycle status of a project pipeline version.

    Valid lifecycle_status values: Draft, Available, Deprecated, Archived.

    Args:
        pipeline_id:      The pipeline unique identifier (UUID).
        pipeline_version: Version string in semver format (e.g. "1.0.0").
        lifecycle_status: Target lifecycle status.
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
        project_id:       Project ID (falls back to the session default; see set_default_project).
        archiving_date:   UTC date-time (ISO 8601) used when requesting Deprecated status.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.change_project_pipeline_status(
            pa_init.get_session(), org, proj, pipeline_id, pipeline_version,
            lifecycle_status, archiving_date=archiving_date or None,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error changing status for project pipeline '{pipeline_id}': {e}"


# ---------------------------------------------------------------------------
# Job tools – organisation level
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def list_jobs(
    org_id: str = "",
    statuses: list[str] | None = None,
    pipeline_ids: list[str] | None = None,
    automation_ids: list[str] | None = None,
    order_by: str | None = None,
    order: str | None = None,
    inputs: dict | None = None,
    include_all_org_project_jobs: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List pipeline jobs for the organisation, with optional filtering and sorting.

    Args:
        org_id:         Organisation ID (falls back to the session default; see set_default_organization).
        statuses:       Filter by job status. Valid values: Queued, Pending, Running,
                        Succeeded, Failed, Error, Terminated, Suspended, Unknown.
        pipeline_ids:   Filter by pipeline IDs.
        automation_ids: Filter by automation IDs (jobs created by those automations).
        order_by:       Sort field – CreatedAt, StartedAt, FinishedAt, UpdatedAt,
                        Progress, Status, Duration.
        order:          Sort direction – Asc or Desc.
        inputs:         Server-side input filter: a map of input parameter names to
                        values — returns only jobs whose input matches, e.g.
                        {"assetId": "123"} finds the job(s) triggered with that
                        asset. Much cheaper than listing all jobs and scanning.
        include_all_org_project_jobs: True to also include jobs from all projects
                        within the organisation (owner only).
        offset:         Number of items to skip.
        limit:          Maximum number of items to return.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.list_jobs(
            pa_init.get_session(), org,
            statuses=statuses, pipeline_ids=pipeline_ids,
            automation_ids=automation_ids,
            order_by=order_by, order=order,
            inputs=inputs,
            include_all_org_project_jobs=include_all_org_project_jobs,
            offset=offset, limit=limit,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing jobs: {e}"


@mcp.tool()
@_require_auth
def get_job(job_id: str, org_id: str = "") -> str:
    """Get full details of a specific organisation-level job, including step statuses.

    Args:
        job_id:  The job unique identifier (UUID).
        org_id:  Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_job(pa_init.get_session(), org, job_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting job '{job_id}': {e}"


@mcp.tool()
@_require_auth
def get_job_stats(org_id: str = "") -> str:
    """Get running and queued job statistics for the organisation.

    Returns running job count, queued job count, and the concurrency limit.

    Args:
        org_id: Organisation ID (falls back to the session default; see set_default_organization).
    """
    if _vpc.is_vpc():
        return (
            "Job statistics are not available in this private cloud's automation "
            "API version (verified live: the route returns 404). Use "
            "list_jobs with a status filter to gauge queue depth instead."
        )

    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_job_stats(pa_init.get_session(), org)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting job stats: {e}"


@mcp.tool()
@_require_auth
def terminate_job(job_id: str, org_id: str = "") -> str:
    """Terminate (cancel) a running or queued organisation-level job.

    Args:
        job_id:  The job unique identifier (UUID).
        org_id:  Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.terminate_job(pa_init.get_session(), org, job_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error terminating job '{job_id}': {e}"


@mcp.tool()
@_require_auth
def resume_job(job_id: str, step_id: str, org_id: str = "", parameters: dict | None = None) -> str:
    """Resume a suspended organisation-level job at its suspended step.

    Args:
        job_id:     The job unique identifier (UUID).
        step_id:    The suspended step's id within the job (see get_job's steps —
                    resume is step-scoped in the API).
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        parameters: Optional values for a suspend step that waits for user-supplied
                    input — passed through as the resume request's parameters map.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.resume_job(pa_init.get_session(), org, job_id, step_id, parameters=parameters)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error resuming job '{job_id}' step '{step_id}': {e}"


@mcp.tool()
@_require_auth
def approve_job_step(
    job_id: str,
    step_id: str,
    approved: bool,
    org_id: str = "",
    comment: str = "",
) -> str:
    """Approve or reject a suspended step in an organisation-level job.

    Args:
        job_id:    The job unique identifier (UUID).
        step_id:   The step unique identifier.
        approved:  True to approve, False to reject.
        org_id:    Organisation ID (falls back to the session default; see set_default_organization).
        comment:   Optional comment explaining the approval or rejection.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.approve_job_step(pa_init.get_session(), org, job_id, step_id, approved, comment=comment)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error approving step '{step_id}' in job '{job_id}': {e}"


# ---------------------------------------------------------------------------
# Job tools – project level
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def list_project_jobs(
    org_id: str = "",
    project_id: str = "",
    statuses: list[str] | None = None,
    pipeline_ids: list[str] | None = None,
    automation_ids: list[str] | None = None,
    order_by: str | None = None,
    order: str | None = None,
    inputs: dict | None = None,
    include_all_org_project_jobs: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List pipeline jobs for a specific project, with optional filtering.

    Args:
        org_id:         Organisation ID (falls back to the session default; see set_default_organization).
        project_id:     Project ID (falls back to the session default; see set_default_project).
        statuses:       Filter by job status. Valid values: Queued, Pending, Running,
                        Succeeded, Failed, Error, Terminated, Suspended, Unknown.
        pipeline_ids:   Filter by pipeline IDs.
        automation_ids: Filter by automation IDs (jobs created by those automations).
        order_by:       Sort field – CreatedAt, StartedAt, FinishedAt, UpdatedAt,
                        Progress, Status, Duration.
        order:          Sort direction – Asc or Desc.
        inputs:         Server-side input filter: a map of input parameter names to
                        values — returns only jobs whose input matches, e.g.
                        {"assetId": "123"} finds the job(s) triggered with that
                        asset. Much cheaper than listing all jobs and scanning.
        include_all_org_project_jobs: True to also include jobs from all projects
                        within the organisation (owner only).
        offset:         Number of items to skip.
        limit:          Maximum number of items to return.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.list_project_jobs(
            pa_init.get_session(), org, proj,
            statuses=statuses, pipeline_ids=pipeline_ids,
            automation_ids=automation_ids,
            order_by=order_by, order=order,
            inputs=inputs,
            include_all_org_project_jobs=include_all_org_project_jobs,
            offset=offset, limit=limit,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing project jobs: {e}"


@mcp.tool()
@_require_auth
def get_project_job(job_id: str, org_id: str = "", project_id: str = "") -> str:
    """Get full details of a specific project job, including step statuses.

    Args:
        job_id:     The job unique identifier (UUID).
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.get_project_job(pa_init.get_session(), org, proj, job_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting project job '{job_id}': {e}"


@mcp.tool()
@_require_auth
def terminate_project_job(job_id: str, org_id: str = "", project_id: str = "") -> str:
    """Terminate (cancel) a running or queued project job.

    Args:
        job_id:     The job unique identifier (UUID).
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.terminate_project_job(pa_init.get_session(), org, proj, job_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error terminating project job '{job_id}': {e}"


@mcp.tool()
@_require_auth
def resume_project_job(job_id: str, step_id: str, org_id: str = "", project_id: str = "", parameters: dict | None = None) -> str:
    """Resume a suspended project job at its suspended step.

    Args:
        job_id:     The job unique identifier (UUID).
        step_id:    The suspended step's id within the job (see get_project_job's
                    steps — resume is step-scoped in the API).
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Project ID (falls back to the session default; see set_default_project).
        parameters: Optional values for a suspend step that waits for user-supplied
                    input — passed through as the resume request's parameters map.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.resume_project_job(pa_init.get_session(), org, proj, job_id, step_id, parameters=parameters)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error resuming project job '{job_id}' step '{step_id}': {e}"


@mcp.tool()
@_require_auth
def approve_project_job_step(
    job_id: str,
    step_id: str,
    approved: bool,
    org_id: str = "",
    project_id: str = "",
    comment: str = "",
) -> str:
    """Approve or reject a suspended step in a project job.

    Args:
        job_id:     The job unique identifier (UUID).
        step_id:    The step unique identifier.
        approved:   True to approve, False to reject.
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Project ID (falls back to the session default; see set_default_project).
        comment:    Optional comment explaining the approval or rejection.
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.approve_project_job_step(
            pa_init.get_session(), org, proj, job_id, step_id, approved, comment=comment
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error approving step '{step_id}' in project job '{job_id}': {e}"


# ---------------------------------------------------------------------------
# Log tools
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def get_job_step_logs(job_id: str, step_id: str, org_id: str = "") -> str:
    """Get logs for a specific step in an organisation-level pipeline job.

    Args:
        job_id:   The job unique identifier (UUID).
        step_id:  The step unique identifier.
        org_id:   Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_job_step_logs(pa_init.get_session(), org, job_id, step_id)
        return json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
    except Exception as e:
        return f"Error getting logs for step '{step_id}' in job '{job_id}': {e}"


@mcp.tool()
@_require_auth
def get_project_job_step_logs(
    job_id: str,
    step_id: str,
    org_id: str = "",
    project_id: str = "",
) -> str:
    """Get logs for a specific step in a project pipeline job.

    Args:
        job_id:     The job unique identifier (UUID).
        step_id:    The step unique identifier.
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.get_project_job_step_logs(pa_init.get_session(), org, proj, job_id, step_id)
        return json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
    except Exception as e:
        return f"Error getting logs for step '{step_id}' in project job '{job_id}': {e}"


@mcp.tool()
@_require_auth
def get_job_logs(job_id: str, org_id: str = "") -> str:
    """Get logs for an entire organisation-level pipeline job (all steps at once).

    Use get_job_step_logs instead to fetch a single step's logs.

    Args:
        job_id:  The job unique identifier (UUID).
        org_id:  Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_job_logs(pa_init.get_session(), org, job_id)
        return json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
    except Exception as e:
        return f"Error getting logs for job '{job_id}': {e}"


@mcp.tool()
@_require_auth
def get_project_job_logs(
    job_id: str,
    org_id: str = "",
    project_id: str = "",
) -> str:
    """Get logs for an entire project pipeline job (all steps at once).

    Use get_project_job_step_logs instead to fetch a single step's logs.

    Args:
        job_id:     The job unique identifier (UUID).
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj = _proj(project_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not proj:
        return "Error: no project selected. Ask the user which project to use, then set_default_project (or pass project_id)."
    try:
        result = pa_utils.get_project_job_logs(pa_init.get_session(), org, proj, job_id)
        return json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
    except Exception as e:
        return f"Error getting logs for project job '{job_id}': {e}"


# ---------------------------------------------------------------------------
# App and Action tools
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def list_apps(
    org_id: str = "",
    owned: bool | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List all apps accessible by the organisation, including their actions.

    Returns the latest version of each app. Each result includes the app's
    actions with their actionIds, which can be used as step actionIds in pipelines.

    Args:
        org_id:  Organisation ID (falls back to the session default; see set_default_organization).
        owned:   True to return only apps owned by this org.
        offset:  Number of items to skip (pagination).
        limit:   Maximum number of items to return.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.list_apps(pa_init.get_session(), org, owned=owned, offset=offset, limit=limit)
        for item in result.get("results", []):
            item.get("app", {}).pop("logo", None)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing apps: {e}"


@mcp.tool()
@_require_auth
def list_app_versions(
    app_id: str,
    org_id: str = "",
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List all versions of a specific app.

    Args:
        app_id:  The app unique identifier (UUID).
        org_id:  Organisation ID (falls back to the session default; see set_default_organization).
        offset:  Number of items to skip.
        limit:   Maximum number of items to return.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.list_app_versions(pa_init.get_session(), org, app_id, offset=offset, limit=limit)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing versions for app '{app_id}': {e}"


@mcp.tool()
@_require_auth
def get_app_version(
    app_id: str,
    app_version: str,
    org_id: str = "",
) -> str:
    """Get full details of a specific app version, including all its actions and their actionIds.

    Use this to discover the actionId values needed when building pipeline steps.

    Args:
        app_id:      The app unique identifier (UUID).
        app_version: Version string in semver format (e.g. "1.0.0").
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_app_version(pa_init.get_session(), org, app_id, app_version)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting app version '{app_version}' for app '{app_id}': {e}"


@mcp.tool()
@_require_auth
def get_app_action(
    app_id: str,
    app_version: str,
    action_id: str,
    org_id: str = "",
) -> str:
    """Get full details of a specific app action, including its input/output parameters.

    Args:
        app_id:      The app unique identifier (UUID).
        app_version: Version string in semver format (e.g. "1.0.0").
        action_id:   The action identifier.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_app_action(pa_init.get_session(), org, app_id, app_version, action_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting action '{action_id}' for app '{app_id}' v{app_version}: {e}"


# ---------------------------------------------------------------------------
# Automation tools (read-only)
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def list_automations(
    org_id: str = "",
    project_id: str = "",
    include_fields: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List automations (event-driven pipeline triggers) for the organisation or a project.

    Automations bind a pipeline to a trigger (e.g. a webhook or Unity Cloud
    event) so jobs run without a manual trigger_pipeline call. This tool is
    read-only; automations are created and edited in the Unity Cloud dashboard.

    Args:
        org_id:         Organisation ID (falls back to the session default; see set_default_organization).
        project_id:     Optional project ID — pass to list against the
                        project-scoped endpoint instead of the organisation one.
        include_fields: Comma-separated extra fields to include in the response.
                        Supported value: "bot".
        offset:         Number of items to skip.
        limit:          Maximum number of items to return.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        if project_id:
            result = pa_utils.list_project_automations(
                pa_init.get_session(), org, project_id,
                include_fields=include_fields, offset=offset, limit=limit,
            )
        else:
            result = pa_utils.list_automations(
                pa_init.get_session(), org,
                include_fields=include_fields, offset=offset, limit=limit,
            )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing automations: {e}"


@mcp.tool()
@_require_auth
def get_automation(
    automation_id: str,
    org_id: str = "",
    project_id: str = "",
    include_fields: str | None = None,
) -> str:
    """Get full details of a specific automation (event-driven pipeline trigger).

    This tool is read-only; automations are created and edited in the Unity
    Cloud dashboard.

    Args:
        automation_id:  The automation unique identifier (UUID).
        org_id:         Organisation ID (falls back to the session default; see set_default_organization).
        project_id:     Optional project ID — pass to read from the
                        project-scoped endpoint instead of the organisation one.
        include_fields: Comma-separated extra fields to include in the response.
                        Supported value: "bot".
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        if project_id:
            result = pa_utils.get_project_automation(
                pa_init.get_session(), org, project_id, automation_id,
                include_fields=include_fields,
            )
        else:
            result = pa_utils.get_automation(
                pa_init.get_session(), org, automation_id,
                include_fields=include_fields,
            )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting automation '{automation_id}': {e}"


# ---------------------------------------------------------------------------
# Pipeline template tools
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def list_pipeline_templates(
    org_id: str = "",
    app_ids: list[str] | None = None,
    tags: list[str] | None = None,
    metadata: list[str] | None = None,
    system_metadata: list[str] | None = None,
    used_with: list[str] | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """List pipeline templates accessible to the organisation, with optional filtering.

    Pipeline templates are reusable pipeline definitions that steps can
    reference (templateref) instead of repeating the definition inline.

    Args:
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
        app_ids:         Filter by the app IDs the templates belong to.
        tags:            Filter by template tags.
        metadata:        Filter by metadata entries.
        system_metadata: Filter by system metadata flags.
        used_with:       Filter by the app IDs the templates are associated with.
        offset:          Number of items to skip.
        limit:           Maximum number of items to return.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.list_pipeline_templates(
            pa_init.get_session(), org,
            app_ids=app_ids, tags=tags, metadata=metadata,
            system_metadata=system_metadata, used_with=used_with,
            offset=offset, limit=limit,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing pipeline templates: {e}"


@mcp.tool()
@_require_auth
def get_pipeline_template(
    pipeline_template_id: str,
    org_id: str = "",
) -> str:
    """Get full details of a specific pipeline template.

    Args:
        pipeline_template_id: The pipeline template unique identifier.
        org_id:               Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        result = pa_utils.get_pipeline_template(pa_init.get_session(), org, pipeline_template_id)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting pipeline template '{pipeline_template_id}': {e}"


# ---------------------------------------------------------------------------
# Auth tools
# ---------------------------------------------------------------------------

@mcp.tool()
def unity_login() -> str:
    """Sign in to Unity Cloud using a browser-based PKCE flow.

    Opens the system browser to the Unity sign-in page and waits for the redirect
    callback. The resulting tokens are cached on disk under ~/.uap_mcp/token.json
    (or $UAP_MCP_HOME) and refreshed automatically; subsequent server starts won't
    re-prompt until the refresh token can no longer be used. The cache is shared
    with the Asset Manager MCP server, so one login authenticates both.
    """
    try:
        pa_init.trigger_user_login()
    except Exception as e:
        return f"Unity login failed: {e}"
    return "Logged in to Unity Cloud successfully."


@mcp.tool()
def unity_logout() -> str:
    """Clear the cached Unity user-login tokens.

    The token cache is shared with the Asset Manager MCP server, so this signs
    you out of both Pipeline Automation and Asset Manager.
    """
    pa_init.logout()
    return (
        "Cleared cached Unity tokens (shared with Asset Manager — both servers "
        "are now signed out). Call `unity_login` to sign in again."
    )


@mcp.tool()
def unity_auth_status() -> str:
    """Report whether the server can currently make authenticated Pipeline Automation calls.

    Returns 'ready' or the message tools would return when called without a
    valid identity.
    """
    err = pa_init.auth_status_message()
    return json.dumps(
        {
            "ready": err is None,
            "message": err or "Authenticated.",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
