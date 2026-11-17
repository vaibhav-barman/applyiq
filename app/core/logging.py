"""Structured JSON logging with an allow-list of keys (SECURITY.md section 6).

Our own loggers use structlog. Records from other libraries (uvicorn, later
SQLAlchemy) reach the same JSON handler through the standard library.

To log a new field, add its name to ALLOWED_KEYS. That one frozenset is where a
reviewer checks what can leave the system in a log line.
"""

import logging
import re
import sys
from typing import TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "event",
        "level",
        "timestamp",
        "logger",
        "request_id",
        "method",
        "route",
        "status_code",
        "duration_ms",
        "error_code",
        "error_type",
        "app_env",
    }
)

# Keys the server generates itself, never from user input. The phone pattern could
# match a run of digits inside an ISO timestamp or a UUID, so these are not redacted.
_GENERATED_KEYS: frozenset[str] = frozenset({"timestamp", "request_id"})

_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Nine or more digits, optionally separated by spaces, dots, dashes or brackets.
_PHONE = re.compile(r"(?<!\w)\+?\(?\d(?:[\s().-]{0,2}\d){8,}(?!\w)")
_REDACTED = "[redacted]"

# Loggers that uvicorn configures itself. They are re-routed to the root handler.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error")
_UVICORN_ACCESS = "uvicorn.access"

_installed_handler: logging.Handler | None = None


def check_event_name(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Replace an event that is not a snake_case identifier.

    This stops an f-string that contains user data from being used as the message.
    """
    event = event_dict.get("event")
    if not isinstance(event, str) or not _EVENT_NAME.match(event):
        event_dict["event"] = "invalid_event_name"
    return event_dict


def drop_unlisted_keys(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Remove every key that is not in ALLOWED_KEYS."""
    return {key: value for key, value in event_dict.items() if key in ALLOWED_KEYS}


def redact_pii(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Replace email addresses and phone-like digit runs in string values."""
    for key, value in event_dict.items():
        if isinstance(value, str) and key not in _GENERATED_KEYS:
            value = _EMAIL.sub(_REDACTED, value)
            event_dict[key] = _PHONE.sub(_REDACTED, value)
    return event_dict


def _shared_processors() -> list[Processor]:
    """Processors that run on every record, ours and other libraries'."""
    return [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Send every log record to one JSON handler on `stream` (stdout by default).

    Safe to call more than once: it replaces the handler it installed before.
    """
    global _installed_handler

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.contextvars.merge_contextvars,
            *_shared_processors(),
            check_event_name,
            drop_unlisted_keys,
            redact_pii,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*_shared_processors(), redact_pii],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    if _installed_handler is not None:
        root.removeHandler(_installed_handler)
    root.addHandler(handler)
    root.setLevel(level)
    _installed_handler = handler

    _route_uvicorn_to_root()


def _route_uvicorn_to_root() -> None:
    """Make uvicorn's own records use our handler, and silence its access log.

    The access log prints raw paths and client addresses, so our middleware writes
    the access line instead.
    """
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    access = logging.getLogger(_UVICORN_ACCESS)
    access.handlers.clear()
    access.propagate = False
    access.disabled = True
