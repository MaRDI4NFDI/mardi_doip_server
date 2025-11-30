import asyncio
import logging
from typing import List

from . import object_registry, protocol, storage_lakefs, workflows
from .protocol import ComponentBlock, DOIPMessage

log = logging.getLogger(__name__)


async def handle_hello(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Respond to hello/health check requests with server metadata.

    Args:
        msg: Incoming DOIP hello request.
        registry: Object registry resolver (unused, for signature parity).

    Returns:
        DOIPMessage: Response containing server status and capabilities.
    """
    log.info("Handling hello request for object_id=%s", msg.object_id)
    metadata_block = {
        "operation": "hello",
        "status": "ok",
        "server": "mardi_doip_server",
        "version": protocol.DOIP_VERSION,
        "availableOperations": {
            "hello": protocol.OP_HELLO,
            "retrieve": protocol.OP_RETRIEVE,
            "describe": protocol.OP_DESCRIBE, # not standard
            "invoke": protocol.OP_INVOKE, # not standard
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


async def handle_retrieve(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Retrieve metadata or a specific component for a DOIP object.

    Args:
        msg: Incoming DOIP retrieve request.
        registry: Object registry used to fetch manifests/components.

    Returns:
        DOIPMessage: Response containing metadata and optional components.

    Raises:
        KeyError: If a requested component cannot be found.
    """
    pid    = msg.object_id.upper()
    meta   = (msg.metadata_blocks[0] if msg.metadata_blocks else {})
    elem   = meta.get("element")  # componentId or None

    if elem == "rocrate":
        crate = await _build_rocrate_payload(pid, registry)
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

    if elem:
        try:
            content = await registry.get_component(pid, elem)
            size = len(content)
        except Exception as exc:
            raise KeyError(f"Component id not found: {elem}") from exc

        media_type = await _get_component_media_type(registry, pid, elem)

        return DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_RESPONSE,
            operation=protocol.OP_RETRIEVE,
            flags=0,
            object_id=pid,
            metadata_blocks=[],
            component_blocks=[
                ComponentBlock(
                    component_id=elem,
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
        content = await storage_lakefs.get_component_bytes(qid)
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
            "invoke": protocol.OP_INVOKE,
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
    """
    Build a minimal RO-Crate ZIP containing the primary dataset file.

    This constructs an in-memory ZIP archive compliant with the RO-Crate 1.1
    packaging model. The crate includes:
      • a single CSV file associated with the PID (assumed to be the only payload)
      • a generated `ro-crate-metadata.json` file describing the dataset root entity
        and the file entity using JSON-LD with the official RO-Crate context

    The dataset PID becomes the root `Dataset` identifier and the CSV file is
    represented as a `File` entity linked via `hasPart`. No additional provenance,
    licensing, or authorship information is included.

    Args:
        pid: Upper-case PID string representing the dataset object.
        registry: ObjectRegistry instance capable of returning the CSV payload.

    Returns:
        bytes: A ZIP archive as raw bytes containing metadata and the dataset file.

    Raises:
        KeyError: If the expected dataset component is missing.
        RuntimeError: If underlying storage access fails.
    """

    import io, zipfile, json, mimetypes

    component_id = f"{pid}.csv"
    content = await registry.get_component(pid, component_id)
    media_type = mimetypes.guess_type(component_id)[0] or "application/octet-stream"

    metadata = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "./",
                "@type": "Dataset",
                "name": pid,
                "hasPart": [{"@id": component_id}],
                "identifier": pid,
            },
            {
                "@id": component_id,
                "@type": "File",
                "name": component_id,
                "encodingFormat": media_type,
            },
        ],
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("ro-crate-metadata.json", json.dumps(metadata))
        z.writestr(component_id, content)

    return buf.getvalue()
