"""Application factory. `app/main.py` builds the instance that uvicorn serves."""

from fastapi import FastAPI

from app.api.routers import API_V1_PREFIX, api_v1_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

DOCS_URL = f"{API_V1_PREFIX}/docs"
OPENAPI_URL = f"{API_V1_PREFIX}/openapi.json"


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
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_v1_router)
    return app
