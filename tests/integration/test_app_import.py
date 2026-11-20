"""`app.main` builds the app from the environment; tests never import it (AC15)."""

import ast
import importlib
import os
import subprocess
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


def imports_app_main(source: str) -> bool:
    """True for `import app.main`, `from app.main import x`, `from app import main`
    and `import_module("app.main")`."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import) and any(a.name == "app.main" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom):
            if node.module == "app.main":
                return True
            if node.module == "app" and any(a.name == "main" for a in node.names):
                return True
        if isinstance(node, ast.Constant) and node.value == "app.main":
            return True
    return False


@pytest.mark.parametrize(
    "source",
    [
        "import app.main",
        "from app.main import app",
        "from app import main",
        "import importlib\nimportlib.import_module('app.main')",
    ],
)
def test_main_import_scanner_detects_every_form(source: str) -> None:
    assert imports_app_main(source)


@pytest.mark.parametrize("source", ["from app.factory import create_app", "import app.core.config"])
def test_main_import_scanner_ignores_other_imports(source: str) -> None:
    assert not imports_app_main(source)


@pytest.mark.parametrize("name", ["conftest.py", "db_support.py", "settings_support.py"])
def test_shared_test_support_modules_do_not_import_app_main(name: str) -> None:
    assert not imports_app_main((REPO_ROOT / "tests" / name).read_text())


def test_loading_conftest_does_not_build_the_app() -> None:
    """Run in a fresh process with no DATABASE_URL: conftest must import cleanly
    and leave `app.main` unloaded (it builds the app, which needs the secret)."""
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "APP_ENV"}}
    code = "import tests.conftest, sys; sys.exit(1 if 'app.main' in sys.modules else 0)"
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]
