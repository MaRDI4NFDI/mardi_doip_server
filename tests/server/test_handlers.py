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
    registry = StubRegistry([])
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
    registry = StubRegistry([])
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
    async def fake_get_bytes(qid, comp): return b"hello"
    async def fake_fetch_fdo(pid):
        # include component in kernel so handler knows it exists
        return {
            "kernel": {
                "fdo:hasComponent": [
                    {"componentId": "primary.pdf", "mediaType": "application/pdf"}
                ]
            }
        }

    monkeypatch.setattr(handlers.storage_lakefs, "ensure_lakefs_available", fake_ensure)
    monkeypatch.setattr(handlers.storage_lakefs, "get_component_bytes", fake_get_bytes)

    registry = StubRegistry([])
    registry.fetch_fdo_object = fake_fetch_fdo

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_RETRIEVE,
        flags=0,
        object_id="Q123",
        metadata_blocks=[{"element": "primary.pdf"}],
    )

    response = await handlers.handle_retrieve(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_RETRIEVE
    assert response.metadata_blocks == []

    assert len(response.component_blocks) == 1
    comp = response.component_blocks[0]
    assert comp.component_id == "primary.pdf"
    assert comp.content == b"hello"
    assert comp.media_type == "application/pdf"


@pytest.mark.asyncio
async def test_retrieve_component_defaults_when_manifest_missing(monkeypatch):
    """Component retrieval falls back to octet-stream when media type unknown."""

    async def fake_ensure():
        return True

    async def fake_get_bytes(qid, comp):
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

    registry = StubRegistry([])
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
async def test_handle_update_stores_component_and_commits(monkeypatch):
    """Ensure authenticated updates write one component and commit it.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    calls = {}

    async def fake_fetch_fdo(pid):
        return {"@id": pid}

    async def fake_put_component_bytes(object_id, component_id, data, media_type="application/octet-stream"):
        calls["put"] = {
            "object_id": object_id,
            "component_id": component_id,
            "data": data,
            "media_type": media_type,
        }
        return "main/00/00/01/Q1/components/primary.pdf"

    async def fake_commit_changes(message, metadata=None, branch=None, allow_empty=True):
        calls["commit"] = {
            "message": message,
            "metadata": metadata,
            "branch": branch,
            "allow_empty": allow_empty,
        }
        return {"branch": "main", "commit_id": "abc123", "repo": "repo"}

    async def fake_reset_uncommitted_object(object_path, branch=None):
        calls["reset"] = {"object_path": object_path, "branch": branch}

    registry = StubRegistry([])
    registry.fetch_fdo_object = fake_fetch_fdo

    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)
    monkeypatch.setattr(handlers.storage_lakefs, "put_component_bytes", fake_put_component_bytes)
    monkeypatch.setattr(handlers.storage_lakefs, "commit_changes", fake_commit_changes)
    monkeypatch.setattr(handlers.storage_lakefs, "reset_uncommitted_object", fake_reset_uncommitted_object)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "element": "primary.pdf", "username": "testuser", "password": "testpass"}],
        component_blocks=[
            protocol.ComponentBlock(
                component_id="primary.pdf",
                content=b"pdf-data",
                media_type="application/pdf",
            )
        ],
    )

    response = await handlers.handle_update(request, registry)

    assert calls["put"]["object_id"] == "Q1"
    assert calls["put"]["component_id"] == "primary.pdf"
    assert calls["put"]["data"] == b"pdf-data"
    assert "commit" in calls
    assert "reset" not in calls
    assert response.operation == protocol.OP_UPDATE
    assert response.metadata_blocks[0]["status"] == "committed"
    assert response.metadata_blocks[0]["commitId"] == "abc123"


@pytest.mark.asyncio
async def test_handle_update_rejects_multiple_components(monkeypatch):
    """Ensure update rejects requests carrying more than one component block.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)

    async def fake_fetch_fdo(pid):
        return {"@id": pid}

    registry = StubRegistry([])
    registry.fetch_fdo_object = fake_fetch_fdo
    metadata = [{"operation": "update", "element": "primary", "username": "testuser", "password": "testpass"}]
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=metadata,
        component_blocks=[
            protocol.ComponentBlock(component_id="primary", content=b"one"),
            protocol.ComponentBlock(component_id="secondary", content=b"two"),
        ],
    )

    with pytest.raises(protocol.ProtocolError):
        await handlers.handle_update(request, registry)


