# Tooling: project layout, commands, environment, CI, pre-commit

Read this before writing any spec in TRACKER Phase 0, and whenever a command in `.claude/commands/` fails. It is a brief for those specs, not finished configuration: the specs create the real files.

## 1. Layout decision

Flat layout at the repo root, one uv project, not a package.

```
applyiq/
  app/            FastAPI app, graphs, services (import as `app.…`)
  mcp_servers/    FastMCP servers (import as `mcp_servers.…`)
  tests/
  frontend/       React + Vite, its own package.json
  docs/  docker/  deploy/
  pyproject.toml  uv.lock  alembic.ini
```

Why: this is a deployed application, not a library, so a `src/` layout and a build step add nothing. One project and one lockfile mean the API, the graphs and the MCP server share the same models with no path tricks. Every command in this repo runs from the root.

## 2. What the first spec must change

`uv init` created a packaged `src/` layout. The first scaffold spec replaces it:

- Delete `src/`.
- In `pyproject.toml`: remove `[build-system]` and `[project.scripts]`; add `[tool.uv]` with `package = false`; set a real `description`; keep `requires-python = ">=3.14"`.
- Keep `.python-version` at `3.14`.
- Runtime dependencies under `[project] dependencies`, pinned with `==`. Development tools in a `dev` dependency group.
- Commit `uv.lock`.

Target shape (values are placeholders; pin whatever is current when the spec runs):

```toml
[project]
name = "applyiq"
version = "0.1.0"
description = "AI job-application copilot with grounded drafts and human approval"
requires-python = ">=3.14"
dependencies = []          # added by specs, each pinned with ==

[dependency-groups]
dev = []                   # ruff, mypy, pytest, pytest-asyncio, pytest-cov, httpx (pre-commit joins in the CI bullet)

[tool.uv]
package = false

[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC", "S", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]      # asserts are the point of tests

[tool.mypy]
strict = true
python_version = "3.14"
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
markers = ["llm: calls a real model; skipped unless run with -m llm"]
addopts = "-m 'not llm'"
```

Check each option name against the tool's current docs when writing the real file.

## 3. Versions seen on PyPI on 2026-11-17

These are newer than what a model remembers. Read the library's current docs before using an API from memory.

| Package | Version seen | Note |
|---|---|---|
| langgraph | 1.2.22 | Interrupt and streaming APIs have moved since 0.x. |
| langgraph-checkpoint-postgres | 3.2.1 | Uses psycopg 3. |
| langchain / langchain-core | 1.5.0 / 1.8.1 | |
| langchain-groq, langchain-ollama, langchain-google-genai | 1.2.0, 1.1.0, 4.5.0 | |
| langchain-mcp-adapters | 0.3.2 | |
| fastmcp / mcp | 4.2.0 / 2.3.0 | Major versions newer than most examples online. |
| fastapi | 0.163.1 | |
| sqlalchemy | 2.1.9 | |
| psycopg (binary) | 3.3.9 | The only Postgres driver in this project. |
| pydantic-core | 2.50.4 | |
| pypdf | 7.1.0 | BSD licence. |
| pgvector | 0.5.1 | P1 only. |

Every package above has wheels for Python 3.14.

## 4. Commands

Backend, from the repo root:

| Purpose | Command |
|---|---|
| Install | `uv sync` |
| Lint | `uv run ruff check .` |
| Format check | `uv run ruff format --check .` |
| Types | `uv run mypy app mcp_servers` |
| Tests | `uv run pytest -q` |
| Tests that call a real model | `uv run pytest -m llm` |
| Graph and grounding tests | `uv run pytest tests/graphs tests/grounding -q` |
| New migration | `uv run alembic revision --autogenerate -m "..."` |
| Apply migrations | `uv run alembic upgrade head` |
| Run the API | `uv run uvicorn app.main:app --reload` |

Frontend, from the repo root (the `--prefix` form matches the permission rules in `.claude/settings.json`):

| Purpose | Command |
|---|---|
| Install | `npm --prefix frontend ci` |
| Dev server | `npm --prefix frontend run dev` |
| Lint | `npm --prefix frontend run lint` |
| Tests | `npm --prefix frontend test -- --run` |
| Build | `npm --prefix frontend run build` |

`frontend/package.json` must define the scripts `dev`, `build`, `lint`, `format` and `test` (with `test` set to `vitest`).

Local services: `docker compose up -d postgres redis`. The API and the Vite dev server run on the host during development.

## 5. Environment variables

`.env.example` is the list. Rules:
- Every variable is declared once in `app/core/config.py` (pydantic-settings) with a type and, where safe, a default. No `os.getenv` anywhere else.
- A new variable is added to `.env.example` in the same commit, with a one-line comment and no real value.
- Secrets have no default. The app refuses to start in `prod` if a secret is missing or still set to `change-me`.
- Model names are config, never code.

## 6. CI outline (GitHub Actions)

One workflow, `.github/workflows/ci.yml`, on pull requests and on pushes to `main`. `permissions: contents: read`. Cancel superseded runs on the same branch.

| Job | Steps |
|---|---|
| backend | Check out. Install uv with caching. `uv sync --frozen`. `ruff check`, `ruff format --check`, `mypy app mcp_servers`. `pytest` with coverage for `app/services` and `app/graphs`. Postgres and Redis as service containers. |
| security | Fail if `uv.lock` is out of date. Export the lockfile to requirements format and run `pip-audit` on it. Run gitleaks over the diff. |
| frontend | Runs only when `frontend/` exists. Node with npm caching. `npm ci`, lint, `vitest --run`, `vite build`, `npm audit` at high severity. |

Pin each action to a release tag. Look up the current uv and pip-audit flags when writing the workflow; do not rely on remembered ones.

Until the frontend scaffold has merged, the frontend job is skipped by a path check, not left failing.

## 7. Pre-commit outline

`.pre-commit-config.yaml`, installed with `uv run pre-commit install` in the CI and pre-commit spec (TRACKER Phase 0, bullet 3), which also adds the `pre-commit` package to the `dev` group.

| Hook | Purpose |
|---|---|
| ruff (lint with fix) and ruff-format | Same rules as CI |
| gitleaks | Secret scan on staged changes |
| check-yaml, check-toml, check-json | Config hygiene |
| end-of-file-fixer, trailing-whitespace | |
| check-added-large-files (500 kB) | Stops a resume or a model file being committed |
| check-merge-conflict | |
| no-commit-to-branch for `main` | Enforces "never commit to main" locally |

mypy and the tests stay in CI, so commits remain fast.

## 8. GitHub setup (done by the owner, once)

1. `gh auth login`.
2. Create the repository and add it as `origin`. A public repository gets free Actions minutes and free branch protection.
3. Push `main`.
4. After the CI spec has merged, protect `main`: require a pull request, require the `backend`, `security` and `frontend` checks, block force pushes, allow squash merge only, delete head branches automatically.

Until step 4 is done, `/merge-feature` cannot rely on checks and will say so.
