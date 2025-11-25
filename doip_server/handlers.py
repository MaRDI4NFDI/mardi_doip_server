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
            "invoke": protocol.OP_INVOKE,
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


async def handle_retrieve(msg: DOIPMessage, registry: object_registry.ObjectRegistry) -> DOIPMessage:
    """Handle DOIP retrieve requests by streaming components and metadata.

    Args:
        msg: Incoming DOIP retrieve request.
        registry: Object registry resolver.

    Returns:
        DOIPMessage: Response containing metadata and component blocks.
    """
    qid = msg.object_id
    log.info("Handling retrieve request for object_id=%s", qid)
    if not await storage_lakefs.ensure_lakefs_available():
        log.error("LakeFS/S3 endpoint not configured or unreachable")
        raise protocol.ProtocolError("Storage backend unavailable")
    requested_components = _requested_components(msg)
    manifest_components = await registry.get_components(qid)
    components = [
        comp
        for comp in manifest_components
        if not requested_components or comp["componentId"] in requested_components
    ]
    if requested_components:
        missing = set(requested_components) - {c["componentId"] for c in components}
        if missing:
            raise protocol.ProtocolError(f"Missing components: {sorted(missing)}")

    component_blocks: List[ComponentBlock] = []
    for comp in components:
        content = await storage_lakefs.get_component_bytes(qid, comp["componentId"])
        component_blocks.append(
            ComponentBlock(
                component_id=comp["componentId"],
                content=content,
                media_type=comp.get("mediaType", "application/octet-stream"),
                declared_size=comp.get("size"),
            )
        )

    metadata_block = {
        "operation": "retrieve",
        "objectId": qid,
        "components": components,
    }

    return DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id=qid,
        metadata_blocks=[metadata_block],
        component_blocks=component_blocks,
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
        content = await storage_lakefs.get_component_bytes(qid, comp_id)
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


def _requested_components(msg: DOIPMessage):
    """Extract requested component IDs from metadata blocks.

    Args:
        msg: DOIP request message.

    Returns:
        list[str] | None: Requested component IDs or None for all.
    """
    for meta in msg.metadata_blocks:
        comps = meta.get("components")
        if comps:
            return comps
    return None


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
