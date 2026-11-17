# Spec 001: Backend scaffold

Status: Done
Tracker task: Phase 0, bullet 1: Backend scaffold: flat layout per ARCHITECTURE.md section 8 (delete `src/`, fix `pyproject.toml` per `docs/tooling.md`), uv dependency groups, ruff, mypy, pytest, config (pydantic-settings), allow-list structured logging, `GET /api/v1/health`
Branch: feat/001-backend-scaffold
Depends on: none
Docs read: `docs/tooling.md`; uv project config (`tool.uv.package`), pydantic-settings (`extra`, `_env_file`), pydantic mypy plugin, structlog (stdlib `ProcessorFormatter`, contextvars), pytest-asyncio configuration; PyPI for versions and licences (2026-11-17)
PR:

## 1. Goal
After this ships, `uv sync` builds the environment, `uv run uvicorn app.main:app --reload` serves `GET /api/v1/health`, every log line is JSON filtered by an allow-list, and the four backend checks (ruff, format, mypy, pytest) pass on a flat `app/` layout that later specs build on.

## 2. Scope
In scope:
- Delete `src/`; rewrite `pyproject.toml` to the non-package shape in `docs/tooling.md` section 2; commit `uv.lock`.
- Tool config for ruff, mypy (strict, pydantic plugin), pytest, coverage.
- `app/core/config.py`: typed settings for the variables this spec uses (`APP_ENV`, `LOG_LEVEL`).
- `app/core/logging.py`: JSON logs, allow-list of keys, email and phone redaction, request id.
- `app/main.py` with an app factory, request-id and access-log middleware, `GET /api/v1/health`.
- Tests for config, logging and the health route.

Out of scope (explicitly not doing):
- Postgres, Redis, Alembic, docker-compose (Phase 0 bullet 2). Health does not check the database yet.
- CI workflow and pre-commit, including the `pre-commit` package (bullet 3).
- problem+json error handler, rate limits, CSRF, auth, audit log (Phase 1). The health route is unauthenticated and not rate-limited until SlowAPI lands.
- Settings for variables no code reads yet (database, auth, LLM, storage). Each later spec declares its own. The "refuse to start in prod with a `change-me` secret" check arrives with the first secret (auth).
- Empty placeholder packages for `services/`, `db/`, `graphs/`, `llm/`, `grounding/`, `mcp_clients/`. They are created by the spec that first puts code in them.

## 3. Design
### Backend
Files created:
```
app/__init__.py
app/main.py                    create_app(settings) factory + module-level `app`
app/api/__init__.py
app/api/routers/__init__.py
app/api/routers/health.py      GET /health
app/api/schemas/__init__.py
app/api/schemas/health.py      HealthResponse
app/core/__init__.py
app/core/config.py             Settings, get_settings()
app/core/logging.py            configure_logging(), processors, ALLOWED_KEYS
app/core/middleware.py         RequestContextMiddleware (pure ASGI)
mcp_servers/__init__.py        docstring only, so `mypy app mcp_servers` runs as documented
tests/conftest.py              settings, app and httpx client fixtures
tests/unit/test_config.py
tests/unit/test_logging.py
tests/integration/test_health.py
```
Files changed: `pyproject.toml`, `uv.lock` (new), `README.md` and docs only where they still mention `src/` or the `applyiq` script. Deleted: `src/`.

**pyproject.toml.** Remove `[build-system]`, `[project.scripts]`, `readme` and `authors`. Add `[tool.uv] package = false`, a real `description`, `requires-python = ">=3.14"`, the pinned dependencies below, and the tool sections from `docs/tooling.md` section 2 with these additions:
- pytest: `asyncio_default_fixture_loop_scope = "function"` (pytest-asyncio warns when it is unset), `addopts = "-m 'not llm' --import-mode=importlib"` so `tests/unit` and `tests/integration` can hold files with the same name.
- coverage: `[tool.coverage.run] source = ["app"]`, `branch = true`. No threshold yet; the 80% target applies to packages that do not exist.
- `[tool.pydantic-mypy] init_forbid_extra = true`, `init_typed = true`.

