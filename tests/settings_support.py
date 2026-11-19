"""Build `Settings` in tests without reading the developer's `.env` or environment."""

from typing import Any

from app.core.config import Settings

# Never connected to: tests that need a real database use tests/db_support.py.
DUMMY_DATABASE_URL = "postgresql+psycopg://applyiq:unused@127.0.0.1:1/applyiq_unused"


def make_settings(**overrides: Any) -> Settings:
    """Settings from defaults plus `overrides`, with a dummy database URL."""
    values: dict[str, Any] = {"database_url": DUMMY_DATABASE_URL, **overrides}
    return Settings(_env_file=None, **values)
