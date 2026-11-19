"""Structured JSON logging with an allow-list of keys (SECURITY.md section 6).

Our own loggers use structlog. Records from other libraries (uvicorn,
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

_EVENT_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
# Every part is length-bounded so the cost stays linear on attacker-controlled input.
_EMAIL = re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}")
# Nine or more digits, optionally separated by spaces, dots, dashes or brackets.
_PHONE = re.compile(r"(?<!\w)\+?\(?\d(?:[\s().-]{0,2}\d){8,}(?!\w)")
_REDACTED = "[redacted]"

# Longer strings are cut before redaction, which also bounds the regex cost.
MAX_VALUE_LENGTH = 200
_TRUNCATED = "[truncated]"

# Loggers that uvicorn configures itself. They are re-routed to the root handler.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error")
_UVICORN_ACCESS = "uvicorn.access"

# HTTP client libraries log every request URL, query string included, at INFO. A URL
# can carry an API key or a search term, so they only log from WARNING up.
# SQLAlchemy's engine and pool loggers print SQL text and parameter values at INFO.
_QUIET_LOGGERS = ("httpx", "httpcore", "sqlalchemy.engine", "sqlalchemy.pool")

_installed_handler: logging.Handler | None = None


def check_event_name(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Replace an event that is not a snake_case identifier.

    This stops an f-string that contains user data from being used as the message.
    """
    event = event_dict.get("event")
    if not isinstance(event, str) or not _EVENT_NAME.fullmatch(event):
        event_dict["event"] = "invalid_event_name"
    return event_dict


def drop_unlisted_keys(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Remove every key that is not in ALLOWED_KEYS."""
    return {key: value for key, value in event_dict.items() if key in ALLOWED_KEYS}


def limit_values(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Keep only scalar values, and cut long strings.

    A list or dict under an allowed key would skip redaction, so it is dropped.
    """
    limited: EventDict = {}
    for key, value in event_dict.items():
        if value is not None and not isinstance(value, str | int | float | bool):
            continue
        if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
            value = value[:MAX_VALUE_LENGTH] + _TRUNCATED
        limited[key] = value
    return limited


def redact_pii(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Replace email addresses and phone-like digit runs in string values."""
    for key, value in event_dict.items():
        if isinstance(value, str) and key not in _GENERATED_KEYS:
            value = _EMAIL.sub(_REDACTED, value)
            event_dict[key] = _PHONE.sub(_REDACTED, value)
    return event_dict


# Keys structlog's ProcessorFormatter adds to a foreign record and removes itself later.
_FORMATTER_META_KEYS = ("_record", "_from_structlog")


def sanitize_foreign(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Apply the allow-list, value limits and redaction to another library's record.

    Its message is free text, but exc_info, stack_info and any other extra key are
    dropped. The formatter's own meta keys are set aside and put back afterwards.
    """
    meta = {key: event_dict[key] for key in _FORMATTER_META_KEYS if key in event_dict}
    cleaned = drop_unlisted_keys(logger, method_name, event_dict)
    cleaned = limit_values(logger, method_name, cleaned)
    cleaned = redact_pii(logger, method_name, cleaned)
    return {**cleaned, **meta}


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
            limit_values,
            redact_pii,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            *_shared_processors(),
            sanitize_foreign,
        ],
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

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
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
