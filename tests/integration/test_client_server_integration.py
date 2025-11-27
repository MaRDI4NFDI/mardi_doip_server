import asyncio
import contextlib
from functools import partial
import logging

import pytest

from doip_client import StrictDOIPClient
from doip_server import handlers, main, protocol, storage_lakefs

logger = logging.getLogger(__name__)


class StubRegistry:
    async def fetch_fdo_object(self, pid):
        return {"@id": pid}

    async def fetch_bitstream_bytes(self, pid):
        return b"hello-bytes"


@pytest.mark.asyncio
async def test_client_server_integration_hello_and_retrieve(monkeypatch):
    async def fake_ensure():
        return True

    monkeypatch.setattr(storage_lakefs, "ensure_lakefs_available", fake_ensure)
    monkeypatch.setattr(storage_lakefs, "get_component_bytes", lambda *_, **__: b"hello-bytes")

    registry = StubRegistry()

    server = await asyncio.start_server(
        partial(main.handle_connection, registry), host="127.0.0.1", port=0
    )
    if not server.sockets:
        pytest.skip("no sockets")

    port = server.sockets[0].getsockname()[1]
    server_task = asyncio.create_task(server.serve_forever())

    try:
        client = StrictDOIPClient(host="127.0.0.1", port=port, use_tls=False, verify_tls=False)

        hello = await asyncio.to_thread(client.hello)
        assert hello.get("operation") == "hello"

        resp_meta = await asyncio.to_thread(client.retrieve, "Q123")
        assert resp_meta.header.op_code == protocol.OP_RETRIEVE
        assert resp_meta.metadata_blocks
        assert not resp_meta.component_blocks

    finally:
        server.close()
        await server.wait_closed()
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task
