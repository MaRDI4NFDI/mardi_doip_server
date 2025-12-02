import pytest

from unittest.mock import AsyncMock

from doip_server.handlers import _build_rocrate_payload


@pytest.mark.asyncio
async def test_build_rocrate_payload_returns_existing_component():
    pid = "Q12345"
    rocrate_bytes = b"ZIPDATA"

    registry = AsyncMock()
    registry.get_component.return_value = rocrate_bytes
    registry.fetch_fdo_object.return_value = {}

    crate_bytes = await _build_rocrate_payload(pid, registry)
    assert crate_bytes == rocrate_bytes


@pytest.mark.asyncio
async def test_build_rocrate_payload_downloads_when_missing(monkeypatch):
    pid = "Q12345"
    download_bytes = b"file-content"

    registry = AsyncMock()
    registry.get_component.side_effect = KeyError
    registry.fetch_fdo_object.return_value = {
        "profile": {"distribution": [{"contentUrl": "https://example.test/data.csv"}]}
    }

    class _Resp:
        def __init__(self, content: bytes):
            self.content = content

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            return _Resp(download_bytes)

    monkeypatch.setattr("doip_server.handlers.httpx.AsyncClient", _Client)

    crate_bytes = await _build_rocrate_payload(pid, registry)
    assert crate_bytes.startswith(b"PK")  # zip magic