**Endpoint.** `GET /api/v1/health` -> `200 {"status": "ok"}`. Response model `HealthResponse(status: Literal["ok"])`. No request body, no auth, no service layer (there is no logic to put in one). The router is mounted under an `/api/v1` parent router that later specs add to.

**App factory.** `create_app(settings: Settings | None = None) -> FastAPI` calls `configure_logging`, adds the middleware, includes the v1 router. Tests pass their own settings; `app = create_app()` at module level is what uvicorn imports. OpenAPI and docs are served at `/api/v1/openapi.json` and `/api/v1/docs` when `APP_ENV` is `dev` or `test`, and turned off in `prod` (the production CSP would block the docs page anyway).

**Config.** `Settings(BaseSettings)` with `app_env: Literal["dev", "test", "prod"] = "dev"` and `log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"`. `SettingsConfigDict(env_file=".env", extra="ignore")`: pydantic-settings defaults to `extra="forbid"` and would raise on every `.env` variable not yet declared. `get_settings()` is cached with `functools.lru_cache`. No `os.getenv` anywhere.

**Logging.** structlog routed through the standard library with `structlog.stdlib.ProcessorFormatter`, one stdout handler on the root logger, `JSONRenderer` last. This makes uvicorn's and later SQLAlchemy's records JSON too. Processor chain for our own loggers:
1. `merge_contextvars` (carries `request_id`)
2. add level, logger name, ISO-8601 UTC timestamp
3. `check_event_name`: `event` must match `[a-z][a-z0-9_]{0,63}` in full, otherwise it is replaced with `invalid_event_name`. This stops an f-string with user data from being used as the message.
4. `drop_unlisted_keys`: removes every key not in `ALLOWED_KEYS`.
5. `limit_values`: keeps only string, number, boolean and null values (a list or dict under an allowed key would skip redaction) and cuts strings longer than 200 characters.
6. `redact_pii`: replaces email addresses and phone-like digit runs in string values with `[redacted]` (second line of defence, SECURITY.md section 6). Both patterns are length-bounded, so the cost stays linear on hostile input.

`ALLOWED_KEYS` starts as: `event, level, timestamp, logger, request_id, method, route, status_code, duration_ms, error_code, error_type, app_env`. A later spec that needs a new key adds it to this one frozenset, which is where a reviewer checks it.

Records from other libraries go through step 2 and then the same allow-list, value limits and redaction (steps 4 to 6), plus `merge_contextvars` so they carry the request id. Their message is free text by nature and is kept; `exc_info`, `stack_info` and any extra key are dropped, because the exception message can echo user data. The `httpx` and `httpcore` loggers are set to WARNING, because they log every request URL, query string included, at INFO. `uvicorn.access` is disabled, because it logs raw paths and client addresses; our middleware writes the access line instead.

**Middleware.** `RequestContextMiddleware` is a pure ASGI middleware (not `BaseHTTPMiddleware`, which would later buffer the SSE stream). Per HTTP request it: clears contextvars, generates a UUID4 request id (an incoming `X-Request-ID` is not trusted), binds it, adds `X-Request-ID` to the response, and logs one `request_completed` line with `method`, `route`, `status_code`, `duration_ms`. `method` is logged only when it is one of the standard verbs, otherwise as `other`. `route` is the full route template (for example `/api/v1/health`), or `unmatched`; never the raw path, the query string or a path-parameter value. FastAPI 0.163 resolves `include_router` lazily, so `scope["route"]` is the original route and knows only its own tail (`/notes/{note_id}`). The middleware recovers the prefixes from the request path: everything before the place where the route's own `path_regex` matches, followed by the route's `path_format`. A prefix is literal text, so this is safe, unless a prefix contains a path parameter: `scope["path_params"]` then holds a name the route does not own, and only the bare tail template is logged. Path parameters in `prefix=` are forbidden (fastapi-conventions), and a test requests every OpenAPI operation with sentinel values and checks the logged route equals the OpenAPI template. Plain Starlette routes such as the docs routes never get `scope["route"]` from FastAPI's router, so they log `unmatched` (dev and test only). On an unhandled exception it logs `request_failed` with `error_type` (the class name only) and re-raises. When the client disconnects and the handler is cancelled it logs `request_cancelled` and re-raises.

