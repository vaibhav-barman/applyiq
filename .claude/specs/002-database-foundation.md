# Spec 002: Database foundation

Status: In progress
Tracker task: Phase 0, bullet 2 (first half): Local services and database: docker-compose (postgres, redis), SQLAlchemy async session on psycopg 3, Alembic baseline migration
Branch: feat/002-database-foundation
Depends on: 001 (merged)
Docs read: `docs/tooling.md`; spec 001; fastapi-conventions skill. Checked on 2026-11-17: SQLAlchemy 2.1 asyncio and PostgreSQL dialect docs, Alembic 1.20.1 tutorial, autogenerate and cookbook, FastAPI "Dependencies with yield", `langgraph-checkpoint-postgres` 3.2.1 source (`aio.py`, `base.py`), the `postgres` image page on Docker Hub, PyPI and Docker Hub for versions and licences.
PR:

## 1. Goal
After this ships, `docker compose up -d` starts a healthy Postgres and Redis on localhost only, `uv run alembic upgrade head` and `downgrade base` work from an empty database, and later specs get a tested async session dependency, a declarative `Base` and the shared model mixins to build tables on.

## 2. Scope
In scope:
- `docker-compose.yml` with Postgres (pgvector image) and Redis.
- Settings: `DATABASE_URL` and four pool settings. `.env.example` updated.
- `app/db/`: engine and session factory, `get_session` dependency, `Base` with a constraint naming convention, UUID and timestamp mixins.
- App lifespan that creates the engine at startup and disposes it at shutdown.
- Alembic: `alembic.ini`, async `env.py`, an empty baseline revision, autogenerate that ignores the LangGraph checkpoint tables.
- Test database fixtures, a `db` marker, skip or fail behaviour when Postgres is down.
- `create_app` moves to `app/factory.py` (reason in section 3, "App factory").
- Docs: `docs/tooling.md`, `MEMORY.md` (D32 to D37), one line in `RULES.md`, the fastapi-conventions skill.

Out of scope (explicitly not doing):
- `REDIS_URL`, the Redis client and the readiness route (spec 003). `GET /api/v1/health` is not touched.
- Any table. The first tables (`users`, `refresh_tokens`) arrive with auth.
- `app/db/repositories/`. Created by the spec that adds the first repository.
- Creating the `langgraph` schema or the checkpoint tables (Graph C part 1). This spec only decides where they live and keeps Alembic away from them.
- The `vector` extension (P1). The image carries it; nothing enables it.
- CI service containers (bullet 3). This spec only makes the tests ready for them.
- Production compose, TLS to Postgres, backups (first deploy bullet).
- Frontend, auth.

## 3. Design
### Backend

Files created:
```
docker-compose.yml
alembic.ini
app/factory.py                          create_app() and the lifespan, moved from app/main.py
app/db/__init__.py
app/db/base.py                          NAMING_CONVENTION, Base, UUIDPrimaryKeyMixin, TimestampMixin
app/db/session.py                       build_engine, build_session_factory, get_session, SessionDep
app/db/autogenerate.py                  CHECKPOINT_TABLES, include_name
app/db/models/__init__.py               docstring only: every model module is imported here so Alembic sees it
app/db/migrations/env.py
app/db/migrations/script.py.mako
app/db/migrations/versions/<date>-<rev>_baseline.py
tests/db_support.py                     test database URL, create-if-missing, reachability check
tests/unit/test_db_base.py
tests/unit/test_autogenerate_filter.py
tests/integration/test_db_session.py
tests/integration/test_migrations.py
tests/integration/test_app_import.py
```
Files changed: `app/main.py`, `app/core/config.py`, `app/core/logging.py`, `.env.example`, `pyproject.toml`, `uv.lock`, `tests/conftest.py`, `tests/unit/test_config.py`, `docs/tooling.md`, `MEMORY.md`, `RULES.md`, `.claude/skills/fastapi-conventions/SKILL.md`.

**docker-compose.yml.** Project name `applyiq`. Compose reads `.env` from the repo root for `${...}` substitution.

