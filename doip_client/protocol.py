"""Client-side DOIP protocol helpers matching the server framing."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Tuple

from doip_shared.constants import (
    BLOCK_COMPONENT,
    BLOCK_METADATA,
    BLOCK_WORKFLOW,
    DOIP_VERSION,
    MSG_TYPE_REQUEST,
)

from . import utils

HEADER_STRUCT = struct.Struct(">BBBBHI")
HEADER_LENGTH = HEADER_STRUCT.size


@dataclass
class Header:
    """Parsed DOIP header fields."""

    version: int
    msg_type: int
    op_code: int
    flags: int
    object_id_len: int
    payload_len: int


def encode_doip_block(block_type: int, body: bytes) -> bytes:
    """Prefix a block body with type and length.

    Args:
        block_type: DOIP block type identifier.
        body: Block payload.

    Returns:
        Bytes containing block type, length, and body.
    """
    return struct.pack(">BI", block_type, len(body)) + body


def decode_header(header_bytes: bytes) -> Header:
    """Decode a DOIP header into a Header dataclass.

    Args:
        header_bytes: Raw header bytes of fixed length.

    Returns:
        Parsed Header instance.

    Raises:
        ValueError: If the header is not the expected length.
    """
    if len(header_bytes) != HEADER_LENGTH:
        raise ValueError(f"Expected {HEADER_LENGTH} header bytes, got {len(header_bytes)}")
    version, msg_type, op_code, flags, object_id_len, payload_len = HEADER_STRUCT.unpack(header_bytes)
    return Header(
        version=version,
        msg_type=msg_type,
        op_code=op_code,
        flags=flags,
        object_id_len=object_id_len,
        payload_len=payload_len,
    )


def decode_doip_blocks(payload: bytes) -> Tuple[list[dict], list["ComponentBlock"], list[dict]]:
    """Decode DOIP payload blocks into metadata/component/workflow lists.

    Args:
        payload: Raw payload bytes containing framed blocks.

    Returns:
        Tuple of (metadata_blocks, component_blocks, workflow_blocks).

    Raises:
        ValueError: If framing is invalid or truncated.
    """
    from .messages import ComponentBlock  # local import to avoid circular dependency

    metadata_blocks: List[dict] = []
    component_blocks: List[ComponentBlock] = []
    workflow_blocks: List[dict] = []

    offset = 0
    payload_len = len(payload)
    while offset < payload_len:
        if offset + 5 > payload_len:
            raise ValueError("Truncated DOIP block header")
        block_type = payload[offset]
        block_len = struct.unpack_from(">I", payload, offset + 1)[0]
        offset += 5
        end = offset + block_len
        if end > payload_len:
            raise ValueError("Truncated DOIP block body")
        block_body = payload[offset:end]
        offset = end

        if block_type == BLOCK_METADATA:
            metadata_blocks.append(utils.json_bytes_to_dict(block_body))
        elif block_type == BLOCK_WORKFLOW:
            workflow_blocks.append(utils.json_bytes_to_dict(block_body))
        elif block_type == BLOCK_COMPONENT:
            component_blocks.append(_decode_component_block(block_body))
        else:
            raise ValueError(f"Unknown DOIP block type {block_type}")

    return metadata_blocks, component_blocks, workflow_blocks


def _decode_component_block(body: bytes) -> "ComponentBlock":
    """Decode a component block body into a ComponentBlock.

    Args:
        body: Block body without the type/length prefix.

    Returns:
        ComponentBlock parsed from the body.

    Raises:
        ValueError: If the body is truncated or malformed.
    """
    from .messages import ComponentBlock  # local import to avoid circular dependency

    if len(body) < 8:
        raise ValueError("Component block too small")
    offset = 0
    comp_id_len = struct.unpack_from(">H", body, offset)[0]
    offset += 2
    comp_id = body[offset : offset + comp_id_len].decode("utf-8")
    offset += comp_id_len
    media_len = struct.unpack_from(">H", body, offset)[0]
    offset += 2
    media_type = body[offset : offset + media_len].decode("utf-8")
    offset += media_len
    content_len = struct.unpack_from(">I", body, offset)[0]
    offset += 4
    content = body[offset : offset + content_len]
    if len(content) != content_len:
        raise ValueError("Component content length mismatch")
    return ComponentBlock(
        component_id=comp_id,
        content=content,
        media_type=media_type or "application/octet-stream",
        declared_size=content_len,
    )
