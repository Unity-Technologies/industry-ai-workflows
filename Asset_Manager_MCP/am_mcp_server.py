"""
Asset_Manager_MCP Server
========================

Exposes Asset Manager asset/collection operations as MCP tools.

Auth is a browser-based PKCE user login: call the `unity_login` tool first.
Tokens are cached on disk and refreshed on demand.

Org/project scope is chosen interactively per session: list_organizations →
ask the user → set_default_organization, then list_projects → ask the user →
set_default_project (or create_project). Every tool also accepts explicit
org_id / project_id arguments.

Start the server:
    python am_mcp_server.py
"""

import functools
import json
import os

from dotenv import load_dotenv

load_dotenv()  # load .env before any auth init resolves env vars

from mcp.server.mcpserver import MCPServer

from am_utils import am_init, am_rest, dependency_vocab
from am_utils.client_identity import ClientIdentityExtension
from am_utils.local_paths import assert_safe_local_path
from am_utils.unity_auth import vpc as _vpc

# The browser PKCE flow is deferred to the unity_login tool so the server can
# start cleanly under marketplace install (no terminal to prompt at).


def _require_auth(func):
    """Decorator: short-circuit a tool call when the current identity isn't usable.

    Returns the user-facing message (telling the caller to run unity_login) so the
    model can react, instead of letting a REST call throw an opaque error mid-call.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        err = am_init.auth_status_message()
        if err:
            return err
        return func(*args, **kwargs)
    return wrapper

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = MCPServer(
    name="Asset_Manager_MCP",
    instructions=(
        "Unity Asset Manager MCP server. "
        "Exposes asset, collection, and project operations on Unity Cloud "
        "Asset Manager: creating and versioning assets, uploading/downloading "
        "files, metadata, references, and org/project scoping. "
        "If the user mentions Unity or Unity workflows beyond these tools "
        "(e.g. installing Unity Editor versions, adding build-support modules, "
        "or opening Unity projects from the terminal), point them to the "
        "Unity CLI (https://docs.unity.com/en-us/unity-cli/use-unity-cli) "
        "and offer to run it for them alongside these tools."
    ),
    extensions=[ClientIdentityExtension()],
)

# Default org / project resolved from environment; individual tools can override.
_ORG_ID = os.environ.get("UNITY_ORG_ID", "")
_PROJECT_ID = os.environ.get("UNITY_PROJECT_ID", "")
# Numeric genesis org ID needed by the list_projects endpoint.
# set UNITY_ORG_GENESIS_ID in the environment if known; otherwise auto-resolved on first use.
_ORG_GENESIS_ID = os.environ.get("UNITY_ORG_GENESIS_ID", "")
_LAST_TARGET_VERSION_BY_ASSET: dict[tuple[str, str, str], tuple[str, str]] = {}
_GENESIS_ID_CACHE: dict[str, str] = {}


def _org(org_id: str) -> str:
    return org_id or _ORG_ID


def _proj(project_id: str) -> str:
    return project_id or _PROJECT_ID


def _get_genesis_id(session, uuid_org_id: str) -> str:
    """Return the numeric genesisId required by the project endpoints
    (list_projects, create_project) and org-level template endpoints.

    Private cloud (VPC): there is no Genesis identity service — organizations
    live in the deployment's own identity system and their ids are used
    as-supplied.

    Resolution order:
      1. UNITY_ORG_GENESIS_ID env var — only when the requested org is the
         configured default org (UNITY_ORG_ID), so the override can never
         redirect a call aimed at a different organization.
      2. Already-numeric input — treated as a genesisId and used as-is.
      3. Cache, then auto-resolve via list_organizations by matching the UUID.

    Raises RuntimeError (listing the organizations that were found) when the
    supplied org does not match any organization visible to this account —
    never silently falls back to a different org.
    """
    if _vpc.is_vpc():
        return uuid_org_id

    if _ORG_GENESIS_ID and _ORG_ID and uuid_org_id == _ORG_ID:
        return _ORG_GENESIS_ID
    if uuid_org_id.isdigit():
        # Caller already supplied a numeric genesisId.
        return uuid_org_id
    cached = _GENESIS_ID_CACHE.get(uuid_org_id)
    if cached:
        return cached
    try:
        orgs = am_rest.list_organizations(session)
    except Exception as e:
        raise RuntimeError(
            f"Could not resolve the numeric organization id for '{uuid_org_id}': "
            f"listing organizations failed ({e}). Set UNITY_ORG_GENESIS_ID in .env "
            "(with UNITY_ORG_ID set to the matching org UUID) or pass the numeric "
            "organization id directly."
        ) from e
    for o in orgs:
        if o.id == uuid_org_id or (o.genesis_id and o.genesis_id == uuid_org_id):
            _GENESIS_ID_CACHE[uuid_org_id] = o.genesis_id
            return o.genesis_id
    found = "; ".join(f"{o.name} (id={o.id})" for o in orgs) or "none"
    raise RuntimeError(
        f"Organization '{uuid_org_id}' does not match any organization visible to "
        f"this account. Organizations found: {found}. Check org_id / UNITY_ORG_ID."
    )


def _collection_exists(session, org_id: str, project_id: str, collection_path: str) -> bool:
    collections = am_rest.list_collections(session, org_id, project_id)
    return any(c.name == collection_path or c.path == collection_path for c in collections)


def _project_list_prompt(org_id: str, header: str) -> str:
    try:
        session = am_init.get_session()
        projects = am_rest.list_projects(session, _get_genesis_id(session, org_id))
        choices = [{"id": p.id, "name": p.name} for p in projects]
        if not choices:
            return (
                f"{header}\n"
                "This organization has no projects yet. Ask the user whether to "
                "create one (create_project), then set_default_project."
            )
        return (
            f"{header}\n"
            "Ask the user to choose a project by name (project_name) or id (project_id), "
            "or to create a new one (create_project).\n"
            f"Available projects:\n{json.dumps(choices, indent=2)}"
        )
    except Exception as e:
        return f"{header}\nCould not list projects for org '{org_id}': {e}"


def _resolve_project_id(org_id: str, project_id: str = "", project_name: str = "") -> tuple[str | None, str | None]:
    if project_id:
        return project_id, None

    if project_name:
        try:
            session = am_init.get_session()
            projects = am_rest.list_projects(session, _get_genesis_id(session, org_id))
        except Exception as e:
            return None, f"Error resolving project name '{project_name}': {e}"

        exact_matches = [p for p in projects if p.name == project_name]
        if len(exact_matches) == 1:
            return exact_matches[0].id, None

        casefold_matches = [p for p in projects if p.name.casefold() == project_name.casefold()]
        if len(casefold_matches) == 1:
            return casefold_matches[0].id, None

        return None, _project_list_prompt(
            org_id,
            f"Project name '{project_name}' was not uniquely resolved."
        )

    configured = _proj("")
    if configured and configured != "your_project_id":
        return configured, None

    return None, _project_list_prompt(
        org_id,
        "No project selected."
    )


def _resolve_status_name(requested_status: str, available_statuses: list[str]) -> str | None:
    """Resolve a requested status value against available statuses using case-insensitive matching."""
    for status in available_statuses:
        if status == requested_status:
            return status
    for status in available_statuses:
        if status.casefold() == requested_status.casefold():
            return status
    return None


def _resolve_asset_for_name(org_id: str, project_id: str, asset_name: str):
    """Resolve an asset by name, preferring the last create-targeted version in this process."""
    session = am_init.get_session()
    cached = _LAST_TARGET_VERSION_BY_ASSET.get((org_id, project_id, asset_name))
    if cached:
        try:
            return am_rest.get_asset(session, org_id, project_id, cached[0], cached[1])
        except Exception:
            pass
    return am_rest.search_assets_by_name(session, org_id, project_id, asset_name)


@mcp.tool()
@_require_auth
def set_default_organization(org_id: str = "", org_name: str = "") -> str:
    """Set the default organization for subsequent tool calls in this server process.

    Typical new-session flow: call list_organizations, ask the user which
    organization to work in, then call this with their choice. Next, do the
    same for the project: list_projects → ask the user → set_default_project /
    set_default_project_by_name, or create_project if the org has no suitable
    project yet.

    Args:
        org_id:   Organization ID (UUID or numeric genesis id) from list_organizations.
        org_name: Exact organization name — resolved via list_organizations.
    """
    global _ORG_ID
    if not org_id and not org_name:
        return "Error: provide org_id or org_name (list_organizations shows both)."
    if _vpc.is_vpc():
        # Private cloud has no organization-discovery service to verify against
        # (that is public Unity Cloud only), so accept the id as given — it is
        # the one from the user's dashboard URL.
        if not org_id:
            return (
                "On private cloud deployments organizations cannot be looked up by "
                "name. Ask the user for the organization id from their dashboard URL "
                "and pass it as org_id."
            )
        _ORG_ID = org_id
        return (
            f"Default organization set to '{org_id}'. Next: call list_projects and ask "
            "the user which project to work in."
        )
    try:
        session = am_init.get_session()
        orgs = am_rest.list_organizations(session)
    except Exception as e:
        if org_id:
            _ORG_ID = org_id
            return f"Default organization set to '{org_id}' (could not verify: {e})."
        return f"Error resolving organization name '{org_name}': {e}"

    match = None
    if org_id:
        match = next((o for o in orgs if o.id == org_id or o.genesis_id == org_id), None)
    else:
        named = [o for o in orgs if o.name == org_name]
        if not named:
            named = [o for o in orgs if o.name.casefold() == org_name.casefold()]
        if len(named) == 1:
            match = named[0]
        elif len(named) > 1:
            ids = ", ".join(o.id for o in named)
            return f"Multiple organizations named '{org_name}' ({ids}) — pass org_id instead."
    if match is None:
        listing = "\n".join(f"{i + 1}. {o.name} [{o.id}]" for i, o in enumerate(orgs))
        return f"Organization not found. Ask the user to choose one of:\n{listing}"

    _ORG_ID = match.id
    return (
        f"Default organization set to '{match.name}' (id={match.id}). "
        "Next: call list_projects and ask the user which project to use "
        "(set_default_project / set_default_project_by_name), or create_project "
        "if none fits."
    )


@mcp.tool()
@_require_auth
def set_default_project(project_id: str) -> str:
    """Set the default project id for subsequent tool calls in this server process."""
    global _PROJECT_ID
    if not project_id or project_id == "your_project_id":
        return "Error setting default project: provide a real project_id."
    _PROJECT_ID = project_id
    return f"Default project id set to '{_PROJECT_ID}'."


@mcp.tool()
@_require_auth
def set_default_project_by_name(project_name: str, org_id: str = "") -> str:
    """Set the default project by exact project name for this server process."""
    global _PROJECT_ID
    org = _org(org_id)
    if not org:
        return "Error setting default project: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    resolved_project_id, error = _resolve_project_id(org, project_name=project_name)
    if error:
        # Exact / case-fold matching failed — try substring as a convenience fallback.
        try:
            session = am_init.get_session()
            projects = am_rest.list_projects(session, _get_genesis_id(session, org))
            partial = [p for p in projects if project_name.casefold() in p.name.casefold()]
            if len(partial) == 1:
                _PROJECT_ID = partial[0].id
                matched_name = partial[0].name
                return (
                    f"Default project set to '{matched_name}' (id={_PROJECT_ID}) "
                    f"via partial match for '{project_name}'."
                )
        except Exception:
            pass
        return error

    _PROJECT_ID = resolved_project_id
    return f"Default project set to '{project_name}' (id={_PROJECT_ID})."


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
@_require_auth
def create_asset(
    asset_name: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    asset_type: str = "",
    description: str = "",
) -> str:
    """Create a new asset, or create a new uploadable version if the asset already exists.

    Returns the target asset id/version to use with upload_files_to_asset.

    Args:
        asset_name:  Name of the asset to create or version.
        tags:        Optional list of tag strings. When versioning an existing asset,
                     supplied tags replace the inherited ones; omit to keep them.
        metadata:    Optional dict of custom metadata field values, e.g. {"source_format": "CATIA"}.
                     Keys must match field definitions created via create_field_definition.
        asset_type:  Asset type shown in the dashboard. Valid values:
                     "2D Asset", "3D Model", "Animation", "Asset", "Audio", "Document",
                     "Environment", "Font", "Image", "Material", "Other", "Prefab",
                     "Scene", "Script", "Shader", "Unity Editor", "Unity Package", "Video".
                     Pick the specific one — "Prefab", "Scene", "Shader" and "Animation"
                     are real values, so Unity content should not be dumped into
                     "Unity Editor" or "Other". Legacy unspaced spellings ("3DModel",
                     "2DAsset", "UnityEditor") are still accepted and mapped.
                     New assets default to "3D Model" when left empty; when versioning
                     an existing asset, empty keeps its current type. Use
                     change_asset_type to retype without creating a version.
        description: Asset description shown in the Asset Manager dashboard. Ask the user
                     what they want here rather than inventing one; empty is fine.
                     When versioning, a supplied description replaces the inherited one.
    """
    org = _org(org_id)
    resolved_tags: list[str] = tags or []

    if not org:
        return "Error creating asset: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error

    try:
        session = am_init.get_session()
        asset = am_rest.search_assets_by_name(session, org, proj, asset_name)
        action = "created"
        if asset is None:
            asset = am_rest.create_asset(
                session, org, proj, asset_name, resolved_tags, metadata,
                asset_type or "3D Model", description
            )
        else:
            action = "new_version"
            if asset.is_frozen is False:
                am_rest.freeze_asset_version(session, org, proj, asset.id, asset.version)
            asset = am_rest.create_unfrozen_asset_version(session, org, proj, asset.id, asset.version)
            # A new version inherits the parent's values — re-apply anything the
            # caller supplied so it isn't silently lost.
            if metadata:
                asset = am_rest.update_asset_metadata(session, org, proj, asset.id, asset.version, metadata)
            if tags is not None or description:
                asset = am_rest.update_asset(
                    session, org, proj, asset.id, asset.version,
                    description=description or None,
                    tags=resolved_tags if tags is not None else None,
                )
            if asset_type:
                am_rest.set_primary_type(session, org, proj, asset.id, asset.version, asset_type)
                asset = am_rest.get_asset(session, org, proj, asset.id, asset.version)

        _LAST_TARGET_VERSION_BY_ASSET[(org, proj, asset_name)] = (asset.id, asset.version)

        return json.dumps(
            {
                "action": action,
                "name": asset.name,
                "id": asset.id,
                "version": asset.version,
                "is_frozen": asset.is_frozen,
                "primary_type": asset.primary_type or None,
                "description": asset.description or None,
                "tags": asset.tags or None,
                "metadata": asset.metadata or None,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error creating asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def create_new_draft_version(
    asset_name: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
    tags: list[str] | None = None,
) -> str:
    """Create a new draft version for an existing asset.

    If the asset does not exist yet, this creates the initial draft asset.
    This is a clearer alias for callers who explicitly want a draft-ready upload target.
    """
    result = create_asset(
        asset_name=asset_name,
        org_id=org_id,
        project_id=project_id,
        project_name=project_name,
        tags=tags,
    )

    # Preserve non-JSON responses (errors/prompts) from create_asset.
    try:
        payload = json.loads(result)
    except Exception:
        return result

    payload["intent"] = "create_new_draft_version"
    if payload.get("action") == "new_version":
        payload["message"] = "New draft version created successfully."
    elif payload.get("action") == "created":
        payload["message"] = "Asset did not exist; initial draft asset created successfully."
    return json.dumps(payload, indent=2)


@mcp.tool()
@_require_auth
def upload_files_to_asset(
    asset_name: str,
    model_files: list[str],
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
    collection_path: str = "",
    freeze_after_upload: bool | None = None,
) -> str:
    """Upload local files to the current (unfrozen) version of an existing asset.

    freeze_after_upload:
      - True  -> freeze the asset version after upload
      - False -> leave the version unfrozen
      - None  -> return a prompt asking the caller to choose
    """
    org = _org(org_id)

    if not org:
        return "Error uploading files: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error

    try:
        session = am_init.get_session()
        asset = None
        cached = _LAST_TARGET_VERSION_BY_ASSET.get((org, proj, asset_name))
        if cached:
            try:
                cached_asset = am_rest.get_asset(session, org, proj, cached[0], cached[1])
                if cached_asset.is_frozen is False:
                    asset = cached_asset
            except Exception:
                asset = None

        if asset is None:
            asset = am_rest.search_assets_by_name(session, org, proj, asset_name)
        if asset is None:
            return f"Error uploading files: asset '{asset_name}' not found. Call create_asset first."
        if asset.is_frozen:
            return (
                f"Error uploading files: asset '{asset_name}' version {asset.version} is frozen. "
                "Call create_asset first to create a new uploadable version."
            )

        datasets = am_rest.get_dataset_list(session, org, proj, asset.id, asset.version)
        dataset_id = datasets[0].id
        failed_files: list[str] = []
        for model_file in model_files:
            try:
                am_rest.upload_file(session, org, proj, asset.id, asset.version, dataset_id, model_file)
            except Exception as file_err:
                err_str = str(file_err)
                if "codec can't encode" in err_str or "charmap" in err_str:
                    failed_files.append(
                        f"{model_file} (non-ASCII characters in path — rename the file and retry)"
                    )
                else:
                    failed_files.append(f"{model_file} ({file_err})")

        collection_linked = ""
        if collection_path:
            if not _collection_exists(session, org, proj, collection_path):
                am_rest.ensure_collection_path(session, org, proj, collection_path)
            am_rest.link_asset_to_collection(session, org, proj, collection_path, asset.id)
            collection_linked = collection_path

        uploaded_count = len(model_files) - len(failed_files)

        base_payload: dict = {
            "asset_name": asset.name,
            "asset_id": asset.id,
            "version": asset.version,
            "uploaded_files": uploaded_count,
            "collection": collection_linked or None,
        }
        if failed_files:
            base_payload["failed_files"] = failed_files

        if freeze_after_upload is True:
            am_rest.freeze_asset_version(session, org, proj, asset.id, asset.version)
            return json.dumps(
                {**base_payload, "frozen": True, "message": "Files uploaded and asset version frozen."},
                indent=2,
            )

        if freeze_after_upload is None:
            return json.dumps(
                {
                    **base_payload,
                    "frozen": False,
                    "prompt_required": True,
                    "message": "Files uploaded. Do you want to freeze this version now?",
                    "prompt": "Call upload_files_to_asset again with freeze_after_upload=true, or call freeze_asset.",
                },
                indent=2,
            )

        return json.dumps(
            {**base_payload, "frozen": False, "message": "Files uploaded and version left unfrozen."},
            indent=2,
        )
    except Exception as e:
        return f"Error uploading files to asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def download_files_from_asset(
    asset_name: str,
    download_folder: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Download all files from the source dataset of an asset to a local folder.

    Mirror of upload_files_to_asset. Resolves the asset by name (latest version
    by default), enumerates files in the primary/source dataset, and downloads
    each one into download_folder (created if missing).
    """
    org = _org(org_id)
    if not org:
        return "Error downloading files: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error

    try:
        session = am_init.get_session()
        asset = am_rest.search_assets_by_name(session, org, proj, asset_name)
        if asset is None:
            return f"Error downloading files: asset '{asset_name}' not found."

        datasets = am_rest.get_dataset_list(session, org, proj, asset.id, asset.version)
        dataset_id = datasets[0].id
        files = am_rest.get_file_list(session, org, proj, asset.id, asset.version, dataset_id)

        # am_rest.download_file validates each destination file, but the folder is created
        # first — so check it here too, or a hostile `download_folder` still gets a
        # directory tree made for it before the first file is refused.
        download_folder = assert_safe_local_path(
            download_folder, purpose="download folder", mode="write"
        )
        os.makedirs(download_folder, exist_ok=True)

        downloaded: list[str] = []
        failed: list[str] = []
        for f in files:
            cloud_path = f.path
            if not cloud_path:
                failed.append("<unknown> (could not resolve cloud path)")
                continue
            dest = os.path.join(download_folder, os.path.basename(cloud_path))
            try:
                am_rest.download_file(
                    session, org, proj, asset.id, asset.version, dataset_id, f.id, dest
                )
                downloaded.append(dest)
            except Exception as file_err:
                failed.append(f"{cloud_path} ({file_err})")

        payload: dict = {
            "asset_name": asset.name,
            "asset_id": asset.id,
            "version": asset.version,
            "dataset_id": dataset_id,
            "download_folder": download_folder,
            "downloaded_files": downloaded,
        }
        if failed:
            payload["failed_files"] = failed
        return json.dumps(payload, indent=2)
    except Exception as e:
        return f"Error downloading files from asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def upload_preview_image_to_asset(
    asset_name: str,
    image_file: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Upload a preview image to the preview dataset (second dataset) of an existing asset.

    The asset must already exist and have an unfrozen version. Call create_asset first if needed.

    Args:
        asset_name:  Name of the asset to upload the preview image to.
        image_file:  Absolute local path to the image file (PNG, JPG, etc.).
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)

    if not org:
        return "Error uploading preview image: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error

    try:
        session = am_init.get_session()
        asset = None
        cached = _LAST_TARGET_VERSION_BY_ASSET.get((org, proj, asset_name))
        if cached:
            try:
                cached_asset = am_rest.get_asset(session, org, proj, cached[0], cached[1])
                if cached_asset.is_frozen is False:
                    asset = cached_asset
            except Exception:
                asset = None

        if asset is None:
            asset = am_rest.search_assets_by_name(session, org, proj, asset_name)
        if asset is None:
            return f"Error uploading preview image: asset '{asset_name}' not found. Call create_asset first."
        if asset.is_frozen:
            return (
                f"Error uploading preview image: asset '{asset_name}' version {asset.version} is frozen. "
                "Call create_asset first to create a new uploadable version."
            )

        datasets = am_rest.get_dataset_list(session, org, proj, asset.id, asset.version)
        if len(datasets) < 2:
            raise ValueError(
                f"Asset {asset.id} v{asset.version} has only {len(datasets)} dataset(s); "
                "preview dataset not found."
            )
        preview_dataset_id = datasets[1].id
        am_rest.upload_file(session, org, proj, asset.id, asset.version, preview_dataset_id, image_file)
        # Uploading into the preview dataset does not by itself set the cover
        # image — designate the file via the version's previewFilePath.
        am_rest.update_asset(
            session, org, proj, asset.id, asset.version,
            preview_file_path=os.path.basename(image_file),
        )

        return json.dumps(
            {
                "asset_name": asset.name,
                "asset_id": asset.id,
                "version": asset.version,
                "preview_image": os.path.basename(image_file),
                "designated_as_cover": True,
                "message": "Preview image uploaded and set as the asset cover.",
            },
            indent=2,
        )
    except Exception as e:
        return f"Error uploading preview image to asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def batch_upload_assets(
    assets: list[dict],
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
    collection_path: str = "",
    freeze_after_upload: bool = True,
    default_asset_type: str = "3D Model",
) -> str:
    """Create and upload multiple assets in one call — ideal for uploading many CAD parts at once.

    Each entry in `assets` must have:
        - "name":  Asset name (str, required)
        - "file":  Absolute local file path (str, required)
        - "tags":  List of tag strings (optional)
        - "type":  Asset type string (optional, overrides default_asset_type per entry)

    Example:
        assets = [
            {"name": "Body", "file": "C:/out/body.glb", "tags": ["grinder"], "type": "3D Model"},
            {"name": "Schematic", "file": "C:/out/schematic.png", "type": "2DAsset"},
        ]

    Args:
        assets:              List of asset dicts (name, file, optional tags, optional type).
        org_id:              Organisation ID (falls back to the session default; see set_default_organization).
        project_id:          Project ID (falls back to the session default; see set_default_project).
        collection_path:     Collection to link every asset to (created if absent). Pass "" to skip.
        freeze_after_upload: Freeze each asset version after upload. Default True.
        default_asset_type:  Asset type applied to all entries that don't specify "type".
                             Valid values: "2D Asset", "3D Model", "Animation", "Asset",
                             "Audio", "Document", "Environment", "Font", "Image", "Material",
                             "Other", "Prefab", "Scene", "Script", "Shader", "Unity Editor",
                             "Unity Package", "Video". Legacy unspaced spellings are mapped.
                             Default: "3D Model".
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error

    try:
        session = am_init.get_session()
    except Exception as e:
        return f"Error starting batch upload: {e}"

    # Ensure collection exists once up-front
    if collection_path:
        try:
            if not _collection_exists(session, org, proj, collection_path):
                am_rest.ensure_collection_path(session, org, proj, collection_path)
        except Exception as e:
            return f"Error ensuring collection '{collection_path}': {e}"

    results = []
    for entry in assets:
        asset_name = entry.get("name", "").strip()
        model_file = entry.get("file", "").strip()
        tags: list[str] = entry.get("tags") or []
        entry_type: str = entry.get("type", "") or default_asset_type

        if not asset_name or not model_file:
            results.append({"name": asset_name or "(missing)", "status": "skipped", "reason": "name or file missing"})
            continue

        try:
            # Create or version the asset
            existing = am_rest.search_assets_by_name(session, org, proj, asset_name)
            if existing is None:
                asset = am_rest.create_asset(session, org, proj, asset_name, tags, asset_type=entry_type)
            else:
                if existing.is_frozen is False:
                    am_rest.freeze_asset_version(session, org, proj, existing.id, existing.version)
                asset = am_rest.create_unfrozen_asset_version(session, org, proj, existing.id, existing.version)
                # New versions inherit the parent's values — re-apply what the
                # entry explicitly specifies so it isn't silently lost.
                if entry.get("tags") is not None:
                    am_rest.update_asset(session, org, proj, asset.id, asset.version, tags=tags)
                if entry.get("type"):
                    am_rest.set_primary_type(session, org, proj, asset.id, asset.version, entry_type)

            _LAST_TARGET_VERSION_BY_ASSET[(org, proj, asset_name)] = (asset.id, asset.version)

            # Upload file
            datasets = am_rest.get_dataset_list(session, org, proj, asset.id, asset.version)
            dataset_id = datasets[0].id
            try:
                am_rest.upload_file(session, org, proj, asset.id, asset.version, dataset_id, model_file)
            except Exception as file_err:
                err_str = str(file_err)
                hint = " (non-ASCII path — rename the file)" if ("codec" in err_str or "charmap" in err_str) else ""
                results.append({"name": asset_name, "status": "upload_failed", "reason": f"{file_err}{hint}"})
                continue

            # Link to collection
            if collection_path:
                am_rest.link_asset_to_collection(session, org, proj, collection_path, asset.id)

            # Optionally freeze
            if freeze_after_upload:
                am_rest.freeze_asset_version(session, org, proj, asset.id, asset.version)

            results.append({
                "name": asset_name,
                "status": "ok",
                "asset_id": asset.id,
                "version": asset.version,
                "frozen": freeze_after_upload,
                "collection": collection_path or None,
            })
        except Exception as e:
            results.append({"name": asset_name, "status": "error", "reason": str(e)})

    ok = sum(1 for r in results if r.get("status") == "ok")
    summary = {"total": len(assets), "succeeded": ok, "failed": len(assets) - ok, "assets": results}
    return json.dumps(summary, indent=2)


@mcp.tool()
@_require_auth
def list_assets(
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
    metadata_filter: dict | None = None,
) -> str:
    """List all assets in an Asset Manager project, including custom metadata.

    Args:
        org_id:           Organisation ID (falls back to the session default; see set_default_organization).
        project_id:       Project ID (falls back to the session default; see set_default_project).
        metadata_filter:  Optional filter criteria for the search endpoint
                          (wrapped into filter.includeQuery automatically).
                          Keys are field paths (e.g. "metadata.source_format", "name",
                          "status"), values are plain strings or criterion objects,
                          e.g. {"metadata.source_format": {"type": "exact-match",
                          "value": "CATIA", "caseInsensitive": false}}.
                          Supported criterion types include exact-match, wildcard,
                          regex, prefix, and fuzzy.
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset_list = am_rest.list_assets(session, org, proj, metadata_filter=metadata_filter)
        result = [
            {
                "name": a.name,
                "id": a.id,
                "version": a.version,
                "is_frozen": a.is_frozen,
                "status": a.status,
                "primary_type": a.primary_type or None,
                "description": a.description or None,
                "tags": a.tags,
                "metadata": a.metadata or {},
            }
            for a in asset_list
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing assets: {e}"


@mcp.tool()
@_require_auth
def search_assets_across_projects(
    name_contains: str = "",
    metadata_filter: dict | None = None,
    project_ids: list[str] | None = None,
    org_id: str = "",
) -> str:
    """Search assets across EVERY project in the organization in one call.

    Use this when you don't know which project holds an asset — each result
    reports the project(s) it lives in. For a known project, list_assets is
    the right tool.

    Args:
        name_contains:   Convenience name filter (contains-match, case-blind wildcard).
        metadata_filter: Same criteria language as list_assets (exact-match,
                         wildcard, regex, prefix, fuzzy...). Combined with
                         name_contains if both are given.
        project_ids:     Restrict the search to these project ids; omit to
                         search every project you can access.
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        session = am_init.get_session()
        criteria: dict = dict(metadata_filter) if metadata_filter else {}
        if name_contains and "name" not in criteria:
            criteria["name"] = {"type": "wildcard", "value": f"*{name_contains}*"}
        assets = am_rest.search_assets_across_projects(
            session, _get_genesis_id(session, org),
            project_ids=project_ids,
            metadata_filter=criteria or None,
        )
        result = [
            {
                "name": a.name,
                "id": a.id,
                "version": a.version,
                "is_frozen": a.is_frozen,
                "status": a.status or None,
                "primary_type": a.primary_type or None,
                "source_project_id": a.source_project_id or None,
                "project_ids": a.project_ids,
                "tags": a.tags,
            }
            for a in assets
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error searching assets across projects: {e}"


@mcp.tool()
@_require_auth
def list_organizations() -> str:
    """List organizations visible to the authenticated identity.

    Not available on private cloud deployments: organization discovery is a
    public Unity Cloud service (verified live: a private-cloud
    token is rejected there). On private cloud, take the organization id from
    your dashboard URL and pass it to set_default_organization.
    """
    if _vpc.is_vpc():
        return (
            "Organization discovery is not available on private cloud deployments "
            "(it is a public Unity Cloud service). Ask the user for the organization "
            "id from their dashboard URL — https://<your-cloud>/home/organizations/"
            "<ORG_ID>/... — then call set_default_organization with it. Everything "
            "else (projects, assets, pipelines) works normally once the org is set."
        )
    try:
        session = am_init.get_session()
        organizations = am_rest.list_organizations(session)
        lines = [f"{i + 1}. {o.name} [{o.id}]" for i, o in enumerate(organizations)]
        return "\n".join(lines)
    except Exception as e:
        if _ORG_ID:
            return f"1. (id={_ORG_ID}) — Could not enumerate organizations ({e}); using configured default org."
        return (
            f"Error listing organizations: {e}. "
            "call set_default_organization (or pass org_id directly to tools)."
        )


@mcp.tool()
@_require_auth
def list_projects(org_id: str = "") -> str:
    """List projects for an organization.

    Args:
        org_id: Organization ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error listing projects: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    try:
        session = am_init.get_session()
        projects = am_rest.list_projects(session, _get_genesis_id(session, org))
        result = [{"id": p.id, "name": p.name} for p in projects]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing projects: {e}"


@mcp.tool()
@_require_auth
def create_project(project_name: str, org_id: str = "", metadata: dict | None = None) -> str:
    """Create a new project in an organization.

    Args:
        project_name: Project display name.
        org_id:       Organization ID (falls back to the session default; see set_default_organization).
        metadata:     Optional metadata dictionary passed to ProjectCreation.
    """
    org = _org(org_id)
    if not org:
        return "Error creating project: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."

    try:
        session = am_init.get_session()
        # The create-project route requires the numeric genesisId (the UUID
        # form returns 403 Forbidden) — resolve it the same way list_projects does.
        genesis_org = _get_genesis_id(session, org)
        project_id = am_rest.create_project(session, genesis_org, project_name, metadata)
        return f"Project '{project_name}' created successfully (id={project_id})."
    except Exception as e:
        err = str(e)
        # A 403 from the create call itself means the signed-in user lacks
        # org-level project-creation rights (org-resolution errors carry their
        # own explanatory message and are not permission failures on this route).
        if "403" in err and "Could not resolve" not in err and "does not match any organization" not in err:
            return (
                f"Error creating project '{project_name}': Your Unity account does not "
                "have permission to create projects in this organization. Ask an "
                "organization owner or manager to grant you project-creation rights, "
                "or create the project from the Unity Cloud dashboard."
            )
        return f"Error creating project '{project_name}': {e}"


@mcp.tool()
@_require_auth
def delete_project(project_id: str = "", project_name: str = "", org_id: str = "", confirm: bool = False) -> str:
    """Permanently delete a project (archive + delete, like the dashboard flow).

    ⚠️  IRREVERSIBLE. The project is archived first, then hard-deleted, along
    with any assets remaining in its trash. Requires the signed-in user to be
    an Owner or Manager of the organization. Uses the same endpoints as the
    Unity Cloud dashboard's Archive/Delete buttons (not part of the documented
    public Assets API).

    Args:
        project_id:   ID of the project to delete (preferred).
        project_name: Name of the project — resolved via list_projects when
                      project_id is not given (errors if ambiguous).
        org_id:       Organisation ID (falls back to the session default; see set_default_organization);
                      only needed for name resolution.
        confirm:      Must be True to actually delete. When False, returns a
                      summary of what would be deleted so the user can confirm.
    """
    if _vpc.is_vpc():
        return (
            "Project deletion is not available on private cloud deployments: it uses "
            "the public Unity Cloud dashboard's entities gateway, which private clouds "
            "do not run (verified live). Delete the project from your "
            "private cloud dashboard instead."
        )
    try:
        session = am_init.get_session()

        if not project_id:
            if not project_name:
                return "Error: provide project_id or project_name."
            org = _org(org_id)
            if not org:
                return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id) to resolve a project by name."
            genesis_org = _get_genesis_id(session, org)
            matches = [p for p in am_rest.list_projects(session, genesis_org) if p.name == project_name]
            if not matches:
                return f"Error: no project named '{project_name}' found in org {org}."
            if len(matches) > 1:
                ids = ", ".join(p.id for p in matches)
                return f"Error: multiple projects named '{project_name}' ({ids}) — pass project_id."
            project_id = matches[0].id

        info = am_rest.get_project_admin(session, project_id)
        label = info.get("name", project_id)
        if not confirm:
            return (
                f"Project '{label}' (id={project_id}) in org {info.get('organizationId', '?')} "
                "would be PERMANENTLY deleted (archive + delete, irreversible). "
                "Call delete_project again with confirm=True to proceed."
            )

        if not info.get("archivedAt"):
            am_rest.archive_project(session, info["organizationId"], project_id)
        am_rest.delete_project(session, info["organizationGenesisId"], project_id)
        return f"Project '{label}' (id={project_id}) archived and permanently deleted."
    except Exception as e:
        err = str(e)
        if "403" in err:
            return (
                f"Error deleting project: your Unity account must be an Owner or Manager "
                f"of the organization to archive/delete projects. ({err})"
            )
        return f"Error deleting project '{project_name or project_id}': {err}"


