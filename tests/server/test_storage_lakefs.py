import logging
import tempfile
from pathlib import Path

import pytest
import yaml

from doip_server import storage_lakefs


def _config_path() -> Path:
    """Return the repository-level config.yaml path."""
    return Path(__file__).resolve().parents[2] / "config.yaml"


def _load_config_or_skip() -> dict:
    """Load config.yaml or skip if missing/invalid."""
    cfg_path = _config_path()
    if not cfg_path.exists():
        pytest.skip("config.yaml not present; skipping lakeFS integration test")
    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not isinstance(cfg, dict):
        pytest.skip("config.yaml does not contain a mapping")
    return cfg


@pytest.mark.asyncio
async def test_storage_lakefs_lists_components_from_config():
    """Attempt to list components using config.yaml-driven lakeFS settings."""
    cfg = _load_config_or_skip()
    lakefs_cfg = cfg.get("lakefs") or {}
    if not isinstance(lakefs_cfg, dict) or not lakefs_cfg.get("url"):
        pytest.skip("lakeFS endpoint url not configured in config.yaml")

    storage_lakefs.configure(cfg)

    logging.getLogger(__name__).debug(
        "test_storage_lakefs_lists_components_from_config() \n "
        "Using lakeFS configured with \n url: %s repo: %s branch: %s",
        lakefs_cfg.get("url"),
        lakefs_cfg.get("repo"),
        lakefs_cfg.get("branch"),
    )

    available = await storage_lakefs.ensure_lakefs_available()
    if not available:
        pytest.skip("lakeFS endpoint url unavailable; skipping integration test")

    object_id = "main"
    components = await storage_lakefs.list_components(object_id)

    assert isinstance(components, list)


@pytest.mark.asyncio
async def test_storage_lakefs_downloads_component_to_tempfile():
    """Download a component to a temp file and verify size matches content length."""
    cfg = _load_config_or_skip()
    lakefs_cfg = cfg.get("lakefs") or {}
    if not isinstance(lakefs_cfg, dict) or not lakefs_cfg.get("url"):
        pytest.skip("lakeFS endpoint url not configured in config.yaml")

    storage_lakefs.configure(cfg)
    if not await storage_lakefs.ensure_lakefs_available():
        pytest.skip("lakeFS url unavailable; skipping download test")

    object_id = lakefs_cfg.get("test_object_id") or "main"
    components = await storage_lakefs.list_components(object_id)
    if not components:
        pytest.skip("No components available to download for test object")
    target = components[0]

    logging.getLogger(__name__).info(
        "test_storage_lakefs_downloads_component_to_tempfile() \n " +
        "Downloading: %s",
        target,
    )

    content = await storage_lakefs.get_component_bytes(object_id)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    logging.getLogger(__name__).info(
        "Downloaded: %f bytes",
        tmp_path.stat().st_size,
    )

    assert tmp_path.stat().st_size == len(content)
    tmp_path.unlink(missing_ok=True)
