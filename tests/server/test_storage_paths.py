import pytest

from doip_server import storage_lakefs


def test_build_object_key_sharded_with_branch(monkeypatch):
    storage_lakefs.configure({"lakefs": {"branch": "dev"}})
    key = storage_lakefs.build_object_key("Q12345", "primary", ".pdf")
    assert key == "dev/01/23/45/Q12345/components/primary.pdf"


@pytest.mark.asyncio
async def test_get_component_bytes_uses_sharded_path(monkeypatch):
    calls = {}

    class FakeClient:
        def get_object(self, Bucket=None, Key=None):
            calls["bucket"] = Bucket
            calls["key"] = Key

            class Body:
                def read(self_inner):
                    return b"data"

            return {"Body": Body()}

        def get_paginator(self, *_args, **_kwargs):
            raise AssertionError("Paginator should not be called in this test")

    monkeypatch.setattr(storage_lakefs, "_client", lambda: FakeClient())
    storage_lakefs.configure({"lakefs": {"repo": "repo-name", "branch": "main"}})

    data = await storage_lakefs.get_component_bytes("Q4", "fulltext", media_type="application/pdf")

    assert data == b"data"
    assert calls["bucket"] == "repo-name"
    assert calls["key"] == "main/00/00/04/Q4/components/fulltext.pdf"