### Agents (if any)
None.

### Frontend (if any)
None.

### New dependencies (need approval)
The standard library has no ASGI framework, settings loader or test runner; all of these are the stack named in ARCHITECTURE.md except structlog and httpx.

| Package | Version | Licence | Why |
|---|---|---|---|
| fastapi | 0.163.1 | MIT | API framework (ARCHITECTURE section 1) |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server. Plain, not `[standard]`: fewer packages, `--reload` still works |
| pydantic | 2.14.3 | MIT | Imported directly for schemas, so pinned directly |
| pydantic-settings | 2.16.3 | MIT | Config (RULES code standards) |
| structlog | 26.1.0 | MIT OR Apache-2.0 | Processor chain for the allow-list and redaction, contextvars for the request id. Doing this on bare `logging` means hand-writing the same pieces |
| ruff (dev) | 0.17.5 | MIT | Lint and format |
| mypy (dev) | 2.4.1 | MIT | Types |
| pytest (dev) | 9.2.0 | MIT | Tests |
| pytest-asyncio (dev) | 1.5.0 | Apache-2.0 | Async tests |
| pytest-cov (dev) | 7.1.0 | MIT | Coverage |
| httpx (dev) | 0.28.1 | BSD-3-Clause | `AsyncClient` against the app in tests (fastapi-conventions skill) |

All have Python 3.14 support on PyPI; none is GPL or AGPL. If `uv lock` cannot resolve these exact pins together, stop and report rather than loosening a pin.

## 4. Security
- Inputs: the health route takes none. The incoming `X-Request-ID` header is untrusted and ignored.
- Auth, CSRF, rate limits: not applicable to a read-only liveness route with no data. SlowAPI arrives in Phase 1 (SECURITY.md section 5); health is added to the general limit then.
- Logging (SECURITY.md section 6): allow-list enforced in code and tested; no request bodies, raw paths, query strings, headers or client IPs are logged; the redaction processor is on.
- Secrets: none added. `.env` stays git-ignored; tests never read it (`Settings(_env_file=None)`).
- Docs endpoints off in prod.
- Licences checked (table above).

## 5. Acceptance criteria
- [x] AC1: `src/` is gone; `pyproject.toml` has no `[build-system]` or `[project.scripts]`, has `[tool.uv] package = false`, and every dependency is pinned with `==`; `uv.lock` is committed and `uv lock --check` passes.
- [x] AC2: `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy app mcp_servers` all exit 0.
- [x] AC3: `uv run pytest -q` passes, and a test marked `llm` is deselected by default.
- [x] AC4: `GET /api/v1/health` returns 200 with exactly `{"status": "ok"}`.
- [x] AC5: Every handled response carries an `X-Request-ID` header holding a UUID; two requests get different ids; a client-supplied `X-Request-ID` is not echoed. A 500 from an unhandled exception is built by Starlette's outermost middleware, outside ours, so it carries no id until the Phase 1 problem+json handler sets one (TRACKER).
- [x] AC6: A request produces one JSON log line `request_completed` whose keys are all in `ALLOWED_KEYS`, with the same `request_id` as the response header and `route` equal to the full route template, including every router prefix (the middleware recovers them from the request path, see Middleware) and never a concrete path-parameter value. A request to an unknown path logs `route: "unmatched"` and not the path.
- [x] AC7: A log call with a key outside the allow-list emits the line without that key. A log call whose event is not a snake_case identifier emits `invalid_event_name`.
- [x] AC8: An email address or phone number inside an allowed string value is emitted as `[redacted]`.
- [x] AC9: `Settings` reads `APP_ENV` and `LOG_LEVEL` from the environment, rejects a value outside the allowed set, and loads without error from an env file containing everything in `.env.example`.
- [x] AC10: With `APP_ENV=prod`, `/api/v1/docs` and `/api/v1/openapi.json` return 404; with `dev` they return 200.
- [x] AC11: No `os.getenv` or `os.environ` under `app/`.