@pytest.mark.asyncio
async def test_handle_update_rejects_mismatched_component_id(monkeypatch):
    """Ensure update rejects mismatched metadata and component identifiers.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    async def fake_fetch_fdo(pid):
        return {"@id": pid}

    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)

    registry = StubRegistry([])
    registry.fetch_fdo_object = fake_fetch_fdo

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "element": "primary", "username": "testuser", "password": "testpass"}],
        component_blocks=[protocol.ComponentBlock(component_id="secondary", content=b"data")],
    )

    with pytest.raises(protocol.ProtocolError):
        await handlers.handle_update(request, registry)


@pytest.mark.asyncio
async def test_handle_update_resets_uncommitted_object_on_commit_failure(monkeypatch):
    """Ensure update resets staged lakeFS changes when commit creation fails.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    calls = {}

    async def fake_fetch_fdo(pid):
        return {"@id": pid}

    async def fake_put_component_bytes(object_id, component_id, data, media_type="application/octet-stream"):
        calls["put"] = True
        return "main/00/00/01/Q1/components/primary"

    async def fake_commit_changes(message, metadata=None, branch=None, allow_empty=True):
        raise RuntimeError("commit failed")

    async def fake_reset_uncommitted_object(object_path, branch=None):
        calls["reset"] = {"object_path": object_path, "branch": branch}

    registry = StubRegistry([])
    registry.fetch_fdo_object = fake_fetch_fdo

    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)
    monkeypatch.setattr(handlers.storage_lakefs, "put_component_bytes", fake_put_component_bytes)
    monkeypatch.setattr(handlers.storage_lakefs, "commit_changes", fake_commit_changes)
    monkeypatch.setattr(handlers.storage_lakefs, "reset_uncommitted_object", fake_reset_uncommitted_object)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "element": "primary", "username": "testuser", "password": "testpass"}],
        component_blocks=[protocol.ComponentBlock(component_id="primary", content=b"data")],
    )

    with pytest.raises(RuntimeError):
        await handlers.handle_update(request, registry)

    assert calls["put"] is True
    assert calls["reset"]["object_path"] == "00/00/01/Q1/components/primary"


@pytest.mark.asyncio
async def test_handle_update_rejects_missing_credentials_before_fetch(monkeypatch):
    """Ensure update credential extraction happens before object lookup and storage writes.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    registry = StubRegistry([])

    async def fake_fetch_fdo(pid):
        raise AssertionError("fetch_fdo_object should not be called without credentials")

    async def fake_put_component_bytes(*args, **kwargs):
        raise AssertionError("put_component_bytes should not be called without credentials")

    async def fake_commit_changes(*args, **kwargs):
        raise AssertionError("commit_changes should not be called without credentials")

    registry.fetch_fdo_object = fake_fetch_fdo
    monkeypatch.setattr(handlers.storage_lakefs, "put_component_bytes", fake_put_component_bytes)
    monkeypatch.setattr(handlers.storage_lakefs, "commit_changes", fake_commit_changes)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "element": "primary"}],
        component_blocks=[protocol.ComponentBlock(component_id="primary", content=b"data")],
    )

    with pytest.raises(protocol.ProtocolError, match="'username' is required"):
        await handlers.handle_update(request, registry)


@pytest.mark.asyncio
async def test_handle_update_rejects_invalid_credentials_before_storage(monkeypatch):
    """Ensure update rejects invalid wiki credentials before any side effects.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    async def _mock_validate_fail(username, password):
        raise protocol.ProtocolError("Invalid wiki credentials")

    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_fail)

    registry = StubRegistry([])

    async def fake_fetch_fdo(pid):
        raise AssertionError("fetch_fdo_object should not be called with invalid credentials")

    async def fake_put_component_bytes(*args, **kwargs):
        raise AssertionError("put_component_bytes should not be called with invalid credentials")

    async def fake_commit_changes(*args, **kwargs):
        raise AssertionError("commit_changes should not be called with invalid credentials")

    registry.fetch_fdo_object = fake_fetch_fdo
    monkeypatch.setattr(handlers.storage_lakefs, "put_component_bytes", fake_put_component_bytes)
    monkeypatch.setattr(handlers.storage_lakefs, "commit_changes", fake_commit_changes)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "element": "primary", "username": "testuser", "password": "testpass"}],
        component_blocks=[protocol.ComponentBlock(component_id="primary", content=b"data")],
    )

    with pytest.raises(protocol.ProtocolError, match="Invalid wiki credentials"):
        await handlers.handle_update(request, registry)


