"""HTTP download gateway that bridges browser requests to the DOIP server.

The gateway exposes a simple REST-style endpoint that accepts an object ID and
component ID via the path, fetches the corresponding component from the
co-located DOIP server, and streams the content back with appropriate HTTP
headers so browsers treat it as a file download.
"""

from __future__ import annotations

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from doip_client import StrictDOIPClient

DEFAULT_DOIP_HOST = os.getenv("DOIP_HOST", "127.0.0.1")
DEFAULT_DOIP_PORT = int(os.getenv("DOIP_PORT", "3567"))
CERT_PATH = Path("certs/server.crt")


def _client(use_tls: Optional[bool] = None) -> StrictDOIPClient:
    """Create a StrictDOIPClient configured for the local server.

    Args:
        use_tls: Optional override for TLS usage. If ``None``, TLS is enabled
            when the container has a server certificate present.

    Returns:
        StrictDOIPClient: Configured client instance.
    """

    tls_enabled = CERT_PATH.exists() if use_tls is None else use_tls
    verify_tls = os.getenv("DOIP_VERIFY_TLS", "false").lower() == "true"

    return StrictDOIPClient(
        host=DEFAULT_DOIP_HOST,
        port=DEFAULT_DOIP_PORT,
        use_tls=tls_enabled,
        verify_tls=verify_tls,
    )


app = FastAPI(title="MaRDI DOIP HTTP Gateway")
log = logging.getLogger(__name__)


@app.get("/doip/{object_id}/{component_id}")
async def download_component(object_id: str, component_id: str):
    """Stream a DOIP component to the caller as an HTTP download.

    Args:
        object_id: PID/QID of the target object.
        component_id: Component identifier to retrieve.

    Returns:
        StreamingResponse: Component bytes with appropriate HTTP headers.

    Raises:
        HTTPException: When the component is missing or backend errors occur.
    """

    log.info("HTTP download requested", extra={"object_id": object_id, "component_id": component_id})

    client = _client()
    try:
        response = await asyncio.to_thread(client.retrieve, object_id, component_id)
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "DOIP backend error during retrieve", extra={"object_id": object_id, "component_id": component_id}
        )
        raise HTTPException(status_code=502, detail=f"DOIP backend error: {exc}")

    if not response.component_blocks:
        log.warning(
            "Component not found", extra={"object_id": object_id, "component_id": component_id}
        )
        raise HTTPException(status_code=404, detail="Component not found")

    comp = response.component_blocks[0]
    media_type = comp.media_type or "application/octet-stream"
    filename = Path(comp.component_id).name or "download"

    log.info(
        "Serving component", extra={"object_id": object_id, "component_id": component_id, "media_type": media_type}
    )

    return StreamingResponse(
        iter([comp.content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Serve the previous landing page and assets (background image, favicon) from /app/landing.
app.mount(
    "/",
    StaticFiles(directory="/app/landing", html=True),
    name="landing",
)
