"""The `/api/v1` parent router. Later specs include their routers here."""

from fastapi import APIRouter

from app.api.routers import health

API_V1_PREFIX = "/api/v1"

api_v1_router = APIRouter(prefix=API_V1_PREFIX)
api_v1_router.include_router(health.router)
