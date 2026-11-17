"""Request id and access-log edge cases through the whole app (AC5, AC6, AC9, AC10)."""

import asyncio
import io
import uuid
from typing import Literal

import httpx
import pytest
import structlog
from fastapi import FastAPI, Response

from app.api.routers import API_V1_PREFIX
from app.core.config import Settings
from app.core.logging import ALLOWED_KEYS
from tests.conftest import AppFactory, parse_log_lines

CLIENT_REQUEST_ID = {"X-Request-ID": "attacker-chosen"}


@pytest.mark.parametrize("method", ["HEAD", "POST", "PUT", "DELETE", "PATCH"])
async def test_wrong_method_on_health_is_405_and_logs_the_route_template(
    client: httpx.AsyncClient, log_stream: io.StringIO, method: str
) -> None:
    response = await client.request(method, "/api/v1/health?token=abc123")
    assert response.status_code == 405
    [entry] = parse_log_lines(log_stream)
    assert entry["event"] == "request_completed"
    assert entry["method"] == method
    assert entry["route"] == "/api/v1/health"
    assert entry["status_code"] == 405
    assert entry["request_id"] == response.headers["X-Request-ID"]
    assert "abc123" not in log_stream.getvalue()


async def test_query_string_never_reaches_the_log_for_a_matched_route(
    client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    response = await client.get("/api/v1/health?token=abc123&q=jane%40example.com")
    assert response.status_code == 200
    [entry] = parse_log_lines(log_stream)
    assert entry["route"] == "/api/v1/health"
    assert set(entry) <= ALLOWED_KEYS
    assert "abc123" not in log_stream.getvalue()
    assert "token" not in log_stream.getvalue()
    assert "jane" not in log_stream.getvalue()


@pytest.mark.parametrize("path", ["/", "/api/v1/health/extra", "/api/v2/health", "/api/v1/secret"])
async def test_404_body_leaks_nothing_and_has_a_single_request_id(
    client: httpx.AsyncClient, log_stream: io.StringIO, path: str
) -> None:
    response = await client.get(path, headers=CLIENT_REQUEST_ID)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert len(response.headers.get_list("X-Request-ID")) == 1
    [entry] = parse_log_lines(log_stream)
    assert entry["route"] == "unmatched"
    assert entry["status_code"] == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/v1/health"), ("HEAD", "/api/v1/health"), ("GET", "/api/v1/missing")],
)
async def test_request_id_header_appears_exactly_once(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path, headers=CLIENT_REQUEST_ID)
    values = response.headers.get_list("X-Request-ID")
    assert len(values) == 1
    uuid.UUID(values[0])


async def test_a_handler_cannot_set_a_different_request_id(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    async def sets_its_own_id(response: Response) -> dict[str, str]:
        response.headers["X-Request-ID"] = "handler-chosen"
        return {}

    application.add_api_route(f"{API_V1_PREFIX}/own-id", sets_its_own_id)
    response = await client.get(f"{API_V1_PREFIX}/own-id")
    assert response.headers.get_list("X-Request-ID") == [
        parse_log_lines(log_stream)[0]["request_id"]
    ]


async def test_concurrent_requests_each_log_their_own_request_id(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    """Handlers that finish out of order must still log the id of their own request."""

    def add_route(name: str, delay: float) -> None:
        async def handler() -> dict[str, str]:
            await asyncio.sleep(delay)
            structlog.get_logger("tests").info("handler_ran", error_code=name)
            return {}

        application.add_api_route(f"{API_V1_PREFIX}/{name}", handler)

    add_route("slow", 0.05)
    add_route("fast", 0.0)

    names = ["slow", "fast", "slow", "fast", "slow", "fast"]
    responses = await asyncio.gather(*(client.get(f"{API_V1_PREFIX}/{name}") for name in names))
    header_ids = [response.headers["X-Request-ID"] for response in responses]
    assert len(set(header_ids)) == len(names)

    entries = parse_log_lines(log_stream)
    handler_lines = {
        e["request_id"]: e["error_code"] for e in entries if e["event"] == "handler_ran"
    }
    completed = {e["request_id"]: e["route"] for e in entries if e["event"] == "request_completed"}
    assert set(handler_lines) == set(header_ids)
    assert set(completed) == set(header_ids)
    for request_id, route in completed.items():
        assert route == f"{API_V1_PREFIX}/{handler_lines[request_id]}"
    for header_id, name in zip(header_ids, names, strict=True):
        assert handler_lines[header_id] == name


async def test_context_from_one_request_does_not_leak_into_the_next(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    async def binds_context() -> dict[str, str]:
        structlog.contextvars.bind_contextvars(error_code="from_request_one")
        return {}

    application.add_api_route(f"{API_V1_PREFIX}/binds", binds_context)
    first = await client.get(f"{API_V1_PREFIX}/binds")
    second = await client.get("/api/v1/health")

    first_entry, second_entry = parse_log_lines(log_stream)
    assert first_entry["error_code"] == "from_request_one"
    assert first_entry["request_id"] == first.headers["X-Request-ID"]
    assert second_entry["request_id"] == second.headers["X-Request-ID"]
    assert second_entry["request_id"] != first_entry["request_id"]
    assert "error_code" not in second_entry


async def test_failed_request_does_not_leak_its_id_into_the_next_line(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    async def boom() -> None:
        raise RuntimeError("boom")

    application.add_api_route(f"{API_V1_PREFIX}/boom", boom)
    await client.get(f"{API_V1_PREFIX}/boom")
    ok = await client.get("/api/v1/health")

    entries = parse_log_lines(log_stream)
    failed = next(e for e in entries if e["event"] == "request_failed")
    completed = [e for e in entries if e["event"] == "request_completed"]
    assert [e["request_id"] for e in completed] == [ok.headers["X-Request-ID"]]
    assert failed["request_id"] != completed[0]["request_id"]


@pytest.mark.parametrize(
    ("level", "expected_lines"), [("DEBUG", 1), ("INFO", 1), ("WARNING", 0), ("ERROR", 0)]
)
async def test_log_level_setting_filters_access_lines(
    make_app: AppFactory,
    log_stream: io.StringIO,
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"],
    expected_lines: int,
) -> None:
    app_settings = Settings(_env_file=None, app_env="test", log_level=level)
    transport = httpx.ASGITransport(app=make_app(app_settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get("/api/v1/health")
    assert response.status_code == 200
    assert len(parse_log_lines(log_stream)) == expected_lines


async def test_error_level_still_logs_an_unhandled_failure(
    make_app: AppFactory, log_stream: io.StringIO
) -> None:
    application = make_app(Settings(_env_file=None, app_env="test", log_level="ERROR"))

    async def boom() -> None:
        raise RuntimeError("boom")

    application.add_api_route(f"{API_V1_PREFIX}/boom", boom)
    transport = httpx.ASGITransport(app=application, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(f"{API_V1_PREFIX}/boom")
    assert response.status_code == 500
    [entry] = parse_log_lines(log_stream)
    assert entry["event"] == "request_failed"
    assert entry["level"] == "error"


async def test_prod_has_no_docs_route_and_logs_it_as_unmatched(
    make_app: AppFactory, log_stream: io.StringIO
) -> None:
    application = make_app(Settings(_env_file=None, app_env="prod"))
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get("/api/v1/docs")
    assert response.status_code == 404
    [entry] = parse_log_lines(log_stream)
    assert entry["route"] == "unmatched"
