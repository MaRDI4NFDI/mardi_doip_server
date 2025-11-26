import asyncio
import os
from typing import Dict, List, Optional

import httpx

from . import storage_lakefs


FDO_API = os.getenv("FDO_API", "https://fdo.portal.mardi4nfdi.de/fdo/")


class ObjectRegistry:
    """Caches manifests and component metadata for DOIP objects."""

    def __init__(self):
        """Initialize registry caches."""
        self._manifest_cache: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def fetch_fdo_object(self, pid: str) -> Dict:
        """Fetch and cache the FDO JSON-LD for a given PID (Q... or Q..._FULLTEXT)."""
        pid = pid.upper()
        async with self._lock:
            if pid in self._manifest_cache:
                return self._manifest_cache[pid]

        data = await self._fetch_manifest(pid)

        async with self._lock:
            self._manifest_cache[pid] = data

        return data

    async def fetch_bitstream_bytes(self, pid: str) -> bytes:
        """
        Resolve the primary bitstream bytes for a bitstream PID.

        Convention:
        - PID ends with '_FULLTEXT'
        - Base QID is PID without suffix
        - LakeFS component id is fixed as 'primary'
        """
        pid_u = pid.upper()
        if not pid_u.startswith("Q") or not pid_u.endswith("_FULLTEXT"):
            raise ValueError(f"Not a bitstream PID: {pid}")

        qid = pid_u[:-9]  # strip '_FULLTEXT'

        if not await storage_lakefs.ensure_lakefs_available():
            raise RuntimeError("Storage backend unavailable")

        # internal convention: (qid, 'primary') → PDF
        return await storage_lakefs.get_component_bytes(qid, "primary")

    async def get_manifest(self, qid: str) -> Dict:
        """treat manifest == FDO JSON for base QID."""
        return await self.fetch_fdo_object(qid)

    async def _fetch_manifest(self, qid: str) -> Dict:
        """Retrieve manifest JSON-LD from the FDO façade.

        Args:
            qid: Object identifier.

        Returns:
            Dict: Manifest payload.
        """
        url = f"{FDO_API}{qid}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
