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
        app_env="prod",
        database_url=f"postgresql+psycopg://u:{SENTINEL}@db:5432/app?sslmode=require",
    )
    assert settings.database_url.get_secret_value().endswith("/app?sslmode=require")


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


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql+psycopg2://u:{SENTINEL}@db:5432/app",
        f"sqlite+aiosqlite:///{SENTINEL}.db",
        f"mysql+pymysql://u:{SENTINEL}@db:3306/app",
        f"postgres://u:{SENTINEL}@db:5432/app",
        f"postgresql+psycopg://u:{SENTINEL}@db:5432/",
        SENTINEL,
        "",
    ],
)
def test_other_unusable_urls_are_rejected_without_echoing_them(url: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(database_url=url)
    text = str(caught.value)
    assert "DATABASE_URL" in text
    assert SENTINEL not in text
    assert "db:5432" not in text


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql://u:{SENTINEL}@db.internal:5432/app",
        f"postgresql+asyncpg://u:{SENTINEL}@db.internal:5432/app",
        f"postgresql+psycopg://u:{SENTINEL}@/app",
    ],
)
def test_error_text_contains_neither_the_password_nor_the_host(url: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(database_url=url)
    text = str(caught.value)
    assert SENTINEL not in text
    assert "db.internal" not in text
    assert url not in text


def test_required_url_error_names_the_variable() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, database_url=None)  # type: ignore[arg-type]
    assert "database_url" in str(caught.value).lower()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:@db.internal:5432/app",
        "postgresql+psycopg://db.internal:5432/app",
        f"postgresql+psycopg://u:REPLACE_WITH_{SENTINEL}@db.internal:5432/app",
    ],
)
def test_prod_password_errors_do_not_echo_the_url(url: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(app_env="prod", database_url=url)
    text = str(caught.value)
    assert "db.internal" not in text
    assert SENTINEL not in text
    assert "DATABASE_URL" in text


@pytest.mark.parametrize("app_env", ["dev", "test"])
def test_non_prod_environments_accept_a_missing_password(app_env: str) -> None:
    make_settings(app_env=app_env, database_url="postgresql+psycopg://u@127.0.0.1:5432/app")


def test_prod_only_rejects_the_documented_placeholders() -> None:
    """Only `change-me` exactly and the `REPLACE_WITH` prefix are placeholders."""
    make_settings(
        app_env="prod",
        database_url="postgresql+psycopg://u:change-me-not-really-x@db:5432/app?sslmode=require",
    )


@pytest.mark.parametrize("password", ["Change-Me", "CHANGE-ME", "replace_with_x_long_enough"])
def test_prod_placeholders_match_in_any_case(password: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(
            app_env="prod",
            database_url=f"postgresql+psycopg://u:{password}@db:5432/app?sslmode=require",
        )
    assert "placeholder password" in str(caught.value)
    assert password not in str(caught.value)


def test_prod_rejects_a_short_password() -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(
            app_env="prod",
            database_url="postgresql+psycopg://u:zq7short@db:5432/app?sslmode=require",
        )
    assert "at least 16 characters" in str(caught.value)
    assert "zq7short" not in str(caught.value)


@pytest.mark.parametrize("query", ["", "?sslmode=disable", "?sslmode=prefer", "?sslmode=allow"])
def test_prod_requires_tls(query: str) -> None:
    with pytest.raises(ValidationError) as caught:
        make_settings(
            app_env="prod", database_url=f"postgresql+psycopg://u:{SENTINEL}@db:5432/app{query}"
        )
    assert "sslmode=require, verify-ca or verify-full" in str(caught.value)
    assert SENTINEL not in str(caught.value)


@pytest.mark.parametrize("mode", ["require", "verify-ca", "verify-full"])
def test_prod_accepts_each_tls_mode(mode: str) -> None:
    make_settings(
        app_env="prod", database_url=f"postgresql+psycopg://u:{SENTINEL}@db:5432/app?sslmode={mode}"
    )


@pytest.mark.parametrize("app_env", ["dev", "test"])
def test_non_prod_needs_neither_tls_nor_a_long_password(app_env: str) -> None:
    make_settings(app_env=app_env, database_url="postgresql+psycopg://u:pw@127.0.0.1:5432/app")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("db_pool_size", 1),
        ("db_pool_size", 20),
        ("db_max_overflow", 0),
        ("db_max_overflow", 20),
        ("db_pool_timeout_seconds", 1),
        ("db_pool_timeout_seconds", 60),
        ("db_pool_recycle_seconds", 60),
        ("db_pool_recycle_seconds", 7200),
    ],
)
def test_pool_settings_at_their_limits_are_accepted(field: str, value: int) -> None:
    assert getattr(make_settings(**{field: value}), field) == value


@pytest.mark.parametrize("variable", POOL_VARIABLES)
def test_pool_settings_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "7" if variable != "DB_POOL_RECYCLE_SECONDS" else "100")
    settings = Settings(_env_file=None)
    expected = 100 if variable == "DB_POOL_RECYCLE_SECONDS" else 7
    assert getattr(settings, variable.lower()) == expected


def test_pool_setting_out_of_range_in_the_environment_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "21")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_example_has_no_password_values() -> None:
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    assert "POSTGRES_PASSWORD=" in lines
    assert "APP_DB_PASSWORD=" in lines
    assert "REDIS_PASSWORD=" in lines


def test_env_example_database_settings_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    url = settings.database_url.get_secret_value()
    assert "REPLACE_WITH_APP_DB_PASSWORD" in url
    # The app connects as the non-superuser role, not the bootstrap POSTGRES_USER.
    assert url.startswith("postgresql+psycopg://applyiq_app:")
    assert settings.db_pool_recycle_seconds == 1800


def test_env_example_pool_values_match_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    defaults = make_settings()
    for field in ("db_pool_size", "db_max_overflow", "db_pool_timeout_seconds"):
        assert getattr(settings, field) == getattr(defaults, field)


def test_env_example_lists_every_database_variable() -> None:
    names = {
        line.split("=", 1)[0]
        for line in (REPO_ROOT / ".env.example").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    }
    required = {
        "POSTGRES_USER",
        "POSTGRES_DB",
        "POSTGRES_PORT",
        "POSTGRES_PASSWORD",
        "APP_DB_USER",
        "APP_DB_PASSWORD",
        "DATABASE_URL",
        "REDIS_PORT",
        "REDIS_PASSWORD",
        "REDIS_URL",
        *POOL_VARIABLES,
    }
    assert required <= names