| | postgres | redis |
|---|---|---|
| Image | `pgvector/pgvector:0.8.7-pg18-trixie` | `redis:8.8.4-alpine` |
| Port | `127.0.0.1:${POSTGRES_PORT:-5432}:5432` | `127.0.0.1:${REDIS_PORT:-6379}:6379` |
| Credentials | `POSTGRES_USER` (default `applyiq`), `POSTGRES_DB` (default `applyiq`), `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}` | `REDIS_PASSWORD: ${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}`, passed to `redis-server --requirepass`; `REDISCLI_AUTH` set from it for the healthcheck |
| Volume | `postgres_data:/var/lib/postgresql` | `redis_data:/data` |
| Healthcheck | `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`, every 5 s, 3 s timeout, 10 retries, 10 s start period | `redis-cli ping`, same timings |
| Limits | 512 MB memory, 1 CPU; `shared_buffers=128MB`, `max_connections=50` | 192 MB memory, 0.5 CPU; `--maxmemory 128mb --maxmemory-policy noeviction` |
| Restart | `unless-stopped` | `unless-stopped` |

- `:?` makes `docker compose up` stop with that message when a password is missing. No password, real or weak, is in the repo.
- Postgres 18 images moved the volume path to `/var/lib/postgresql`. Mounting the old `/var/lib/postgresql/data` path would lose data when the container is recreated.
- `noeviction`: Redis will hold rate-limit counters and run event streams. Evicting those silently is worse than a write error.
- Together the two containers are capped at about 700 MB, which leaves room for Ollama on a 16 GB machine.
- Check the exact limit keys (`mem_limit` and `cpus`, or `deploy.resources.limits`) against the current Compose file reference, and confirm with `docker compose config`.

**pgvector image now: yes.** `pgvector/pgvector` is the official `postgres` image plus the extension files, so nothing changes until someone runs `CREATE EXTENSION vector`. Starting on it means the P1 memory feature needs one migration and no image swap or data move. Cost: a slightly larger image, and the tag pins the pgvector version together with the Postgres major. The CI service container (bullet 3) uses the same tag.

**Settings (`app/core/config.py`).**

| Variable | Type | Default | Validation |
|---|---|---|---|
| `DATABASE_URL` | `SecretStr` | none, required | see below |
| `DB_POOL_SIZE` | int | 5 | 1 to 20 |
| `DB_MAX_OVERFLOW` | int | 5 | 0 to 20 |
| `DB_POOL_TIMEOUT_SECONDS` | int | 10 | 1 to 60 |
| `DB_POOL_RECYCLE_SECONDS` | int | 1800 | 60 to 7200 |

`DATABASE_URL` is checked by a validator that runs after the value is already a `SecretStr`:
- It parses with `sqlalchemy.engine.make_url`.
- The driver is exactly `postgresql+psycopg`.
- It has a host and a database name.
- When `APP_ENV=prod`, it has a password, and the password is not `change-me` and does not start with `REPLACE_WITH`.

Each failure raises a fixed message that names the variable and the rule, for example "DATABASE_URL must start with postgresql+psycopg://". The message never contains the value, and a parse error from SQLAlchemy is replaced, not chained. This is the first secret, so the prod check deferred by spec 001 starts here.

**`.env.example`.** The database block becomes:
```
POSTGRES_USER=applyiq
POSTGRES_DB=applyiq
POSTGRES_PORT=5432
# Generate with: openssl rand -hex 24
POSTGRES_PASSWORD=
# Same password as POSTGRES_PASSWORD. Hex needs no URL escaping.
DATABASE_URL=postgresql+psycopg://applyiq:REPLACE_WITH_POSTGRES_PASSWORD@127.0.0.1:5432/applyiq
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT_SECONDS=10
DB_POOL_RECYCLE_SECONDS=1800
REDIS_PORT=6379
# Generate with: openssl rand -hex 24
REDIS_PASSWORD=
REDIS_URL=redis://:REPLACE_WITH_REDIS_PASSWORD@127.0.0.1:6379/0
```
The old line `postgresql+psycopg://applyiq:applyiq@localhost...` carried a weak default password and goes. `REDIS_URL` stays listed but no code reads it until spec 003.

