import asyncio

import pytest

from doip_server import protocol


@pytest.mark.asyncio
async def test_doip_roundtrip_with_metadata_components_and_workflow():
    """Verify DOIP message roundtrip retains metadata, workflow, and components.

    Returns:
        None
    """
    message = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[{"foo": "bar"}],
        component_blocks=[
            protocol.ComponentBlock(
                component_id="doip:bitstream/Q123/main-pdf",
                content=b"hello",
                media_type="application/pdf",
            )
        ],
        workflow_blocks=[{"workflow": "noop", "status": "ok"}],
    )

    payload = message.to_bytes()

    reader = asyncio.StreamReader()
    reader.feed_data(payload)
    reader.feed_eof()

    parsed = await protocol.read_doip_message(reader)

    assert parsed.version == protocol.DOIP_VERSION
    assert parsed.msg_type == protocol.MSG_TYPE_REQUEST
    assert parsed.operation == protocol.OP_RETRIEVE
    assert parsed.object_id == "Q123"
    assert parsed.metadata_blocks == [{"foo": "bar"}]
    assert parsed.workflow_blocks == [{"workflow": "noop", "status": "ok"}]
    assert len(parsed.component_blocks) == 1
    comp = parsed.component_blocks[0]
    assert comp.component_id == "doip:bitstream/Q123/main-pdf"
    assert comp.media_type == "application/pdf"
    assert comp.content == b"hello"