@pytest.mark.asyncio
async def test_handle_update_rejects_when_mediawiki_api_unreachable(monkeypatch):
    """Ensure update rejects requests when the MediaWiki API cannot be reached.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None
    """
    async def _mock_validate_unreachable(username, password):
        raise protocol.ProtocolError("Could not reach MediaWiki API for credential validation: connection refused")

    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_unreachable)

    registry = StubRegistry([])

    async def fake_fetch_fdo(pid):
        raise AssertionError("fetch_fdo_object should not run when API is unreachable")

    registry.fetch_fdo_object = fake_fetch_fdo

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "element": "primary", "username": "testuser", "password": "testpass"}],
        component_blocks=[protocol.ComponentBlock(component_id="primary", content=b"data")],
    )

    with pytest.raises(protocol.ProtocolError, match="Could not reach MediaWiki API"):
        await handlers.handle_update(request, registry)


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
    async def fake_get_component_bytes(object_id, component_id="primary"):
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
    async def fake_get_bytes(qid, comp):
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



class _FakeHttpClient:
    """Stub httpx.AsyncClient that simulates a healthy importer returning Q999."""

    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass

    async def get(self, url, **kw):
        class _R:
            status_code = 200
            def raise_for_status(self): pass
        return _R()

    async def post(self, url, **kw):
        class _R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"qid": "Q999", "status": "success"}
        return _R()


@pytest.mark.asyncio
async def test_handle_create_success(monkeypatch):
    """Successful create returns 'created' status and the new QID."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)
    monkeypatch.setattr(handlers.httpx, "AsyncClient", lambda **kw: _FakeHttpClient())

    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "create", "username": "testuser", "password": "testpass", "json": '{"label": "Test item"}'}],
    )

    response = await handlers.handle_create(request, registry)

    assert response.msg_type == protocol.MSG_TYPE_RESPONSE
    assert response.operation == protocol.OP_CREATE
    meta = response.metadata_blocks[0]
    assert meta["status"] == "created"
    assert meta["qid"] == "Q999"


@pytest.mark.asyncio
async def test_handle_create_missing_username(monkeypatch):
    """Create request without a username raises ProtocolError."""
    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "create", "json": '{"label": "Test item"}'}],
    )

    with pytest.raises(protocol.ProtocolError, match="'username' is required"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_create_missing_password(monkeypatch):
    """Create request with username but no password raises ProtocolError."""
    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "create", "username": "testuser", "json": '{"label": "Test item"}'}],
    )

    with pytest.raises(protocol.ProtocolError, match="'password' is required"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_create_missing_json_field(monkeypatch):
    """Create request without a 'json' field raises ProtocolError."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)
    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "create", "username": "testuser", "password": "testpass"}],
    )

    with pytest.raises(protocol.ProtocolError, match="'json' field"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_create_invalid_property_id(monkeypatch):
    """Create request with a malformed property ID raises ProtocolError."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)
    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{
            "operation": "create",
            "username": "testuser",
            "password": "testpass",
            "json": '{"label": "Test", "claims": {"wdt:P31": "Q5"}}',
        }],
    )

    with pytest.raises(protocol.ProtocolError, match="invalid property ID"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_create_list_claim_values_accepted(monkeypatch):
    """Create request with a list of QIDs for a property is accepted."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)
    monkeypatch.setattr(handlers.httpx, "AsyncClient", lambda **kw: _FakeHttpClient())

    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{
            "operation": "create",
            "username": "testuser",
            "password": "testpass",
            "json": '{"label": "Test", "claims": {"P31": ["Q68657", "Q6830884"]}}',
        }],
    )

    response = await handlers.handle_create(request, registry)
    assert response.metadata_blocks[0]["status"] == "created"


