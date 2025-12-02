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
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from doip_client import StrictDOIPClient


def _parse_host(raw: Optional[str]) -> str:
    """Return a host string, handling values like ``tcp://host:port``.

    Args:
        raw: Raw host value from the environment.

    Returns:
        str: Hostname portion suitable for socket connections.
    """

    if not raw:
        return "127.0.0.1"
    parsed = urlparse(raw)
    return parsed.hostname or raw


def _parse_port(raw: Optional[str], default: int = 3567) -> int:
    """Return an integer port, tolerating Kubernetes-style ``tcp://HOST:PORT`` envs.

    Args:
        raw: Raw port value from the environment.
        default: Fallback port when parsing fails.

    Returns:
        int: Parsed port number.
    """

    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        parsed = urlparse(raw)
        if parsed.port:
            return parsed.port
        # Fallback for values like host:port without scheme
        try:
            maybe_port = raw.rsplit(":", 1)[-1]
            return int(maybe_port)
        except Exception:
            logging.getLogger(__name__).warning(
                "Invalid DOIP_PORT value '%s', falling back to %s", raw, default
            )
            return default


DEFAULT_DOIP_HOST = _parse_host(os.getenv("DOIP_HOST"))
DEFAULT_DOIP_PORT = _parse_port(os.getenv("DOIP_PORT"), default=3567)
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


@app.get("/doip/retrieve/{object_id}/{component_id}")
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
