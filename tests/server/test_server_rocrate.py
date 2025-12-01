import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

from unittest.mock import AsyncMock

from doip_server.handlers import _build_rocrate_payload


@pytest.mark.asyncio
async def test_build_rocrate_payload_creates_zip_and_metadata():
    pid = "Q12345"
    component_id = f"{pid}.csv"
    csv_content = b"col1,col2\n1,2\n3,4\n"

    registry = AsyncMock()
    registry.get_component.return_value = csv_content

    crate_bytes = await _build_rocrate_payload(pid, registry)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(crate_bytes)
        tmp_path = tmp.name

    # BEGIN - FOR DEBUB
    # src = Path(tmp_path)
    # dst = Path("/temp") / src.name
    # shutil.copy2(src, dst)
    # print(f"Written to: {dst}", flush=True)
    # END - FOR DEBUB

    try:
        with zipfile.ZipFile(tmp_path, "r") as z:
            names = z.namelist()
            assert "ro-crate-metadata.json" in names
            assert component_id in names

            extracted_data = z.read(component_id)
            assert extracted_data == csv_content

            meta_data = z.read("ro-crate-metadata.json")
            assert b"@context" in meta_data
            assert pid.encode() in meta_data
    finally:
        os.remove(tmp_path)
