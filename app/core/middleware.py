"""Request id and access logging, as a pure ASGI middleware.

It is not `BaseHTTPMiddleware`, which would buffer streaming responses such as the
SSE stream added later.
"""

import asyncio
import re
import time
import uuid
from functools import lru_cache

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
UNMATCHED_ROUTE = "unmatched"

# The method is client-supplied text, so anything else is logged as "other".
KNOWN_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
OTHER_METHOD = "other"


@lru_cache(maxsize=256)
def _tail_search(pattern: str) -> re.Pattern[str]:
    """A route's path regex without its leading `^`, so it can be searched for."""
    return re.compile(pattern.removeprefix("^"))


def _route_template(scope: Scope) -> str:
    """Return the matched route's full template, never a raw path or a path value.

    FastAPI resolves `include_router` lazily, so `scope["route"]` is the original
    route and only knows its own tail (`/notes/{note_id}`), not the prefixes added by
    the routers it was included in. The prefix is recovered from the request path:
    everything before the place where the route's own regex matches. The tail always
    comes from `path_format`, so no parameter value of the route itself is logged.

    A prefix is literal text, so this is safe, unless a prefix contains a path
    parameter (`prefix="/applications/{application_id}"`): its concrete value would be
    in the recovered text. The scope's `path_params` then holds a name the route does
    not own, and only the bare tail template is logged. fastapi-conventions forbids
    path parameters in `prefix=`, and a test checks every route against the OpenAPI
    template.
    """
    route = scope.get("route")
    template = getattr(route, "path_format", None)
    pattern = getattr(getattr(route, "path_regex", None), "pattern", None)
    if not isinstance(template, str) or not isinstance(pattern, str):
        return UNMATCHED_ROUTE

    own_params = set(getattr(route, "param_convertors", {}))
    if set(scope.get("path_params", {})) - own_params:
        return template

    path = str(scope["path"])
    match = _tail_search(pattern).search(path)
    if match is None:
        return template
    return path[: match.start()] + template


def _method(scope: Scope) -> str:
    method = scope["method"]
    return method if method in KNOWN_METHODS else OTHER_METHOD


class RequestContextMiddleware:
    """Give each request a fresh id and log one line when it finishes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # An incoming X-Request-ID is never read: the id is always ours.
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        status_code = 0

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except asyncio.CancelledError:
            # A client that disconnects cancels the handler. Log it and let it propagate.
            logger.info(
                "request_cancelled",
                method=_method(scope),
                route=_route_template(scope),
                duration_ms=_elapsed_ms(started),
            )
            raise
        except Exception as error:
            logger.error(
                "request_failed",
                method=_method(scope),
                route=_route_template(scope),
                error_type=type(error).__name__,
                duration_ms=_elapsed_ms(started),
            )
            raise

        logger.info(
            "request_completed",
            method=_method(scope),
            route=_route_template(scope),
            status_code=status_code,
            duration_ms=_elapsed_ms(started),
        )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