@pytest.mark.asyncio
async def test_handle_create_list_claim_with_invalid_element_rejected(monkeypatch):
    """Create request with a list containing a non-scalar value raises ProtocolError."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)

    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{
            "operation": "create",
            "username": "testuser",
            "password": "testpass",
            "json": '{"label": "Test", "claims": {"P31": ["Q68657", {"nested": "bad"}]}}',
        }],
    )

    with pytest.raises(protocol.ProtocolError, match="in list for"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_create_qualifier_object_accepted(monkeypatch):
    """Claim value as {value, qualifiers} object is accepted and forwarded to the importer."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)
    monkeypatch.setattr(handlers.httpx, "AsyncClient", lambda **kw: _FakeHttpClient())

    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{
            "operation": "create",
            "username": "testuser",
            "password": "testpass",
            "json": '{"label": "Test formula", "claims": {"P983": {"value": "y_n", "qualifiers": {"P984": "Q12345"}}}}',
        }],
    )

    response = await handlers.handle_create(request, registry)
    assert response.metadata_blocks[0]["status"] == "created"


@pytest.mark.asyncio
async def test_handle_create_qualifier_object_missing_value_rejected(monkeypatch):
    """Qualifier object without a 'value' field raises ProtocolError."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)

    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{
            "operation": "create",
            "username": "testuser",
            "password": "testpass",
            "json": '{"label": "Test", "claims": {"P983": {"qualifiers": {"P984": "Q123"}}}}',
        }],
    )

    with pytest.raises(protocol.ProtocolError, match="'value' field must be a string or number"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_create_qualifier_invalid_pid_rejected(monkeypatch):
    """Qualifier with a malformed property ID raises ProtocolError."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)

    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{
            "operation": "create",
            "username": "testuser",
            "password": "testpass",
            "json": '{"label": "Test", "claims": {"P983": {"value": "y_n", "qualifiers": {"BADPID": "Q123"}}}}',
        }],
    )

    with pytest.raises(protocol.ProtocolError, match="invalid qualifier property ID"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_create_unreachable_importer(monkeypatch):
    """Create request raises ProtocolError when importer health check fails."""
    async def _mock_validate_ok(username, password): pass
    monkeypatch.setattr(handlers, "_validate_wiki_credentials", _mock_validate_ok)

    class _FailClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url, **kw): raise Exception("connection refused")

    monkeypatch.setattr(handlers.httpx, "AsyncClient", lambda **kw: _FailClient())

    registry = StubRegistry([])
    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_CREATE,
        flags=0,
        object_id="",
        metadata_blocks=[{"operation": "create", "username": "testuser", "password": "testpass", "json": '{"label": "Test item"}'}],
    )

    with pytest.raises(protocol.ProtocolError, match="not reachable"):
        await handlers.handle_create(request, registry)


@pytest.mark.asyncio
async def test_handle_property_update_success(monkeypatch):
    """Property update routes to importer and returns updated status."""
    import httpx

    purged = []

    class StubRegistryPurge(StubRegistry):
        async def purge(self, object_id):
            purged.append(object_id)

    registry = StubRegistryPurge([])
    monkeypatch.setenv("IMPORTER_API_URL", "http://importer")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(200, json={"qid": "Q1", "status": "updated"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "properties": {"label": "New"}, "username": "testuser", "password": "testpass"}],
        component_blocks=[],
    )

    response = await handlers.handle_update(request, registry)

    assert response.metadata_blocks[0]["status"] == "updated"
    assert purged == ["Q1"]


