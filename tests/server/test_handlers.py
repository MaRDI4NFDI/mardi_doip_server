import asyncio
from pathlib import Path

import pytest
import yaml

from doip_server import handlers, object_registry, protocol, storage_lakefs


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

    async def fetch_fdo_object(self, pid):
        """Return a minimal manifest to avoid network access during tests."""
        return {"kernel": {"fdo:hasComponent": self._components}}


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
async def test_retrieve_metadata_for_qid(monkeypatch):
    registry = StubRegistry({})
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[]
    )

    response = await handlers.handle_retrieve(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE
    assert len(response.metadata_blocks) == 1
    assert response.component_blocks == []


@pytest.mark.asyncio
async def test_retrieve_fdo_metadata(monkeypatch):
    async def fake_fetch_fdo(pid):
        return {"foo": "bar"}

    # Registry returns JSON-LD FDO metadata
    registry = StubRegistry({})
    registry.fetch_fdo_object = fake_fetch_fdo

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[]
    )

    response = await handlers.handle_retrieve(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE

    # Metadata present, no binary components
    assert response.component_blocks == []
    assert response.metadata_blocks == [{"foo": "bar"}]


@pytest.mark.asyncio
async def test_retrieve_specific_component(monkeypatch):
    async def fake_ensure(): return True
    async def fake_get_bytes(qid, comp, media_type=None, extension=None): return b"hello"
    async def fake_fetch_fdo(pid):
        # include component in kernel so handler knows it exists
        return {
            "kernel": {
                "fdo:hasComponent": [
                    {"componentId": "primary", "mediaType": "application/pdf"}
                ]
            }
        }

    monkeypatch.setattr(handlers.storage_lakefs, "ensure_lakefs_available", fake_ensure)
    monkeypatch.setattr(handlers.storage_lakefs, "get_component_bytes", fake_get_bytes)

    registry = StubRegistry({})
    registry.fetch_fdo_object = fake_fetch_fdo

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[{"element": "primary"}],
    )

    response = await handlers.handle_retrieve(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE
    assert response.metadata_blocks == []

    assert len(response.component_blocks) == 1
    comp = response.component_blocks[0]
    assert comp.component_id == "primary"
    assert comp.content == b"hello"
    assert comp.media_type == "application/pdf"


@pytest.mark.asyncio
async def test_retrieve_component_defaults_when_manifest_missing(monkeypatch):
    """Component retrieval falls back to octet-stream when media type unknown."""

    async def fake_ensure():
        return True

    async def fake_get_bytes(qid, comp, media_type=None, extension=None):
        return b"content"

    async def fake_fetch_fdo(pid):
        # Manifest lists component without media type
        return {
            "kernel": {
                "fdo:hasComponent": [
                    {"componentId": "primary"}
                ]
            }
        }

    monkeypatch.setattr(handlers.storage_lakefs, "ensure_lakefs_available", fake_ensure)
    monkeypatch.setattr(handlers.storage_lakefs, "get_component_bytes", fake_get_bytes)

    registry = StubRegistry({})
    registry.fetch_fdo_object = fake_fetch_fdo

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[{"element": "primary"}],
    )

    response = await handlers.handle_retrieve(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE
    assert response.metadata_blocks == []

    assert len(response.component_blocks) == 1
    comp = response.component_blocks[0]
    assert comp.component_id == "primary"
    assert comp.media_type == "application/octet-stream"
    assert comp.content == b"content"


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
    async def fake_get_component_bytes(object_id, component_id="primary", media_type=None, extension=None):
        """Return stubbed workflow-derived component bytes.

        Args:
            object_id: Requested object identifier.
            component_id: Component identifier being fetched.
            media_type: Media type (unused).
            extension: Extension (unused).

        Returns:
            bytes: Dummy workflow content.
        """
        return b"{}"

    monkeypatch.setattr(handlers.storage_lakefs, "get_component_bytes", fake_get_component_bytes)

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


@pytest.mark.asyncio
async def test_handle_retrieve_uses_registry_and_storage(monkeypatch):
    """Retrieve on base PID returns metadata only; no storage access."""

    class StubRegistry:
        def __init__(self):
            self.fdo_call_count = 0

        async def fetch_fdo_object(self, pid):
            self.fdo_call_count += 1
            return {"@id": f"https://fdo.portal/fdo/{pid}"}

    registry = StubRegistry()

    # verify storage backend is NOT called for metadata PIDs
    async def fake_get_bytes(qid, comp, media_type=None, extension=None):
        assert False, "Should not fetch bitstream bytes for non-bitstream PID"

    async def fake_ensure():
        return True

    monkeypatch.setattr(handlers.storage_lakefs, "ensure_lakefs_available", fake_ensure)
    monkeypatch.setattr(handlers.storage_lakefs, "get_component_bytes", fake_get_bytes)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[],
    )

    response = await handlers.handle_retrieve(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE
    assert len(response.metadata_blocks) == 1
    assert response.component_blocks == []
    assert registry.fdo_call_count == 1



def _load_config_or_skip() -> dict:
    """Load config.yaml from repo root or skip if unavailable/invalid."""
    cfg_path = Path(__file__).resolve().parents[2] / "config.yaml"
    if not cfg_path.exists():
        pytest.skip("config.yaml not present; skipping lakeFS integration test")
    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not isinstance(cfg, dict):
        pytest.skip("config.yaml does not contain a mapping")
    return cfg

