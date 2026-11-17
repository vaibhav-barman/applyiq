"""Settings tests (AC9, AC11)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

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


def test_app_never_reads_the_environment_directly() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "app").rglob("*.py")
        if "os.getenv" in path.read_text() or "os.environ" in path.read_text()
    ]
    assert offenders == []
