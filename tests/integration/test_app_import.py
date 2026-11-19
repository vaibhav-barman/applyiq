"""`app.main` builds the app from the environment; tests never import it (AC15)."""

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.core.config import get_settings
from tests.settings_support import DUMMY_DATABASE_URL

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_importing_app_main_gives_a_fastapi_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)
    get_settings.cache_clear()
    sys.modules.pop("app.main", None)
    try:
        module = importlib.import_module("app.main")
        assert isinstance(module.app, FastAPI)
    finally:
        sys.modules.pop("app.main", None)
        get_settings.cache_clear()


def test_conftest_does_not_import_app_main() -> None:
    assert "app.main" not in (REPO_ROOT / "tests" / "conftest.py").read_text()
