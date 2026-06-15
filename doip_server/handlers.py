from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import httpx
from rocrate.rocrate import ROCrate
from rocrate.model.file import File

from . import object_registry, protocol, storage_lakefs, workflows
from .logging_config import log
from .protocol import ComponentBlock, DOIPMessage
from doip_shared.constants import KNOWN_TYPE_IDS

_VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
SERVER_VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip() if _VERSION_FILE.exists() else "unknown"


async def handle_hello(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Respond to hello/health check requests with server metadata.

    Args:
        msg: Incoming DOIP hello request.
        registry: Object registry resolver (unused, for signature parity).

    Returns:
        DOIPMessage: Response containing server status and capabilities.
    """
    log.info("Handling hello request for object_id=%s", msg.object_id)
    type_base = getattr(registry, "fdo_api", "").rstrip("/") + "/types/"
    metadata_block = {
        "operation": "hello",
        "status": "ok",
        "server": "mardi_doip_server",
        "version": protocol.DOIP_VERSION,
        "server_version": SERVER_VERSION,
        "availableOperations": {
            "hello": protocol.OP_HELLO,
            "retrieve": protocol.OP_RETRIEVE,
            "update": protocol.OP_UPDATE,
            "describe": protocol.OP_DESCRIBE, # not standard
            "invoke": protocol.OP_INVOKE, # not standard
            "create": protocol.OP_CREATE,
        },
        "typeRegistry": {
            "baseUri": type_base,
            "types": {t: f"{type_base}{t}" for t in KNOWN_TYPE_IDS},
        },
    }

    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_HELLO,
        flags=0,
        object_id=msg.object_id,
        metadata_blocks=[metadata_block],
    )

async def handle_describe(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Return the registry description for a PID/QID.

    Args:
        msg: Incoming DOIP describe request.
        registry: Object registry used to resolve manifests.

    Returns:
        DOIPMessage: Response containing the fetched manifest metadata.
    """
    pid = msg.object_id
    fdo_json = await registry.fetch_fdo_object(pid)
    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_DESCRIBE,
        flags=0,
        object_id=pid,
        metadata_blocks=[fdo_json],
    )


def _extract_type_id(object_id: str, fdo_api_base: str) -> str | None:
    """Return the type ID if object_id refers to a MaRDI type FDO, otherwise None.

    Accepts both the short form ``types/ScholarlyArticle`` and the full URI
    ``https://fdo.portal.mardi4nfdi.de/fdo/types/ScholarlyArticle``.

    Args:
        object_id: Raw object_id from the DOIP message.
        fdo_api_base: The configured FDO API base URL (e.g. "https://…/fdo/").

    Returns:
        str | None: Type ID (e.g. "ScholarlyArticle") or None if not a type ID.
    """
    if object_id.startswith("types/"):
        return object_id[len("types/"):]
    full_prefix = fdo_api_base.rstrip("/") + "/types/"
    if object_id.startswith(full_prefix):
        return object_id[len(full_prefix):]
    return None


