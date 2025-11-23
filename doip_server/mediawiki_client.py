import asyncio
import os
import time
import uuid
from typing import Dict, Optional

import requests


API_URL = os.getenv("MEDIAWIKI_API", "https://www.wikidata.org/w/api.php")


def _generate_qid() -> str:
    """Generate a pseudo QID for mock item creation.

    Returns:
        str: Synthetic QID.
    """
    return f"Q{int(time.time())}{uuid.uuid4().hex[:6]}"


async def create_equation_item(source_qid: str, latex: str, metadata: Optional[Dict] = None) -> str:
    """Create a MediaWiki/Wikibase item representing an extracted equation.

    Args:
        source_qid: Source object identifier.
        latex: LaTeX representation of the equation.
        metadata: Optional metadata for the item.

    Returns:
        str: Newly created QID (mocked).
    """
    payload = {
        "labels": {"en": {"language": "en", "value": f"Equation from {source_qid}"}},
        "claims": [
            {"property": "P123", "value": source_qid},
            {"property": "P999", "value": latex},
        ],
    }
    if metadata:
        payload["metadata"] = metadata
    await _post_item(payload)
    return _generate_qid()


async def create_generic_item(label: str, description: str, claims: Optional[Dict] = None) -> str:
    """Create a generic item with label, description, and claims.

    Args:
        label: Human-readable label.
        description: Human-readable description.
        claims: Optional claims payload.

    Returns:
        str: Newly created QID (mocked).
    """
    payload = {
        "labels": {"en": {"language": "en", "value": label}},
        "descriptions": {"en": {"language": "en", "value": description}},
        "claims": claims or {},
    }
    await _post_item(payload)
    return _generate_qid()


async def _post_item(payload: Dict):
    """Post an item payload to the MediaWiki API (best-effort, mocked).

    Args:
        payload: Entity payload for Wikibase.
    """
    await asyncio.to_thread(
        requests.post,
        API_URL,
        params={"action": "wbeditentity", "format": "json", "new": "item"},
        json=payload,
        timeout=10,
    )
