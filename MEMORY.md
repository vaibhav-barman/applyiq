# MEMORY: project memory for Claude Code

Persistent context. Update it when a decision is made or a gotcha is found. Keep it short. Newest entries at the bottom of each section.

This file is the project's decision log and is tracked in git. It is not Claude Code's own auto-memory (which lives outside the repo). When a command says "add to MEMORY.md", it means this file.

## Owner context
- Solo developer, learning while building, about 15 hours a week alongside university coursework.
- Machine: MacBook Air, Apple M5, 16 GB RAM, macOS. Docker installed. uv is the Python package manager. Ollama installed with `llama3.2:3b` and `nomic-embed-text`.
- Comfortable with: Python, FastAPI, Pydantic, SQLAlchemy, Alembic, LangChain, LangGraph, MCP/FastMCP, ChromaDB, Redis, Docker, Postgres, AWS basics.
- New to React; does not know TypeScript. Frontend is React in plain JavaScript. Explain React patterns briefly in comments and PR summaries. Never introduce TypeScript.
- Goal of this project: portfolio piece for a remote AI-engineer job. Production-style quality matters more than feature count. A finished, deployed MVP beats a half-built large system.
- Day-to-day building is done with Sonnet. Decisions must be written in repo files, not left in a chat.

## Decisions (ADR log)
- D1: UI is a minimal React + Vite SPA in JavaScript, black-and-white design ("paper and desk", see DESIGN.md). FastAPI is a JSON API only. Same-origin deploy via Nginx.
- D2: No auto-submit, no scraping of job sites that forbid it. Legal sources only.
- D3: Superseded by D9. (Was: all agent tool access goes through MCP servers.)
- D4: LLM provider is swappable; default to free-tier or local to avoid billing. Refined by D16.
- D5: LangGraph Postgres checkpointer for resumable runs and HITL interrupts.
- D6: Drafts may only use facts from the user's profile (grounding check is mandatory). Design in D12.

### Fable review (2026-11-17)
A design review before any code was written. Each decision has its reason, so a later session does not undo it by accident. Full findings were given in chat; the outcomes are below and in the docs they changed.

