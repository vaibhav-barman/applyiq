"""Logging tests (AC7, AC8)."""

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
import structlog

from app.core.logging import ALLOWED_KEYS, configure_logging


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    """Configure logging onto an in-memory stream and clean up afterwards."""
    buffer = io.StringIO()
    configure_logging("INFO", stream=buffer)
    yield buffer
    structlog.contextvars.clear_contextvars()


def lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_emits_one_json_line_with_standard_fields(stream: io.StringIO) -> None:
    structlog.get_logger("tests").info("something_happened", status_code=200)
    [entry] = lines(stream)
    assert entry["event"] == "something_happened"
    assert entry["level"] == "info"
    assert entry["logger"] == "tests"
    assert entry["status_code"] == 200
    assert entry["timestamp"].endswith("Z")


def test_unlisted_key_is_dropped(stream: io.StringIO) -> None:
    structlog.get_logger().info("something_happened", resume_text="secret", status_code=200)
    [entry] = lines(stream)
    assert "resume_text" not in entry
    assert entry["status_code"] == 200
    assert set(entry) <= ALLOWED_KEYS


def test_exception_info_is_not_emitted(stream: io.StringIO) -> None:
    try:
        raise ValueError("resume says jane@example.com")
    except ValueError:
        structlog.get_logger().exception("something_failed", error_type="ValueError")
    [entry] = lines(stream)
    assert "exc_info" not in entry
    assert "Traceback" not in stream.getvalue()
    assert "jane@example.com" not in stream.getvalue()


@pytest.mark.parametrize("bad_event", ["User jane logged in", "Upper", "1starts_with_digit", ""])
def test_bad_event_name_is_replaced(stream: io.StringIO, bad_event: str) -> None:
    structlog.get_logger().info(bad_event)
    [entry] = lines(stream)
    assert entry["event"] == "invalid_event_name"


def test_non_string_event_is_replaced(stream: io.StringIO) -> None:
    structlog.get_logger().info(12345)
    [entry] = lines(stream)
    assert entry["event"] == "invalid_event_name"


@pytest.mark.parametrize(
    "text",
    [
        "jane.doe+jobs@example.co.uk",
        "+1 555 123 4567",
        "(555) 123-4567",
        "555-123-4567",
        "9876543210",
    ],
)
def test_email_and_phone_are_redacted(stream: io.StringIO, text: str) -> None:
    structlog.get_logger().info("something_happened", error_code=f"see {text} now")
    [entry] = lines(stream)
    assert entry["error_code"] == "see [redacted] now"


def test_timestamp_and_request_id_are_not_redacted(stream: io.StringIO) -> None:
    request_id = "12345678-1234-4123-8123-123456789012"
    structlog.contextvars.bind_contextvars(request_id=request_id)
    structlog.get_logger().info("something_happened")
    [entry] = lines(stream)
    assert entry["request_id"] == request_id
    assert "[redacted]" not in entry["timestamp"]


def test_bound_request_id_is_present(stream: io.StringIO) -> None:
    structlog.contextvars.bind_contextvars(request_id="abc")
    structlog.get_logger().info("something_happened")
    [entry] = lines(stream)
    assert entry["request_id"] == "abc"


def test_foreign_records_are_json_and_redacted(stream: io.StringIO) -> None:
    logging.getLogger("some.library").warning("failed for jane@example.com")
    [entry] = lines(stream)
    assert entry["event"] == "failed for [redacted]"
    assert entry["level"] == "warning"
    assert entry["logger"] == "some.library"


def test_foreign_exception_has_no_traceback(stream: io.StringIO) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("some.library").exception("library_failed")
    assert "Traceback" not in stream.getvalue()


def test_uvicorn_access_log_is_silenced(stream: io.StringIO) -> None:
    logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /secret?q=1 HTTP/1.1" 200')
    assert stream.getvalue() == ""


def test_configuring_twice_does_not_duplicate_lines(stream: io.StringIO) -> None:
    configure_logging("INFO", stream=stream)
    structlog.get_logger().info("something_happened")
    assert len(lines(stream)) == 1


@pytest.mark.parametrize("name", ["httpx", "httpcore"])
def test_http_client_libraries_do_not_log_urls(stream: io.StringIO, name: str) -> None:
    logging.getLogger(name).info('HTTP Request: GET https://api.example.com/?key=secret "200 OK"')
    assert stream.getvalue() == ""


def test_level_filters_records(stream: io.StringIO) -> None:
    structlog.get_logger().debug("too_quiet")
    assert stream.getvalue() == ""
