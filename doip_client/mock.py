"""Mock client implementation for development and tests."""

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class MockDoipClient:
    """Lightweight fake DOIP client for local testing."""

    responses: Dict[str, Dict[str, Any]]

    def hello(self) -> Dict[str, Any]:
        """Return a canned hello response."""
        return self.responses.get(
            "hello",
            {
                "operation": "hello",
                "status": "ok",
                "server": "mock_doip_client",
            },
        )

    def retrieve(self, object_id: str) -> Dict[str, Any]:
        """Return a canned retrieve response for the given object."""
        return self.responses.get(
            "retrieve",
            {"operation": "retrieve", "objectId": object_id, "components": []},
        )

    def invoke(self, object_id: str, workflow: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Return a canned invoke response for the given workflow."""
        return self.responses.get(
            "invoke",
            {
                "operation": "invoke",
                "objectId": object_id,
                "workflow": workflow,
                "params": params or {},
                "result": {},
            },
        )
