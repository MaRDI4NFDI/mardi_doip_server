import struct

from doip_client.client import StrictDOIPClient
from doip_client.messages import ComponentBlock, DoipResponse
from doip_shared.constants import OP_UPDATE


def test_encode_component_body():
    """Ensure component body encoding preserves lengths and content.

    Returns:
        None
    """
    comp = ComponentBlock(component_id="cid", content=b"data", media_type="text/plain")
    body = StrictDOIPClient._encode_component_body(comp)

    comp_id_len = struct.unpack_from(">H", body, 0)[0]
    assert comp_id_len == len("cid")
    assert body[2 : 2 + comp_id_len].decode() == "cid"

    media_offset = 2 + comp_id_len
    media_len = struct.unpack_from(">H", body, media_offset)[0]
    assert media_len == len("text/plain")
    assert body[media_offset + 2 : media_offset + 2 + media_len].decode() == "text/plain"

    content_offset = media_offset + 2 + media_len
    content_len = struct.unpack_from(">I", body, content_offset)[0]
    assert content_len == 4
    assert body[content_offset + 4 : content_offset + 4 + content_len] == b"data"


def test_update_component_builds_update_request(monkeypatch):
    captured = {}

    def fake_send_message(self, request):
        captured["request"] = request
        return DoipResponse(header=request.header, metadata_blocks=[], component_blocks=[], workflow_blocks=[])

    monkeypatch.setattr(StrictDOIPClient, "send_message", fake_send_message)

    client = StrictDOIPClient(host="127.0.0.1", port=3567, use_tls=False)
    client.update_component("Q123", "primary", b"hello", media_type="application/pdf")

    request = captured["request"]
    assert request.header.op_code == OP_UPDATE
    assert request.object_id == "Q123"
    assert request.metadata_blocks == [{"operation": "update", "element": "primary"}]
    assert len(request.component_blocks) == 1
    assert request.component_blocks[0].component_id == "primary"
    assert request.component_blocks[0].media_type == "application/pdf"
