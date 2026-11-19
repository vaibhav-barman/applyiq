"""Test database support: which database tests use, creating it, and reaching it.

This is the one place tests read the real environment or `.env`: only to learn
where Postgres is. Tests always run against `<name>_test`, never the dev database.
"""

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings

START_HINT = "start it with: docker compose up -d postgres"
TEST_SUFFIX = "_test"
# Tests create and drop databases, so they only ever touch a server on this machine.
# GitHub Actions service containers are reached on localhost too.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_CONNECT_TIMEOUT_SECONDS = 3


class DatabaseUnavailableError(Exception):
    """Postgres cannot be used for tests. The message is safe to print."""


def base_database_url() -> URL:
    """The configured `DATABASE_URL`, from the environment or `.env`."""
    try:
        settings = Settings()
    except ValidationError:
        raise DatabaseUnavailableError(
            f"DATABASE_URL is missing or invalid; set it in .env and {START_HINT}"
        ) from None
    return make_url(settings.database_url.get_secret_value())


def derived_url(base: URL, suffix: str = TEST_SUFFIX) -> URL:
    """The same server and credentials, with `suffix` added to the database name."""
    return base.set(database=f"{base.database}{suffix}")


def require_test_database(url: URL) -> None:
    """Refuse a database not named `*_test`, or on a server not on this machine.

    Either could hold real data, and the fixtures create and drop databases.
    """
    if not (url.database or "").endswith(TEST_SUFFIX):
        raise RuntimeError("refusing to run tests against a database not named *_test")
    if url.host not in LOCAL_HOSTS:
        raise RuntimeError("refusing to run tests against a database server not on localhost")


def make_test_engine(url: URL) -> AsyncEngine:
    """An engine for one test: no pool shared across pytest-asyncio's event loops."""
    require_test_database(url)
    return create_async_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "options": "-c timezone=utc",
            "connect_timeout": _CONNECT_TIMEOUT_SECONDS,
        },
    )


async def ensure_database(url: URL, *, recreate: bool = False) -> None:
    """Create the database if missing (or drop and recreate it) via the maintenance db."""
    require_test_database(url)
    admin = create_async_engine(
        url.set(database="postgres"),
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": _CONNECT_TIMEOUT_SECONDS},
    )
    name = admin.dialect.identifier_preparer.quote(url.database or "")
    try:
        async with admin.connect() as connection:
            if recreate:
                await connection.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            )
            if not exists:
                await connection.execute(text(f"CREATE DATABASE {name}"))
    except DatabaseUnavailableError:
        raise
    except Exception as error:
        raise DatabaseUnavailableError(
            f"Postgres is unreachable at {url.host}:{url.port} ({type(error).__name__}); "
            f"{START_HINT}"
        ) from None
    finally:
        await admin.dispose()
