import asyncio
import contextlib
from functools import partial
import logging

import pytest

from doip_client import StrictDOIPClient
from doip_server import handlers, main, object_registry, protocol, storage_s3

logger = logging.getLogger(__name__)

class StubRegistry(object_registry.ObjectRegistry):
    """Registry stub returning a fixed component manifest."""

    def __init__(self, components):
        """Initialize stub registry with static components.

        Args:
            components: Component metadata entries to return.
        """
        super().__init__()
        self._components = components

    async def get_components(self, qid):
        """Return preconfigured components regardless of QID.

        Args:
            qid: Ignored object identifier.

        Returns:
            list[dict]: Component metadata entries.
        """
        return self._components


@pytest.mark.asyncio
async def test_client_server_integration_hello_and_retrieve(monkeypatch):
    """Spin up the server and call it with the strict client over TCP.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
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
        """Return True to simulate available storage backend.

        Returns:
            bool: Always True for tests.
        """
        return True

    monkeypatch.setattr(storage_s3, "ensure_lakefs_available", fake_ensure)

    async def fake_get_component_bytes(object_id, component_id):
        """Return stubbed component bytes for retrieval tests.

        Args:
            object_id: Requested object identifier.
            component_id: Requested component identifier.

        Returns:
            bytes: Dummy content payload.
        """
        return b"hello-bytes"

    monkeypatch.setattr(storage_s3, "get_component_bytes", fake_get_component_bytes)

    logger.debug("Starting server...")
    server = await asyncio.start_server(
        partial(main.handle_connection, registry), host="127.0.0.1", port=0
    )
    if not server.sockets:
        logger.error("No sockets available for test server")
        pytest.skip("No sockets available for test server")
    port = server.sockets[0].getsockname()[1]
    server_task = asyncio.create_task(server.serve_forever())

    try:
        logger.debug("Starting client...")
        client = StrictDOIPClient(host="127.0.0.1", port=port, use_tls=False, verify_tls=False)

        logger.debug("Invoke 'client.hello()' ...")
        hello = await asyncio.to_thread(client.hello)
        assert hello.get("operation") == "hello"

        logger.debug("Invoke 'client.retrieve()' ...")
        response = await asyncio.to_thread(client.retrieve, "Q123")
        assert response.header.op_code == protocol.OP_RETRIEVE
        assert response.metadata_blocks[0]["operation"] == "retrieve"
        assert len(response.component_blocks) == 1
        assert response.component_blocks[0].content == b"hello-bytes"
    finally:
        logger.debug("Stopping server...")
        server.close()
        await server.wait_closed()
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task

    logger.debug("Done.")
