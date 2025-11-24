import asyncio
import contextlib
from functools import partial

import pytest

from doip_client import StrictDOIPClient
from doip_server import handlers, main, object_registry, protocol, storage_s3


class StubRegistry(object_registry.ObjectRegistry):
    """Registry stub returning a fixed component manifest."""

    def __init__(self, components):
        super().__init__()
        self._components = components

    async def get_components(self, qid):
        return self._components


@pytest.mark.asyncio
async def test_client_server_integration_hello_and_retrieve(monkeypatch, unused_tcp_port):
    """Spin up the server and call it with the strict client over TCP."""
    components = [
        {
            "componentId": "doip:bitstream/Q123/main-pdf",
            "mediaType": "application/pdf",
            "size": 5,
        }
    ]
    registry = StubRegistry(components)

    # Avoid external dependencies during test.
    async def fake_ensure():
        return True

    monkeypatch.setattr(storage_s3, "ensure_lakefs_available", fake_ensure)

    async def fake_get_component_bytes(object_id, component_id):
        return b"hello-bytes"

    monkeypatch.setattr(storage_s3, "get_component_bytes", fake_get_component_bytes)

    server = await asyncio.start_server(
        partial(main.handle_connection, registry), host="127.0.0.1", port=unused_tcp_port
    )
    server_task = asyncio.create_task(server.serve_forever())

    try:
        client = StrictDOIPClient(host="127.0.0.1", port=unused_tcp_port, use_tls=False, verify_tls=False)

        hello = await asyncio.to_thread(client.hello)
        assert hello.get("operation") == "hello"

        response = await asyncio.to_thread(client.retrieve, "Q123")
        assert response.header.op_code == protocol.OP_RETRIEVE
        assert response.metadata_blocks[0]["operation"] == "retrieve"
        assert len(response.component_blocks) == 1
        assert response.component_blocks[0].content == b"hello-bytes"
    finally:
        server.close()
        await server.wait_closed()
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task