async def handle_retrieve(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Retrieve metadata or a specific component for a DOIP object.

    If "element" is set in the meta-data block, the server tries to fetch it from the storage.

    If "element" == "rocrate" the server tries to build a rocrate object from the data stored with
    the object.

    Type FDOs (object_id starting with "types/" or the full type URI) are routed to
    the type registry endpoint and returned as metadata-only responses.

    Args:
        msg: Incoming DOIP retrieve request.
        registry: Object registry used to fetch manifests/components.

    Returns:
        DOIPMessage: Response containing metadata and optional components.

    Raises:
        KeyError: If a requested component cannot be found.
    """
    type_id = _extract_type_id(msg.object_id, getattr(registry, "fdo_api", ""))
    if type_id:
        fdo_json = await registry.fetch_type_fdo(type_id)
        return DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_RESPONSE,
            operation=protocol.OP_RETRIEVE,
            flags=0,
            object_id=msg.object_id,
            metadata_blocks=[fdo_json],
            component_blocks=[],
        )

    pid    = msg.object_id.upper()
    meta   = (msg.metadata_blocks[0] if msg.metadata_blocks else {})
    element   = meta.get("element")  # componentId or None

    log.info("handle_retrieve() for object_id=%s", pid)

    if element == "rocrate":
        try:
            crate, _ = await registry.get_component(pid, "rocrate")
        except KeyError:
            crate = await _build_rocrate_payload(pid, registry)
        except Exception as exc:
            raise KeyError(f"Component id not found: {element}") from exc
        return DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_RESPONSE,
            operation=protocol.OP_RETRIEVE,
            flags=0,
            object_id=pid,
            metadata_blocks=[],
            component_blocks=[
                ComponentBlock(
                    component_id="rocrate",
                    media_type="application/zip",
                    content=crate,
                    declared_size=len(crate),
                )
            ],
        )

    if element:
        try:
            content, media_type = await registry.get_component(pid, element)
            size = len(content)
        except Exception as exc:
            raise KeyError(f"Component id not found: {element}") from exc

        return DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_RESPONSE,
            operation=protocol.OP_RETRIEVE,
            flags=0,
            object_id=pid,
            metadata_blocks=[],
            component_blocks=[
                ComponentBlock(
                    component_id=element,
                    media_type=media_type,
                    content=content,
                    declared_size=size,
                )
            ],
        )

    fdo_json = await registry.fetch_fdo_object(pid)
    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id=pid,
        metadata_blocks=[fdo_json],
        component_blocks=[],
    )


async def handle_update(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Route an update request to either property update or component upload.

    If the metadata block contains a ``properties`` key and no component blocks
    are present, the request is treated as a Wikibase property update and
    forwarded to the importer. Otherwise the existing lakeFS component-upload
    path is taken.

    Args:
        msg: Incoming DOIP update request.
        registry: Object registry used to verify object existence and purge cache.

    Returns:
        DOIPMessage: Response confirming the update.

    Raises:
        protocol.ProtocolError: If authorization fails or the request is malformed.
    """
    object_id = msg.object_id.upper()
    metadata = msg.metadata_blocks[0] if msg.metadata_blocks else {}

    if "properties" in metadata and not msg.component_blocks:
        return await _handle_property_update(object_id, metadata, registry)

    element = metadata.get("element")
    username, password = _extract_wiki_credentials(metadata)
    await _validate_wiki_credentials(username, password)

    await registry.fetch_fdo_object(object_id)

    if len(msg.component_blocks) != 1:
        raise protocol.ProtocolError("update requires exactly one component block")

    component = msg.component_blocks[0]
    if not component.component_id:
        raise protocol.ProtocolError("update component_id is required")
    if element and element != component.component_id:
        raise protocol.ProtocolError("update metadata element must match component block id")

    media_type = component.media_type or "application/octet-stream"
    object_path = storage_lakefs.build_component_object_path(object_id, component.component_id)

    try:
        await storage_lakefs.put_component_bytes(
            object_id,
            component.component_id,
            component.content,
            media_type=media_type,
        )
        commit = await storage_lakefs.commit_changes(
            message=f"Update {object_id} component {component.component_id}",
            metadata={
                "operation": "update",
                "object_id": object_id,
                "component_id": component.component_id,
                "media_type": media_type,
            },
        )
    except Exception:
        try:
            await storage_lakefs.reset_uncommitted_object(object_path)
        except Exception:
            log.exception("Failed to reset uncommitted lakeFS object for %s", object_path)
        raise

    await registry.purge(object_id)

    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id=object_id,
        metadata_blocks=[
            {
                "operation": "update",
                "status": "committed",
                "objectId": object_id,
                "componentId": component.component_id,
                "mediaType": media_type,
                "size": len(component.content),
                "branch": commit["branch"],
                "commitId": commit["commit_id"],
            }
        ],
    )