@pytest.mark.asyncio
async def test_handle_property_update_conflict(monkeypatch):
    """Property update raises ProtocolError on 409 conflict from importer."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("IMPORTER_API_URL", "http://importer")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            409,
            json={"status": "conflict", "error": "P16 already has values", "existing_values": ["Q50"]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "properties": {"claims": {"P16": "Q99"}}, "username": "testuser", "password": "testpass"}],
        component_blocks=[],
    )

    with pytest.raises(protocol.ProtocolError, match="conflict"):
        await handlers.handle_update(request, registry)


@pytest.mark.asyncio
async def test_handle_property_update_qid_in_properties_ignored(monkeypatch):
    """A 'qid' key inside properties must not override the object_id."""
    import httpx

    sent_bodies = []

    async def fake_post(self, url, **kwargs):
        sent_bodies.append(kwargs.get("json", {}))
        return httpx.Response(200, json={"qid": "Q1", "status": "updated"})

    registry = StubRegistry([])
    monkeypatch.setenv("IMPORTER_API_URL", "http://importer")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[
            {"operation": "update", "properties": {"qid": "Q999", "label": "x"}, "username": "testuser", "password": "testpass"}
        ],
        component_blocks=[],
    )

    await handlers.handle_update(request, registry)
    assert sent_bodies[0]["qid"] == "Q1"


@pytest.mark.asyncio
async def test_handle_property_update_409_non_json_body(monkeypatch):
    """ProtocolError is raised even when the 409 body is not valid JSON."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("IMPORTER_API_URL", "http://importer")

    async def fake_post(self, url, **kwargs):
        return httpx.Response(409, content=b"upstream proxy error")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    request = protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_UPDATE,
        flags=0,
        object_id="Q1",
        metadata_blocks=[{"operation": "update", "properties": {"label": "x"}, "username": "testuser", "password": "testpass"}],
        component_blocks=[],
    )

    with pytest.raises(protocol.ProtocolError, match="conflict"):
        await handlers.handle_update(request, registry)


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


# ── handle_search tests ────────────────────────────────────────────────────────

def _search_request(meta: dict) -> protocol.DOIPMessage:
    return protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_SEARCH,
        flags=0,
        object_id="",
        metadata_blocks=[meta],
    )


def _mediawiki_response(total_hits: int, results: list) -> dict:
    return {"query": {"searchinfo": {"totalhits": total_hits}, "search": results}}


def _mock_search_response(status_code: int, body: dict):
    import httpx
    req = httpx.Request("GET", "http://wiki/w/api.php")
    return httpx.Response(status_code, json=body, request=req)


@pytest.mark.asyncio
async def test_handle_search_success(monkeypatch):
    """Search returns parsed results with extracted QIDs; srnamespace=120 when no type."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("MEDIAWIKI_API_URL", "http://wiki/w/api.php")
    captured_params = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured_params.update(params or {})
        return _mock_search_response(200, _mediawiki_response(1, [
            {"ns": 120, "title": "Item:Q6242573", "snippet": "scientific article", "timestamp": "2026-01-01T00:00:00Z"},
        ]))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    response = await handlers.handle_search(_search_request({"query": "10.1103/PHYSREVA.88.052328"}), registry)

    assert response.operation == protocol.OP_SEARCH
    meta = response.metadata_blocks[0]
    assert meta["status"] == "ok"
    assert meta["total_hits"] == 1
    assert meta["results"][0]["qid"] == "Q6242573"
    assert "namespace" not in meta["results"][0]
    assert captured_params["srnamespace"] == "120"


@pytest.mark.asyncio
async def test_handle_search_with_type(monkeypatch):
    """Type filter prepends haswbfacet:P1460=Q… and omits srnamespace."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("MEDIAWIKI_API_URL", "http://wiki/w/api.php")
    captured_params = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured_params.update(params or {})
        return _mock_search_response(200, _mediawiki_response(1, [
            {"ns": 120, "title": "Item:Q6534216", "snippet": "a workflow", "timestamp": "2026-01-01T00:00:00Z"},
        ]))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    response = await handlers.handle_search(
        _search_request({"query": "navier stokes", "type": "workflow"}), registry
    )

    meta = response.metadata_blocks[0]
    assert meta["status"] == "ok"
    assert meta["type"] == "workflow"
    assert "haswbfacet:P1460=Q6534216" in captured_params["srsearch"]
    assert "navier stokes" in captured_params["srsearch"]
    assert "srnamespace" not in captured_params


