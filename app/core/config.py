"""Application settings. The only place environment variables are read."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

_DATABASE_DRIVER = "postgresql+psycopg"
_PLACEHOLDER_EXACT = "change-me"
_PLACEHOLDER_PREFIX = "replace_with"
_PROD_MIN_PASSWORD_LENGTH = 16
# SECURITY.md section 4: Postgres over TLS in production.
_PROD_SSL_MODES = frozenset({"require", "verify-ca", "verify-full"})


class Settings(BaseSettings):
    """Typed settings loaded from the environment and an optional `.env` file.

    `extra="ignore"` is needed because pydantic-settings defaults to "forbid"
    and `.env` already lists variables that no code reads yet.
    `hide_input_in_errors=True` keeps secret values out of validation errors.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: SecretStr
    db_pool_size: int = Field(default=5, ge=1, le=20)
    db_max_overflow: int = Field(default=5, ge=0, le=20)
    db_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60, le=7200)

    @model_validator(mode="after")
    def _check_database_url(self) -> Self:
        """Check the URL's shape. A model validator, because the prod rule needs `app_env`."""
        url = _parse_database_url(self.database_url)
        if url.drivername != _DATABASE_DRIVER:
            raise ValueError(f"DATABASE_URL must start with {_DATABASE_DRIVER}://")
        if not url.host:
            raise ValueError("DATABASE_URL must include a host")
        if not url.database:
            raise ValueError("DATABASE_URL must include a database name")
        if self.app_env == "prod":
            _check_prod_password(url)
            _check_prod_tls(url)
        return self


def _parse_database_url(value: SecretStr) -> URL:
    """Parse the URL, replacing SQLAlchemy's error so the value never appears in it."""
    try:
        return make_url(value.get_secret_value())
    except Exception:
        raise ValueError("DATABASE_URL could not be parsed as a database URL") from None


def _check_prod_password(url: URL) -> None:
    password = url.password
    if not password:
        raise ValueError("DATABASE_URL must include a password when APP_ENV=prod")
    lowered = password.lower()
    if lowered == _PLACEHOLDER_EXACT or lowered.startswith(_PLACEHOLDER_PREFIX):
        raise ValueError("DATABASE_URL must not use a placeholder password when APP_ENV=prod")
    if len(password) < _PROD_MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"DATABASE_URL password must be at least {_PROD_MIN_PASSWORD_LENGTH} characters "
            "when APP_ENV=prod"
        )


def _check_prod_tls(url: URL) -> None:
    ssl_mode = url.query.get("sslmode")
    if ssl_mode not in _PROD_SSL_MODES:
        raise ValueError(
            "DATABASE_URL must set sslmode=require, verify-ca or verify-full when APP_ENV=prod"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, built once."""
    return Settings()