**`app/db/base.py`.**
- `NAMING_CONVENTION`: `ix_%(column_0_label)s`, `uq_%(table_name)s_%(column_0_name)s`, `ck_%(table_name)s_%(constraint_name)s`, `fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s`, `pk_%(table_name)s`. Named constraints are what lets Alembic drop or alter them later.
- `class Base(DeclarativeBase)` with `metadata = MetaData(naming_convention=NAMING_CONVENTION)`.
- `UUIDPrimaryKeyMixin`: `id: Mapped[uuid.UUID]`, primary key, `default=uuid.uuid4`.
- `TimestampMixin`: `created_at` and `updated_at`, both `DateTime(timezone=True)`, `server_default=func.now()`; `updated_at` also has `onupdate=func.now()`.

**`app/db/session.py`.**
- `build_engine(settings) -> AsyncEngine`: `create_async_engine` with the URL's secret value, the four pool settings, `pool_pre_ping=True`, `echo=False`, `hide_parameters=True`, and `connect_args={"options": "-c timezone=utc"}` so `timestamptz` values come back in UTC. Creating the engine opens no connection.
- `build_session_factory(engine)`: `async_sessionmaker(engine, expire_on_commit=False)`.
- `get_session(request)`: opens a session from `request.app.state.session_factory`, yields it, commits when the handler returns, rolls back and re-raises on any exception, always closes.
- `SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]`. FastAPI's default scope for a `yield` dependency is `"request"`, which runs the exit code after the response is sent. With the default, a failed commit would follow a 200 the client already has. `scope="function"` commits before the response, and also releases the connection before an SSE stream starts.
- Two rules follow, written into the skill: a `yield` dependency that depends on `SessionDep` must also be `scope="function"`; and background graph runs build their own sessions from the factory and never use `get_session`.

**App factory (`app/factory.py`, `app/main.py`).** `create_app` and a new lifespan move to `app/factory.py`. `app/main.py` keeps only `app = create_app()`, so `uvicorn app.main:app` is unchanged. Why: `DATABASE_URL` is now required, `app.main` builds the app at import, and `tests/conftest.py` imports `app.main`. Without the move, the whole suite would fail at collection on a machine with no `.env`. Tests import `create_app` from `app.factory`. This also removes the existing `APP_ENV` collection gotcha in MEMORY.md.

The lifespan sets `app.state.engine` and `app.state.session_factory` at startup and awaits `engine.dispose()` at shutdown. It does not connect, so the app starts with Postgres down (readiness in spec 003 reports that). `httpx.ASGITransport` does not run lifespans, so the `client` fixture enters `application.router.lifespan_context(application)` itself.

**Logging (`app/core/logging.py`).** Add `sqlalchemy.engine` and `sqlalchemy.pool` to the loggers held at WARNING, next to `httpx`. At INFO and DEBUG they log SQL text and parameter values. `ALLOWED_KEYS` does not change and this spec adds no log event. Foreign records already lose `exc_info`, so a driver error message cannot reach the log.

**Alembic.**
- `alembic.ini`: `script_location = app/db/migrations`, `prepend_sys_path = .`, a date-prefixed `file_template`. No `sqlalchemy.url` and no logging sections.
- `env.py` starts from Alembic's `async` template (`run_async_migrations` with `async_engine_from_config`-style setup, `pool.NullPool`, `connection.run_sync(do_run_migrations)`, `asyncio.run`). Changes from the template:
  - The URL comes from `config.attributes["database_url"]` when a test sets it, otherwise from `get_settings().database_url`.
  - No `fileConfig`. A command-line run calls `configure_logging`, so Alembic's lines are JSON through the same allow-list. A programmatic run (tests) leaves logging alone.
  - Online mode only. Offline `--sql` mode is removed; nothing here uses it.
  - `target_metadata = Base.metadata`, after importing `app.db.models`.
  - `include_name=include_name` from `app/db/autogenerate.py`. `include_schemas` stays off.
- `app/db/autogenerate.py`: `CHECKPOINT_TABLES = frozenset({"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"})` (the four names in `langgraph-checkpoint-postgres` 3.2.1). `include_name(name, type_, parent_names)` returns `False` for any schema other than the default (`name is None`) and for any table in `CHECKPOINT_TABLES`, `True` otherwise. It lives outside `env.py` because `env.py` cannot be imported outside an Alembic run.
- Baseline revision: message `baseline`, empty `upgrade()` and `downgrade()`. There are no tables yet. It fixes the start of the revision chain and proves the wiring; `upgrade head` creates only `alembic_version`.

