"""Message and block representations for the DOIP client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .protocol import Header


@dataclass
class ComponentBlock:
    """Binary component block inside a DOIP payload."""

    component_id: str
    content: bytes
    media_type: str = "application/octet-stream"
    declared_size: int | None = None


@dataclass
class DoipRequest:
    """Outgoing DOIP request envelope."""

    header: Header
    object_id: str
    metadata_blocks: List[dict] = field(default_factory=list)
    component_blocks: List[ComponentBlock] = field(default_factory=list)
    workflow_blocks: List[dict] = field(default_factory=list)


@dataclass
class DoipResponse:
    """Incoming DOIP response envelope."""

    header: Header
    metadata_blocks: List[dict]
    component_blocks: List[ComponentBlock]
    workflow_blocks: List[dict]
