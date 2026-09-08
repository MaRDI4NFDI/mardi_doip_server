"""Tests for the shared operation registry.

These lock in the invariant the registry exists to protect: every operation the
server advertises is dispatchable, reachable from the CLI, and reported
consistently by both discovery responses.
"""

import pytest

from doip_shared import operations as ops


def test_names_and_codes_are_unique():
    names = [op.name for op in ops.OPERATIONS]
    codes = [op.code for op in ops.OPERATIONS]
    assert len(names) == len(set(names))
    assert len(codes) == len(set(codes))


def test_aliases_do_not_collide_with_names():
    names = {op.name for op in ops.OPERATIONS}
    for op in ops.OPERATIONS:
        for alias in op.aliases:
            assert alias not in names


@pytest.mark.parametrize("name", ["hello", "list_ops", "retrieve", "describe", "invoke", "purge"])
def test_by_name_round_trips(name):
    op = ops.by_name(name)
    assert op is not None
    assert ops.by_code(op.code) is op


def test_list_operations_alias_resolves():
    assert ops.by_name("list_operations") is ops.by_name("list_ops")


def test_resolve_prefers_code_but_falls_back_to_name():
    retrieve = ops.by_name("retrieve")
    assert ops.resolve(retrieve.code, None) is retrieve
    assert ops.resolve(None, "retrieve") is retrieve
    assert ops.resolve(9999, "retrieve") is retrieve
    assert ops.resolve(9999, "nonsense") is None


def test_purge_and_describe_are_advertised():
    """Both were implemented but missing from discovery before the registry."""
    advertised = ops.available_operations()
    assert "purge" in advertised
    assert "describe" in advertised


def test_descriptors_namespace_standard_and_local_operations():
    by_name = {d["name"]: d for d in ops.operation_descriptors()}
    assert by_name["retrieve"]["id"] == "0.DOIP/Op.Retrieve"
    assert by_name["list_ops"]["id"] == "0.DOIP/Op.ListOperations"
    assert by_name["retrieve"]["standard"] is True
    # purge, describe and invoke are MaRDI extensions, not DOIP 2.0 operations
    for local in ("purge", "describe", "invoke"):
        assert by_name[local]["id"].startswith("0.MaRDI/Op.")
        assert by_name[local]["standard"] is False


def test_dispatch_table_covers_every_advertised_operation():
    from doip_server.main import _HANDLERS

    assert set(_HANDLERS) == {op.name for op in ops.OPERATIONS}


def test_cli_exposes_every_server_operation():
    from client_cli.main import _ACTIONS, _ACTION_HELP

    for name in ops.cli_action_names():
        assert name in _ACTIONS, f"{name} advertised but not a CLI action"
        assert name in _ACTION_HELP, f"{name} is a CLI action but has no help entry"