**Where the checkpoint tables live.** In their own schema, `langgraph`, in the same database. Graph C part 1 creates them at app startup: `CREATE SCHEMA IF NOT EXISTS langgraph`, then `AsyncPostgresSaver.setup()` on a psycopg connection pool opened with `options=-c search_path=langgraph`. The saver has no schema parameter and uses unqualified table names, so the search path is what places them. Alembic never creates, alters or drops them, and has two guards: it reflects only the default schema, and `include_name` filters the four names in case they ever land in `public`. Deleting an application or account removes checkpoints through the saver's own delete call, not through a migration.

### Agents (if any)
None. LLM calls added: none.

### Frontend (if any)
None.

### New dependencies (need approval)
| Package | Version | Licence | Why |
|---|---|---|---|
| sqlalchemy[asyncio] | 2.1.9 | MIT | ORM (ARCHITECTURE section 1). 2.1 no longer installs greenlet by default; the `asyncio` extra adds it (greenlet 3.5.6, MIT AND PSF-2.0) |
| psycopg[binary] | 3.3.9 | **LGPL-3.0-only** | The one Postgres driver (D16); the LangGraph checkpointer requires it |
| alembic | 1.20.1 | MIT | Migrations. Brings Mako (MIT) and MarkupSafe (BSD-3-Clause) |

All three have Python 3.14 wheels. No dev dependency is added. If `uv lock` cannot resolve these exact pins, stop and report.

**Licence note.** RULES.md says "No AGPL or GPL dependencies". psycopg is LGPL, which allows use as an unmodified library without affecting our code's licence, and D16 already chose it. Redis 8 is AGPLv3 / RSALv2 / SSPL and runs only as an unmodified container. D32 records both readings.

Container images: `pgvector/pgvector:0.8.7-pg18-trixie` (PostgreSQL 18.x; PostgreSQL licence), `redis:8.8.4-alpine`.

## 4. Security
- **Secrets (SECURITY.md section 1, tooling section 5).** `DATABASE_URL` is a `SecretStr` with no default. No password is committed; compose refuses to start without one. Validation errors never contain the URL. Prod rejects a missing or placeholder password.
- **Logging (section 6).** No new log events or keys. SQL text and parameters cannot reach the log: `echo=False`, SQLAlchemy loggers held at WARNING, `hide_parameters=True` keeps parameter values out of exception messages, and foreign records drop `exc_info`. Tested with a sentinel value.
- **Network.** Both ports bind to 127.0.0.1 only. Redis requires a password even locally.
- **Data protection (section 4).** No user data and no tables. TLS to Postgres and encrypted backups belong to the deploy bullet.
- **Auth scoping, CSRF, rate limits, untrusted input.** Not applicable: no route and no table is added.
- **Tests.** The database fixtures refuse to run against a database whose name does not end in `_test`, so a wrong URL cannot wipe development data.
- **Licences.** Checked, see the table and D32.

