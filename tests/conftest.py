"""Test configuration that ensures project modules are importable and async tests run."""

import sys
from pathlib import Path

import pytest

pytest_plugins = ("pytest_asyncio",)

# Add project root to sys.path so `doip_server` and `doip_client` can be imported in tests.
ROOT = Path(__file__).resolve().parent.parent
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)
