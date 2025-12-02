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

    Returns:
        None
    """
    await asyncio.to_thread(
        requests.post,
        API_URL,
        params={"action": "wbeditentity", "format": "json", "new": "item"},
        json=payload,
        timeout=10,
    )


async def fetch_property_values(qid: str, property_id: str) -> list[str]:
    """Fetch values for a Wikibase property from the MediaWiki API.

    Args:
        qid: Item identifier (e.g., ``\"Q6190920\"``).
        property_id: Property identifier (e.g., ``\"P205\"``).

    Returns:
        list[str]: Extracted string values for the property, empty if missing or on error.
    """
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    }

    try:
        response = await asyncio.to_thread(
            requests.get, API_URL, params=params, timeout=10
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    entities = data.get("entities", {})
    entity = entities.get(qid, {})
    claims = entity.get("claims", {})
    statements = claims.get(property_id, []) if isinstance(claims, dict) else []

    values: list[str] = []
    for stmt in statements:
        mainsnak = stmt.get("mainsnak") if isinstance(stmt, dict) else None
        datavalue = mainsnak.get("datavalue") if isinstance(mainsnak, dict) else None
        if not isinstance(datavalue, dict):
            continue
        value = datavalue.get("value")
        if isinstance(value, dict):
            if "id" in value and isinstance(value["id"], str):
                values.append(value["id"])
            elif "text" in value and isinstance(value["text"], str):
                values.append(value["text"])
        elif isinstance(value, str):
            values.append(value)
    return values
