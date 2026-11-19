"""Application factory. `app/main.py` builds the instance that uvicorn serves."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from app.api.routers import API_V1_PREFIX, api_v1_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import build_engine, build_session_factory

DOCS_URL = f"{API_V1_PREFIX}/docs"
OPENAPI_URL = f"{API_V1_PREFIX}/openapi.json"


def make_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create the engine at startup and dispose of it at shutdown.

    Nothing connects here, so the app starts even when Postgres is down.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings)
        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    # The interactive docs are for development only. The production CSP would block
    # the docs page anyway.
    docs_enabled = settings.app_env in ("dev", "test")
    app = FastAPI(
        title="ApplyIQ",
        docs_url=DOCS_URL if docs_enabled else None,
        redoc_url=None,
        openapi_url=OPENAPI_URL if docs_enabled else None,
        # Without this the docs add a route outside /api/v1.
        swagger_ui_oauth2_redirect_url=None,
        lifespan=make_lifespan(settings),
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_v1_router)
    return app