@mcp.tool()
@_require_auth
def get_asset(asset_name: str, org_id: str = "", project_id: str = "", project_name: str = "") -> str:
    """Get details of a specific asset by name.

    Args:
        asset_name:  Name of the asset to look up.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        # Search results carry only a field subset; fetch the version for the
        # full on-demand details (description, changeLog, authorship, ...).
        session = am_init.get_session()
        details = am_rest.get_asset(session, org, proj, asset.id, asset.version)
        return json.dumps(
            {
                "name": details.name,
                "id": details.id,
                "version": details.version,
                "version_number": details.version_number if details.version_number >= 0 else None,
                "is_frozen": details.is_frozen,
                "status": details.status or None,
                "primary_type": details.primary_type or None,
                "description": details.description or None,
                "tags": details.tags,
                "metadata": details.metadata or {},
                "change_log": details.change_log or None,
                "created": details.created or None,
                "created_by": details.created_by or None,
                "updated": details.updated or None,
                "updated_by": details.updated_by or None,
                "preview_file_url": details.preview_file_url or None,
                "status_flow_name": details.status_flow_name or None,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error getting asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def update_asset_metadata(
    asset_name: str,
    metadata: dict,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Set or update custom metadata fields on an existing asset.

    Merges the supplied metadata into the asset's existing metadata — fields not
    mentioned are left unchanged. To clear a field pass null/None as its value:
    nulls are routed to the documented remove-fields endpoint (a null inside the
    metadata PATCH does not clear anything).

    Args:
        asset_name:  Name of the asset to update.
        metadata:    Dict of field key → value pairs, e.g. {"source_format": "CATIA", "lod_count": 3}.
                     Keys must match field definitions created via create_field_definition.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        to_remove = [k for k, v in metadata.items() if v is None]
        to_set = {k: v for k, v in metadata.items() if v is not None}
        if to_remove:
            am_rest.remove_asset_metadata_fields(session, org, proj, asset.id, asset.version, to_remove)
        if to_set:
            updated = am_rest.update_asset_metadata(session, org, proj, asset.id, asset.version, to_set)
        else:
            updated = am_rest.get_asset(session, org, proj, asset.id, asset.version)
        return json.dumps(
            {
                "asset_name": asset.name,
                "asset_id": asset.id,
                "version": asset.version,
                "metadata": updated.metadata,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error updating metadata for asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def update_asset(
    asset_name: str,
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Update the name, description, or tags of an existing (unfrozen) asset version.

    Only the fields you provide are changed; omitted fields are left unchanged.

    Args:
        asset_name:   Current name of the asset to update.
        name:         New display name for the asset.
        description:  New description.
        tags:         New list of tags (replaces existing tags entirely).
        org_id:       Organisation ID (falls back to the session default; see set_default_organization).
        project_id:   Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    if name is None and description is None and tags is None:
        return "Nothing to update — provide at least one of: name, description, tags."
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        if asset.is_frozen:
            return (
                f"Asset '{asset_name}' version {asset.version} is frozen. "
                "Create a new version with create_asset before updating."
            )
        updated = am_rest.update_asset(session, org, proj, asset.id, asset.version, name, description, tags)
        if name:
            _LAST_TARGET_VERSION_BY_ASSET.pop((org, proj, asset_name), None)
            _LAST_TARGET_VERSION_BY_ASSET[(org, proj, updated.name)] = (updated.id, updated.version)
        return json.dumps(
            {
                "asset_name": updated.name,
                "asset_id": updated.id,
                "version": updated.version,
                "tags": updated.tags,
                "message": "Asset updated successfully.",
            },
            indent=2,
        )
    except Exception as e:
        return f"Error updating asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def list_asset_labels(
    asset_name: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """List system labels on an asset's current version.

    Labels are system-assigned identifiers — "Latest" marks the most recently frozen
    version; "Pending" marks an unfrozen draft. They cannot be created or deleted by
    users but are useful for understanding asset state and for resolving references by
    label name.

    Args:
        asset_name:  Name of the asset to inspect.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        labels = am_rest.list_asset_labels(session, org, proj, asset.id, asset.version)
        return json.dumps(
            {
                "asset_name": asset.name,
                "asset_id": asset.id,
                "version": asset.version,
                "active_labels": labels["active"],
                "archived_labels": labels["archived"],
            },
            indent=2,
        )
    except Exception as e:
        return f"Error listing labels for asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def list_field_definitions(org_id: str = "") -> str:
    """List all custom metadata field definitions for the organisation.

    Returns each field's key, display name, type, and accepted values (for SELECTION fields).

    Args:
        org_id:  Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error listing field definitions: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        session = am_init.get_session()
        fields = am_rest.list_field_definitions(session, _get_genesis_id(session, org))
        result = [
            {
                "key": f.key,
                "display_name": f.display_name,
                "type": f.field_type,
                "accepted_values": f.accepted_values or None,
                "multiselection": f.multiselection,
            }
            for f in fields
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing field definitions: {e}"


@mcp.tool()
@_require_auth
def create_field_definition(
    field_key: str,
    display_name: str,
    field_type: str,
    accepted_values: list[str] | None = None,
    multiselection: bool = False,
    org_id: str = "",
) -> str:
    """Create a custom metadata field definition at the organisation level.

    Once created, the field is available on all assets in the org and can be set
    via create_asset(metadata=...) or update_asset_metadata.

    Args:
        field_key:       Unique snake_case key, e.g. "source_format". Cannot be changed after creation.
        display_name:    Human-readable label shown in the Asset Manager UI.
        field_type:      One of: TEXT, NUMBER, BOOLEAN, SELECTION, TIMESTAMP, URL, USER.
        accepted_values: Required for SELECTION type — list of allowed string values.
        multiselection:  Allow multiple selections (SELECTION type only).
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error creating field definition: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    valid_types = {"TEXT", "NUMBER", "BOOLEAN", "SELECTION", "TIMESTAMP", "URL", "USER"}
    if field_type.upper() not in valid_types:
        return f"Error: field_type '{field_type}' is not valid. Must be one of: {', '.join(sorted(valid_types))}."
    if field_type.upper() == "SELECTION" and not accepted_values:
        return "Error: accepted_values is required for SELECTION type."
    try:
        session = am_init.get_session()
        fd = am_rest.create_field_definition(
            session, _get_genesis_id(session, org),
            key=field_key,
            display_name=display_name,
            field_type=field_type.upper(),
            accepted_values=accepted_values,
            multiselection=multiselection,
        )
        return json.dumps(
            {
                "key": fd.key,
                "display_name": fd.display_name,
                "type": fd.field_type,
                "accepted_values": fd.accepted_values or None,
                "multiselection": fd.multiselection,
                "message": f"Field definition '{fd.key}' created successfully.",
            },
            indent=2,
        )
    except Exception as e:
        return f"Error creating field definition '{field_key}': {e}"


