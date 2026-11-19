"""Shared fixtures: settings, an app with its log output captured, an HTTP client,
and the test database (tests marked `db`)."""

import asyncio
import io
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import structlog
from fastapi import FastAPI
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Settings
from app.core.logging import configure_logging
from app.factory import create_app
from tests.db_support import (
    DatabaseUnavailableError,
    base_database_url,
    derived_url,
    ensure_database,
    make_test_engine,
)
from tests.settings_support import make_settings

AppFactory = Callable[[Settings], FastAPI]

REQUIRE_SERVICES = "--require-services"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        REQUIRE_SERVICES,
        action="store_true",
        help="fail, instead of skip, tests whose services (Postgres) are unreachable; CI sets it",
    )


def services_unavailable(config: pytest.Config, reason: str) -> None:
    """Skip the test, or fail it when the run requires services."""
    if config.getoption(REQUIRE_SERVICES):
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def _test_database() -> URL | DatabaseUnavailableError:
    """Find and create `<name>_test` once per run; remember the failure instead of raising.

    A sync session fixture, so `asyncio.run` does not clash with a test's event loop.
    """
    try:
        url = derived_url(base_database_url())
        asyncio.run(ensure_database(url))
    except DatabaseUnavailableError as error:
        return error
    return url


@pytest.fixture
def test_database_url(
    request: pytest.FixtureRequest, _test_database: URL | DatabaseUnavailableError
) -> URL:
    """The test database URL, or a skip (a failure with --require-services)."""
    if isinstance(_test_database, DatabaseUnavailableError):
        services_unavailable(request.config, str(_test_database))
    assert isinstance(_test_database, URL)
    return _test_database


@pytest.fixture
async def db_engine(test_database_url: URL) -> AsyncIterator[AsyncEngine]:
    engine = make_test_engine(test_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside one outer transaction that is rolled back after the test.

    `create_savepoint` turns the code's own commits and rollbacks into savepoints,
    so nothing a test writes survives it.
    """
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
def settings() -> Settings:
    """Test settings that never read the developer's `.env` file."""
    return make_settings(app_env="test")


@pytest.fixture
def log_stream() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def make_app(log_stream: io.StringIO) -> AppFactory:
    """Build an app from the given settings, with log lines written to `log_stream`."""

    def build(app_settings: Settings) -> FastAPI:
        application = create_app(app_settings)
        # create_app logs to stdout; point the same handler at the capture buffer.
        configure_logging(app_settings.log_level, stream=log_stream)
        return application

    return build


@pytest.fixture
def application(settings: Settings, make_app: AppFactory) -> FastAPI:
    return make_app(settings)


@pytest.fixture
async def client(application: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    # raise_app_exceptions=False returns a 500 response, like a real server would,
    # instead of re-raising an unhandled error inside the test.
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    # ASGITransport does not run the lifespan, so enter it here (engine setup and disposal).
    async with application.router.lifespan_context(application):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    structlog.contextvars.clear_contextvars()


def parse_log_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]
