# pytest -o log_cli=true -o log_cli_level=DEBUG

import logging
from pathlib import Path

import pytest
import yaml

from doip_server import storage_lakefs


@pytest.mark.asyncio
async def test_storage_lakefs_lists_components_from_config():
    """Attempt to list components using config.yaml-driven lakeFS settings.

    Returns:
        None
    """
    cfg_path = Path("config.yaml")
    if not cfg_path.exists():
        pytest.skip("config.yaml not present; skipping lakeFS integration test")

    with cfg_path.open("r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    if not isinstance(cfg, dict):
        pytest.skip("config.yaml does not contain a mapping")

    lakefs_cfg = cfg.get("lakefs") or {}
    if not isinstance(lakefs_cfg, dict) or not lakefs_cfg.get("url"):
        pytest.skip("lakeFS endpoint url not configured in config.yaml")

    storage_lakefs.configure(cfg)

    logging.getLogger(__name__).info(
        "Using lakeFS endpoint %s and bucket %s for integration test",
        lakefs_cfg.get("url"),
        lakefs_cfg.get("repo"),
    )

    available = await storage_lakefs.ensure_lakefs_available()
    if not available:
        pytest.skip("lakeFS endpoint url unavailable; skipping integration test")

    object_id = lakefs_cfg.get("test_object_id") or "test"
    components = await storage_lakefs.list_components(object_id)
    assert isinstance(components, list)
