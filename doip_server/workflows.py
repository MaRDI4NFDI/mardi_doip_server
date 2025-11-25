import asyncio
import json
from typing import Dict, List

from . import mediawiki_client, storage_lakefs


async def run_equation_extraction_workflow(qid: str, params: Dict) -> Dict:
    """Run the equation extraction workflow for a given object.

    Args:
        qid: Object identifier in the registry.
        params: Workflow parameters including optional componentId.

    Returns:
        Dict: Metadata describing derived components and created items.
    """
    component_id = params.get("componentId", f"doip:bitstream/{qid}/main-pdf")
    pdf_bytes = await storage_s3.get_component_bytes(qid, component_id)

    equations: List[Dict] = _mock_extract_equations(pdf_bytes)
    equations_json = json.dumps(equations).encode("utf-8")

    derived_component_id = f"doip:bitstream/{qid}/equations-json"
    s3_key = await storage_s3.put_component_bytes(
        qid, derived_component_id, equations_json, content_type="application/json"
    )

    new_item_id = await mediawiki_client.create_equation_item(
        qid, latex="; ".join(eq["latex"] for eq in equations), metadata={"source": qid}
    )

    return {
        "workflow": "equation_extraction",
        "sourceObject": qid,
        "derivedComponents": [
            {
                "componentId": derived_component_id,
                "mediaType": "application/json",
                "s3Key": s3_key,
                "size": len(equations_json),
            }
        ],
        "createdItems": [new_item_id],
    }


def _mock_extract_equations(pdf_bytes: bytes) -> List[Dict]:
    """Mock equation extraction from PDF bytes.

    Args:
        pdf_bytes: Raw PDF content.

    Returns:
        List[Dict]: Mocked equation records.
    """
    return [
        {"page": 1, "latex": r"E=mc^2"},
        {"page": 2, "latex": r"\\int_a^b f(x) dx"},
    ]