## 5. Acceptance criteria
- [ ] AC1: `docker compose config` succeeds with both passwords set, and fails with the "Set POSTGRES_PASSWORD in .env" message when it is unset. Both images are pinned to a full version tag, both published ports start with `127.0.0.1:`, both services have a healthcheck, a named volume and a memory limit, and the Postgres volume mounts at `/var/lib/postgresql`.
- [ ] AC2: `Settings` requires `DATABASE_URL`. It rejects a URL that is unparseable, uses another driver (`postgresql://`, `postgresql+asyncpg://`), or lacks a host or database name. With `APP_ENV=prod` it rejects a missing, `change-me` or `REPLACE_WITH...` password. The text of every such error does not contain the password or the URL. Pool settings outside their ranges are rejected.
- [ ] AC3: `Settings` loads from an env file holding everything in `.env.example`. `.env.example` has no value for `POSTGRES_PASSWORD` or `REDIS_PASSWORD`.
- [ ] AC4: A table built on `Base` with both mixins gets constraint names from the convention (`pk_<table>`, `uq_<table>_<column>`, `fk_...`, `ix_...`, `ck_...`).
- [ ] AC5: A row inserted through a session gets a UUID `id`, and timezone-aware `created_at` and `updated_at` with a zero UTC offset. Updating the row moves `updated_at` forward and leaves `created_at` unchanged.
- [ ] AC6: A route using `SessionDep` that returns normally has its change committed. A route that raises has its change rolled back and returns 500.
- [ ] AC7: A route whose commit fails (unique violation raised at commit) returns 500, not the handler's 200, and no row is stored.
- [ ] AC8: The app starts and serves `GET /api/v1/health` with Postgres unreachable. After the lifespan ends, the engine is disposed.
- [ ] AC9: On an empty database, `alembic upgrade head` succeeds and leaves `alembic_version` as the only table in `public`. `alembic check` then reports no changes. `alembic downgrade base` succeeds and leaves `alembic_version` empty.
- [ ] AC10: With the four checkpoint tables present in `public` and also in a `langgraph` schema, `alembic check` still reports no changes, autogenerate produces no operations, and the tables still exist after `upgrade head` and `downgrade base`.
- [ ] AC11: With `LOG_LEVEL=DEBUG`, a statement that fails with a sentinel parameter value puts the sentinel in neither the captured log nor the exception text. No SQL text appears in the log.
- [ ] AC12: With Postgres unreachable, `uv run pytest -q` passes, every `db` test is reported as skipped with a reason that includes `docker compose up -d postgres`, and none is reported as passed. With `--require-services`, the same run fails. With no `DATABASE_URL` in the environment and no `.env`, the non-`db` tests are still collected and pass.
- [ ] AC13: The database fixtures refuse a database name that does not end in `_test`.
- [ ] AC14: `uv lock --check`, `ruff check`, `ruff format --check`, `mypy app mcp_servers` and `pytest` all exit 0. The three new packages are pinned with `==`. No `os.getenv` or `os.environ` under `app/`.
- [ ] AC15: Importing `app.main` with a valid environment gives a FastAPI `app`. `tests/conftest.py` does not import `app.main`.

## 6. Implementation tasks
Each task is one commit or a few. Run `git branch --show-current` before every commit.
- [x] T1: Add the three dependencies to `pyproject.toml`, run `uv lock` and `uv sync`. Add the `db` marker and `testpaths = ["tests"]` to the pytest config (the second makes `tests/conftest.py` an initial conftest, which `pytest_addoption` needs; verify against the pytest docs).
- [x] T2: `docker-compose.yml` and the `.env.example` block. Verify with `docker compose config`. (AC1, AC3)
- [x] T3: Settings fields and the `DATABASE_URL` validator; extend `tests/unit/test_config.py`. Every existing `Settings(_env_file=None, ...)` call in the tests now passes a dummy `database_url`; put it in one helper. (AC2, AC3)
- [x] T4: Move `create_app` to `app/factory.py`, reduce `app/main.py` to the instance, point tests at `app.factory`, add `tests/integration/test_app_import.py`. No behaviour change; the suite stays green. (AC15)
- [ ] T5: `app/db/base.py` and `tests/unit/test_db_base.py` (compile `CreateTable` for a test-only table against the PostgreSQL dialect; no database needed). (AC4)
- [ ] T6: `app/db/session.py`, the lifespan in `app/factory.py`, the two SQLAlchemy loggers in `app/core/logging.py`. Confirm `hide_parameters`, `join_transaction_mode` and `Depends(scope=...)` in the current docs before using them. (AC8)
- [ ] T7: `tests/db_support.py` and the fixtures in `tests/conftest.py`: `--require-services`, the test database URL, create-if-missing, skip or fail, `db_session` with rollback, the lifespan in the `client` fixture. (AC12, AC13)
- [ ] T8: `tests/integration/test_db_session.py`. (AC5, AC6, AC7, AC11)
- [ ] T9: `alembic.ini`, `app/db/autogenerate.py`, `env.py`, `script.py.mako`, the baseline revision; `tests/unit/test_autogenerate_filter.py` and `tests/integration/test_migrations.py`. (AC9, AC10)
- [ ] T10: Docs. `docs/tooling.md`: section 3 versions, section 4 commands (compose up, ps, down; `alembic downgrade base`, `alembic check`; `pytest --require-services`), section 5 note on the two passwords, section 6 note that CI sets `DATABASE_URL` and passes `--require-services`. `MEMORY.md`: D32 to D37, replace the `APP_ENV` collection gotcha, add the gotchas in section 9. `RULES.md` Dependencies: one sentence from D32. fastapi-conventions skill: `SessionDep`, the scope rule, background runs use the factory. Run all checks. (AC14)

