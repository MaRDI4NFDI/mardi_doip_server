import struct

from doip_client import StrictDOIPClient
from doip_client.protocol import (
    BLOCK_COMPONENT,
    BLOCK_METADATA,
    HEADER_STRUCT,
    decode_doip_blocks,
    decode_header,
)
from doip_shared.constants import DOIP_VERSION, MSG_TYPE_RESPONSE, OP_RETRIEVE


def test_decode_header_and_blocks_roundtrip():
    """Verify client can decode headers and payload blocks.

    Returns:
        None
    """
    # Build a fake DOIP message (response) with one metadata and one component block.
    object_id = "QX"
    object_id_bytes = object_id.encode("utf-8")
    meta_body = b'{"operation":"retrieve"}'
    comp_body = (
        struct.pack(">H", 3)
        + b"foo"
        + struct.pack(">H", len(b"text/plain"))
        + b"text/plain"
        + struct.pack(">I", 5)
        + b"hello"
    )
    payload = (
        struct.pack(">BI", BLOCK_METADATA, len(meta_body))
        + meta_body
        + struct.pack(">BI", BLOCK_COMPONENT, len(comp_body))
        + comp_body
    )
    header_bytes = HEADER_STRUCT.pack(
        DOIP_VERSION,
        MSG_TYPE_RESPONSE,
        OP_RETRIEVE,
        0,
        len(object_id_bytes),
        len(payload),
    )
    wire = header_bytes + object_id_bytes + payload

    hdr = decode_header(wire[: HEADER_STRUCT.size])
    assert hdr.version == DOIP_VERSION
    assert hdr.msg_type == MSG_TYPE_RESPONSE
    assert hdr.op_code == OP_RETRIEVE
    assert hdr.payload_len == len(payload)

    meta, comps, wfs = decode_doip_blocks(payload)
    assert meta == [{"operation": "retrieve"}]
    assert not wfs
    assert len(comps) == 1
    comp = comps[0]
    assert comp.component_id == "foo"
    assert comp.media_type == "text/plain"
    assert comp.content == b"hello"
