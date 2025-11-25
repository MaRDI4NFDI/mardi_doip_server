import asyncio

import pytest

from doip_server import handlers, object_registry, protocol


class StubRegistry(object_registry.ObjectRegistry):
    def __init__(self, components):
        """Initialize stub registry with predefined components.

        Args:
            components: Component entries to return for any request.
        """
        super().__init__()
        self._components = components

    async def get_components(self, qid):
        """Return stubbed components for any QID.

        Args:
            qid: Ignored object identifier.

        Returns:
            list[dict]: Predefined component metadata.
        """
        return self._components


@pytest.mark.asyncio
async def test_handle_hello_returns_capabilities():
    """Ensure hello handler returns basic status and operations metadata.

    Returns:
        None
    """
    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_HELLO,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "hello"}],
    )

    response = await handlers.handle_hello(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_HELLO
    meta = response.metadata_blocks[0]
    assert meta["operation"] == "hello"
    assert meta["status"] == "ok"
    assert "availableOperations" in meta


@pytest.mark.asyncio
async def test_handle_retrieve_streams_requested_components(monkeypatch):
    """Ensure retrieve handler streams requested components.

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

    async def fake_get_component_bytes(object_id, component_id):
        """Return stubbed component bytes for retrieve handler tests.

        Args:
            object_id: Requested object identifier.
            component_id: Requested component identifier.

        Returns:
            bytes: Dummy content payload.
        """
        return b"hello"

    async def fake_ensure():
        """Pretend the storage backend is available.

        Returns:
            bool: Always True for tests.
        """
        return True

    monkeypatch.setattr(handlers.storage_s3, "ensure_lakefs_available", fake_ensure)
    monkeypatch.setattr(handlers.storage_s3, "get_component_bytes", fake_get_component_bytes)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[{"components": ["doip:bitstream/Q123/main-pdf"]}],
    )

    response = await handlers.handle_retrieve(request, registry)
    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE
    assert response.metadata_blocks[0]["components"][0]["componentId"] == "doip:bitstream/Q123/main-pdf"
    assert len(response.component_blocks) == 1
    comp = response.component_blocks[0]
    assert comp.component_id == "doip:bitstream/Q123/main-pdf"
    assert comp.content == b"hello"
    assert comp.media_type == "application/pdf"


@pytest.mark.asyncio
async def test_handle_invoke_returns_workflow_results(monkeypatch):
    """Ensure invoke handler returns workflow metadata and derived components.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    registry = StubRegistry([])
    workflow_result = {
        "workflow": "equation_extraction",
        "sourceObject": "Q123",
        "derivedComponents": [
            {
                "componentId": "doip:bitstream/Q123/equations-json",
                "mediaType": "application/json",
                "size": 10,
            }
        ],
        "createdItems": ["Q999"],
    }

    async def fake_workflow(qid, params):
        """Return canned workflow results for invoke handler tests.

        Args:
            qid: Requested object identifier.
            params: Workflow parameters.

        Returns:
            dict: Stubbed workflow result.
        """
        return workflow_result

    monkeypatch.setattr(handlers.workflows, "run_equation_extraction_workflow", fake_workflow)
    async def fake_get_component_bytes(object_id, component_id):
        """Return stubbed workflow-derived component bytes.

        Args:
            object_id: Requested object identifier.
            component_id: Requested component identifier.

        Returns:
            bytes: Dummy workflow content.
        """
        return b"{}"

    monkeypatch.setattr(handlers.storage_s3, "get_component_bytes", fake_get_component_bytes)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_INVOKE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[{"workflow": "equation_extraction", "params": {}}],
    )

    response = await handlers.handle_invoke(request, registry)
    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_INVOKE
    assert response.workflow_blocks[0]["workflow"] == "equation_extraction"
    assert len(response.component_blocks) == 1
    comp = response.component_blocks[0]
    assert comp.component_id == "doip:bitstream/Q123/equations-json"
    assert comp.media_type == "application/json"
    assert comp.content == b"{}"