@mcp.tool()
@_require_auth
def delete_field_definition(
    field_key: str,
    org_id: str = "",
) -> str:
    """Delete a custom metadata field definition from the organisation library.

    ⚠️  This removes the field definition, but existing asset metadata values that
    used this key are not automatically cleared. The deleted definition may still
    appear in list_field_definitions responses.

    Args:
        field_key:  The key of the field definition to delete (e.g. "source_format").
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error deleting field definition: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        session = am_init.get_session()
        am_rest.delete_field_definition(session, _get_genesis_id(session, org), field_key)
        return f"Field definition '{field_key}' deleted successfully."
    except Exception as e:
        return f"Error deleting field definition '{field_key}': {e}"


@mcp.tool()
@_require_auth
def freeze_asset(asset_name: str, change_log: str = "", org_id: str = "", project_id: str = "", project_name: str = "") -> str:
    """Freeze the current version of an asset.

    Freezing is required before a new asset version can be created.

    Args:
        asset_name:  Name of the asset to freeze.
        change_log:  Optional change log recorded on the frozen version and shown
                     in the dashboard's version history (e.g. "- Added metallic map").
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        if asset.is_frozen:
            return f"Asset '{asset_name}' is already frozen (version={asset.version})."
        am_rest.freeze_asset_version(session, org, proj, asset.id, asset.version, change_log=change_log)
        return f"Asset '{asset_name}' (version={asset.version}) frozen successfully."
    except Exception as e:
        return f"Error freezing asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def delete_asset(
    asset_name: str = "",
    asset_id: str = "",
    delete_all_versions: bool = False,
    trash: bool = True,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Delete an asset draft version, or remove the entire asset from the project.

    Provide asset_id (preferred — unambiguous) or asset_name (resolved by search).

    delete_all_versions=False (default): deletes only the current unfrozen draft version.
      Frozen versions cannot be deleted this way.

    delete_all_versions=True: removes the entire asset and ALL its versions from the
      project. With trash=True (default) it goes to the project trash and can be
      recovered via restore_asset; trash=False is a permanent unlink. ⚠️ Irreversible
      when trash=False.

    Args:
        asset_name:           Name of the asset (resolved by search — prefer asset_id).
        asset_id:             Asset ID, bypasses name lookup entirely.
        delete_all_versions:  If True, remove the entire asset from the project.
        trash:                Soft-delete to the recoverable trash (default True).
                              Only applies with delete_all_versions=True.
        org_id:               Organisation ID (falls back to the session default; see set_default_organization).
        project_id:           Project ID (falls back to the session default; see set_default_project).
    """
    if not asset_id and not asset_name:
        return "Error: provide either asset_id or asset_name."
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()

        # Resolve asset — always need the asset record to get a confirmed id/name
        if asset_id:
            asset = am_rest.find_asset_by_id(session, org, proj, asset_id)
            if asset is None:
                return f"Asset id={asset_id} not found in project."
        else:
            asset = _resolve_asset_for_name(org, proj, asset_name)
            if asset is None:
                return f"Asset '{asset_name}' not found."

        if delete_all_versions:
            am_rest.unlink_asset_from_project(session, org, proj, asset.id, trash=trash)
            if trash:
                return (
                    f"Asset '{asset.name}' (id={asset.id}) and all its versions moved to "
                    "the project trash. Recoverable via restore_asset; permanent after "
                    "the trash is emptied."
                )
            return (
                f"Asset '{asset.name}' (id={asset.id}) and all its versions have been "
                "permanently unlinked from the project (trash=False)."
            )

        # Single-version delete — must be unfrozen
        if asset.is_frozen:
            return (
                f"Asset '{asset.name}' (id={asset.id}) version {asset.version} is frozen "
                "and cannot be deleted individually. Use delete_all_versions=True to remove "
                "the entire asset from the project."
            )
        am_rest.delete_asset(session, org, proj, asset.id, asset.version)
        return f"Asset '{asset.name}' (id={asset.id}) version {asset.version} deleted successfully."
    except Exception as e:
        label = asset_id or asset_name
        return f"Error deleting asset '{label}': {e}"


@mcp.tool()
@_require_auth
def get_asset_status(
    asset_name: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Read an asset's current status and the statuses reachable from it.

    Use this before change_asset_status to see which transitions are valid.

    Args:
        asset_name:  Name of the asset to inspect.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        details = am_rest.get_asset(session, org, proj, asset.id, asset.version)
        reachable = am_rest.get_asset_reachable_statuses(session, org, proj, asset.id, asset.version)
        return json.dumps(
            {
                "asset_name": asset.name,
                "asset_id": asset.id,
                "version": asset.version,
                "current_status": details.status or None,
                "status_flow_name": details.status_flow_name or None,
                "reachable_statuses": reachable,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error reading status for asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def list_asset_versions(
    asset_name: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """List ALL versions of an asset, including older frozen ones.

    Regular list_assets/search only surfaces Latest/Pending versions; use this
    to see an asset's full version history (version numbers, change logs, status).

    Args:
        asset_name:  Name of the asset to enumerate versions for.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        versions = am_rest.list_asset_versions(session, org, proj, asset.id)
        result = [
            {
                "version": v.version,
                "version_number": v.version_number if v.version_number >= 0 else None,
                "is_frozen": v.is_frozen,
                "status": v.status or None,
                "change_log": v.change_log or None,
                "tags": v.tags,
            }
            for v in versions
        ]
        return json.dumps({"asset_name": asset.name, "asset_id": asset.id, "versions": result}, indent=2)
    except Exception as e:
        return f"Error listing versions for asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def list_trashed_assets(org_id: str = "", project_id: str = "", project_name: str = "") -> str:
    """List soft-deleted assets in the project trash (recoverable via restore_asset).

    Args:
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        trashed = am_rest.list_trashed_assets(session, org, proj)
        result = [
            {"name": a.name, "id": a.id, "version": a.version, "primary_type": a.primary_type or None}
            for a in trashed
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing trashed assets: {e}"


@mcp.tool()
@_require_auth
def restore_asset(
    asset_ids: list[str],
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Restore trashed assets back into the project (see list_trashed_assets for ids).

    Args:
        asset_ids:   Asset IDs to restore from the trash.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        am_rest.restore_assets(session, org, proj, asset_ids)
        return json.dumps({"restored_asset_ids": asset_ids, "message": "Assets restored from trash."}, indent=2)
    except Exception as e:
        return f"Error restoring assets: {e}"


@mcp.tool()
@_require_auth
def link_asset_to_project(
    destination_project_id: str,
    asset_name: str = "",
    asset_id: str = "",
    link_referenced_assets: bool = False,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Link (share) an asset into another project in the same organization.

    The asset stays in the source project and becomes visible in the destination
    project too. With link_referenced_assets=True, all recursively referenced
    assets are linked as well and a per-asset detail report is returned.

    Args:
        destination_project_id: The project to link the asset into.
        asset_name:             Name of the asset (resolved by search — prefer asset_id).
        asset_id:               Asset ID, bypasses name lookup.
        link_referenced_assets: Also link everything the asset references.
        org_id:                 Organisation ID (falls back to the session default; see set_default_organization).
        project_id:             SOURCE project ID (falls back to the session default; see set_default_project).
    """
    if not asset_id and not asset_name:
        return "Error: provide asset_id or asset_name."
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        if not asset_id:
            asset = _resolve_asset_for_name(org, proj, asset_name)
            if asset is None:
                return f"Asset '{asset_name}' not found."
            asset_id = asset.id
        detail = am_rest.link_asset_to_project(
            session, org, proj, asset_id, destination_project_id,
            link_referenced_assets=link_referenced_assets if link_referenced_assets else None,
        )
        return json.dumps(
            {
                "asset_id": asset_id,
                "destination_project_id": destination_project_id,
                "linked": True,
                "detail": detail,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error linking asset to project '{destination_project_id}': {e}"


@mcp.tool()
@_require_auth
def list_labels(org_id: str = "", status: str = "", include_system: bool = True) -> str:
    """List the labels defined in the organization (system and user labels).

    Args:
        org_id:         Organisation ID (falls back to the session default; see set_default_organization).
        status:         Optional filter: "Active" or "Archived".
        include_system: Set False to list only user-created labels.
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        session = am_init.get_session()
        labels = am_rest.list_labels(
            session, org, status=status,
            is_system_label=None if include_system else False,
        )
        result = [
            {
                "name": lbl.get("name"),
                "description": lbl.get("description"),
                "colour": lbl.get("colour"),
                "is_system_label": lbl.get("isSystemLabel"),
                "is_user_assignable": lbl.get("isUserAssignable"),
            }
            for lbl in labels
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing labels: {e}"


@mcp.tool()
@_require_auth
def create_label(name: str, description: str, colour: str = "", org_id: str = "") -> str:
    """Create a user label in the organization (assign it with assign_label).

    Args:
        name:        Label name, e.g. "release-candidate".
        description: What the label marks.
        colour:      Optional RGB hex colour, e.g. "#00FF00".
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        session = am_init.get_session()
        label_name = am_rest.create_label(session, org, name, description, colour)
        return json.dumps({"label_name": label_name, "message": "Label created."}, indent=2)
    except Exception as e:
        return f"Error creating label '{name}': {e}"


@mcp.tool()
@_require_auth
def assign_label(
    asset_name: str,
    label_names: list[str],
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Assign labels to the current version of an asset.

    Labels mark specific versions (e.g. "release-candidate"). The system labels
    Latest and Pending are restricted and cannot be assigned manually.

    Args:
        asset_name:  Name of the asset whose current version gets the labels.
        label_names: Label names to assign (created via create_label).
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        am_rest.assign_labels(session, org, proj, asset.id, asset.version, label_names)
        return json.dumps(
            {"asset_name": asset.name, "version": asset.version, "assigned_labels": label_names},
            indent=2,
        )
    except Exception as e:
        return f"Error assigning labels to asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def unassign_label(
    asset_name: str,
    label_names: list[str],
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Remove labels from the current version of an asset (see assign_label).

    Args:
        asset_name:  Name of the asset whose current version loses the labels.
        label_names: Label names to unassign. Latest/Pending are restricted.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        am_rest.unassign_labels(session, org, proj, asset.id, asset.version, label_names)
        return json.dumps(
            {"asset_name": asset.name, "version": asset.version, "unassigned_labels": label_names},
            indent=2,
        )
    except Exception as e:
        return f"Error unassigning labels from asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def list_status_flows(org_id: str = "") -> str:
    """List the status flows defined in the organization (assign with assign_status_flow).

    Args:
        org_id: Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        session = am_init.get_session()
        flows = am_rest.list_status_flows(session, org)
        return json.dumps(flows, indent=2)
    except Exception as e:
        return f"Error listing status flows: {e}"


@mcp.tool()
@_require_auth
def assign_status_flow(
    asset_name: str,
    status_flow_id: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Assign a status flow to the current (unfrozen) version of an asset.

    Args:
        asset_name:     Name of the asset.
        status_flow_id: The flow's id (see list_status_flows).
        org_id:         Organisation ID (falls back to the session default; see set_default_organization).
        project_id:     Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        am_rest.assign_status_flow(session, org, proj, asset.id, asset.version, status_flow_id)
        return json.dumps(
            {"asset_name": asset.name, "version": asset.version, "status_flow_id": status_flow_id},
            indent=2,
        )
    except Exception as e:
        return f"Error assigning status flow to asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def update_field_definition(
    field_name: str,
    display_name: str = "",
    accepted_values: list[str] | None = None,
    add_values: list[str] | None = None,
    remove_values: list[str] | None = None,
    org_id: str = "",
) -> str:
    """Update a metadata field definition without delete + recreate.

    Field type and name cannot be changed. accepted_values REPLACES the whole
    list; add_values/remove_values change it incrementally (Selection fields).

    Args:
        field_name:      The field's key (see list_field_definitions).
        display_name:    New display name.
        accepted_values: Full replacement list of accepted values.
        add_values:      Values to add to the accepted list.
        remove_values:   Values to remove from the accepted list.
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    if not any([display_name, accepted_values is not None, add_values, remove_values]):
        return "Error: nothing to update — provide display_name, accepted_values, add_values, or remove_values."
    try:
        session = am_init.get_session()
        applied = []
        if display_name or accepted_values is not None:
            am_rest.update_field_definition(
                session, org, field_name,
                display_name=display_name, accepted_values=accepted_values,
            )
            applied.append("definition")
        if add_values:
            am_rest.add_accepted_values(session, org, field_name, add_values)
            applied.append(f"added {len(add_values)} value(s)")
        if remove_values:
            am_rest.remove_accepted_values(session, org, field_name, remove_values)
            applied.append(f"removed {len(remove_values)} value(s)")
        return json.dumps({"field_name": field_name, "applied": applied}, indent=2)
    except Exception as e:
        return f"Error updating field definition '{field_name}': {e}"


@mcp.tool()
@_require_auth
def update_collection(
    collection_path: str,
    name: str = "",
    description: str = "",
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Rename and/or re-describe a collection ('%' is not allowed in names).

    Args:
        collection_path: Full path of the collection (see list_collections).
        name:            New collection name.
        description:     New description.
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
        project_id:      Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    if not name and not description:
        return "Error: nothing to update — provide name and/or description."
    try:
        session = am_init.get_session()
        am_rest.update_collection(session, org, proj, collection_path, name=name, description=description)
        return json.dumps({"collection_path": collection_path, "updated": True}, indent=2)
    except Exception as e:
        return f"Error updating collection '{collection_path}': {e}"


@mcp.tool()
@_require_auth
def move_collection(
    collection_path: str,
    destination_parent_path: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Move a collection under a new parent collection (same project only).

    Args:
        collection_path:         Full path of the collection to move.
        destination_parent_path: New parent path ("" moves it to the top level).
        org_id:                  Organisation ID (falls back to the session default; see set_default_organization).
        project_id:              Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        new_path = am_rest.move_collection(session, org, proj, collection_path, destination_parent_path)
        return json.dumps({"collection_path": collection_path, "new_path": new_path or None}, indent=2)
    except Exception as e:
        return f"Error moving collection '{collection_path}': {e}"


@mcp.tool()
@_require_auth
def update_asset_reference(
    asset_name: str,
    reference_id: str,
    target_asset_version: str = "",
    target_label: str = "",
    dependency_type: str = "",
    vocabulary: str = "",
    source_path: str = "",
    target_path: str = "",
    relative_path: str = "",
    metadata: dict | None = None,
    metadata_to_remove: list[str] | None = None,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Update a reference in place instead of remove + re-add.

    Retarget to a specific version or a label, change the dependency type or
    relativePath, merge reference metadata, or remove metadata keys.

    Retyping existing references is the main use for `vocabulary` here: an edge typed under
    one vocabulary can be re-derived under another without touching the graph. See
    list_dependency_vocabularies, and note that `dependencyType` is free text — nothing
    validates the result.

    Args:
        asset_name:           Name of the SOURCE asset that owns the reference.
        reference_id:         The reference to update (see list_asset_references).
        target_asset_version: Retarget to this version of the target asset.
        target_label:         Retarget to a label (tracks whatever version the label points at).
        dependency_type:      New dependency type string, sent verbatim. Wins over `vocabulary`.
        vocabulary:           Named vocabulary to classify with instead ("unity", "usd", "cad").
        source_path:          Source file path used for classification (optional).
        target_path:          Target file path used for classification. Required with
                              `vocabulary` (relative_path is used as a fallback) — unlike
                              add_asset_reference there is no asset name to fall back on,
                              and classification is driven by the TARGET's extension.
        relative_path:        New relative path recorded on the reference.
        metadata:             Reference metadata to merge.
        metadata_to_remove:   Reference metadata keys to remove.
        org_id:               Organisation ID (falls back to the session default; see set_default_organization).
        project_id:           Project ID (falls back to the session default; see set_default_project).
    """
    if vocabulary and not dependency_type and not (target_path or relative_path):
        # Without a target extension the classifier can only emit the vague
        # catch-all (clobbering a possibly specific existing type) or nothing at
        # all (a silent no-op reported as success). Refuse instead of either.
        return (
            "Error: `vocabulary` needs `target_path` (or `relative_path`) to classify "
            "from — pass one, or pass an explicit `dependency_type` instead."
        )
    try:
        resolved_type = dependency_vocab.resolve_dependency_type(
            dependency_type=dependency_type,
            vocabulary=vocabulary,
            source_path=source_path,
            target_path=target_path or relative_path,
        )
    except dependency_vocab.UnknownVocabulary as e:
        return f"Error: {e}"
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        am_rest.update_asset_reference(
            session, org, proj, asset.id, reference_id,
            target_asset_version=target_asset_version,
            target_label=target_label,
            dependency_type=resolved_type,
            relative_path=relative_path,
            metadata=metadata,
            metadata_to_remove=metadata_to_remove,
        )
        payload = {
            "asset_name": asset.name,
            "reference_id": reference_id,
            "updated": True,
        }
        # Only report the type when this call actually wrote one — a null here
        # on a metadata-only update reads as "the edge is now untyped".
        if resolved_type:
            payload["dependency_type"] = resolved_type
            payload["dependency_type_source"] = (
                "explicit" if dependency_type else vocabulary.strip().lower()
            )
        return json.dumps(payload, indent=2)
    except Exception as e:
        return f"Error updating reference '{reference_id}' on asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def change_asset_status(
    asset_name: str,
    requested_status: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Change asset status when the target status is reachable from the current status.

    If the requested status is not directly reachable, this tool returns the currently
    reachable statuses so the user can choose the next valid transition.
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error

    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."

        asset_details = am_rest.get_asset(session, org, proj, asset.id, asset.version)
        current_status = asset_details.status
        reachable_statuses = am_rest.get_asset_reachable_statuses(session, org, proj, asset.id, asset.version)
        resolved_target = _resolve_status_name(requested_status, reachable_statuses)

        if current_status and requested_status.casefold() == str(current_status).casefold():
            return json.dumps(
                {
                    "asset_name": asset.name,
                    "asset_id": asset.id,
                    "version": asset.version,
                    "current_status": current_status,
                    "requested_status": requested_status,
                    "applied": False,
                    "message": "Asset is already in the requested status.",
                },
                indent=2,
            )

        if not resolved_target:
            draft_hint = None
            if requested_status.casefold() == "draft":
                draft_hint = (
                    "Draft is often not directly reachable from approved/published states. "
                    "Create a new version via create_asset(asset_name=...) to start from a new draft."
                )
            return json.dumps(
                {
                    "asset_name": asset.name,
                    "asset_id": asset.id,
                    "version": asset.version,
                    "current_status": current_status,
                    "requested_status": requested_status,
                    "applied": False,
                    "prompt_required": True,
                    "message": "Requested status is not directly reachable from the current status.",
                    "reachable_statuses": reachable_statuses,
                    "prompt": "Choose one of reachable_statuses and call change_asset_status again.",
                    "draft_next_step": draft_hint,
                },
                indent=2,
            )

        transition_ok = am_rest.update_asset_status(session, org, proj, asset.id, asset.version, resolved_target)
        updated_asset = am_rest.get_asset(session, org, proj, asset.id, asset.version)

        return json.dumps(
            {
                "asset_name": asset.name,
                "asset_id": asset.id,
                "version": asset.version,
                "previous_status": current_status,
                "requested_status": requested_status,
                "applied_status": resolved_target,
                "current_status": updated_asset.status,
                "applied": bool(transition_ok),
            },
            indent=2,
        )
    except Exception as e:
        return f"Error changing status for asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def change_asset_type(
    asset_name: str,
    new_type: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Change the asset type (primaryType) shown in the Asset Manager dashboard.

    Only works on an unfrozen version: the type is set at create time and inherited
    by new versions, so a frozen asset needs a new draft first
    (create_new_draft_version), then this tool, then freeze_asset.

    Args:
        asset_name: Name of the asset to retype.
        new_type:   One of the asset types listed in create_asset's asset_type.
                    Legacy unspaced spellings ("3DModel", "2DAsset", "UnityEditor")
                    are accepted and mapped.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error

    resolved_type = am_rest.normalise_primary_type(new_type)
    if resolved_type == "Other" and new_type.replace(" ", "").casefold() != "other":
        return json.dumps(
            {
                "requested_type": new_type,
                "applied": False,
                "message": "Unrecognised asset type.",
                "valid_types": list(am_rest.PRIMARY_TYPES),
            },
            indent=2,
        )

    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."

        details = am_rest.get_asset(session, org, proj, asset.id, asset.version)

        if details.primary_type == resolved_type:
            return json.dumps(
                {
                    "asset_name": asset.name,
                    "asset_id": asset.id,
                    "version": asset.version,
                    "current_type": details.primary_type,
                    "requested_type": new_type,
                    "applied": False,
                    "message": "Asset is already the requested type.",
                },
                indent=2,
            )

        if details.is_frozen:
            return json.dumps(
                {
                    "asset_name": asset.name,
                    "asset_id": asset.id,
                    "version": asset.version,
                    "current_type": details.primary_type,
                    "requested_type": new_type,
                    "applied": False,
                    "message": (
                        "This version is frozen, so its type cannot be changed. "
                        "Create a new draft via create_new_draft_version, change the "
                        "type on it, then freeze_asset again."
                    ),
                },
                indent=2,
            )

        am_rest.set_primary_type(session, org, proj, asset.id, asset.version, resolved_type)
        updated = am_rest.get_asset(session, org, proj, asset.id, asset.version)

        return json.dumps(
            {
                "asset_name": asset.name,
                "asset_id": asset.id,
                "version": asset.version,
                "previous_type": details.primary_type,
                "applied_type": resolved_type,
                "current_type": updated.primary_type,
                "applied": True,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error changing type for asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def list_collections(org_id: str = "", project_id: str = "", project_name: str = "") -> str:
    """List all collections in an Asset Manager project.

    Args:
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        collections = am_rest.list_collections(session, org, proj)
        result = [{"name": c.name, "path": c.path} for c in collections]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing collections: {e}"


@mcp.tool()
@_require_auth
def create_collection(
    collection_name: str,
    parent_collection_path: str = "",
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
    description: str = "",
) -> str:
    """Create a new collection in an Asset Manager project.

    Supports nested collections: pass the full path of an existing collection in
    parent_collection_path to create a child collection beneath it.

    Args:
        collection_name:         Name for the new collection (last segment only).
        parent_collection_path:  Full path of the parent collection (e.g. "Root/Sub").
                                 Omit or leave empty to create a top-level collection.
        org_id:                  Organisation ID (falls back to the session default; see set_default_organization).
        project_id:              Project ID (falls back to the session default; see set_default_project).
        description:             Collection description shown in the dashboard. Ask the
                                 user what they want here; when omitted the collection
                                 name is used (the API rejects empty descriptions).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    full_path = f"{parent_collection_path}/{collection_name}" if parent_collection_path else collection_name
    try:
        session = am_init.get_session()
        if _collection_exists(session, org, proj, full_path):
            return f"Collection '{full_path}' already exists."
        created = am_rest.create_collection(
            session, org, proj, collection_name,
            parent_path=parent_collection_path, description=description,
        )
        if not created:
            # The pre-check races a concurrent create; the API's 409 is the
            # authoritative answer, so report it as such rather than "created".
            return f"Collection '{full_path}' already exists."
        return f"Collection '{full_path}' created successfully."
    except Exception as e:
        return f"Error creating collection '{full_path}': {e}"


@mcp.tool()
@_require_auth
def delete_collection(
    collection_path: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Delete a collection from an Asset Manager project.

    ⚠️  Assets inside the collection are NOT deleted — they remain in the project
    but will no longer be grouped under this collection.

    Args:
        collection_path: Path of the collection to delete (use list_collections to find the path).
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
        project_id:      Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        if not _collection_exists(session, org, proj, collection_path):
            return f"Collection '{collection_path}' not found."
        success = am_rest.delete_collection(session, org, proj, collection_path)
        if success:
            return f"Collection '{collection_path}' deleted successfully."
        return f"Delete request sent for collection '{collection_path}', but the server returned a non-success response."
    except Exception as e:
        return f"Error deleting collection '{collection_path}': {e}"


@mcp.tool()
@_require_auth
def link_asset_to_collection(
    asset_name: str,
    collection_path: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Link an existing asset to a collection.

    Args:
        asset_name:      Name of the asset to link.
        collection_path: Path of the target collection.
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
        project_id:      Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        am_rest.link_asset_to_collection(session, org, proj, collection_path, asset.id)
        return f"Asset '{asset_name}' linked to collection '{collection_path}'."
    except Exception as e:
        return f"Error linking asset '{asset_name}' to collection '{collection_path}': {e}"


@mcp.tool()
@_require_auth
def unlink_asset_from_collection(
    asset_name: str,
    collection_path: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Remove an asset from a collection without deleting the asset itself.

    Useful when an asset was added to the wrong collection or should only live
    at the project level rather than inside a specific collection.

    Args:
        asset_name:      Name of the asset to unlink.
        collection_path: Path of the collection to remove the asset from.
        org_id:          Organisation ID (falls back to the session default; see set_default_organization).
        project_id:      Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."
        am_rest.unlink_asset_from_collection(session, org, proj, collection_path, asset.id)
        return f"Asset '{asset_name}' removed from collection '{collection_path}'."
    except Exception as e:
        return f"Error unlinking asset '{asset_name}' from collection '{collection_path}': {e}"


@mcp.tool()
@_require_auth
def get_asset_url(
    asset_name: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Get the Asset Manager dashboard URL for an asset.

    Returns a clickable link to the asset in the Asset Manager web portal.
    The URL targets the project assets page with an ``assetId`` query in the
    form ``<asset_id>:<version>``.

    Args:
        asset_name:  Name of the asset to look up.
        org_id:      Organisation ID (falls back to the session default; see set_default_organization).
        project_id:  Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."

        dashboard_url = (
            f"https://cloud.unity.com/home/organizations/{org}"
            f"/projects/{proj}/assets?assetId={asset.id}:{asset.version}"
        )

        return json.dumps(
            {
                "asset_name": asset.name,
                "asset_id": asset.id,
                "version": asset.version,
                "dashboard_url": dashboard_url,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error getting URL for asset '{asset_name}': {e}"


@mcp.tool()
def list_dependency_vocabularies() -> str:
    """List the named dependency-type vocabularies this server can classify with.

    Read this before typing references in bulk. `dependencyType` on an Asset Manager
    reference is **free text** — verified against the live API, where 22 candidate values
    were submitted and all 22 were accepted, including invented ones. There is no enum,
    no validation, and no error when an edge is mislabelled.

    Two things follow, and they are worth stating plainly because neither is obvious:

    1. **A vocabulary is a choice, not a constraint.** These are the sets this server can
       derive; you are free to pass any `dependency_type` string instead and it will be sent
       verbatim. Nothing here is imposed.
    2. **Consistency is the whole value.** Because the field is free text, two tools writing
       different words for the same relationship produce a graph nobody can filter. Pick one
       vocabulary per project and stay in it — and prefer the `unity_`/`usd_` prefixed sets
       when a project mixes Unity, USD and CAD content, so the three stay distinguishable.

    Note that the coarse `type` field (Dependency | Compound | Converted) is separate and
    server-set; Unity Pipeline Automation's dependency traversal follows THAT, not this.

    Requires no authentication — it reports local configuration only.
    """
    return json.dumps(
        {
            "field_is_free_text": True,
            "verified": "22/22 candidate values accepted against the live API, zero rejections",
            "precedence": [
                "an explicit dependency_type is sent verbatim",
                "otherwise a named vocabulary classifies from the file paths",
                "otherwise no dependencyType is written at all",
            ],
            "vocabularies": dependency_vocab.describe_vocabularies(),
        },
        indent=2,
    )


@mcp.tool()
@_require_auth
def add_asset_reference(
    source_asset_name: str,
    target_asset_name: str,
    dependency_type: str = "",
    vocabulary: str = "",
    source_path: str = "",
    target_path: str = "",
    target_label: str = "",
    relative_path: str = "",
    metadata: dict | None = None,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Add a reference from one asset to another within the same project.

    The target asset version is resolved automatically by default (pinned to the current version).
    If the target is still in an unfrozen/pending state it will be **frozen automatically** before
    the reference is created — this ensures the reference always points to a stable, unambiguous
    version rather than a moving draft.

    Optionally supply target_label if you have explicitly assigned a custom label to a version
    in Asset Manager. Do NOT pass "latest" — Asset Manager does not auto-assign that label; omit
    target_label to pin to the current version instead (with auto-freeze if needed).

    The source asset must NOT be frozen; freeze it only after all references are added.

    ## Typing the relationship

    `dependencyType` is **free text** — verified against the live API, where 22 candidate
    values including invented ones were all accepted. There is no enum to validate against and
    nothing will ever tell you an edge is mislabelled. So this tool never invents a value:

    * pass `dependency_type` and it is sent **verbatim**;
    * or pass `vocabulary` ("unity", "usd", "cad") and the type is derived from the file
      extensions — see list_dependency_vocabularies;
    * pass neither and no type is written at all.

    Args:
        source_asset_name: Name of the asset that POINTS to the target.
        target_asset_name: Name of the asset being REFERENCED.
        dependency_type:   Exact dependencyType string to send. Wins over `vocabulary`.
        vocabulary:        Named vocabulary to classify with instead ("unity", "usd", "cad").
                           Opt-in — omit it and nothing is written.
        source_path:       Source file path used for classification (e.g. "Assets/Robot.prefab").
                           Defaults to source_asset_name, which is usually the basename.
        target_path:       Target file path used for classification. Defaults to target_asset_name.
        target_label:      Optional custom label already assigned in Asset Manager.
        relative_path:     Optional relative file path of the dependency within the source asset.
        metadata:          Optional dict of key-value metadata stored on the reference itself
                           (separate from asset-level metadata).
        org_id:            Organisation ID (falls back to the session default; see set_default_organization).
        project_id:        Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        # Resolve the type BEFORE any write, so an unknown vocabulary name fails without
        # having already frozen the target asset as a side effect.
        resolved_type = dependency_vocab.resolve_dependency_type(
            dependency_type=dependency_type,
            vocabulary=vocabulary,
            source_path=source_path or source_asset_name,
            target_path=target_path or target_asset_name,
        )
    except dependency_vocab.UnknownVocabulary as e:
        return f"Error: {e}"
    try:
        session = am_init.get_session()
        source = _resolve_asset_for_name(org, proj, source_asset_name)
        if source is None:
            return f"Error: source asset '{source_asset_name}' not found."

        if getattr(source, "is_frozen", False):
            return (
                f"Error: source asset '{source_asset_name}' is frozen (version={source.version}). "
                "References can only be added to an unfrozen version. "
                "Call create_new_draft_version first to create a new editable version."
            )

        target = _resolve_asset_for_name(org, proj, target_asset_name)
        if target is None:
            return f"Error: target asset '{target_asset_name}' not found."

        # Ensure the target is frozen so the reference pins to a stable, unambiguous version.
        target_frozen_now = False
        if not target_label and not target.is_frozen:
            am_rest.freeze_asset_version(session, org, proj, target.id, target.version)
            target = am_rest.get_asset(session, org, proj, target.id, target.version)
            target_frozen_now = True

        ref = am_rest.add_asset_reference(
            session,
            org_id=org,
            project_id=proj,
            source_asset_id=source.id,
            source_asset_version=source.version,
            target_asset_id=target.id,
            target_asset_version="" if target_label else target.version,
            target_label=target_label,
            dependency_type=resolved_type,
            relative_path=relative_path,
            metadata=metadata,
        )
        return json.dumps(
            {
                "reference_id": ref.id,
                "is_valid": ref.is_valid,
                "source_asset_id": ref.source_asset_id,
                "source_asset_version": ref.source_asset_version,
                "target_asset_id": ref.target_asset_id,
                "target_asset_version": ref.target_asset_version,
                "target_asset_label": ref.target_asset_label,
                "dependency_type": ref.dependency_type or resolved_type,
                # Named so a reader can tell a caller-supplied value from a derived one —
                # the API records only the string, not where it came from.
                "dependency_type_source": (
                    "explicit" if dependency_type else (vocabulary.strip().lower() if resolved_type else "none")
                ),
                "target_frozen_before_reference": target_frozen_now,
            },
            indent=2,
        )
    except Exception as e:
        return f"Error adding asset reference from '{source_asset_name}' to '{target_asset_name}': {e}"


@mcp.tool()
@_require_auth
def list_asset_references(
    asset_name: str,
    context: str = "both",
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """List references for an asset — incoming, outgoing, or both.

    Args:
        asset_name: Name of the asset to inspect.
        context:    'both' (default), 'source' (references this asset makes),
                    or 'target' (references pointing at this asset).
        org_id:     Organisation ID (falls back to the session default; see set_default_organization).
        project_id: Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        ctx_map = {"both": "BOTH", "source": "SOURCE", "target": "TARGET"}
        ctx = ctx_map.get(context.lower(), "BOTH")

        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."

        refs = am_rest.list_asset_references(
            session,
            org_id=org,
            project_id=proj,
            asset_id=asset.id,
            asset_version=asset.version,
            context=ctx,
        )
        result = [
            {
                "reference_id": r.id,
                "is_valid": r.is_valid,
                "source_asset_id": r.source_asset_id,
                "source_asset_version": r.source_asset_version,
                "target_asset_id": r.target_asset_id,
                "target_asset_version": r.target_asset_version,
                "target_asset_label": r.target_asset_label,
                "dependency_type": r.dependency_type,
                "relative_path": r.relative_path or None,
                "metadata": r.metadata or None,
                "reference_type": r.reference_type or None,
            }
            for r in refs
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error listing references for asset '{asset_name}': {e}"


@mcp.tool()
@_require_auth
def remove_asset_reference(
    asset_name: str,
    reference_id: str,
    org_id: str = "",
    project_id: str = "",
    project_name: str = "",
) -> str:
    """Remove a specific reference from an asset version.

    Args:
        asset_name:   Name of the source asset that owns the reference.
        reference_id: The reference ID to remove (obtained from list_asset_references).
        org_id:       Organisation ID (falls back to the session default; see set_default_organization).
        project_id:   Project ID (falls back to the session default; see set_default_project).
    """
    org = _org(org_id)
    proj, resolve_error = _resolve_project_id(org, project_id=project_id, project_name=project_name)
    if resolve_error:
        return resolve_error
    try:
        session = am_init.get_session()
        asset = _resolve_asset_for_name(org, proj, asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found."

        success = am_rest.remove_asset_reference(
            session,
            org_id=org,
            project_id=proj,
            asset_id=asset.id,
            asset_version=asset.version,
            reference_id=reference_id,
        )
        if success:
            return f"Reference '{reference_id}' removed from asset '{asset_name}' successfully."
        return f"Failed to remove reference '{reference_id}' from asset '{asset_name}'."
    except Exception as e:
        return f"Error removing reference '{reference_id}' from asset '{asset_name}': {e}"


# ---------------------------------------------------------------------------
# Auth tools
# ---------------------------------------------------------------------------

@mcp.tool()
def unity_login() -> str:
    """Sign in to Unity Cloud using a browser-based PKCE flow.

    Opens the system browser to the Unity sign-in page and waits for the
    redirect callback. The resulting tokens are cached on disk under
    ~/.uap_mcp/token.json (or $UAP_MCP_HOME) and refreshed automatically;
    subsequent server starts won't re-prompt until the refresh token can no
    longer be used. The cache is shared with the Pipeline Automation MCP
    server, so one login authenticates both.
    """
    try:
        am_init.trigger_user_login()
    except Exception as e:
        return f"Unity login failed: {e}"
    return "Logged in to Unity Cloud successfully."


@mcp.tool()
def unity_logout() -> str:
    """Clear the cached Unity user-login tokens.

    The token cache is shared with the Pipeline Automation MCP server, so this
    signs you out of both Asset Manager and Pipeline Automation.
    """
    am_init.logout()
    return (
        "Cleared cached Unity tokens (shared with Pipeline Automation — both "
        "servers are now signed out). Call `unity_login` to sign in again."
    )


@mcp.tool()
def unity_auth_status() -> str:
    """Report whether the server can currently make authenticated Unity Cloud calls.

    Returns 'ready' or the message tools would return when called without a
    valid identity.
    """
    err = am_init.auth_status_message()
    return json.dumps(
        {
            "ready": err is None,
            "message": err or "Authenticated.",
        },
        indent=2,
    )


@mcp.tool()
@_require_auth
def check_entitlements(org_id: str = "") -> str:
    """Check the signed-in user's Asset Manager entitlements (license seats) in an org.

    Use this to diagnose permission/quota surprises before they happen: an org
    without Asset Manager seats works for asset metadata operations but is
    limited to the free 10 GB storage baseline, so file uploads can fail with
    HTTP 402 'Maximum quota reached'.

    Args:
        org_id: Organization ID (falls back to the session default; see set_default_organization).
    """
    org = _org(org_id)
    if not org:
        return "Error: no organization selected. Call list_organizations, ask the user to pick one, then set_default_organization (or pass org_id)."
    try:
        session = am_init.get_session()
        genesis_org = _get_genesis_id(session, org)
        data = am_rest.get_entitlements(session, genesis_org)
        seats = sorted(set(data.get("userSeats", [])))
        org_entitlements = sorted(set(data.get("entitlements", [])))
        licensed = bool(org_entitlements)
        result = {
            "org_id": org,
            "org_entitlements": org_entitlements,
            "user_seats": seats,
            "licensed": licensed,
            "note": (
                "Entitlements found — full Asset Manager functionality available."
                if licensed
                else (
                    "No Asset Manager entitlements reported for this organization. On "
                    "private cloud deployments access is governed by your deployment's "
                    "identity roles rather than Unity seats, so this may be expected — "
                    "check with your administrator if operations are denied."
                    if _vpc.is_vpc() else
                    "No Asset Manager entitlements in this organization: storage is "
                    "limited to the free 10 GB baseline and file uploads may fail with "
                    "HTTP 402 'Maximum quota reached'. Assign Pro/Enterprise/Industry "
                    "seats at https://id.unity.com (Subscriptions)."
                )
            ),
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error checking entitlements for org '{org}': {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
