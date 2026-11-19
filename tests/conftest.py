"""Shared fixtures: settings, an app with its log output captured, and an HTTP client."""

import io
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import structlog
from fastapi import FastAPI

from app.core.config import Settings
from app.core.logging import configure_logging
from app.factory import create_app
from tests.settings_support import make_settings

AppFactory = Callable[[Settings], FastAPI]


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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    structlog.contextvars.clear_contextvars()


def parse_log_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]
