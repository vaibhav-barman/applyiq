"""Settings tests (AC9, AC11)."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure the developer's shell cannot change what these tests see."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "dev"
    assert settings.log_level == "INFO"


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)
    assert settings.app_env == "prod"
    assert settings.log_level == "DEBUG"


def test_rejects_unknown_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_rejects_unknown_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "TRACE")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_loads_from_env_example() -> None:
    """`.env.example` lists variables later specs will declare; none may break startup."""
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    assert settings.app_env == "dev"
    assert settings.log_level == "INFO"


def test_environment_variable_names_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("app_env", "prod")
    monkeypatch.setenv("Log_Level", "ERROR")
    settings = Settings(_env_file=None)
    assert settings.app_env == "prod"
    assert settings.log_level == "ERROR"


@pytest.mark.parametrize(
    "line", ["APP_ENV=staging", "LOG_LEVEL=info", "LOG_LEVEL=TRACE", "APP_ENV=", "APP_ENV=PROD"]
)
def test_env_file_with_an_invalid_value_is_rejected(tmp_path: Path, line: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{line}\n")
    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)


def test_env_file_values_are_read_and_unknown_variables_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=test\nLOG_LEVEL=WARNING\nSOME_FUTURE_SETTING=x\n")
    settings = Settings(_env_file=env_file)
    assert settings.app_env == "test"
    assert settings.log_level == "WARNING"
    assert not hasattr(settings, "some_future_setting")


def test_real_environment_wins_over_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=dev\n")
    monkeypatch.setenv("APP_ENV", "prod")
    assert Settings(_env_file=env_file).app_env == "prod"


def test_get_settings_is_built_once(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    try:
        monkeypatch.setenv("APP_ENV", "prod")
        first = get_settings()
        monkeypatch.setenv("APP_ENV", "test")
        assert get_settings() is first
        assert first.app_env == "prod"
    finally:
        get_settings.cache_clear()


def environment_reads(source: str) -> list[str]:
    """Find direct environment access: `os.getenv`, `os.environ` and `from os import ...`."""
    reads: list[str] = []
    os_names = {"environ", "environb", "getenv", "getenvb", "putenv", "unsetenv"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in os_names:
            reads.append(node.attr)
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            reads.extend(alias.name for alias in node.names if alias.name in os_names)
    return reads


@pytest.mark.parametrize(
    "source",
    [
        "import os\nos.getenv('X')",
        "import os\nos.environ['X']",
        "import os\nos.environ.get('X')",
        "from os import environ",
        "from os import getenv as read_env",
        "from os import path, getenv",
        "import os as operating_system\noperating_system.getenv('X')",
    ],
)
def test_environment_scanner_detects_every_form(source: str) -> None:
    assert environment_reads(source) != []


@pytest.mark.parametrize(
    "source",
    ["import os\nos.path.join('a', 'b')", "from os import path", "environ = {}\nenviron['X']"],
)
def test_environment_scanner_ignores_unrelated_code(source: str) -> None:
    assert environment_reads(source) == []


def test_app_never_reads_the_environment_directly() -> None:
    offenders = {
        str(path.relative_to(REPO_ROOT)): environment_reads(path.read_text())
        for path in (REPO_ROOT / "app").rglob("*.py")
    }
    assert {path: reads for path, reads in offenders.items() if reads} == {}
