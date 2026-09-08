"""Single source of truth for the DOIP operations this deployment implements.

Every place that needs to know "which operations exist" derives from
:data:`OPERATIONS` here: the server's ``hello`` and ``list_operations``
responses, the server's dispatch table, and the CLI's ``--action`` choices.
Adding an operation means adding one entry below and one handler.

Historically these lists were maintained by hand in five places and had drifted:
``purge`` was implemented but advertised nowhere, and ``describe`` was
advertised by ``hello`` but missing from ``list_operations`` and from the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import (
    OP_CREATE,
    OP_DESCRIBE,
    OP_HELLO,
    OP_INVOKE,
    OP_LIST_OPS,
    OP_PURGE,
    OP_RETRIEVE,
    OP_SEARCH,
    OP_UPDATE,
)

#: Identifier prefix for operations defined by the DOIP 2.0 specification.
DOIP_OP_NAMESPACE = "0.DOIP/Op."
#: Identifier prefix for operations local to MaRDI, i.e. not in the spec.
MARDI_OP_NAMESPACE = "0.MaRDI/Op."


@dataclass(frozen=True)
class Operation:
    """One operation the server can execute.

    Attributes:
        name: Wire/CLI name, as it appears in a metadata block's ``operation``.
        code: Numeric DOIP operation code sent in the message header.
        doip_id: Fully qualified operation identifier. Operations defined by
            DOIP 2.0 use the ``0.DOIP/Op.`` namespace; MaRDI-local ones use
            ``0.MaRDI/Op.`` so the distinction is visible to clients.
        summary: One-line description, surfaced in discovery responses.
        standard: True when the operation is part of DOIP 2.0.
        aliases: Alternative names accepted on the wire.
        cli: Whether the CLI exposes this operation as an ``--action``.
    """

    name: str
    code: int
    doip_id: str
    summary: str
    standard: bool = True
    aliases: tuple[str, ...] = ()
    cli: bool = True

    @property
    def names(self) -> tuple[str, ...]:
        """Return the wire name together with any aliases."""
        return (self.name, *self.aliases)


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="hello",
        code=OP_HELLO,
        doip_id=f"{DOIP_OP_NAMESPACE}Hello",
        summary="Return server identity, available operations and the type registry.",
    ),
    Operation(
        name="list_ops",
        code=OP_LIST_OPS,
        doip_id=f"{DOIP_OP_NAMESPACE}ListOperations",
        summary="List the operations this server supports.",
        aliases=("list_operations",),
    ),
    Operation(
        name="retrieve",
        code=OP_RETRIEVE,
        doip_id=f"{DOIP_OP_NAMESPACE}Retrieve",
        summary="Retrieve an object's metadata, or one of its components.",
    ),
    Operation(
        name="create",
        code=OP_CREATE,
        doip_id=f"{DOIP_OP_NAMESPACE}Create",
        summary="Create a new object in the knowledge graph.",
    ),
    Operation(
        name="update",
        code=OP_UPDATE,
        doip_id=f"{DOIP_OP_NAMESPACE}Update",
        summary="Update an existing object's properties or components.",
    ),
    Operation(
        name="search",
        code=OP_SEARCH,
        doip_id=f"{DOIP_OP_NAMESPACE}Search",
        summary="Search the knowledge graph and return matching object ids.",
    ),
    Operation(
        name="describe",
        code=OP_DESCRIBE,
        doip_id=f"{MARDI_OP_NAMESPACE}Describe",
        summary="Return the FDO record for an object as served by the FDO API.",
        standard=False,
    ),
    Operation(
        name="invoke",
        code=OP_INVOKE,
        doip_id=f"{MARDI_OP_NAMESPACE}Invoke",
        summary="Run a named server-side workflow against an object.",
        standard=False,
    ),
    Operation(
        name="purge",
        code=OP_PURGE,
        doip_id=f"{MARDI_OP_NAMESPACE}Purge",
        summary="Evict an object's cached manifest so the next read refetches it.",
        standard=False,
    ),
)

_BY_NAME: dict[str, Operation] = {n: op for op in OPERATIONS for n in op.names}
_BY_CODE: dict[int, Operation] = {op.code: op for op in OPERATIONS}


def by_name(name: str | None) -> Operation | None:
    """Return the operation with this wire name or alias, if any."""
    if not name:
        return None
    return _BY_NAME.get(name)


def by_code(code: int | None) -> Operation | None:
    """Return the operation with this numeric code, if any."""
    if code is None:
        return None
    return _BY_CODE.get(code)


def resolve(code: int | None, name: str | None) -> Operation | None:
    """Return the operation a request refers to.

    The numeric header code wins; the metadata ``operation`` name is the
    fallback, which keeps lenient clients working.

    Args:
        code: Operation code from the message header.
        name: Operation name from a metadata block.

    Returns:
        Operation | None: The matching operation, or None if unknown.
    """
    return by_code(code) or by_name(name)


def available_operations() -> dict[str, int]:
    """Return the ``{name: code}`` mapping used by discovery responses.

    This is the historical shape of the ``availableOperations`` field and is
    kept for backwards compatibility with existing clients.
    """
    return {op.name: op.code for op in OPERATIONS}


def operation_descriptors() -> list[dict]:
    """Return the richer operation list, including DOIP operation identifiers."""
    return [
        {
            "name": op.name,
            "id": op.doip_id,
            "code": op.code,
            "standard": op.standard,
            "summary": op.summary,
        }
        for op in OPERATIONS
    ]


def cli_action_names() -> tuple[str, ...]:
    """Return the operation names the CLI exposes as ``--action`` values."""
    return tuple(op.name for op in OPERATIONS if op.cli)
