"""Settings tests (AC9, AC11)."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from tests.settings_support import DUMMY_DATABASE_URL, make_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
POOL_VARIABLES = (
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT_SECONDS",
    "DB_POOL_RECYCLE_SECONDS",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure the developer's shell cannot change what these tests see."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    for name in POOL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", DUMMY_DATABASE_URL)


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


def test_loads_from_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.env.example` lists variables later specs will declare; none may break startup."""
    monkeypatch.delenv("DATABASE_URL")
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


# ---- DATABASE_URL and pool settings (spec 002, AC2, AC3) ----

SENTINEL = "zq7SentinelValue"


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_url_is_a_secret() -> None:
    settings = make_settings(database_url=f"postgresql+psycopg://u:{SENTINEL}@db:5432/app")
    assert SENTINEL not in repr(settings)
    assert SENTINEL not in str(settings.database_url)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        (f"not a url {SENTINEL}", "could not be parsed"),
        (f"postgresql://u:{SENTINEL}@db:5432/app", "must start with postgresql+psycopg://"),
        (f"postgresql+asyncpg://u:{SENTINEL}@db:5432/app", "must start with postgresql+psycopg://"),
        (f"postgresql+psycopg://u:{SENTINEL}@/app", "must include a host"),
        (f"postgresql+psycopg://u:{SENTINEL}@db:5432", "must include a database name"),
        (f"postgresql+psycopg://u:{SENTINEL}@db:5432/", "must include a database name"),
    ],
)
def test_bad_database_url_is_rejected_without_echoing_it(url: str, message: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(database_url=url)
    text = str(caught.value)
    assert message in text
    assert "DATABASE_URL" in text
    assert SENTINEL not in text
    assert "postgresql+" not in text.split("must start with")[0]
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u@db:5432/app",
        "postgresql+psycopg://u:change-me@db:5432/app",
        "postgresql+psycopg://u:REPLACE_WITH_POSTGRES_PASSWORD@db:5432/app",
    ],
)
def test_prod_rejects_missing_or_placeholder_password(url: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(app_env="prod", database_url=url)
    text = str(caught.value)
    assert "password when APP_ENV=prod" in text or "placeholder password" in text
    assert "REPLACE_WITH_POSTGRES" not in text
    assert "change-me" not in text


def test_prod_accepts_a_real_password() -> None:
    settings = make_settings(
        app_env="prod", database_url=f"postgresql+psycopg://u:{SENTINEL}@db:5432/app"
    )
    assert settings.database_url.get_secret_value().endswith("/app")


def test_dev_accepts_the_placeholder_password() -> None:
    make_settings(database_url="postgresql+psycopg://u:REPLACE_WITH_X@127.0.0.1:5432/app")


def test_pool_defaults() -> None:
    settings = make_settings()
    assert settings.db_pool_size == 5
    assert settings.db_max_overflow == 5
    assert settings.db_pool_timeout_seconds == 10
    assert settings.db_pool_recycle_seconds == 1800


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("db_pool_size", 0),
        ("db_pool_size", 21),
        ("db_max_overflow", -1),
        ("db_max_overflow", 21),
        ("db_pool_timeout_seconds", 0),
        ("db_pool_timeout_seconds", 61),
        ("db_pool_recycle_seconds", 59),
        ("db_pool_recycle_seconds", 7201),
    ],
)
def test_pool_settings_out_of_range_are_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: value})


def test_env_example_has_no_password_values() -> None:
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    assert "POSTGRES_PASSWORD=" in lines
    assert "REDIS_PASSWORD=" in lines


def test_env_example_database_settings_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    assert "REPLACE_WITH_POSTGRES_PASSWORD" in settings.database_url.get_secret_value()
    assert settings.db_pool_recycle_seconds == 1800