async def _handle_property_update(
    object_id: str,
    metadata: dict,
    registry: object_registry.ObjectRegistry,
) -> DOIPMessage:
    """Forward a Wikibase property update to the importer service.

    Extracts wiki credentials, then posts ``{qid, username, password, ...properties}``
    to ``IMPORTER_API_URL/update/item``. On HTTP 409 (conflict) the importer's
    error and existing_values are surfaced as a ProtocolError so the caller
    knows what values are already present.

    Args:
        object_id: Target QID.
        metadata: Metadata block from the DOIP request.
        registry: Object registry; cache entry is purged on success.

    Returns:
        DOIPMessage: Response confirming the update.

    Raises:
        protocol.ProtocolError: On auth failure, bad payload, or importer error.
    """
    username, password = _extract_wiki_credentials(metadata)

    # The "properties" dict must use Wikibase P-IDs as keys (e.g. {"P28": "2024-01-15",
    # "P16": "Q456"}). Schema.org field names are NOT resolved server-side. To build a
    # valid payload, clients should first RETRIEVE the item's digitalObjectType FDO
    # (e.g. RETRIEVE fdo/types/ScholarlyArticle) and consult its propertyMappings to
    # translate field names to P-IDs before sending this request.
    properties = metadata.get("properties", {})
    if not isinstance(properties, dict):
        raise protocol.ProtocolError("update 'properties' must be a JSON object")

    importer_url = os.getenv("IMPORTER_API_URL", "http://localhost:8000").rstrip("/")
    safe_props = {k: v for k, v in properties.items() if k != "qid"}
    body = {"qid": object_id, "username": username, "password": password, **safe_props}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(f"{importer_url}/update/item", json=body)
        except Exception as exc:
            raise protocol.ProtocolError(f"Importer update/item request failed: {exc}")

    if resp.status_code == 409:
        try:
            result = resp.json()
        except Exception:
            result = {}
        existing = result.get("existing_values", [])
        raise protocol.ProtocolError(
            f"conflict: {result.get('error', 'property already set')} "
            f"Existing values: {existing}"
        )
    if not resp.is_success:
        raise protocol.ProtocolError(
            f"Importer update/item failed with status {resp.status_code}: {resp.text}"
        )

    await registry.purge(object_id)
    log.info("Updated properties for %s via importer", object_id)

    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id=object_id,
        metadata_blocks=[{
            "operation": "update",
            "status": "updated",
            "objectId": object_id,
        }],
    )


def _extract_wiki_credentials(metadata: dict) -> tuple[str, str]:
    """Extract wiki bot credentials from a DOIP metadata block.

    Args:
        metadata: DOIP metadata block from the incoming request.

    Returns:
        tuple[str, str]: (username, password)

    Raises:
        protocol.ProtocolError: If either field is absent or empty.
    """
    username = metadata.get("username")
    password = metadata.get("password")
    if not isinstance(username, str) or not username:
        raise protocol.ProtocolError("'username' is required in the metadata block")
    if not isinstance(password, str) or not password:
        raise protocol.ProtocolError("'password' is required in the metadata block")
    return username, password


async def _validate_wiki_credentials(username: str, password: str) -> None:
    """Verify wiki bot credentials against the MediaWiki login API.

    Used for operations that write to lakeFS directly (component uploads) and
    therefore cannot rely on the importer to surface an auth failure.

    Args:
        username: MediaWiki username (bot-password format: ``User@AppName``).
        password: MediaWiki bot password.

    Raises:
        protocol.ProtocolError: If the API is unreachable or credentials are invalid.
    """
    api_url = os.getenv("MEDIAWIKI_API_URL", "http://wikibase-jobrunner/w/api.php")
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(api_url, params={
                "action": "query",
                "meta": "tokens",
                "type": "login",
                "format": "json",
            })
            r.raise_for_status()
            login_token = r.json()["query"]["tokens"]["logintoken"]
        except Exception as exc:
            raise protocol.ProtocolError(f"Could not reach MediaWiki API for credential validation: {exc}")

        try:
            r = await client.post(api_url, data={
                "action": "login",
                "lgname": username,
                "lgpassword": password,
                "lgtoken": login_token,
                "format": "json",
            })
            r.raise_for_status()
            result = r.json().get("login", {}).get("result")
        except Exception as exc:
            raise protocol.ProtocolError(f"MediaWiki credential validation failed: {exc}")

    if result != "Success":
        log.warning("Wiki credential validation failed for user %s: %s", username, result)
        raise protocol.ProtocolError("Invalid wiki credentials")


