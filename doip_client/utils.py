"""Utility helpers for DOIP client encoding/decoding."""

from __future__ import annotations

import json
from typing import Any, Dict


def dict_to_json_bytes(data: Dict[str, Any]) -> bytes:
    """Serialize a dict to JSON bytes using compact separators.

    Args:
        data: Dictionary to encode.

    Returns:
        UTF-8 encoded JSON bytes.
    """
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def json_bytes_to_dict(data: bytes) -> Dict[str, Any]:
    """Parse JSON bytes into a dictionary.

    Args:
        data: UTF-8 JSON payload.

    Returns:
        Decoded dictionary.
    """
    return json.loads(data.decode("utf-8"))
