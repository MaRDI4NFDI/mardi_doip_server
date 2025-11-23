"""Strict DOIP v2.0 client implementation."""

from __future__ import annotations

import socket
import struct
from typing import Optional

from . import protocol, tls, utils
from .messages import ComponentBlock, DoipRequest, DoipResponse
from .protocol import (
    BLOCK_COMPONENT,
    BLOCK_METADATA,
    BLOCK_WORKFLOW,
    DOIP_VERSION,
    HEADER_STRUCT,
    MSG_TYPE_REQUEST,
    encode_doip_block,
    decode_doip_blocks,
    decode_header,
    Header,
)

OP_HELLO = 0x01
OP_RETRIEVE = 0x02
OP_LIST_OPS = 0x04


class StrictDOIPClient:
    """Blocking TCP/TLS DOIP v2.0 client."""

    def __init__(self, host: str, port: int, use_tls: bool = True, verify_tls: bool = True, timeout: int = 10):
        """Initialize the client.

        Args:
            host: Server hostname or IP.
            port: Server port.
            use_tls: Wrap connection with TLS if True.
            verify_tls: Verify server certificate/hostname when TLS is enabled.
            timeout: Socket timeout in seconds.
        """
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.verify_tls = verify_tls
        self.timeout = timeout

    def hello(self) -> dict:
        """Perform the DOIP hello operation and return response metadata.

        Returns:
            Metadata dictionary from the server.
        """
        request = DoipRequest(
            header=Header(DOIP_VERSION, MSG_TYPE_REQUEST, OP_HELLO, 0, 0, 0),
            object_id="",
            metadata_blocks=[{"operation": "hello"}],
        )
        response = self.send_message(request)
        return response.metadata_blocks[0] if response.metadata_blocks else {}

    def list_ops(self) -> dict:
        """Request the list of supported operations from the server.

        Returns:
            Metadata dictionary describing available operations.
        """
        request = DoipRequest(
            header=Header(DOIP_VERSION, MSG_TYPE_REQUEST, OP_LIST_OPS, 0, 0, 0),
            object_id="",
            metadata_blocks=[{"operation": "list_operations"}],
        )
        response = self.send_message(request)
        return response.metadata_blocks[0] if response.metadata_blocks else {}

    def retrieve(self, object_id: str, component: Optional[str] = None) -> DoipResponse:
        """Retrieve components for a given object ID.

        Args:
            object_id: Target object identifier.
            component: Optional component ID to filter the response.

        Returns:
            Parsed DOIP response envelope.
        """
        metadata = {"operation": "retrieve", "objectId": object_id}
        if component:
            metadata["components"] = [component]
        request = DoipRequest(
            header=Header(DOIP_VERSION, MSG_TYPE_REQUEST, OP_RETRIEVE, 0, 0, 0),
            object_id=object_id,
            metadata_blocks=[metadata],
        )
        return self.send_message(request)

    def send_message(self, request: DoipRequest) -> DoipResponse:
        """Send a strict DOIP request and parse the response.

        Args:
            request: Fully constructed DOIP request envelope.

        Returns:
            Parsed DOIP response envelope.

        Raises:
            ConnectionError: If the socket closes unexpectedly.
            ValueError: If framing is invalid.
        """
        object_id_bytes = request.object_id.encode("utf-8")
        payload_parts: list[bytes] = []

        for meta in request.metadata_blocks:
            payload_parts.append(encode_doip_block(BLOCK_METADATA, utils.dict_to_json_bytes(meta)))
        for comp in request.component_blocks:
            payload_parts.append(encode_doip_block(BLOCK_COMPONENT, self._encode_component_body(comp)))
        for wf in request.workflow_blocks:
            payload_parts.append(encode_doip_block(BLOCK_WORKFLOW, utils.dict_to_json_bytes(wf)))

        payload = b"".join(payload_parts)
        payload_len = len(payload)

        header_bytes = HEADER_STRUCT.pack(
            DOIP_VERSION,
            MSG_TYPE_REQUEST,
            request.header.op_code,
            request.header.flags,
            len(object_id_bytes),
            payload_len,
        )
        message = header_bytes + object_id_bytes + payload

        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise ConnectionError(
                f"Failed to connect to {self.host}:{self.port} "
                f"(tls={self.use_tls}, verify_tls={self.verify_tls}, timeout={self.timeout}s): {exc}"
            ) from exc
        sock = tls.wrap_socket(sock, self.host, self.use_tls, self.verify_tls)
        try:
            sock.sendall(message)

            resp_header_bytes = self._recv_exact(sock, protocol.HEADER_LENGTH)
            resp_header = decode_header(resp_header_bytes)

            object_id = self._recv_exact(sock, resp_header.object_id_len)
            payload_bytes = self._recv_exact(sock, resp_header.payload_len)

            metadata_blocks, component_blocks, workflow_blocks = decode_doip_blocks(payload_bytes)

            return DoipResponse(
                header=resp_header,
                metadata_blocks=metadata_blocks,
                component_blocks=component_blocks,
                workflow_blocks=workflow_blocks,
            )
        finally:
            sock.close()

    @staticmethod
    def _encode_component_body(block: ComponentBlock) -> bytes:
        """Encode a component block body (without type/length).

        Args:
            block: Component block to encode.

        Returns:
            Encoded component body bytes.
        """
        comp_id_bytes = block.component_id.encode("utf-8")
        media_bytes = (block.media_type or "").encode("utf-8")
        content = block.content
        body = b"".join(
            [
                struct.pack(">H", len(comp_id_bytes)),
                comp_id_bytes,
                struct.pack(">H", len(media_bytes)),
                media_bytes,
                struct.pack(">I", len(content)),
                content,
            ]
        )
        return body

    @staticmethod
    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        """Receive exactly size bytes from the socket.

        Args:
            sock: Socket to read from.
            size: Number of bytes to read.

        Returns:
            Bytes read from the socket.

        Raises:
            ConnectionError: If the socket closes early.
        """
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = sock.recv(remaining)
            if not chunk:
                raise ConnectionError("Socket closed before receiving expected bytes")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
