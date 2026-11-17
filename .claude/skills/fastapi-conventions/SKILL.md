---
name: fastapi-conventions
description: ApplyIQ backend conventions for FastAPI routes, services, SQLAlchemy async repos, Alembic, auth, pagination, errors, rate limits. Use when adding or changing anything under app/api, app/services, app/db.
---

# FastAPI conventions for ApplyIQ

## Layers
`app/api/routers/*.py` (HTTP only) -> `app/services/*.py` (business logic) -> `app/db/repositories/*.py` or the MCP client. Routers never touch the session directly. Graph nodes call services too, through the deps object.

## Routes
- Prefix `/api/v1`. Request and response models in `app/api/schemas/`, `model_config = ConfigDict(extra="forbid")` on write models.
- Current user via `Depends(get_current_user)`; pass `user.id` down. Every repository method takes `user_id` and filters by it.
- The one shared table is `jobs`: a row with `owner_user_id IS NULL` is a public listing, a row with an owner is visible only to that owner. Job queries always apply `owner_user_id IS NULL OR owner_user_id = :user_id`.
- Rate-limit every new route with SlowAPI using the limits in SECURITY.md. Limits are stored in Redis.
- State-changing routes require the CSRF dependency (signed token in `X-CSRF-Token`, plus the Origin check).
- No CORS middleware. Development is same-origin through the Vite proxy.
- No path parameters in a router `prefix=` (`APIRouter(prefix="/applications/{application_id}")` or `include_router(..., prefix=...)`). Put them in the route path instead. The access log rebuilds the route template from the request, and a parameter in a prefix would put its concrete value in the log, so the middleware falls back to a bare, less useful template. `tests/integration/test_route_template.py` checks every route against its OpenAPI template and fails if one drifts.
- Behind Nginx, read the client IP from the forwarded header only when the request comes from a trusted proxy.

## Pagination
Cursor-based: `limit` (max 50) and `cursor` (opaque base64 of `(created_at, id)`), response `{items, next_cursor}`.

## Errors
Raise `AppError(code="job_not_found", status=404, detail="...")`; a handler returns problem+json. Never leak stack traces or SQL. Auth failures use one generic message.

## Database
- SQLAlchemy 2 async on the psycopg 3 driver (`postgresql+psycopg://`). It is the only Postgres driver in the project.
- `Mapped[...]` typed models, UUID primary keys, `created_at/updated_at` in UTC.
- Every model change ships with an Alembic migration (`uv run alembic revision --autogenerate -m "..."`), reviewed by hand.
- LangGraph's checkpoint tables are not ours. Alembic's `env.py` excludes them from autogenerate; a migration must never create, alter or drop them.

## Long tasks
- `POST /applications/{id}/prepare` creates a `runs` row, starts the graph as an asyncio task, and returns `202` with the run id. Honour the `Idempotency-Key` header; if an active run exists, return it.
- Progress via SSE at `/applications/{id}/stream`, which tails a Redis Stream and replays from `Last-Event-ID`. Check ownership before streaming.
- The API runs as one uvicorn worker. Do not add code that assumes several.

## Logging
Log ids, enum values, counts, durations and codes. Never request bodies, resume or job text, prompts, model output, emails or tokens.

## Tests
`httpx.AsyncClient` against the app with a test database; one test per route for success, validation error, unauthenticated, another user's resource, and (for state-changing routes) a missing CSRF token.
