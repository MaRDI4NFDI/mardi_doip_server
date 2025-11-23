import asyncio
import json
import logging
import os
import ssl
import struct
from pathlib import Path
from functools import partial

from . import handlers, object_registry, protocol

log = logging.getLogger("doip_server")
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")


async def handle_connection(registry: object_registry.ObjectRegistry, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Process DOIP messages on a single TCP connection.

    Args:
        registry: Object registry instance.
        reader: StreamReader for the client.
        writer: StreamWriter for the client.
    """
    peer = writer.get_extra_info("peername")
    log.info("Connection from %s", peer)
    try:
        while True:
            try:
                msg = await protocol.read_doip_message(reader)
            except asyncio.IncompleteReadError:
                break
            except protocol.ProtocolError as exc:
                log.warning("Protocol error from %s: %s", peer, exc)
                await _send_error(writer, "", exc)
                break

            try:
                response = await dispatch(msg, registry)
            except protocol.ProtocolError as exc:
                log.warning("Operation error for %s: %s", peer, exc)
                response = _error_message(msg, exc)
            except Exception as exc:  # noqa: BLE001
                log.exception("Unhandled error for %s", peer)
                response = _error_message(msg, exc)

            writer.write(response.to_bytes())
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()
        log.info("Connection closed %s", peer)


def _metadata_operation_name(msg: protocol.DOIPMessage) -> str | None:
    """Return the requested operation name from metadata if present."""
    for meta in msg.metadata_blocks:
        op_name = meta.get("operation")
        if isinstance(op_name, str):
            return op_name
    return None


async def dispatch(msg: protocol.DOIPMessage, registry: object_registry.ObjectRegistry) -> protocol.DOIPMessage:
    """Route a DOIP request to the appropriate handler.

    Args:
        msg: Parsed DOIP request.
        registry: Object registry instance.

    Returns:
        DOIPMessage: Handler response message.
    """
    if msg.msg_type != protocol.MSG_TYPE_REQUEST:
        raise protocol.ProtocolError("Only request messages are supported")
    op_name = _metadata_operation_name(msg)
    if msg.operation == protocol.OP_HELLO or op_name == "hello":
        return await handlers.handle_hello(msg, registry)
    if msg.operation == protocol.OP_RETRIEVE or op_name == "retrieve":
        return await handlers.handle_retrieve(msg, registry)
    if msg.operation == protocol.OP_INVOKE or op_name == "invoke":
        return await handlers.handle_invoke(msg, registry)
    raise protocol.ProtocolError(f"Unsupported operation code {msg.operation}")


def _error_message(msg: protocol.DOIPMessage, exc: Exception) -> protocol.DOIPMessage:
    """Build an error response message.

    Args:
        msg: Original DOIP message.
        exc: Exception raised.

    Returns:
        DOIPMessage: Error envelope.
    """
    return protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_ERROR,
        operation=msg.operation,
        flags=0,
        object_id=msg.object_id,
        metadata_blocks=[{"error": type(exc).__name__, "message": str(exc)}],
    )


async def _send_error(writer: asyncio.StreamWriter, object_id: str, exc: Exception):
    """Send an error envelope directly to a writer.

    Args:
        writer: Destination writer.
        object_id: Object identifier context.
        exc: Exception to serialize.
    """
    msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_ERROR,
        operation=0,
        flags=0,
        object_id=object_id,
        metadata_blocks=[{"error": type(exc).__name__, "message": str(exc)}],
    )
    writer.write(msg.to_bytes())
    await writer.drain()


async def main(port: int = 3567):
    """Entrypoint: start the asyncio DOIP TCP server.

    Args:
        port: TCP port for the server.
    """
    registry = object_registry.ObjectRegistry()
    ssl_ctx = _maybe_create_ssl_context()
    server = await asyncio.start_server(
        partial(handle_connection, registry), host="0.0.0.0", port=port, ssl=ssl_ctx
    )
    compat_server = await asyncio.start_server(
        partial(handle_compat_connection, registry), host="0.0.0.0", port=port + 1, ssl=ssl_ctx
    )
    sockets = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    compat_sockets = ", ".join(str(sock.getsockname()) for sock in compat_server.sockets or [])
    if ssl_ctx:
        log.info("DOIP server listening with TLS on %s", sockets)
        log.info("Compat JSON-segment listener with TLS on %s", compat_sockets)
    else:
        log.info("DOIP server listening (plaintext) on %s", sockets)
        log.info("Compat JSON-segment listener (plaintext) on %s", compat_sockets)
    async with server, compat_server:
        await asyncio.gather(server.serve_forever(), compat_server.serve_forever())


def _maybe_create_ssl_context() -> ssl.SSLContext | None:
    """Create an SSL context using local certificate/key files if present."""
    cert_path = Path("certs/server.crt")
    key_path = Path("certs/server.key")
    if not cert_path.exists() or not key_path.exists():
        return None
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return ctx


async def handle_compat_connection(
    registry: object_registry.ObjectRegistry, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
):
    """Handle doipy JSON-segmented requests and bridge to DOIP handlers."""
    peer = writer.get_extra_info("peername")
    log.info("Compat connection from %s", peer)
    try:
        try:
            segments = await _read_segments(reader)
        except Exception as exc:  # noqa: BLE001
            log.warning("Compat read failed from %s: %s", peer, exc)
            writer.close()
            await writer.wait_closed()
            return
        if not segments:
            writer.close()
            await writer.wait_closed()
            return
        try:
            request_json = json.loads(segments[0].decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Compat invalid JSON from %s: %s", peer, exc)
            writer.close()
            await writer.wait_closed()
            return
        response_segments = await _process_compat_request(request_json, registry)
        await _write_segments(writer, response_segments)
    finally:
        writer.close()
        await writer.wait_closed()
        log.info("Compat connection closed %s", peer)


async def _process_compat_request(body: dict, registry: object_registry.ObjectRegistry) -> list[bytes]:
    """Translate a doipy JSON request into a DOIP handler response."""
    target = body.get("targetId") or body.get("target_id")
    operation = body.get("operationId") or body.get("operation_id")
    attributes = body.get("attributes") or {}
    component = attributes.get("element") or attributes.get("componentId")

    if operation in (protocol.OP_HELLO, "HELLO", "hello", 1):
        msg = protocol.DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_REQUEST,
            operation=protocol.OP_HELLO,
            flags=0,
            object_id=target or "",
            metadata_blocks=[{"operation": "hello"}],
        )
        response = await handlers.handle_hello(msg, registry)
        return _compat_response_from_doip(response)

    if operation in (protocol.OP_RETRIEVE, "RETRIEVE", "retrieve", 2):
        msg = protocol.DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_REQUEST,
            operation=protocol.OP_RETRIEVE,
            flags=0,
            object_id=target or "",
            metadata_blocks=[{"components": [component]}] if component else [],
        )
        response = await handlers.handle_retrieve(msg, registry)
        return _compat_response_from_doip(response)

    if operation in (protocol.OP_INVOKE, "INVOKE", "invoke", 5):
        workflow = attributes.get("workflow") or body.get("workflow") or "equation_extraction"
        params = attributes.get("params") or body.get("params") or {}
        msg = protocol.DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_REQUEST,
            operation=protocol.OP_INVOKE,
            flags=0,
            object_id=target or "",
            metadata_blocks=[{"workflow": workflow, "params": params}],
        )
        response = await handlers.handle_invoke(msg, registry)
        return _compat_response_from_doip(response)

    meta = {"status": "error", "message": f"Unsupported operation {operation}"}
    return [_json_segment(meta)]


def _compat_response_from_doip(msg: protocol.DOIPMessage) -> list[bytes]:
    """Convert a DOIPMessage response into doipy-style segments."""
    segments: list[bytes] = []
    status = {
        "status": "success",
        "metadata": msg.metadata_blocks,
    }
    if msg.component_blocks:
        first = msg.component_blocks[0]
        status.setdefault("attributes", {})["filename"] = first.component_id
    segments.append(_json_segment(status))
    for comp in msg.component_blocks:
        segments.append(comp.content)
    return segments


async def _read_segments(reader: asyncio.StreamReader) -> list[bytes]:
    """Read length-prefixed segments terminated by a zero-length segment."""
    segments: list[bytes] = []
    while True:
        length_bytes = await reader.readexactly(4)
        length = struct.unpack(">I", length_bytes)[0]
        if length == 0:
            break
        data = await reader.readexactly(length)
        segments.append(data)
    return segments


async def _write_segments(writer: asyncio.StreamWriter, segments: list[bytes]) -> None:
    """Write length-prefixed segments ending with an empty terminator."""
    for seg in segments:
        writer.write(struct.pack(">I", len(seg)))
        writer.write(seg)
    writer.write(struct.pack(">I", 0))
    await writer.drain()


def _json_segment(data: dict) -> bytes:
    """Serialize a JSON dict to bytes for compat responses."""
    return json.dumps(data).encode("utf-8")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Server stopped by user")