## 7. Test plan
Tests marked `db` need Postgres. Everything else runs with Docker off.

**How tests get a database.** `tests/db_support.py` builds `Settings()` from the real environment or `.env` (the one place tests read it), takes `DATABASE_URL`, and swaps the database name for `<name>_test`. It creates that database if missing, through a short autocommit connection to the `postgres` maintenance database. If settings cannot be built or the server cannot be reached, the fixture calls `pytest.skip` with the reason and the command to run; with `--require-services` it calls `pytest.fail` instead. CI (bullet 3) passes that flag, so a missing service container can never look like a pass.

**Isolation.** `db_session` opens one connection, begins a transaction, binds an `AsyncSession` with `join_transaction_mode="create_savepoint"`, and rolls the transaction back after the test. The engine is function-scoped with `NullPool`, which avoids sharing connections across pytest-asyncio's per-test event loops. Tests that need real commits (AC6, AC7) use a test-only table on a test-only `DeclarativeBase` built from `NAMING_CONVENTION` and the mixins, created before and dropped after. Migration tests are plain sync tests on their own database, `<name>_test_migrations`, dropped and recreated each run, because `env.py` calls `asyncio.run` itself.

| Test | Marker | Proves |
|---|---|---|
| `tests/unit/test_config.py`: required URL; each rejected URL shape; prod password rules; error text has no password or URL; pool ranges; `.env.example` loads and has empty passwords | | AC2, AC3 |
| `tests/unit/test_pyproject.py` (extend): the three pins | | AC14 |
| `tests/unit/test_db_base.py`: constraint names from compiled DDL | | AC4 |
| `tests/unit/test_autogenerate_filter.py`: `include_name` for the default schema, another schema, each checkpoint table, an ordinary table | | AC10 |
| `tests/unit/test_compose_file.py`: parse `docker-compose.yml` as text and check pins, `127.0.0.1:` ports, healthchecks, volumes, limits, the `:?` guards, no literal password | | AC1 |
| `tests/integration/test_db_session.py`: mixin values and `updated_at`; commit on success; rollback on error; failed commit gives 500; sentinel parameter absent from log and exception at DEBUG | `db` | AC5, AC6, AC7, AC11 |
| `tests/integration/test_db_session.py`: app with an unreachable URL still serves health; engine disposed after lifespan | | AC8 |
| `tests/integration/test_migrations.py`: upgrade, check, downgrade on an empty database; the same with checkpoint tables in `public` and `langgraph` | `db` | AC9, AC10 |
| `tests/unit/test_db_fixtures.py` with `pytester`: unreachable URL skips with the message; `--require-services` fails; no `DATABASE_URL` still collects; a name without `_test` is refused | | AC12, AC13 |
| `tests/integration/test_app_import.py`: import `app.main` with the environment set by `monkeypatch`; scan `tests/conftest.py` for `app.main` | | AC15 |
| Commands in `/ship-feature` and `/test-feature`: `docker compose config` with and without the password, `uv lock --check`, ruff, format, mypy, pytest | | AC1, AC14 |

`test_compose_file.py` reads the file as text because no YAML parser is a direct dependency. If that proves too brittle, it is replaced by the `docker compose config` command check and noted in section 10.

No cross-user test applies: there is no route and no user data.

## 8. Manual checks (owner)
No browser checks. Terminal checks on the Mac, from the repo root. Step 1 is needed before `/ship-feature 002`.

1. Create `.env` and the passwords:
   ```
   cp -n .env.example .env
   openssl rand -hex 24
   openssl rand -hex 24
   ```
   Put the first value in `POSTGRES_PASSWORD` and in `DATABASE_URL` (replacing `REPLACE_WITH_POSTGRES_PASSWORD`), the second in `REDIS_PASSWORD` and `REDIS_URL`.
