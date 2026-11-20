"""Build `Settings` in tests without reading the developer's `.env` or environment."""

from typing import Any

from app.core.config import Settings

# Never connected to: tests that need a real database use tests/db_support.py.
# Shaped to pass the prod checks too (16+ character password, sslmode=require).
DUMMY_DATABASE_URL = (
    "postgresql+psycopg://applyiq:unused-dummy-password@127.0.0.1:1/applyiq_unused?sslmode=require"
)


def make_settings(**overrides: Any) -> Settings:
    """Settings from defaults plus `overrides`, with a dummy database URL."""
    values: dict[str, Any] = {"database_url": DUMMY_DATABASE_URL, **overrides}
    return Settings(_env_file=None, **values)
