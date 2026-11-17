# Architecture: ApplyIQ

Deeper designs live in `docs/` and are read on demand: `docs/application-prep.md` (Graph C, grounding, review, memory), `docs/job-sources.md`, `docs/tooling.md`.

## 1. Stack
| Layer | Choice |
|---|---|
| Language | Python 3.14 |
| API | FastAPI, Pydantic v2, async, SlowAPI rate limiting |
| DB | PostgreSQL, SQLAlchemy 2 (async) with the psycopg 3 driver, Alembic migrations |
| Cache | Redis: rate limits, run event streams for SSE, small caches. No job queue. |
| Vector store | None in the MVP. pgvector in the same Postgres when memory lands (P1). |
| Agents | LangGraph + LangChain, Postgres checkpointer (also psycopg 3) |
| Tools | One FastMCP server, `jobs_server`, at the internet boundary. An outward-facing `applyiq_server` in P1. |
| LLM | Provider abstraction: Ollama (dev default), Groq (hosted default), Gemini optional on the paid tier |
| Observability | Structured JSON logs. LangSmith traces optional, inputs and outputs hidden with real data. |
| Frontend | React 18 + Vite (JavaScript, no TypeScript), React Router, TanStack Query, CSS Modules + CSS variables, SSE via EventSource. See DESIGN.md |
| Infra | Docker, docker-compose, Nginx (serves built frontend + proxies /api), one small VM |

## 2. Component diagram
```
Browser: React SPA (static build, SSE for streaming)
        |
   Nginx (TLS, rate limit per IP, serves /  ->  frontend/dist, proxies /api -> FastAPI, buffering off for SSE)
        |
   FastAPI app (JSON API only, one uvicorn worker)
     |      |        |
     |      |        +-- Postgres (users, profiles, jobs, applications, drafts, runs, checkpoints)
     |      +----------- Redis (rate limits, run:{id}:events streams)
     |
     +-- services  <-- routers call services; graph nodes call services through an injected deps object
     |
     +-- LangGraph runtime (runs as asyncio tasks inside the API process)
     |     |-- Graph B: Job Fit Scoring
     |     |-- Graph C: Application Prep (human-in-the-loop)
     |
     +-- LLM provider (Ollama | Groq | Gemini)
     |
     +-- MCP client adapter
           |-- jobs-server (stdio subprocess; the only component that calls the open internet; no DB credentials)
                 tools: search_jobs, get_board_jobs    (P1: fetch_job_url)
```
Where MCP is used and where it is not:
- **MCP**: anything that reaches the open internet (job APIs, later URL fetch) runs in `jobs_server`. The app calls it through the MCP client adapter. In P1 the company research node lets a model call these tools under a per-node allow-list.
- **Not MCP**: profile, applications, drafts, fit scores and memories are plain services and repositories. They are our own database; wrapping them in a subprocess adds cost and shows nothing.
- **P1**: `applyiq_server` exposes read-only tools over the same services so an external client such as Claude Desktop can query the pipeline.

Graph nodes never import a DB session or a repository. They receive a typed deps object (services) through LangGraph's runtime context. This keeps nodes testable with fakes.

## 3. Data model (Postgres)
- users(id, email, password_hash, created_at)
- refresh_tokens(id, user_id, token_hash, family_id, expires_at, revoked_at, created_at)
- profiles(id, user_id, data JSONB, status[needs_review|confirmed], version, updated_at)  -- structured resume (Pydantic `Profile`); every fact inside has a stable id
- preferences(id, user_id, data JSONB)
- jobs(id, owner_user_id NULL, source, external_id, title, company, location, remote, description, brief JSONB, apply_url, source_url, posted_at, content_hash)  -- unique(source, external_id); `owner_user_id` NULL = shared public listing, set = private pasted job
- fit_scores(id, user_id, job_id, score, reasons JSONB, profile_version, prompt_version, model, created_at)  -- unique(user_id, job_id, profile_version, prompt_version)
- applications(id, user_id, job_id, stage, stage_changed_at, notes, created_at, updated_at)  -- unique(user_id, job_id)
- runs(id, application_id, user_id, status[running|awaiting_review|completed|rejected|failed], idempotency_key, error_code, started_at, finished_at)  -- one active run per application
- drafts(id, application_id, run_id, kind[resume|cover_letter], version, author[agent|user], segments JSONB, content, status[pending|approved|rejected], created_at)
- llm_calls(id, user_id, application_id NULL, run_id NULL, task, provider, model, input_tokens, output_tokens, cost_usd, latency_ms, created_at)
- audit_log(id, user_id, action, detail JSONB, created_at)  -- detail holds ids and enums, never free text
- P1: memories(id, user_id, kind[preference|correction], text, embedding vector, status[active|dismissed], source_application_id, created_at)

Not in the MVP: a `reminders` table. "Follow up" is computed on read from `stage = Applied` and `stage_changed_at` older than `FOLLOW_UP_DAYS`.

LangGraph's checkpoint tables are created by the checkpointer's own setup call, not by Alembic. Alembic's autogenerate must be told to ignore them, or it will try to drop them. They hold draft text, so deleting an application or an account also deletes that run's checkpoints.

## 4. Pipelines and graphs
**Resume ingestion (a plain service pipeline, not a graph).** validate upload -> parse PDF in a subprocess with a timeout -> extract structured `Profile` (Pydantic structured output, facts get stable ids, low-confidence fields marked) -> save with `status = needs_review`. The Profile page is the human review; saving it sets `confirmed`.

