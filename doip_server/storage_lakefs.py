import asyncio
import logging
from functools import lru_cache
from typing import Dict, List, Optional

import boto3
import httpx
from botocore.client import Config

log = logging.getLogger()
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

_CFG: Dict = {}

_TYPE_SUFFIX_MAP = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
}


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


def _branch() -> str:
    """Return branch name for lakeFS-backed storage."""
    lakefs_cfg = _CFG.get("lakefs", {}) if isinstance(_CFG, dict) else {}
    return lakefs_cfg.get("branch") or "main"


def _endpoint_url() -> Optional[str]:
    """Resolve the lakeFS/S3-compatible endpoint URL.

    Returns:
        Optional[str]: Endpoint URL or None for default boto behavior.
    """
    lakefs_cfg = _CFG.get("lakefs", {}) if isinstance(_CFG, dict) else {}

    url = lakefs_cfg.get("url")
    if isinstance(url, str):
        trimmed_url = url.strip()
        if trimmed_url and not trimmed_url.startswith(("http://", "https://")):
            lakefs_cfg["url"] = f"https://{trimmed_url}"
            log.info("Normalized lakefs.url to %s", lakefs_cfg["url"])

    return lakefs_cfg.get("url")


async def ensure_lakefs_available() -> bool:
    """Verify lakeFS/S3 endpoint is configured and reachable.

    Returns:
        bool: True if available, False otherwise.
    """
    endpoint = _endpoint_url()

    log.debug("Checking lakeFS server @: %s", endpoint)

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

def s3_key_from_component(object_id: str, ext: str) -> str:
    """Construct an S3 key from a DOIP component identifier. """
    qid = _extract_qid(object_id)
    return f"{_branch()}/{qid}/{object_id}{ext}"


async def get_component_bytes(object_id: str) -> bytes:
    """Fetch component content bytes from lakeFS/S3.

    Args:
        object_id: Object identifier/QID.

    Returns:
        bytes: Component content.
    """

    log.debug( "Try to retrieve object with \n object_id: %s", object_id )

    # TODO: resolve from registry instead of hardcoding
    media_type = "application/pdf"

    ext = _TYPE_SUFFIX_MAP.get(media_type, "")
    key = s3_key_from_component(object_id, ext)

    log.debug( "Try to retrieve object from lakeFS with key: %s", key )

    response = await asyncio.to_thread(_client().get_object, Bucket=_repo(), Key=key)

    return response["Body"].read()

async def put_component_bytes(
    object_id: str, data: bytes, content_type: str = "application/octet-stream"
) -> str:
    """Store component bytes to lakeFS/S3 and return the key.

    Args:
        object_id: Object identifier/QID.
        data: Content bytes to upload.
        content_type: MIME type for the object.

    Returns:
        str: Stored S3 key.
    """
    key = s3_key_from_component(object_id)
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

    logging.getLogger(__name__).info(
        "Using lakeFS \n repo: %s \n branch: %s \n prefix: %s \n object_id %s",
        _repo(),
        _branch(),
        prefix,
        object_id,
    )

    paginator = _client().get_paginator("list_objects_v2")
    result: List[str] = []
    async for page in _async_paginate(paginator, Bucket=_repo(), Prefix=f"{_branch()}/{prefix}"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            expected_prefix = f"{_branch()}/{prefix}"
            if key.startswith(expected_prefix):
                result.append(key[len(expected_prefix) :])
    return result


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

def _extract_qid(object_id: str) -> str:
    obj = object_id.upper()
    if not obj.startswith("Q"):
        raise ValueError("invalid identifier: must start with Q")

    i = 1
    n = len(obj)
    while i < n and obj[i].isdigit():
        i += 1

    qid = obj[:i]
    if len(qid) == 1:
        raise ValueError("invalid identifier: no digits after Q")

    return qid
