"""Health route, request id, access log and docs switch (AC4, AC5, AC6, AC10)."""

import io
import uuid
from typing import Literal

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from app.api.routers import API_V1_PREFIX
from app.core.config import Settings
from app.core.logging import ALLOWED_KEYS
from tests.conftest import AppFactory, parse_log_lines


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_every_response_has_a_uuid_request_id(client: httpx.AsyncClient) -> None:
    first = await client.get("/api/v1/health")
    second = await client.get("/api/v1/health")
    missing = await client.get("/api/v1/nothing-here")
    for response in (first, second, missing):
        uuid.UUID(response.headers["X-Request-ID"])
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_client_supplied_request_id_is_not_echoed(
    client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "attacker-chosen"})
    assert response.headers["X-Request-ID"] != "attacker-chosen"
    assert "attacker-chosen" not in log_stream.getvalue()


async def test_request_logs_one_allow_listed_line(
    client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    response = await client.get("/api/v1/health")
    [entry] = parse_log_lines(log_stream)
    assert entry["event"] == "request_completed"
    assert set(entry) <= ALLOWED_KEYS
    assert entry["request_id"] == response.headers["X-Request-ID"]
    assert entry["route"] == "/api/v1/health"
    assert entry["method"] == "GET"
    assert entry["status_code"] == 200
    assert entry["duration_ms"] >= 0


async def test_route_that_already_has_the_prefix_is_not_prefixed_twice(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    """A route registered on the app with the full path must not get the prefix twice."""

    async def direct() -> dict[str, str]:
        return {}

    application.add_api_route(f"{API_V1_PREFIX}/direct", direct)
    await client.get(f"{API_V1_PREFIX}/direct")
    [entry] = parse_log_lines(log_stream)
    assert entry["route"] == "/api/v1/direct"


async def test_unknown_path_is_logged_as_unmatched(
    client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    response = await client.get("/api/v1/private-path?token=abc123")
    assert response.status_code == 404
    [entry] = parse_log_lines(log_stream)
    assert entry["route"] == "unmatched"
    assert entry["status_code"] == 404
    assert "private-path" not in log_stream.getvalue()
    assert "abc123" not in log_stream.getvalue()


async def test_unhandled_error_logs_request_failed(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    router = APIRouter(prefix=API_V1_PREFIX)

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("resume says jane@example.com")

    application.include_router(router)

    response = await client.get("/api/v1/boom")
    assert response.status_code == 500
    entries = parse_log_lines(log_stream)
    [failed] = [entry for entry in entries if entry["event"] == "request_failed"]
    assert failed["error_type"] == "RuntimeError"
    assert failed["route"] == "/api/v1/boom"
    assert set(failed) <= ALLOWED_KEYS
    assert "jane@example.com" not in log_stream.getvalue()


@pytest.mark.parametrize(
    ("app_env", "expected_status"), [("dev", 200), ("test", 200), ("prod", 404)]
)
async def test_docs_are_off_in_prod(
    make_app: AppFactory, app_env: Literal["dev", "test", "prod"], expected_status: int
) -> None:
    app_settings = Settings(_env_file=None, app_env=app_env)
    transport = httpx.ASGITransport(app=make_app(app_settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        docs = await http_client.get("/api/v1/docs")
        schema = await http_client.get("/api/v1/openapi.json")
    assert docs.status_code == expected_status
    assert schema.status_code == expected_status