@pytest.mark.asyncio
async def test_handle_search_type_only(monkeypatch):
    """Type without query uses haswbfacet as the full search string."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("MEDIAWIKI_API_URL", "http://wiki/w/api.php")
    captured_params = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured_params.update(params or {})
        return _mock_search_response(200, _mediawiki_response(0, []))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    await handlers.handle_search(_search_request({"type": "dataset"}), registry)

    assert captured_params["srsearch"] == "haswbfacet:P1460=Q5984635"
    assert "srnamespace" not in captured_params


@pytest.mark.asyncio
async def test_handle_search_type_raw_qid(monkeypatch):
    """Raw QID is accepted as type value."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("MEDIAWIKI_API_URL", "http://wiki/w/api.php")
    captured_params = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured_params.update(params or {})
        return _mock_search_response(200, _mediawiki_response(0, []))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    await handlers.handle_search(_search_request({"type": "Q6534216"}), registry)

    assert captured_params["srsearch"] == "haswbfacet:P1460=Q6534216"


@pytest.mark.asyncio
async def test_handle_search_no_query_no_type(monkeypatch):
    """Neither query nor type raises ProtocolError."""
    registry = StubRegistry([])
    with pytest.raises(protocol.ProtocolError, match="query.*type|type.*query"):
        await handlers.handle_search(_search_request({}), registry)


@pytest.mark.asyncio
async def test_handle_search_unknown_type(monkeypatch):
    """Unknown type name raises ProtocolError."""
    registry = StubRegistry([])
    with pytest.raises(protocol.ProtocolError, match="Unknown type"):
        await handlers.handle_search(_search_request({"type": "unicorn"}), registry)


@pytest.mark.asyncio
async def test_handle_search_api_unreachable(monkeypatch):
    """MediaWiki API failure raises ProtocolError."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("MEDIAWIKI_API_URL", "http://wiki/w/api.php")

    async def fake_get(self, url, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(protocol.ProtocolError, match="unreachable"):
        await handlers.handle_search(_search_request({"query": "test"}), registry)


@pytest.mark.asyncio
async def test_handle_search_software_type_queries_both_facets(monkeypatch):
    """'software' type issues two MW queries (P1460=Q5976450 and P31=Q57080) and merges results."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("MEDIAWIKI_API_URL", "http://wiki/w/api.php")
    captured_queries: list[str] = []

    async def fake_get(self, url, params=None, **kwargs):
        sr = params.get("srsearch", "")
        captured_queries.append(sr)
        if "P1460" in sr:
            body = _mediawiki_response(1, [
                {"ns": 120, "title": "Item:Q27041", "snippet": "Lean theorem prover", "timestamp": "2026-01-01T00:00:00Z"},
            ])
        else:
            body = _mediawiki_response(1, [
                {"ns": 120, "title": "Item:Q63925", "snippet": "CRAN R package", "timestamp": "2026-01-01T00:00:00Z"},
            ])
        return _mock_search_response(200, body)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    response = await handlers.handle_search(_search_request({"type": "software"}), registry)

    assert any("haswbfacet:P1460=Q5976450" in q for q in captured_queries)
    assert any("haswbfacet:P31=Q57080" in q for q in captured_queries)
    assert any("haswbfacet:P31=Q56605" in q for q in captured_queries)
    assert all("srnamespace" not in q for q in captured_queries)

    meta = response.metadata_blocks[0]
    assert meta["status"] == "ok"
    returned_qids = {r["qid"] for r in meta["results"]}
    assert returned_qids == {"Q27041", "Q63925"}


@pytest.mark.asyncio
async def test_handle_search_software_type_deduplicates(monkeypatch):
    """Items appearing in both facet queries are only returned once."""
    import httpx

    registry = StubRegistry([])
    monkeypatch.setenv("MEDIAWIKI_API_URL", "http://wiki/w/api.php")

    async def fake_get(self, url, params=None, **kwargs):
        body = _mediawiki_response(1, [
            {"ns": 120, "title": "Item:Q99999", "snippet": "same item", "timestamp": "2026-01-01T00:00:00Z"},
        ])
        return _mock_search_response(200, body)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    response = await handlers.handle_search(_search_request({"type": "software"}), registry)

    meta = response.metadata_blocks[0]
    assert meta["total_hits"] == 1
    assert len(meta["results"]) == 1
