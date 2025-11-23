import json

import pytest

from doip_server import handlers, main, protocol


class StubDOIPMessage(protocol.DOIPMessage):
    """Simple subclass to ease instantiation in tests."""


@pytest.mark.asyncio
async def test_compat_process_hello(monkeypatch):
    fake_msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_HELLO,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "hello", "status": "ok"}],
        component_blocks=[],
    )

    async def fake_handle_hello(msg, registry):
        return fake_msg

    monkeypatch.setattr(handlers, "handle_hello", fake_handle_hello)

    body = {"operationId": protocol.OP_HELLO}
    segments = await main._process_compat_request(body, registry=None)  # type: ignore[arg-type]

    status = json.loads(segments[0])
    assert status["status"] == "success"
    assert status["metadata"] == fake_msg.metadata_blocks
    assert len(segments) == 1


@pytest.mark.asyncio
async def test_compat_process_retrieve(monkeypatch):
    fake_msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="QX",
        metadata_blocks=[{"operation": "retrieve"}],
        component_blocks=[
            protocol.ComponentBlock(
                component_id="comp1",
                content=b"data",
                media_type="application/octet-stream",
            )
        ],
    )

    async def fake_handle_retrieve(msg, registry):
        return fake_msg

    monkeypatch.setattr(handlers, "handle_retrieve", fake_handle_retrieve)

    body = {"targetId": "QX", "operationId": protocol.OP_RETRIEVE, "attributes": {"element": "comp1"}}
    segments = await main._process_compat_request(body, registry=None)  # type: ignore[arg-type]

    # First segment is JSON status, second is component content
    status = json.loads(segments[0])
    assert status["status"] == "success"
    assert status["metadata"] == fake_msg.metadata_blocks
    assert segments[1] == b"data"


@pytest.mark.asyncio
async def test_compat_process_invoke(monkeypatch):
    fake_msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_RESPONSE,
        operation=protocol.OP_INVOKE,
        flags=0,
        object_id="QY",
        metadata_blocks=[{"operation": "invoke"}],
        component_blocks=[],
    )

    async def fake_handle_invoke(msg, registry):
        return fake_msg

    monkeypatch.setattr(handlers, "handle_invoke", fake_handle_invoke)

    body = {"targetId": "QY", "operationId": protocol.OP_INVOKE, "attributes": {"workflow": "wf"}}
    segments = await main._process_compat_request(body, registry=None)  # type: ignore[arg-type]

    status = json.loads(segments[0])
    assert status["status"] == "success"
    assert status["metadata"] == fake_msg.metadata_blocks
    assert len(segments) == 1  # no components returned