## 6. Implementation tasks
- [x] T1: Delete `src/`. Rewrite `pyproject.toml` (project table, pinned dependencies, `dev` group, `[tool.uv]`, ruff, mypy, pytest, coverage). Run `uv lock` and `uv sync`. Commit with `uv.lock`.
- [x] T2: Make `uv run ruff check .` and `ruff format --check .` pass on what already exists, including `.claude/hooks/format_file.py`. Fix findings in the file; see decision 3 in section 9 for the one allowed `noqa`.
- [x] T3: `app/core/config.py` and `tests/unit/test_config.py` (AC9, AC11).
- [x] T4: `app/core/logging.py` and `tests/unit/test_logging.py` (AC7, AC8).
- [x] T5: `app/core/middleware.py`, `app/api/schemas/health.py`, `app/api/routers/health.py`, `app/main.py`, `mcp_servers/__init__.py`.
- [x] T6: `tests/conftest.py` and `tests/integration/test_health.py` (AC4, AC5, AC6, AC10). AC3's deselection is proved without adding a placeholder `llm` test to the suite: use pytest's `pytester` fixture on a temporary `llm`-marked test.
- [x] T7: Run all four checks. Remove stale mentions of `src/` or the `applyiq` script from README and docs. Correct the two `pre-commit` lines in `docs/tooling.md` (sections 2 and 7) per decision 2. Record the three decisions from section 9 in MEMORY.md, and add `ALLOWED_KEYS` as the place to extend logging to MEMORY.md (Conventions).

## 7. Test plan
| Test | Proves |
|---|---|
| `tests/unit/test_config.py`: defaults; env override via `monkeypatch`; invalid `APP_ENV` raises; env file copied from `.env.example` loads | AC9 |
| `tests/unit/test_config.py`: scan `app/**/*.py` for `os.getenv` / `os.environ` | AC11 |
| `tests/unit/test_logging.py`: capture stdout, parse JSON; unlisted key dropped; bad event name replaced; email and phone redacted; bound `request_id` present | AC7, AC8 |
| `tests/integration/test_health.py`: httpx `AsyncClient` with `ASGITransport` on `create_app(test_settings)`; status and body; header checks; captured access line; unknown path; docs on and off | AC4, AC5, AC6, AC10 |
| Commands run in `/ship-feature` and `/test-feature`: `uv lock --check`, ruff, format, mypy, pytest | AC1, AC2, AC3 |

No graph, grounding or cross-user tests apply: there are no graphs and no user data yet.

## 8. Manual checks (owner)
No browser checks. One optional terminal check: run `uv run uvicorn app.main:app --reload`, then `curl -i localhost:8000/api/v1/health`, and confirm the terminal shows a single-line JSON `request_completed` entry and no plain-text access line.

Owner confirmation (2026-11-17): ran both commands. Got 200, `{"status":"ok"}`, an `x-request-id` header, and one JSON `request_completed` line carrying the same request id, with no plain-text access line. The only plain-text lines were the three reloader startup lines at the top. They come from uvicorn's `--reload` supervisor process before the app is imported, so they appear in development only.

## 9. Open questions
None blocking. Three decisions made here, to be recorded in MEMORY.md by `/ship-feature` if approved:
1. **structlog** is the logging library (the docs said "structured JSON logs" and "redaction processor" without naming one).
2. **pre-commit moves to bullet 3.** `docs/tooling.md` sections 2 and 7 place the `pre-commit` package and its install in "the scaffold spec", while TRACKER.md puts pre-commit in the CI bullet. This spec follows TRACKER.md, and T7 corrects the two lines in `docs/tooling.md`.
3. **The hook file is linted, not excluded.** If ruff's `S603` fires on the formatter `subprocess.run` call in `.claude/hooks/format_file.py`, it gets a single `# noqa: S603` with the reason on the line (the arguments are a fixed list, no shell). No rule is turned off globally.

## 10. Implementation notes
Implemented on branch `feat/001-backend-scaffold`, tasks T1 to T7. Checks at the end: `uv lock --check`, ruff, ruff format, `mypy --strict app mcp_servers` and the suite all pass (40 tests at this point, 132 after review); the `llm` marker deselects by default. A real `uvicorn` run showed JSON-only output, one `request_completed` line per request, and no path or query string in any line.

