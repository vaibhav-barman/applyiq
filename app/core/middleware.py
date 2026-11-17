"""Request id and access logging, as a pure ASGI middleware.

It is not `BaseHTTPMiddleware`, which would buffer streaming responses such as the
SSE stream added later.
"""

import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.routers import API_V1_PREFIX

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
UNMATCHED_ROUTE = "unmatched"


def _route_template(scope: Scope) -> str:
    """Return the matched route's template, never the raw path or query string.

    Starlette's router stores the matched route in `scope["route"]` once it matches.
    FastAPI resolves routers added with `include_router` lazily, so for those routes
    `path` lacks the `/api/v1` prefix of the parent router. The prefix is added back
    here. Routes registered straight on the app (the docs routes) already carry it.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    if not isinstance(path, str):
        return UNMATCHED_ROUTE
    if path.startswith(API_V1_PREFIX):
        return path
    return API_V1_PREFIX + path


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
        except Exception as error:
            logger.error(
                "request_failed",
                method=scope["method"],
                route=_route_template(scope),
                error_type=type(error).__name__,
                duration_ms=_elapsed_ms(started),
            )
            raise

        logger.info(
            "request_completed",
            method=scope["method"],
            route=_route_template(scope),
            status_code=status_code,
            duration_ms=_elapsed_ms(started),
        )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
