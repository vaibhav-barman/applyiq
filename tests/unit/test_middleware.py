"""RequestContextMiddleware behaviour that does not need the whole app (AC5, AC6)."""

import io
from collections.abc import Iterator

import pytest
import structlog
from starlette.types import Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from tests.conftest import AppFactory, parse_log_lines


@pytest.fixture(autouse=True)
def clean_contextvars() -> Iterator[None]:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


async def no_receive() -> Message:
    return {"type": "http.disconnect"}


async def no_send(message: Message) -> None:
    return None


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
async def test_non_http_scope_is_passed_through_untouched(
    log_stream: io.StringIO, scope_type: str
) -> None:
    configure_logging("INFO", stream=log_stream)
    structlog.contextvars.bind_contextvars(request_id="bound-before")
    seen: list[Scope] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope)

    scope: Scope = {"type": scope_type}
    await RequestContextMiddleware(inner)(scope, no_receive, no_send)

    assert seen == [scope]
    # No fresh id was bound and the earlier context was not cleared.
    assert structlog.contextvars.get_contextvars() == {"request_id": "bound-before"}
    assert log_stream.getvalue() == ""
    assert "headers" not in scope


async def test_lifespan_through_the_whole_app_logs_nothing_and_sends_no_request_id(
    make_app: AppFactory, settings: Settings, log_stream: io.StringIO
) -> None:
    application = make_app(settings)
    incoming: list[Message] = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    sent: list[Message] = []

    async def receive() -> Message:
        return incoming.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    await application({"type": "lifespan"}, receive, send)

    assert [message["type"] for message in sent] == [
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]
    assert not any("request_completed" in line for line in log_stream.getvalue().splitlines())
    assert structlog.contextvars.get_contextvars() == {}


async def test_http_scope_binds_a_fresh_id_and_clears_earlier_context(
    log_stream: io.StringIO,
) -> None:
    configure_logging("INFO", stream=log_stream)
    structlog.contextvars.bind_contextvars(request_id="stale", error_code="stale_code")

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    scope: Scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}
    await RequestContextMiddleware(inner)(scope, no_receive, no_send)

    [entry] = parse_log_lines(log_stream)
    assert entry["event"] == "request_completed"
    assert entry["request_id"] != "stale"
    assert "error_code" not in entry
    assert entry["status_code"] == 204
    assert entry["route"] == "unmatched"


async def test_failure_logs_class_name_only_and_reraises(log_stream: io.StringIO) -> None:
    configure_logging("INFO", stream=log_stream)

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        raise ValueError("candidate phone 555 123 4567")

    scope: Scope = {"type": "http", "method": "POST", "path": "/secret", "headers": []}
    with pytest.raises(ValueError, match="candidate phone"):
        await RequestContextMiddleware(inner)(scope, no_receive, no_send)

    [entry] = parse_log_lines(log_stream)
    assert entry["event"] == "request_failed"
    assert entry["error_type"] == "ValueError"
    assert entry["route"] == "unmatched"
    assert "status_code" not in entry
    assert "555" not in log_stream.getvalue()
    assert "/secret" not in log_stream.getvalue()
