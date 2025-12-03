import asyncio
from functools import lru_cache
from typing import Dict, List, Tuple

import boto3
import httpx
from botocore.client import Config

from .logging_config import log
from doip_shared.sharding import get_component_path, shard_qid

_CFG: Dict = {}

_TYPE_SUFFIX_MAP = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "application/json": ".json",
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
    """Return branch name for lakeFS-backed storage.

    Returns:
        str: Branch name configured for the lakeFS repository.
    """
    lakefs_cfg = _CFG.get("lakefs", {}) if isinstance(_CFG, dict) else {}
    return lakefs_cfg.get("branch") or "main"


def _endpoint_url() -> str | None:
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

def _extension_from_media_type(media_type: str | None, explicit_extension: str | None) -> str:
    """Return a normalized extension (with leading dot) for a media type or explicit extension.

    Args:
        media_type: MIME type string.
        explicit_extension: Optional extension provided by caller.

    Returns:
        str: Extension including a leading dot or empty string when unknown.
    """
    if explicit_extension:
        ext = explicit_extension if explicit_extension.startswith(".") else f".{explicit_extension}"
        return ext
    if media_type and media_type in _TYPE_SUFFIX_MAP:
        return _TYPE_SUFFIX_MAP[media_type]
    return ".bin"


def build_object_key(qid: str, component_id: str, extension: str, branch: str | None = None) -> str:
    """Return the full lakeFS key (including branch) for a component.

    Args:
        qid: QID of the object.
        component_id: Component identifier.
        extension: File extension with or without leading dot.
        branch: Optional branch override; defaults to configured branch.

    Returns:
        str: LakeFS object key suitable for S3 operations.
    """
    ext = extension.lstrip(".")
    branch_name = branch or _branch()
    path = get_component_path(qid, component_id, ext)
    return f"{branch_name}/{path}"


async def get_component_bytes(
    object_id: str,
    component_id: str,
    media_type: str | None = None,
    extension: str | None = None,
) -> bytes:
    """Fetch component content bytes from lakeFS/S3 using sharded paths.

    Args:
        object_id: Object identifier/QID.
        component_id: Component identifier (e.g. "fulltext").
        media_type: Optional media type used to derive file extension.
        extension: Optional file extension override.

    Returns:
        bytes: Component content.

    Raises:
        KeyError: If the component is not found in storage.
    """
    qid = _extract_qid(object_id)
    ext = _extension_from_media_type(media_type, extension)
    key = build_object_key(qid, component_id, ext)

    log.info("Retrieving lakeFS object key=%s", key)

    try:
        response = await asyncio.to_thread(_client().get_object, Bucket=_repo(), Key=key)
    except Exception as exc:
        raise KeyError(f"S3 object not found: {key}") from exc

    return response["Body"].read()

async def put_component_bytes(
    object_id: str,
    component_id: str,
    data: bytes,
    media_type: str = "application/octet-stream",
    extension: str | None = None,
) -> str:
    """Store component bytes to lakeFS/S3 and return the object key.

    Args:
        object_id: Object identifier/QID.
        component_id: Component identifier to store.
        data: Content bytes to upload.
        media_type: MIME type for the object (used for extension).
        extension: Optional file extension override.

    Returns:
        str: Stored S3 key (branch + sharded path).
    """
    qid = _extract_qid(object_id)
    ext = _extension_from_media_type(media_type, extension)
    key = build_object_key(qid, component_id, ext)
    await asyncio.to_thread(
        _client().put_object,
        Bucket=_repo(),
        Key=key,
        Body=data,
        ContentType=media_type,
    )
    return key


async def list_components(object_id: str) -> List[str]:
    """List component keys under a given object prefix.

    Args:
        object_id: Object identifier/QID.

    Returns:
        List[str]: Component suffixes stored for the object.
    """
    qid = _extract_qid(object_id)
    prefix = f"{_branch()}/{shard_qid(qid)}/components/"

    log.info(
        "Listing components repo=%s branch=%s prefix=%s object_id=%s",
        _repo(),
        _branch(),
        prefix,
        object_id,
    )

    paginator = _client().get_paginator("list_objects_v2")
    result: List[str] = []
    async for page in _async_paginate(paginator, Bucket=_repo(), Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.startswith(prefix):
                result.append(key[len(prefix) :])
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
    """Normalize and validate an object identifier, returning its QID prefix.

    Args:
        object_id: Object identifier that should start with a leading ``Q``.

    Returns:
        str: Uppercased QID prefix (e.g., ``Q123``).

    Raises:
        ValueError: If the identifier is malformed or missing digits.
    """
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
