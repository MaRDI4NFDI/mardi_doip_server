import asyncio
import os
from typing import Dict, List

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
                log.info(f"Cache hit for {pid}.")
                return self._manifest_cache[pid]

        data = await self._fetch_manifest(pid)

        async with self._lock:
            self._manifest_cache[pid] = data

        return data

    async def get_component(self, object_id: str, component_id: str) -> tuple[bytes, str]:
        """Resolve a component via manifest and load its bytes from storage.

        Args:
            object_id: PID/QID containing the component.
            component_id: Identifier of the component to load.

        Returns:
            tuple[bytes, str]: Component content and resolved media type.

        Raises:
            RuntimeError: When the storage backend is unavailable or errors.
            KeyError: When the component is missing.
        """
        log.info(f"get_component() for {object_id}/{component_id}")

        manifest = await self.fetch_fdo_object(object_id)
        component = _find_component(component_id, manifest)
        if component is None:
            raise KeyError(f"component-not-found:{component_id}")

        media_type = _component_media_type(component)
        extension = _component_extension(component, media_type)

        if not await storage_lakefs.ensure_lakefs_available():
            raise ConnectionError()

        try:
            content = await storage_lakefs.get_component_bytes(
                object_id, component_id, media_type=media_type, extension=extension
            )
        except KeyError as exc:
            raise KeyError(f"component-not-found:{component_id}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("storage-backend error") from exc

        return content, media_type


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
        log.info("(registry._fetch_manifest) Using FDO API endpoint: %s", self.fdo_api)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()


def _find_component(component_id: str, manifest: Dict) -> Dict | None:
    """Return the component dict matching ``component_id`` from a manifest.

    Args:
        component_id: Target component identifier.
        manifest: FDO JSON-LD manifest.

    Returns:
        dict | None: Matching component dictionary or ``None`` if not found.
    """
    kernel = manifest.get("kernel") if isinstance(manifest, dict) else None
    components = kernel.get("fdo:hasComponent") if isinstance(kernel, dict) else None
    if not isinstance(components, list):
        return None
    for comp in components:
        if isinstance(comp, dict) and comp.get("componentId") == component_id:
            return comp
    return None


def _component_media_type(component: Dict) -> str:
    """Return the media type for a component dictionary."""
    media_type = component.get("mediaType") or component.get("mimeType") or "application/octet-stream"
    return media_type


def _component_extension(component: Dict, media_type: str) -> str | None:
    """Infer file extension from component location or media type.

    Args:
        component: Component dictionary from the manifest.
        media_type: Resolved media type string.

    Returns:
        str | None: Extension without leading dot when derivable, else None.
    """
    location = component.get("location")
    if isinstance(location, str) and "." in location:
        return location.rsplit(".", 1)[-1]
    if media_type.startswith("application/pdf"):
        return "pdf"
    if media_type == "application/json":
        return "json"
    return None
