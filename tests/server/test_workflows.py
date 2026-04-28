import pytest

from doip_server import mediawiki_client, storage_lakefs, workflows


@pytest.mark.asyncio
async def test_equation_extraction_defaults_to_primary_pdf(monkeypatch):
    calls = {}

    async def fake_get_component_bytes(object_id, component_id):
        calls["get_component_bytes"] = {
            "object_id": object_id,
            "component_id": component_id,
        }
        return b"%PDF"

    async def fake_put_component_bytes(object_id, component_id, data, media_type="application/octet-stream"):
        return "main/00/01/23/Q123/components/doip:bitstream/Q123/equations-json"

    async def fake_create_equation_item(source_qid, latex, metadata=None):
        return "Q999"

    monkeypatch.setattr(storage_lakefs, "get_component_bytes", fake_get_component_bytes)
    monkeypatch.setattr(storage_lakefs, "put_component_bytes", fake_put_component_bytes)
    monkeypatch.setattr(mediawiki_client, "create_equation_item", fake_create_equation_item)

    result = await workflows.run_equation_extraction_workflow("Q123", {})

    assert calls["get_component_bytes"] == {
        "object_id": "Q123",
        "component_id": "primary.pdf",
    }
    assert result["workflow"] == "equation_extraction"


@pytest.mark.asyncio
async def test_equation_extraction_uses_component_id_param(monkeypatch):
    calls = {}

    async def fake_get_component_bytes(object_id, component_id):
        calls["get_component_bytes"] = {
            "object_id": object_id,
            "component_id": component_id,
        }
        return b"%PDF"

    async def fake_put_component_bytes(object_id, component_id, data, media_type="application/octet-stream"):
        return "main/00/01/23/Q123/components/doip:bitstream/Q123/equations-json"

    async def fake_create_equation_item(source_qid, latex, metadata=None):
        return "Q999"

    monkeypatch.setattr(storage_lakefs, "get_component_bytes", fake_get_component_bytes)
    monkeypatch.setattr(storage_lakefs, "put_component_bytes", fake_put_component_bytes)
    monkeypatch.setattr(mediawiki_client, "create_equation_item", fake_create_equation_item)

    await workflows.run_equation_extraction_workflow("Q123", {"componentId": "primary"})

    assert calls["get_component_bytes"] == {
        "object_id": "Q123",
        "component_id": "primary",
    }