Changes from the spec, all approved by the owner during `/ship-feature`:
- **Logged route (D30, reworked in review).** FastAPI 0.163 resolves `include_router` lazily, so `scope["route"].path` is only the route's own tail. The first version prepended an `API_V1_PREFIX` constant; review showed it logged the wrong route for nested routers and for `include_router(prefix=...)`. It now recovers the prefix from the request path and the route's `path_regex`, falls back to the bare tail template when a prefix holds a path parameter, and the middleware no longer imports from `app.api`. Tests: nested routers, `include_router` prefixes, path converters, routes registered on the app, the parameter-in-prefix fallback, and a guard that checks every OpenAPI operation of the real app.
- **AC5 reworded** to "every handled response". Starlette's outermost middleware builds the 500 for an unhandled exception, outside ours, so that response has no `X-Request-ID`. TRACKER.md's Phase 1 request hardening bullet now says the problem+json handler must set it.
- **httpx and httpcore held at WARNING (D31)** in `configure_logging`, because they log request URLs with query strings at INFO. Noted in SECURITY.md section 6.

Choices the spec left open:
- `configure_logging(level, stream=None)` takes the level string and an optional stream (tests pass a buffer). It replaces the handler it installed earlier, so repeated calls do not duplicate lines. It also routes `uvicorn` and `uvicorn.error` to the root handler and disables `uvicorn.access`.
- `redact_pii` skips the server-generated `timestamp` and `request_id` keys: the phone pattern could otherwise match digits in a timestamp or a UUID (about 0.3 percent of UUID4 ids would have been redacted). The phone pattern needs nine or more digits.
- The exception traceback key (`exc_info`) is not in `ALLOWED_KEYS`, so tracebacks are never logged. Foreign records (uvicorn and others) go through the same allow-list since review, so they emit no traceback or exception message either (tested).
- `app_env` is in `ALLOWED_KEYS` as the spec lists it, but nothing emits it yet.
- The dev-only docs routes are plain Starlette routes, which FastAPI's router does not put in `scope["route"]`, so they log `route: "unmatched"`.
- AC3 is proved with `pytester` in `tests/unit/test_pytest_config.py`, which copies the repo's real `pyproject.toml` into a temporary project, so no placeholder `llm` test is in the suite.
- T2: ruff flagged S603 in `.claude/hooks/format_file.py` as predicted; it now has the single `# noqa: S603` with the reason.

Verification (`/test-feature`): all 11 acceptance criteria are covered by tests or commands, 104 tests at that point, 100 percent line and branch coverage of `app/`. Seven deliberate breaks of `app/` were each caught by a test. The owner confirmed the optional terminal check in section 8.

Review (`/code-review-feature`): a code reviewer and a security reviewer each read the full diff in a fresh context. No Blockers. Findings fixed, all chosen by the owner:
- **Major.** Foreign log records (uvicorn and others) bypassed the key allow-list, so `exc_info` wrote the raw exception message to the log. The email regex was quadratic and reachable through the client-supplied HTTP method (0.75 s for 16,000 characters on the single worker). The logged route was wrong for nested routers and `include_router(prefix=...)`.
- **Minor.** The HTTP method is logged only when it is a standard verb. Foreign records carry `request_id`. `/docs/oauth2-redirect` is removed. A cancelled request logs `request_cancelled`. Non-scalar values are dropped, strings are cut at 200 characters, and event names match in full with a 64-character cap. The middleware no longer imports from `app.api`. New tests cover uvicorn re-routing and nested routers.
- After the fixes: 132 tests pass, and 12 deliberate breaks of the new code were each caught by a test.

Left alone, with the reason written in MEMORY.md (Gotchas): an invalid `APP_ENV` in the shell fails test collection (the fix would change the documented run command). Deferred to later specs: rejecting `LOG_LEVEL=DEBUG` in prod and quieting third-party loggers, `APP_ENV` failing open with `SecretStr` for secrets, the `Server: uvicorn` header, and a HEAD route if the deploy's health probe uses HEAD. Skipped as low value: phone-pattern separators of more than two characters.
