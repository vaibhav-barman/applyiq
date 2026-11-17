"""The logged `route` is the full route template and never holds a concrete value (AC6)."""

import io
import re

import httpx
from fastapi import APIRouter, FastAPI

from app.api.routers import API_V1_PREFIX
from tests.conftest import parse_log_lines

SENTINEL = "SENTINEL"
HTTP_METHODS = {"get", "put", "post", "delete", "patch", "head", "options"}


async def note(note_id: str) -> dict[str, str]:
    return {}


async def note_in_application(application_id: str, note_id: str) -> dict[str, str]:
    return {}


async def file(p: str) -> dict[str, str]:
    return {}


async def ping() -> dict[str, str]:
    return {}


def add_nested_routes(application: FastAPI) -> None:
    """Routers nested two levels, with prefixes, as later specs will add them."""
    notes = APIRouter(prefix="/notes")
    notes.add_api_route("/{note_id}", note, methods=["GET"])
    applications = APIRouter(prefix="/applications")
    applications.include_router(notes)
    parent = APIRouter(prefix=API_V1_PREFIX)
    parent.include_router(applications)
    application.include_router(parent)

    files = APIRouter()
    files.add_api_route("/files/{p:path}", file, methods=["GET"])
    application.include_router(files, prefix=f"{API_V1_PREFIX}/storage")

    pings = APIRouter()
    pings.add_api_route("/ping", ping, methods=["GET"])
    application.include_router(pings, prefix=f"{API_V1_PREFIX}/jobs")


def add_route_with_parameter_in_prefix(application: FastAPI) -> None:
    inner = APIRouter()
    inner.add_api_route("/notes/{note_id}", note_in_application, methods=["GET"])
    parent = APIRouter(prefix=API_V1_PREFIX)
    parent.include_router(inner, prefix="/applications/{application_id}")
    application.include_router(parent)


async def logged_route(client: httpx.AsyncClient, log_stream: io.StringIO, url: str) -> str:
    log_stream.seek(0)
    log_stream.truncate(0)
    await client.get(url)
    [entry] = parse_log_lines(log_stream)
    return str(entry["route"])


async def logged_routes_by_operation(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> dict[str, tuple[str, str]]:
    """For each OpenAPI operation, request it with sentinel values: (template, logged)."""
    application.openapi_schema = None  # routes were added after the schema was built
    result: dict[str, tuple[str, str]] = {}
    for template, operations in application.openapi()["paths"].items():
        url = re.sub(r"\{(\w+)\}", lambda match: f"{SENTINEL}-{match[1]}", template)
        for method in operations.keys() & HTTP_METHODS:
            log_stream.seek(0)
            log_stream.truncate(0)
            await client.request(method.upper(), url)
            [entry] = parse_log_lines(log_stream)
            result[f"{method.upper()} {template}"] = (template, str(entry["route"]))
    return result


async def test_every_route_logs_its_openapi_template(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    """This is the guard for every router a later spec adds: no sentinel, same template."""
    add_nested_routes(application)
    results = await logged_routes_by_operation(application, client, log_stream)
    assert "GET /api/v1/health" in results
    assert "GET /api/v1/applications/notes/{note_id}" in results
    for operation, (template, logged) in results.items():
        assert logged == template, operation
        assert SENTINEL not in logged


async def test_the_real_app_alone_passes_the_openapi_guard(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    results = await logged_routes_by_operation(application, client, log_stream)
    assert results
    assert all(template == logged for template, logged in results.values())


async def test_nested_router_keeps_every_prefix(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    add_nested_routes(application)
    route = await logged_route(client, log_stream, "/api/v1/applications/notes/N9")
    assert route == "/api/v1/applications/notes/{note_id}"
    assert "N9" not in log_stream.getvalue()


async def test_include_router_prefix_is_kept(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    add_nested_routes(application)
    assert await logged_route(client, log_stream, "/api/v1/jobs/ping") == "/api/v1/jobs/ping"


async def test_path_converter_logs_without_the_converter_and_without_the_value(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    add_nested_routes(application)
    route = await logged_route(client, log_stream, "/api/v1/storage/files/a/files/secret.pdf")
    assert route == "/api/v1/storage/files/{p}"
    assert "secret.pdf" not in log_stream.getvalue()


async def test_route_registered_on_the_app_without_the_prefix_is_not_given_one(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    application.add_api_route("/health", ping, methods=["GET"])
    assert await logged_route(client, log_stream, "/health") == "/health"


async def test_parameter_in_a_prefix_never_reaches_the_log(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    """The fallback: only the route's own template is logged, with no concrete value."""
    add_route_with_parameter_in_prefix(application)
    url = "/api/v1/applications/SECRET-123/notes/N9"
    route = await logged_route(client, log_stream, url)
    assert route == "/notes/{note_id}"
    assert "SECRET-123" not in log_stream.getvalue()
    assert "N9" not in log_stream.getvalue()


async def test_openapi_guard_fails_for_a_parameter_in_a_prefix(
    application: FastAPI, client: httpx.AsyncClient, log_stream: io.StringIO
) -> None:
    """Proves the guard works: such a route is safe but does not match its template."""
    add_route_with_parameter_in_prefix(application)
    results = await logged_routes_by_operation(application, client, log_stream)
    template, logged = results["GET /api/v1/applications/{application_id}/notes/{note_id}"]
    assert logged != template
    assert SENTINEL not in logged