2. Start the services and check health:
   ```
   docker compose up -d
   docker compose ps
   ```
   Expect both services `running (healthy)` within about 20 seconds.
3. Confirm the ports are local only:
   ```
   docker compose port postgres 5432
   docker compose port redis 6379
   ```
   Expect `127.0.0.1:5432` and `127.0.0.1:6379`.
4. Migrate up:
   ```
   uv run alembic upgrade head
   uv run alembic current
   docker compose exec postgres psql -U applyiq -d applyiq -c '\dt'
   ```
   Expect the baseline revision marked `(head)`, and `alembic_version` as the only table.
5. Migrate down and up again:
   ```
   uv run alembic downgrade base
   uv run alembic current
   uv run alembic upgrade head
   ```
   Expect no revision after the downgrade.
6. Confirm pgvector is available but not enabled:
   ```
   docker compose exec postgres psql -U applyiq -d applyiq -c "select name, installed_version from pg_available_extensions where name = 'vector'"
   ```
   Expect one row with an empty `installed_version`.
7. Tests with and without Postgres:
   ```
   uv run pytest -q
   docker compose stop postgres
   uv run pytest -q -rs
   uv run pytest -q --require-services
   docker compose start postgres
   ```
   Expect: no skips; then the `db` tests skipped with the `docker compose up -d postgres` reason; then a failing run.
8. Data survives a restart: `docker compose down`, `docker compose up -d`, `uv run alembic current` still shows the baseline.

Readiness behaviour is checked in spec 003, where the route is built.

## 9. Open questions
None blocking. Decisions made here, recorded in MEMORY.md by T10:
- **D32 Licence rule scope.** "No AGPL or GPL" covers code we link or ship. LGPL psycopg, used unmodified, is allowed. An unmodified service container (Redis 8) is not a dependency in that sense.
- **D33 Postgres image.** `pgvector/pgvector` on Postgres 18 from the start, extension not enabled until P1. Why: no image swap or data move later.
- **D34 Checkpoint tables.** Schema `langgraph`, created by the saver's `setup()` at app startup in Graph C part 1, over a connection with `search_path=langgraph`. Alembic reflects only the default schema and filters the four table names.
- **D35 Test database.** `<name>_test` on the same server, a rolled-back transaction per test, a `db` marker, skip when Postgres is down, fail with `--require-services`.
- **D36 Session scope.** `SessionDep` uses `Depends(scope="function")` so the commit runs before the response.
- **D37 App factory.** `create_app` lives in `app/factory.py`; `app/main.py` only builds the instance. Why: a required secret must not break test collection.

Gotchas to add to MEMORY.md: Postgres 18 volume path; SQLAlchemy 2.1 needs the `asyncio` extra for greenlet; `httpx.ASGITransport` does not run the lifespan; the password appears in both `POSTGRES_PASSWORD` and `DATABASE_URL`; `docker compose down -v` deletes the data.

For bullet 3 (CI): the backend job needs the `pgvector/pgvector:0.8.7-pg18-trixie` service container, `DATABASE_URL` in the job environment, and `pytest --require-services`.

### Proposal for spec 003 (not part of this spec)
The second half of the original bullet, kept here so it is not lost.
- `REDIS_URL` as a `SecretStr` (`redis://` or `rediss://`), same error rules as `DATABASE_URL`.
- `app/core/redis.py`: build a `redis.asyncio` client from the URL; the lifespan creates it and awaits `aclose()` at shutdown. No features.
- **Readiness route: yes, as a separate route.** `GET /api/v1/ready` returns 200 `{"status": "ready"}` or 503 `{"status": "not_ready"}`. It runs `SELECT 1` and `PING`, each with a 2-second timeout, through a small service. The body never says which dependency failed or why; that goes to the log as `readiness_check_failed` with `component` (`postgres` or `redis`, a new allowed key) and `error_type`. It is logged by the existing middleware like every route. `GET /api/v1/health` stays exactly as it is, as the liveness check.
- New dependency for 003: `redis==8.1.0` (MIT).

## 10. Implementation notes
(Filled in by /ship-feature.)