async def handle_invoke(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Handle DOIP invoke requests by executing supported workflows.

    Args:
        msg: Incoming DOIP invoke request.
        registry: Object registry resolver.

    Returns:
        DOIPMessage: Response with workflow metadata and derived components.
    """
    qid = msg.object_id
    log.info("Handling invoke request for object_id=%s", qid)
    workflow_name, params = _requested_workflow(msg)
    if workflow_name == "equation_extraction":
        result = await workflows.run_equation_extraction_workflow(qid, params)
    else:
        raise protocol.ProtocolError(f"Unsupported workflow {workflow_name}")

    derived_blocks: List[ComponentBlock] = []
    for comp in result.get("derivedComponents", []):
        comp_id = comp["componentId"]
        content = await storage_lakefs.get_component_bytes(
            qid,
            comp_id,
        )
        derived_blocks.append(
            ComponentBlock(
                component_id=comp_id,
                content=content,
                media_type=comp.get("mediaType", "application/octet-stream"),
                declared_size=comp.get("size"),
            )
        )

    metadata_block = {
        "operation": "invoke",
        "workflow": workflow_name,
        "result": result,
    }

    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_INVOKE,
        flags=0,
        object_id=qid,
        metadata_blocks=[metadata_block],
        component_blocks=derived_blocks,
        workflow_blocks=[result],
    )


async def handle_purge(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Purge the cached manifest for a PID, forcing a fresh fetch on next access.

    Args:
        msg: Incoming DOIP purge request.
        registry: Object registry whose cache entry will be evicted.

    Returns:
        DOIPMessage: Response confirming the purge.
    """
    pid = msg.object_id
    await registry.purge(pid)
    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_PURGE,
        flags=0,
        object_id=pid,
        metadata_blocks=[{"status": "purged", "pid": pid.upper()}],
    )