**Job brief (a single model call at ingestion, no tools).** Raw job text -> `JobBrief` (must-have skills, nice-to-have skills, seniority, remote and location constraints, salary, a short role summary). Cached by content hash. Everything downstream uses the brief.

**Graph B: Job Fit Scoring.** Three parallel nodes: `skills_match` (LLM), `seniority_match` (LLM), `constraints_check` (plain code over the brief and preferences: remote, location, salary, deal-breakers). Join node: aggregate score + reasons for and against. A deal-breaker hit caps the score and records the reason. Two model calls per job, cached.

**Graph C: Application Prep.**
load_context -> plan_tailoring -> draft_resume_bullets + draft_cover_letter (parallel) -> ground (rule-based guard, then one judge call) -> critique -> loop back to both draft nodes (max 2 rounds) -> persist_drafts (pending) -> human_review (`interrupt`) -> apply_decision. On approve: drafts approved, stage to Ready. On request changes: redraft with the feedback (max 2 human rounds). On reject: stage back to Saved.
Full contract: `docs/application-prep.md`.

State is a typed `TypedDict` per graph. The checkpointer is Postgres, so a run waiting for review survives a restart. `thread_id` is the run id.

## 5. Memory design
- Short-term: the LangGraph checkpoint per thread (run id).
- Long-term (P1): `memories` table with a pgvector column. Kinds are `preference` and `correction` only; facts belong in the profile. A model proposes a memory from the user's own edit or feedback, and it is saved only when the user confirms. Read at the start of Graph C: pinned preferences plus the top 5 corrections by similarity, within a 400 token budget. Limits: 200 characters each, 30 active per user.

## 6. LLM abstraction
`llm/provider.py` exposes `get_chat_model(task)`, where task is `extract`, `score`, `draft` or `judge`. Each task maps to a provider and model in config; no model name appears in code.
- Every call uses structured output with a small, flat Pydantic schema, validated, with one retry that feeds the validation error back.
- A client-side rate limiter sits below the provider's limit; 429s are retried with backoff; an optional fallback model can be configured per task.
- Every call writes a row to `llm_calls` (tokens, estimated cost, latency) with the user id and, when there is one, the application and run ids.
- Per-user and global daily token budgets are enforced before a call is made.
- Results that are pure functions of their input (job brief, fit score) are cached by content hash, profile version, prompt version and model.
- A resume is personal data. A provider may be used with real profiles only if its terms do not allow training on or human review of inputs. Gemini's free tier fails this test; see SECURITY.md.
- Tests use a fake chat model. Real-model tests are marked `llm` and skipped by default.

## 7. API surface (v1)
All routes are under `/api/v1`.
- POST /auth/register, /auth/login, /auth/refresh, /auth/logout; GET /auth/me
- GET/PUT /profile, POST /profile/resume (upload)
- GET/PUT /preferences
- GET /jobs?query=&remote=&cursor= , GET /jobs/{id}, POST /jobs/paste, POST /jobs/{id}/score
- POST /applications, GET /applications, GET /applications/{id}, PATCH /applications/{id}/stage
- POST /applications/{id}/prepare (starts Graph C, Idempotency-Key header, returns 202 + run id)
- GET /applications/{id}/stream (SSE)
- GET /applications/{id}/drafts
- POST /applications/{id}/review (approve | request_changes | reject, with optional edits)
- DELETE /account
- GET /health
- P1: GET/DELETE /memories, POST /memories/{id}/confirm, GET /account/export, POST /boards
Pagination: cursor-based. Errors: RFC 7807 problem+json with a stable `code`.

## 8. Folder structure
```
applyiq/
  app/
    main.py
    api/            routers/, deps.py, schemas/
    core/           config, security, logging, rate_limit
    db/             models/, repositories/, session.py, migrations/
    llm/            provider.py, prompts/
    graphs/         fit_scoring.py, application_prep.py, state.py, deps.py
    grounding/      facts, guard rules, judge
    mcp_clients/    adapter to the MCP servers
    services/       business logic
  mcp_servers/
    jobs_server/    server.py, sources/
    applyiq_server/ (P1)
  frontend/         React + Vite app
    src/api/        fetch client + TanStack Query hooks
    src/components/ src/pages/  src/styles/ (tokens.css)  src/lib/
  tests/            unit/, integration/, graphs/, grounding/, fixtures/
  docs/             on-demand design docs
  docker/  deploy/
  pyproject.toml  uv.lock  alembic.ini  docker-compose.yml
```
One uv project at the root, not a package, no `src/` directory. See `docs/tooling.md`.

## 9. Deployment
Local: docker-compose for postgres and redis; the API with `uvicorn --reload` and the frontend with `npm run dev`, using Vite's proxy for `/api`, so the browser sees one origin in development too.

Production: one small VM running docker-compose (nginx, api, postgres, redis). The frontend is built with `vite build` and served by Nginx from the same origin as the API. Notes that are easy to miss:
- One uvicorn worker, because graph runs live in the API process.
- Nginx turns proxy buffering off for the SSE route and passes the real client IP; uvicorn trusts forwarded headers only from the Nginx container.
- Secrets come from the environment. Resumes are stored on a private volume behind a storage interface; an S3 backend can replace it without touching callers.
- The first deploy happens right after auth (TRACKER Phase 1), so every later phase ships to a live URL.
- Host: not decided. New AWS accounts get time-limited credits, not twelve free months, so pick a host that will still be up during the job search. See MEMORY.md, open questions.
