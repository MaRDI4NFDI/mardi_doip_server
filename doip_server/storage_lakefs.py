import asyncio
from functools import lru_cache
from typing import Dict, List, Optional

import boto3
import httpx
from botocore.client import Config

_CFG: Dict = {}


def configure(cfg: Dict) -> None:
    """Configure lakeFS storage module with application settings.

    Args:
        cfg: Configuration dictionary produced by doip_server.main.set_config().
    """
    global _CFG
    _CFG = cfg or {}
    try:
        _client.cache_clear()
    except Exception:
        # If the client is not yet defined or cacheable, ignore.
        pass


def _repo() -> str:
    """Return repository name for lakeFS-backed storage.

    Returns:
        str: Repo name.
    """
    lakefs_cfg = _CFG.get("lakefs", {}) if isinstance(_CFG, dict) else {}
    return lakefs_cfg.get("repo")


def _endpoint_url() -> Optional[str]:
    """Resolve the lakeFS/S3-compatible endpoint URL.

    Returns:
        Optional[str]: Endpoint URL or None for default boto behavior.
    """
    lakefs_cfg = _CFG.get("lakefs", {}) if isinstance(_CFG, dict) else {}
    return lakefs_cfg.get("url")


async def ensure_lakefs_available() -> bool:
    """Verify lakeFS/S3 endpoint is configured and reachable.

    Returns:
        bool: True if available, False otherwise.
    """
    endpoint = _endpoint_url()
    if not endpoint:
        return False
    try:
        async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
            resp = await client.get(endpoint)
            resp.raise_for_status()
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _client():
    """Create a cached boto3 client configured for lakeFS.

    Returns:
        botocore.client.S3: Configured client instance.
    """
    lakefs_cfg = _CFG.get("lakefs", {}) if isinstance(_CFG, dict) else {}
    return boto3.client(
        "s3",
        endpoint_url=_endpoint_url(),
        aws_access_key_id=lakefs_cfg.get("user"),
        aws_secret_access_key=lakefs_cfg.get("password"),
        config=Config(
            signature_version=lakefs_cfg.get("signature_version") or "s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def s3_key_from_component(object_id: str, component_id: str) -> str:
    """Construct an S3 key from a DOIP component identifier.

    Args:
        object_id: Object identifier/QID.
        component_id: DOIP component ID.

    Returns:
        str: S3 key path under the bucket.
    """
    suffix = component_id.split("/")[-1]
    if "." not in suffix:
        suffix = f"{suffix}.pdf"
    return f"{object_id}/{suffix}"


async def get_component_bytes(object_id: str, component_id: str) -> bytes:
    """Fetch component content bytes from lakeFS/S3.

    Args:
        object_id: Object identifier/QID.
        component_id: DOIP component ID.

    Returns:
        bytes: Component content.
    """
    key = s3_key_from_component(object_id, component_id)
    response = await asyncio.to_thread(
        _client().get_object, Bucket=_repo(), Key=key
    )
    body = response["Body"]
    return body.read()


async def put_component_bytes(
    object_id: str, component_id: str, data: bytes, content_type: str = "application/octet-stream"
) -> str:
    """Store component bytes to lakeFS/S3 and return the key.

    Args:
        object_id: Object identifier/QID.
        component_id: DOIP component ID.
        data: Content bytes to upload.
        content_type: MIME type for the object.

    Returns:
        str: Stored S3 key.
    """
    key = s3_key_from_component(object_id, component_id)
    await asyncio.to_thread(
        _client().put_object,
        Bucket=_repo(),
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


async def list_components(object_id: str) -> List[str]:
    """List component keys under a given object prefix.

    Args:
        object_id: Object identifier/QID.

    Returns:
        List[str]: Component suffixes stored for the object.
    """
    prefix = f"{object_id}/"
    paginator = _client().get_paginator("list_objects_v2")
    result: List[str] = []
    async for page in _async_paginate(paginator, Bucket=_repo(), Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.startswith(prefix):
                result.append(key[len(prefix) :])
    return result


async def component_metadata(object_id: str, component_id: str) -> Dict[str, str]:
    """Return metadata for a stored component.

    Args:
        object_id: Object identifier/QID.
        component_id: DOIP component ID.

    Returns:
        Dict[str, str]: Metadata including media type and size.
    """
    key = s3_key_from_component(object_id, component_id)
    head = await asyncio.to_thread(_client().head_object, Bucket=_repo(), Key=key)
    return {
        "componentId": component_id,
        "mediaType": head.get("ContentType", "application/octet-stream"),
        "size": head.get("ContentLength"),
        "s3Key": key,
    }


async def _async_paginate(paginator, **kwargs):
    """Iterate over paginator pages in a thread to avoid blocking the loop.

    Args:
        paginator: Boto paginator.
        **kwargs: Pagination parameters.

    Yields:
        dict: Paginator page dictionary.
    """
    for page in await asyncio.to_thread(lambda: list(paginator.paginate(**kwargs))):
        yield page