async def handle_create(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Create a new Wikibase item via the importer service.

    Expects a JSON string in the ``json`` field of the first metadata block and
    ``username``/``password`` fields containing the user's wiki bot credentials.
    Runs schema validation before calling the importer.

    Args:
        msg: Incoming DOIP create request.
        registry: Object registry resolver (unused, for signature parity).

    Returns:
        DOIPMessage: Response containing the QID of the newly created item.

    Raises:
        protocol.ProtocolError: If auth fails, the payload is invalid, the
            importer is unreachable, or creation fails.
    """
    meta = msg.metadata_blocks[0] if msg.metadata_blocks else {}

    # 1. Extract wiki credentials
    username, password = _extract_wiki_credentials(meta)

    # 2. Parse JSON payload
    json_str = meta.get("json")
    if not json_str:
        raise protocol.ProtocolError("create requires a 'json' field in the metadata block")
    try:
        body = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise protocol.ProtocolError(f"create: invalid JSON: {exc}")

    # 3. Schema validation
    _validate_create_body(body)

    importer_url = os.getenv("IMPORTER_API_URL", "http://localhost:8000").rstrip("/")

    # 4. Health check
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            health = await client.get(f"{importer_url}/health")
            health.raise_for_status()
        except Exception as exc:
            raise protocol.ProtocolError(f"Importer service is not reachable at {importer_url}: {exc}")

    # 5. Create item with user credentials
    body["username"] = username
    body["password"] = password
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(f"{importer_url}/create/item", json=body)
            resp.raise_for_status()
        except Exception as exc:
            raise protocol.ProtocolError(f"Importer create/item failed: {exc}")

    result = resp.json()
    qid = result.get("qid") or ""
    log.info("Created item %s via importer", qid)

    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id=qid,
        metadata_blocks=[{"operation": "create", "status": "created", "qid": qid}],
    )



_PROP_RE = __import__("re").compile(r"^P\d+$")


def _validate_create_body(body: dict) -> None:
    """Validate the structure of a create request body.

    Accepts two formats:

    Raw format::

        {"label": "My item", "claims": {"P31": "Q5"}}

    Typed format (schema resolution happens in the importer)::

        {"type": "WORKFLOW", "fields": {"name": "My workflow"}}

    Args:
        body: Parsed JSON body from the create request.

    Raises:
        protocol.ProtocolError: If the body fails structural validation.
    """
    if not isinstance(body, dict):
        raise protocol.ProtocolError("create body must be a JSON object")

    if "type" in body:
        if not isinstance(body["type"], str) or not body["type"]:
            raise protocol.ProtocolError("'type' must be a non-empty string")
        fields = body.get("fields")
        if fields is not None and not isinstance(fields, dict):
            raise protocol.ProtocolError("'fields' must be a JSON object")
        return

    if not body.get("label") or not isinstance(body["label"], str):
        raise protocol.ProtocolError("create body must contain a non-empty 'label' string")

    claims = body.get("claims")
    if claims is None:
        return

    if not isinstance(claims, dict):
        raise protocol.ProtocolError("'claims' must be a JSON object")

    for key, value in claims.items():
        if not _PROP_RE.match(key):
            raise protocol.ProtocolError(f"invalid property ID '{key}': must match P<number>")
        if not isinstance(value, (str, int, float)):
            raise protocol.ProtocolError(
                f"invalid value for '{key}': must be a string or number, got {type(value).__name__}"
            )


async def handle_list_ops(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Return the list of supported operations.

    Args:
        msg: Incoming DOIP list-ops request.
        registry: Object registry resolver (unused, included for symmetry).

    Returns:
        DOIPMessage: Response describing available operations.
    """
    log.info("Handling list_ops request for object_id=%s", msg.object_id)
    metadata_block = {
        "operation": "list_operations",
        "availableOperations": {
            "hello": protocol.OP_HELLO,
            "retrieve": protocol.OP_RETRIEVE,
            "update": protocol.OP_UPDATE,
            "invoke": protocol.OP_INVOKE,
            "create": protocol.OP_CREATE,
        },
    }
    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_LIST_OPS,
        flags=0,
        object_id=msg.object_id,
        metadata_blocks=[metadata_block],
    )


def _requested_workflow(msg: DOIPMessage):
    """Extract requested workflow name and params from message blocks.

    Args:
        msg: DOIP invoke request message.

    Returns:
        tuple[str, dict]: Workflow name and parameters.

    Raises:
        protocol.ProtocolError: If workflow is missing.
    """
    for meta in msg.metadata_blocks:
        if "workflow" in meta:
            return meta["workflow"], meta.get("params", {})
    for wf in msg.workflow_blocks:
        if "workflow" in wf:
            return wf["workflow"], wf.get("params", {})
    raise protocol.ProtocolError("Workflow not specified in invoke request")


async def _get_component_media_type(registry: object_registry.ObjectRegistry, pid: str, component_id: str) -> str:
    """Resolve a component's media type from its manifest when possible.

    Args:
        registry: Object registry used to fetch manifests.
        pid: PID/QID of the target object.
        component_id: Component identifier to inspect.

    Returns:
        str: Resolved media type or ``application/octet-stream`` fallback.
    """
    try:
        manifest = await registry.fetch_fdo_object(pid)
    except Exception:
        return "application/octet-stream"

    kernel = manifest.get("kernel") if isinstance(manifest, dict) else None
    components = kernel.get("fdo:hasComponent") if isinstance(kernel, dict) else None
    if not isinstance(components, list):
        return "application/octet-stream"

    for comp in components:
        if not isinstance(comp, dict):
            continue
        if comp.get("componentId") == component_id:
            media_type = comp.get("mediaType") or comp.get("mimeType")
            if isinstance(media_type, str) and media_type.strip():
                return media_type

    return "application/octet-stream"

