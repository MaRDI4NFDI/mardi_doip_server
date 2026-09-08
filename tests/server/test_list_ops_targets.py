"""Tests for target-aware ListOperations.

DOIP v2.0 defines ListOperations as the operations invocable on the *target DO*,
with the target's type informing which those are (Appendix D). These tests cover
the three target kinds and, most importantly, the intersection that stops a
deployment advertising an operation it does not implement.
"""

import pytest

from doip_server import handlers, protocol
from doip_shared import operations as ops

FDO_API = "https://fdo.portal.mardi4nfdi.de/fdo/"


class StubRegistry:
    """Registry returning canned type and object FDOs, with no network."""

    def __init__(self, type_ops=None, object_type_uri=None):
        self.fdo_api = FDO_API
        self._type_ops = type_ops if type_ops is not None else []
        self._object_type_uri = object_type_uri
        self.fetched_types = []
        self.fetched_objects = []

    async def fetch_type_fdo(self, type_id):
        self.fetched_types.append(type_id)
        return {"@id": f"{FDO_API}types/{type_id}", "applicableOperations": self._type_ops}

    async def fetch_fdo_object(self, pid):
        self.fetched_objects.append(pid)
        return {"kernel": {"digitalObjectType": self._object_type_uri}}


def _msg(object_id):
    return protocol.DOIPMessage(
        version=protocol.DOIP_VERSION,
        msg_type=protocol.MSG_TYPE_REQUEST,
        operation=protocol.OP_LIST_OPS,
        flags=0,
        object_id=object_id,
        metadata_blocks=[{"operation": "list_operations"}],
    )


async def _block(object_id, registry):
    resp = await handlers.handle_list_ops(_msg(object_id), registry)
    return resp.metadata_blocks[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["", "service", "SERVICE"])
async def test_no_target_answers_for_the_service(target):
    reg = StubRegistry()
    b = await _block(target, reg)
    assert b["target"] == "service"
    assert set(b["availableOperations"]) == {op.name for op in ops.OPERATIONS}
    assert reg.fetched_types == [] and reg.fetched_objects == []


@pytest.mark.asyncio
async def test_type_target_returns_the_types_operations():
    reg = StubRegistry(type_ops=["0.DOIP/Op.Retrieve", "0.MaRDI/Op.Describe"])
    b = await _block("types/Workflow", reg)
    assert b["target"] == "type"
    assert b["digitalObjectType"] == "Workflow"
    assert [d["name"] for d in b["operations"]] == ["retrieve", "describe"]
    assert reg.fetched_types == ["Workflow"]


@pytest.mark.asyncio
async def test_full_type_uri_is_accepted():
    reg = StubRegistry(type_ops=["0.DOIP/Op.Retrieve"])
    b = await _block(f"{FDO_API}types/Dataset", reg)
    assert b["digitalObjectType"] == "Dataset"


@pytest.mark.asyncio
async def test_object_target_resolves_its_type():
    reg = StubRegistry(
        type_ops=["0.DOIP/Op.Retrieve", "0.MaRDI/Op.Purge"],
        object_type_uri=f"{FDO_API}types/Workflow",
    )
    b = await _block("Q6830877", reg)
    assert b["target"] == "object"
    assert b["digitalObjectType"] == "Workflow"
    assert reg.fetched_objects == ["Q6830877"]
    assert reg.fetched_types == ["Workflow"]
    assert [d["name"] for d in b["operations"]] == ["retrieve", "purge"]


@pytest.mark.asyncio
async def test_declared_but_unimplemented_operations_are_not_advertised():
    """The intersection: a type may declare more than this server implements."""
    reg = StubRegistry(
        type_ops=[
            "0.DOIP/Op.Retrieve",
            "0.MaRDI/Op.GetExecutionPlan",   # proposed, not implemented here
            "0.MaRDI/Op.Validate",           # proposed, not implemented here
        ]
    )
    b = await _block("types/Workflow", reg)
    names = [d["name"] for d in b["operations"]]
    assert names == ["retrieve"]
    ids = {d["id"] for d in b["operations"]}
    assert "0.MaRDI/Op.GetExecutionPlan" not in ids
    assert ids <= {op.doip_id for op in ops.OPERATIONS}


@pytest.mark.asyncio
async def test_type_declaring_nothing_yields_no_operations():
    reg = StubRegistry(type_ops=[])
    b = await _block("types/Formula", reg)
    assert b["operations"] == []
    assert b["availableOperations"] == {}


@pytest.mark.asyncio
async def test_object_without_resolvable_type_is_an_error():
    reg = StubRegistry(object_type_uri="https://example.org/not-a-mardi-type")
    with pytest.raises(protocol.ProtocolError):
        await _block("Q999", reg)


@pytest.mark.asyncio
async def test_service_answer_still_carries_every_implemented_operation():
    """Service-level listing is unaffected by type declarations."""
    b = await _block("", StubRegistry())
    assert {d["id"] for d in b["operations"]} == {op.doip_id for op in ops.OPERATIONS}
