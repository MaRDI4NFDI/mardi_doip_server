import asyncio
import os
from typing import Dict, List, Optional

import httpx

from . import storage_lakefs
from .logging_config import log


class ObjectRegistry:
    """Caches manifests and component metadata for DOIP objects."""

    def __init__(self):
        """Initialize registry caches and shared state."""
        self._manifest_cache: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
        self.fdo_api = os.getenv("FDO_API", "https://fdo.portal.mardi4nfdi.de/fdo/")

    async def fetch_fdo_object(self, pid: str) -> Dict:
        """Fetch and cache the FDO JSON-LD for a given PID.

        Args:
            pid: PID/QID to retrieve.

        Returns:
            Dict: Manifest JSON-LD payload for the PID.
        """
        pid = pid.upper()
        async with self._lock:
            if pid in self._manifest_cache:
                return self._manifest_cache[pid]

        data = await self._fetch_manifest(pid)

        async with self._lock:
            self._manifest_cache[pid] = data

        return data

    async def get_component(self, object_id: str, component_id: str) -> bytes:
        """Load binary component content from the storage backend.

        Args:
            object_id: PID/QID containing the component.
            component_id: Identifier of the component to load.

        Returns:
            bytes: Raw component content.

        Raises:
            RuntimeError: When the storage backend is unavailable or errors.
            KeyError: When the component is missing.
        """
        if not await storage_lakefs.ensure_lakefs_available():
            raise RuntimeError("storage unavailable")

        try:
            content = await storage_lakefs.get_component_bytes(
                object_id, component_id
            )
        except KeyError as exc:
            raise KeyError(f"component-not-found:{component_id}")
        except Exception as exc:
            raise RuntimeError("storage-backend error")

        return content


    async def get_manifest(self, qid: str) -> Dict:
        """Return the manifest (FDO JSON) for a base QID.

        Args:
            qid: PID/QID to load.

        Returns:
            Dict: Manifest JSON-LD payload.
        """
        return await self.fetch_fdo_object(qid)

    async def _fetch_manifest(self, qid: str) -> Dict:
        """Retrieve manifest JSON-LD from the FDO façade.

        Args:
            qid: Object identifier.

        Returns:
            Dict: Manifest payload.

        Raises:
            httpx.HTTPError: If the remote request fails.
        """
        url = f"{self.fdo_api}{qid}"
        log.info("FDO API endpoint set to %s", self.fdo_api)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