async def _build_rocrate_payload(pid: str, registry) -> bytes:
    """Return the RO-Crate payload for the given PID.

    Strategy:
      1. If a stored ``rocrate`` component exists, return it as-is.
      2. Otherwise, resolve a source URL from the FDO manifest and download it.
      3. If a download succeeds, wrap the file into a minimal RO-Crate ZIP.
      4. If nothing can be resolved, return empty bytes.

    Args:
        pid: PID/QID identifying the dataset object.
        registry: ObjectRegistry instance capable of returning components.

    Returns:
        bytes: RO-Crate bytes if available; empty bytes when absent.

    Raises:
        RuntimeError: If underlying storage access fails (non-missing errors).
    """

    # 1) Try stored rocrate component
    try:
        result = await registry.get_component(pid, "rocrate")
        # tolerate legacy signature returning bytes only
        content = result[0] if isinstance(result, tuple) else result
    except KeyError:
        content = None
    except ConnectionError:
        content = None
    except Exception as exc:
        raise RuntimeError(f"storage error fetching rocrate for {pid}") from exc

    if content is not None:
        return content

    # 2) Resolve a source URL from the manifest
    source_url = await _get_source_url(pid, registry)
    if source_url is None:
        return b""

    # 3) Download and package as RO-Crate
    try:
        log.info("Downloading data from %s", source_url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()
            payload = resp.content
    except Exception as exc:  # noqa: BLE001
        log.debug("Failed to download rocrate for %s from %s: %s", pid, source_url, exc)
        return b""

    filename = _filename_from_url(source_url, pid)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    tmp_dir = tempfile.TemporaryDirectory()
    tmp_path = Path(tmp_dir.name)
    tmp_file = tmp_path / filename
    tmp_file.write_bytes(payload)

    crate = ROCrate()
    file_entity = File(crate, str(tmp_file), properties={"encodingFormat": media_type, "name": filename})
    crate.add(file_entity)
    crate.root_dataset["name"] = pid
    crate.root_dataset.append_to("hasPart", file_entity)

    out_zip = tmp_path / "crate.zip"
    crate.write_zip(str(out_zip))
    data = out_zip.read_bytes()
    tmp_dir.cleanup()
    return data


async def _get_source_url(pid: str, registry) -> str | None:
    """Return the first distribution/download URL from the FDO manifest.

    For this project the manifest's distribution URLs play the role of P205. The
    lookup is best-effort; errors are logged and surfaced as ``None`` so the main
    workflow is never blocked.

    Args:
        pid: PID/QID for which to resolve distribution URLs.
        registry: ObjectRegistry used to fetch the manifest.

    Returns:
        str | None: First distribution URL if found, otherwise ``None``.
    """
    try:
        manifest = await registry.fetch_fdo_object(pid)
        if not isinstance(manifest, dict):
            return None

        profile = manifest.get("profile")
        distributions = profile.get("distribution") if isinstance(profile, dict) else None
        if not isinstance(distributions, list):
            log.debug("No distribution list in manifest for %s", pid)
            return None

        for dist in distributions:
            if not isinstance(dist, dict):
                continue
            url = dist.get("contentUrl") or dist.get("contentURL") or dist.get("url")
            if isinstance(url, str):
                log.info("Found distribution URL (P205 equivalent) for %s: %s", pid, url)
                return url

        log.debug("No distribution URLs (P205 equivalent) found for %s", pid)
        return None
    except Exception as exc:  # noqa: BLE001
        log.debug("Skipping P205 lookup for %s: %s", pid, exc)
        return None


def _filename_from_url(url: str, pid: str) -> str:
    """Return a filename derived from a URL, with a safe fallback.

    Args:
        url: Source URL.
        pid: PID/QID used as fallback stem.

    Returns:
        str: Filename to use inside the RO-Crate.
    """
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if name:
        return name
    return f"{pid}.bin"
