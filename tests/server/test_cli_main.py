"""Tests for client_cli.main — focusing on @file JSON loading."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from client_cli import main as cli_main


class _FakeResponse:
    metadata_blocks = [{"operation": "create", "status": "created", "qid": "Q99"}]


class _FakeClient:
    def __init__(self, **_):
        self.last_json = None
        self.last_props = None

    def create(self, json_str, username=None, password=None):
        self.last_json = json_str
        return _FakeResponse()

    def update_properties(self, object_id, props, username=None, password=None):
        self.last_props = props
        return _FakeResponse()


def _patch_client(monkeypatch, fake_client):
    monkeypatch.setattr(cli_main, "StrictDOIPClient", lambda **kw: fake_client)
    monkeypatch.setattr(cli_main, "print_mardi_logo", lambda: None)


def test_create_json_at_file(monkeypatch, tmp_path):
    """--json @path reads JSON from file instead of parsing inline string."""
    payload = {"label": "Euler formula", "claims": {"P989": "E = mc^2"}}
    json_file = tmp_path / "item.json"
    json_file.write_text(json.dumps(payload), encoding="utf-8")

    fake = _FakeClient()
    _patch_client(monkeypatch, fake)

    rc = cli_main.main([
        "--no-banner", "--action", "create",
        "--json", f"@{json_file}",
        "--username", "DoipBot", "--password", "secret",
    ])

    assert rc == 0
    assert json.loads(fake.last_json) == payload


def test_create_json_at_file_missing(monkeypatch, tmp_path):
    """--json @nonexistent returns exit code 1."""
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)

    rc = cli_main.main([
        "--no-banner", "--action", "create",
        "--json", "@/nonexistent/path/item.json",
        "--username", "DoipBot", "--password", "secret",
    ])

    assert rc == 1


def test_update_properties_at_file(monkeypatch, tmp_path):
    """--properties @path reads JSON from file."""
    props = {"claims": {"P983": {"value": "y_n", "qualifiers": {"P984": "Q12345"}}}}
    props_file = tmp_path / "props.json"
    props_file.write_text(json.dumps(props), encoding="utf-8")

    fake = _FakeClient()
    _patch_client(monkeypatch, fake)

    rc = cli_main.main([
        "--no-banner", "--action", "update",
        "--object-id", "Q42",
        "--properties", f"@{props_file}",
        "--username", "DoipBot", "--password", "secret",
    ])

    assert rc == 0
    assert fake.last_props == props