- D7 Layout: flat `app/`, `mcp_servers/`, `tests/`, `frontend/` at the root; one uv project, not a package, no `src/`. Python 3.14. Why: it is an application, not a library, and every doc and command already assumed `app/`. 3.14 is what `uv init` pinned and every planned dependency has wheels for it. The first spec deletes `src/` and fixes `pyproject.toml` (`docs/tooling.md`).
- D8 Git: default branch is `main`. `.claude/` and this file are tracked. Why: the old `.gitignore` ignored both, so specs could never be committed and the whole spec workflow could not run.
- D9 MCP at the boundary only. `jobs_server` is the one process that talks to the open internet and holds no DB credentials. Profile, tracker and drafts are plain services. An outward-facing read-only `applyiq_server` comes in P1. Graph nodes get services through an injected deps object and never import a DB session. Why: in the MVP no model calls tools, so MCP around our own database was a subprocess wrapped round CRUD; stdio has no authenticated context to carry a user id; and the graph needed drafts, memories and scores that no server exposed. The boundary use gives a real isolation story and a better demo.
- D10 Graph runs are asyncio tasks inside the API process, one uvicorn worker, `thread_id` = run id. Progress goes to a Redis Stream and the SSE endpoint tails it with `Last-Event-ID` replay. Why: the plan had no worker, and tying a run to an open browser connection would kill it on a tab close.
- D11 Resume ingestion is a plain service pipeline, not a graph; the Profile page is the review. Why: it is a straight line with a form at the end. A checkpointed interrupt there adds a second human-in-the-loop mechanism for no gain. LangGraph is kept for fit scoring and application prep.
- D12 Grounding is cite-then-verify: facts with stable ids, drafts as segments citing fact ids, a rule-based guard for ids, numbers, dates, names and skills, then one model pass for supported / overstated / unsupported. Flagged segments block approval. Why: "zero invented facts" was not testable as written. This version is testable, cheap (one extra call per round), and maps directly onto the underlines in the design. Contract: `docs/application-prep.md` section 8.
- D13 One review decision per run through `POST /applications/{id}/review`. Drafts are saved as pending before the interrupt, and the interrupt is alone in its node. Why: there is one interrupt, so three per-draft endpoints did not map onto it; and LangGraph re-runs the interrupted node from its first line.
- D14 Memory (P1) holds preferences and corrections only, never facts; every write is confirmed by the user; 200 characters each, 30 per user, 400-token read budget. Why: a "fact" in memory would bypass grounding, and a model writing long-term memory unreviewed is a lasting injection path.
- D15 No vector store in the MVP; pgvector in the existing Postgres when memory arrives. ChromaDB dropped. Why: a one-page profile fits in a prompt, so nothing in the MVP needs retrieval. pgvector avoids an extra container on a small server and keeps deletes and user scoping in SQL.
- D16 LLM: Ollama for development, Groq for the hosted demo, Gemini only on its paid tier or with synthetic data. psycopg 3 is the only Postgres driver. Why: Gemini's free-tier terms say not to submit personal information and allow human review, and reports put free Flash at about 20 requests a day while one prepared application needs 5 to 13 calls. The LangGraph Postgres checkpointer uses psycopg 3, so using it for SQLAlchemy too avoids two drivers.
- D17 Job sources: Himalayas and Jobicy, plus Greenhouse and Ashby public boards for followed companies, plus pasted text. Remotive and Adzuna dropped. No arbitrary URL fetch in the MVP. Why: measured on the day. Remotive's public feed returned 17 jobs; Adzuna's free tier is for evaluation only. Board APIs use fixed hosts, so the MVP has no SSRF surface. Details: `docs/job-sources.md`.
- D18 Auth: no CORS anywhere, `__Host-` cookies in production, signed double-submit CSRF plus an Origin check, a logout endpoint, refresh cookie scoped to the auth path, refresh rotation with reuse detection. Why: the Vite proxy already makes development same-origin, and plain double-submit is weak against cookie injection.
- D19 Pasted jobs are private (`jobs.owner_user_id`). Why: the jobs table was shared with no owner, so one user's pasted text would have appeared in everyone's feed.
- D20 Scope and order: one spec per vertical slice; first deploy right after auth; the core (paste a job, score, prepare, approve) before the job feed; an MVP line in TRACKER.md. Why: the old plan was about 45 specs and 240 to 280 hours with deploy last and the core at Phase 6. The new MVP is about 170 hours.
- D21 PDFs are parsed with pypdf in a subprocess with a timeout. No AGPL or GPL dependencies. Why: PyMuPDF is AGPL, which is a problem for a public repo; the subprocess is the "sandboxed worker" the old doc named but never defined.
- D22 "Follow up" is computed on read from the stage date. No scheduler and no reminders table in the MVP. Why: nothing in the architecture could have fired a reminder.
- D23 Frontend simplifications: editing is a textarea styled as the paper (no `contentEditable`), pipeline cards move with buttons (no drag library), dark mode and "Show changes" are P1. Why: the owner is new to React, and these are the parts most likely to eat weeks.
- D24 LangSmith is off by default and hides inputs and outputs with real data. Why: a resume is personal data as a whole; regex masking does not cover it.
- D25 The public demo has a registration flag, a seeded account with a synthetic resume, and a global daily token budget. Why: a recruiter must see it work in under a minute, and an open sign-up on a free LLM tier would be drained.
- D26 Review subagents stay on Sonnet (owner's choice, cost). The owner can switch the session to Opus before `/code-review-feature` for a risky feature such as auth or Graph C. The reviewers preload the project skills so they check against the same conventions.

### Spec 001 decisions (2026-11-17)
- D27 structlog is the logging library, routed through the standard library so uvicorn's records are JSON too. Why: the allow-list, the event-name check and the redaction are processors in one chain; on bare `logging` they would be hand-written.
- D28 `pre-commit` moves from the scaffold spec to the CI and pre-commit bullet, as TRACKER.md already had it. `docs/tooling.md` was corrected. Why: the two docs disagreed, and the secret scan and branch guard belong with CI.
- D29 `.claude/hooks/format_file.py` is linted like any other file, with one `# noqa: S603` (fixed argument list, no shell). No rule is disabled globally. Why: excluding it would let one file escape the checks.
- D30 The logged `route` is rebuilt from the request: the text before the place where the matched route's own `path_regex` matches, plus the route's `path_format`. A path parameter in a router prefix would put a concrete value in that text, so then only the bare tail template is logged, and `prefix=` may not contain path parameters (fastapi-conventions). Why: FastAPI 0.163 resolves `include_router` lazily, so `scope["route"]` knows only its own tail and the full path is only in private internals. The first version (a shared `API_V1_PREFIX` constant added to the tail) was replaced after review because it logged the wrong route for nested routers and `include_router(prefix=...)`. A test checks every OpenAPI operation against the logged route.
- D31 `configure_logging` holds `httpx` and `httpcore` at WARNING. Why: they log every request URL with its query string at INFO, which can carry an API key or a search term. Also in SECURITY.md section 6.

### Spec 002 decisions (2026-11-20)
- D32 Licence rule scope: "No AGPL or GPL" covers code we link or ship. LGPL psycopg, used unmodified as a library, is allowed. An unmodified service container (Redis 8, AGPLv3/RSALv2/SSPL) is not a dependency in that sense. Why: psycopg is the driver D16 chose and the LangGraph checkpointer needs it; LGPL does not reach our code when the library is unmodified.
- D33 Postgres image: `pgvector/pgvector` on Postgres 18 from the start; the `vector` extension is not enabled until P1. Why: the P1 memory feature then needs one migration, not an image swap or a data move.
- D34 Checkpoint tables live in the `langgraph` schema, created by `AsyncPostgresSaver.setup()` at app startup in Graph C part 1 over a connection with `search_path=langgraph` (the saver has no schema parameter). Alembic reflects only the default schema and also filters the four table names (`app/db/autogenerate.py`). Why: a migration must never create, alter or drop them.
- D35 Test database: `<name>_test` on the same server, a rolled-back transaction per test (`join_transaction_mode="create_savepoint"`), a `db` marker, skip when Postgres is down, fail with `--require-services` (CI). Fixtures refuse a database whose name does not end in `_test`; migration tests use `<name>_migrations_test`. Why: a wrong URL must never wipe development data, and a missing CI service must never look like a pass.
- D36 `SessionDep` uses `Depends(get_session, scope="function")`, so the commit runs before the response. Why: with FastAPI's default `"request"` scope, a failed commit would follow a 200 the client already has.
- D37 `create_app` lives in `app/factory.py`; `app/main.py` only builds the instance. Why: `DATABASE_URL` is a required secret, and building the app at import would break test collection on a machine without `.env`.

## Conventions discovered
- Commands run from the repo root. Frontend commands use `npm --prefix frontend ...` so they match the permission rules.
- Library versions are newer than a model's memory. Check current docs before using an API (`docs/tooling.md` section 3 has the versions seen on 2026-11-17).
- Every new router must pass `tests/integration/test_route_template.py`, which requests each OpenAPI operation of the real app and checks the logged route equals its template. Do not put path parameters in `prefix=`.
- To log a new field, add its name to `ALLOWED_KEYS` in `app/core/logging.py`. Any other key is dropped silently, so a field that never shows up in the logs is probably missing from that set.

## Gotchas
- LangGraph's checkpointer creates its own tables. Alembic autogenerate will try to drop them unless `env.py` excludes them.
- A LangGraph join edge waits for every source node. On a redraft loop, send both draft nodes and let the unneeded one return `{}`.
- A node restarts from its first line when an interrupt resumes. Keep the interrupt alone in its node.
- The formatting hook does not remove unused imports (F401) on purpose: it used to delete an import between the edit that added it and the edit that used it. CI still reports them.
- A `Read(...)` deny rule in `.claude/settings.json` also blocks Write on that path. `.env.example` is readable only because of the `Read(!.env.example)` line after `Read(.env.*)`. Keep that order.
- `git branch -d` refuses after a squash merge. `/merge-feature` uses `-D` after confirming the PR state is MERGED.
- Safari drops `Secure` cookies on `http://localhost`. Development uses `COOKIE_SECURE=false` and no `__Host-` prefix.
- Free LLM tiers change without notice. Check the provider's own limits page before relying on a number in these docs.
- Job API search filters match loosely (a "machine learning" search returns unrelated roles). Filter again on our side.
- Plain Starlette routes (the dev-only `/api/v1/docs` and `/api/v1/openapi.json`) never get `scope["route"]` from FastAPI's router, so they log `route: "unmatched"`. APIRoutes are fine.
- A 500 from an unhandled exception is built by Starlette's outermost middleware, outside `RequestContextMiddleware`, so it has no `X-Request-ID` until the Phase 1 problem+json handler sets one (noted in TRACKER.md).
- The `phone` redaction pattern would hit digit runs in an ISO timestamp or a UUID, so `redact_pii` skips the server-generated `timestamp` and `request_id` keys.
- Records from other libraries now pass the same key allow-list as ours (their `event` message is kept, `exc_info`, `stack_info` and extras are dropped). If a library's field is missing from the logs, it is not in `ALLOWED_KEYS`.
- Tests import `create_app` from `app.factory`, never `app.main` (which builds the app from the real environment at import). A shell with a bad `APP_ENV` or no `DATABASE_URL` no longer breaks collection; it only fails `uv run uvicorn app.main:app` and `alembic`.
- Deferred from the spec 001 review, to pick up later: reject `LOG_LEVEL=DEBUG` when `APP_ENV=prod` and keep third-party loggers at WARNING by default (deploy bullet or the first spec that adds a library that logs request data); `APP_ENV` defaults to `dev`, so a prod deploy that forgets it serves the docs, and secrets must be `SecretStr` so a startup `ValidationError` does not print them (Phase 1 auth spec, with the `change-me` check); the `Server: uvicorn` header should be removed with `--no-server-header` or in Nginx (first deploy bullet). `HEAD /api/v1/health` returns 405 because FastAPI does not add HEAD to GET routes: if the deploy's load balancer probes with HEAD, add a HEAD route then.
- Postgres 18 images keep data under `/var/lib/postgresql`, not `/var/lib/postgresql/data`. Mounting the old path loses data when the container is recreated.
- SQLAlchemy 2.1 no longer installs greenlet; the async engine needs the `sqlalchemy[asyncio]` extra.
- `httpx.ASGITransport` does not run the app's lifespan. Test clients enter `application.router.lifespan_context(application)` themselves, or `app.state.session_factory` is missing.
- The Postgres password is in two places in `.env`: `POSTGRES_PASSWORD` (compose) and `DATABASE_URL` (app). Change both together.
- `docker compose down -v` deletes the database and Redis volumes. Plain `down` keeps them.
- `Settings` sets `hide_input_in_errors=True`: pydantic otherwise prints the raw input (the database URL with its password) in a `ValidationError`.
- Postgres error messages can quote user input (`invalid input syntax for type integer: "..."`, `Key (code)=(...) already exists`). `hide_parameters=True` only hides SQLAlchemy's own parameter dump. Never log or return a database exception's message; the Phase 1 problem+json handler must use fixed text.
- Claude Code permission rules and hooks are read at startup. Restart the session after editing `.claude/settings.json`.
- A force-rename in the owner's terminal (`git branch -M`) can move `main` under a running session: during spec 001 the feature branch was renamed to `main`, and two commits landed on it before anyone noticed. Run `git branch --show-current` before every commit. The `no-commit-to-branch` hook (CI and pre-commit bullet) will add a second guard.

## Open questions
- Where to host the live demo so it stays up through the job search? New AWS accounts get credits that expire in 6 to 12 months, not twelve free months of EC2. Decide before the "First deploy" bullet in Phase 1. Options to compare then: AWS on credits (keeps AWS on the resume), a student-pack credit host, or a small paid VM.
- Which drafting and judging models pass the grounding evaluation, locally (what fits in 16 GB) and on Groq's free tier? Decide in Phase 2 by running the evaluation, and record the result here.
- Confirm Groq's data controls (zero data retention setting) before real resumes go through the hosted demo.

## Current state
See TRACKER.md. Do not duplicate status here.
