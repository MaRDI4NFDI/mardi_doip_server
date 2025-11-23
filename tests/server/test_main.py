import pytest

from doip_server import handlers, main, protocol


class DummyRegistry:
    pass


@pytest.mark.asyncio
async def test_dispatch_routes_hello(monkeypatch):
    called = {}

    async def fake_handle_hello(msg, registry):
        called["op"] = msg.operation
        return protocol.DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_RESPONSE,
            operation=protocol.OP_HELLO,
            flags=0,
            object_id=msg.object_id,
        )

    monkeypatch.setattr(handlers, "handle_hello", fake_handle_hello)

    msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_HELLO,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "hello"}],
    )

    response = await main.dispatch(msg, DummyRegistry())

    assert called["op"] == protocol.OP_HELLO
    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_HELLO


@pytest.mark.asyncio
async def test_dispatch_uses_metadata_operation(monkeypatch):
    async def fake_handle_hello(msg, registry):
        return protocol.DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_RESPONSE,
            operation=protocol.OP_HELLO,
            flags=0,
            object_id=msg.object_id,
        )

    monkeypatch.setattr(handlers, "handle_hello", fake_handle_hello)

    msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=0x99,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "hello"}],
    )

    response = await main.dispatch(msg, DummyRegistry())

    assert response.operation == protocol.OP_HELLO


@pytest.mark.asyncio
async def test_dispatch_routes_retrieve(monkeypatch):
    called = {}

    async def fake_handle_retrieve(msg, registry):
        called["op"] = msg.operation
        return protocol.DOIPMessage(
            version=protocol.DOIP_VERSION,
            msg_type=protocol.MSG_TYPE_RESPONSE,
            operation=protocol.OP_RETRIEVE,
            flags=0,
            object_id=msg.object_id,
        )

    monkeypatch.setattr(handlers, "handle_retrieve", fake_handle_retrieve)

    msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q1",
    )

    response = await main.dispatch(msg, DummyRegistry())

    assert called["op"] == protocol.OP_RETRIEVE
    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE


@pytest.mark.asyncio
async def test_dispatch_rejects_unknown_operation():
    msg = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=0x99,
        flags=0,
        object_id="Q1",
    )

    with pytest.raises(protocol.ProtocolError):
        await main.dispatch(msg, DummyRegistry())
