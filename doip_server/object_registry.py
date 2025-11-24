import asyncio
import os
from typing import Dict, List, Optional

import httpx

from . import storage_s3


FDO_API = os.getenv("FDO_API", "https://fdo.portal.mardi4nfdi.de/fdo/")


class ObjectRegistry:
    """Caches manifests and component metadata for DOIP objects."""

    def __init__(self):
        """Initialize registry caches."""
        self._manifest_cache: Dict[str, Dict] = {}
        self._component_cache: Dict[str, Dict[str, Dict]] = {}
        self._lock = asyncio.Lock()

    async def get_manifest(self, qid: str) -> Dict:
        """Fetch and cache the manifest for a QID.

        Args:
            qid: Object identifier.

        Returns:
            Dict: Manifest JSON-LD document.
        """
        async with self._lock:
            if qid in self._manifest_cache:
                return self._manifest_cache[qid]
        manifest = await self._fetch_manifest(qid)
        async with self._lock:
            self._manifest_cache[qid] = manifest
        return manifest

    async def get_components(self, qid: str) -> List[Dict]:
        """Return component metadata for a QID, caching results.

        Args:
            qid: Object identifier.

        Returns:
            List[Dict]: Component descriptors.
        """
        async with self._lock:
            if qid in self._component_cache:
                return list(self._component_cache[qid].values())
        manifest = await self.get_manifest(qid)
        components = self._parse_manifest_components(qid, manifest)
        async with self._lock:
            self._component_cache[qid] = {c["componentId"]: c for c in components}
        return components

    async def resolve_component(self, qid: str, component_id: str) -> Dict:
        """Resolve a specific component metadata record by ID.

        Args:
            qid: Object identifier.
            component_id: DOIP component identifier.

        Returns:
            Dict: Component metadata.
        """
        components = await self.get_components(qid)
        for comp in components:
            if comp["componentId"] == component_id:
                return comp
        # Fallback: build from convention.
        key = storage_s3.s3_key_from_component(qid, component_id)
        meta = {
            "componentId": component_id,
            "s3Key": key,
            "mediaType": "application/octet-stream",
        }
        async with self._lock:
            self._component_cache.setdefault(qid, {})[component_id] = meta
        return meta

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

    def _parse_manifest_components(self, qid: str, manifest: Dict) -> List[Dict]:
        """Parse component descriptors from a manifest response.

        Args:
            qid: Object identifier.
            manifest: Manifest payload.

        Returns:
            List[Dict]: Component descriptors with IDs and S3 keys.
        """
        components: List[Dict] = []
        access_records = manifest.get("access", []) or manifest.get("accessRecords", [])
        for record in access_records:
            if not isinstance(record, dict):
                continue
            component_id = record.get("componentId") or record.get("id")
            if not component_id:
                continue
            s3_key = record.get("s3Key") or storage_s3.s3_key_from_component(
                qid, component_id
            )
            media_type = record.get("mediaType") or "application/octet-stream"
            size = record.get("size")
            components.append(
                {
                    "componentId": component_id,
                    "s3Key": s3_key,
                    "mediaType": media_type,
                    "size": size,
                }
            )
        if not components:
            # Fallback to a single canonical PDF by convention.
            default_id = f"doip:bitstream/{qid}/main-pdf"
            components.append(
                {
                    "componentId": default_id,
                    "s3Key": storage_s3.s3_key_from_component(qid, default_id),
                    "mediaType": "application/pdf",
                }
            )
        return components
