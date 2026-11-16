# Architecture: ApplyIQ

## 1. Stack
| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI, Pydantic v2, async, SlowAPI rate limiting |
| DB | PostgreSQL, SQLAlchemy 2 (async), Alembic migrations |
| Cache / queue | Redis (rate limits, cache, simple job queue) |
| Vector store | ChromaDB (profile chunks, job embeddings) |
| Agents | LangGraph + LangChain, Postgres checkpointer |
| Tools | MCP servers built with FastMCP |
| LLM | Provider abstraction: Gemini (default), Ollama (local), Anthropic/OpenAI optional |
| Observability | LangSmith traces, structured JSON logs |
| Frontend | React 18 + Vite (JavaScript, no TypeScript), React Router, TanStack Query, CSS Modules + CSS variables, SSE via EventSource. See DESIGN.md |
| Infra | Docker, docker-compose, Nginx (serves built frontend + proxies /api), AWS EC2 (S3 for resume files) |

## 2. Component diagram
```
Browser: React SPA (static build, SSE for streaming)
        |
   Nginx (TLS, rate limit, serves /  ->  frontend/dist, proxies /api -> FastAPI)
        |
   FastAPI app (JSON API only) ------------- Redis
     |   |   |
     |   |   +-- Postgres (users, profiles, jobs, applications, memory, checkpoints)
     |   +------ ChromaDB (profile + job embeddings)
     |
   LangGraph runtime
     |-- Graph A: Resume Ingestion
     |-- Graph B: Job Fit Scoring
     |-- Graph C: Application Prep (HITL)
     |
   MCP client (adapter layer)
     |-- jobs-server     (search_jobs, get_job, fetch_job_url)
     |-- resume-server   (parse_resume, get_profile, render_resume)
     |-- tracker-server  (create_app, update_stage, list_apps, set_reminder)
```
All tools reach agents through the MCP client. Agents never touch the DB directly.

## 3. Data model (Postgres)
- users(id, email, password_hash, created_at)
- profiles(id, user_id, data JSONB, version, updated_at)  -- structured resume (Pydantic `Profile`)
- preferences(id, user_id, data JSONB)
- jobs(id, source, external_id, title, company, location, remote, description, url, posted_at, content_hash)  -- unique(source, external_id)
- fit_scores(id, user_id, job_id, score, reasons JSONB, model, created_at)
- applications(id, user_id, job_id, stage, notes, created_at, updated_at)
- drafts(id, application_id, kind[resume|cover_letter], content, status[pending|approved|rejected], version)
- memories(id, user_id, kind[preference|correction|fact], text, embedding_id, created_at)
- reminders(id, application_id, due_at, done)
- audit_log(id, user_id, action, detail JSONB, created_at)

## 4. LangGraph graphs
**Graph A: Resume Ingestion.** parse_pdf -> extract_structured (Pydantic structured output) -> validate -> user_review (interrupt) -> save_profile + embed.

**Graph B: Job Fit Scoring.** Parallel nodes: skills_match, seniority_match, constraints_check (remote/location/salary/deal-breakers). Join node: aggregate score + reasons. Conditional edge: deal-breaker hit -> score capped, reason recorded.

**Graph C: Application Prep.**
load_job + profile + memories -> company_research (tool calls, optional) -> plan_tailoring -> draft_resume_bullets + draft_cover_letter (parallel) -> grounding_check (every claim must map to a profile fact) -> critic -> loop back to draft (max 2 rounds) -> `interrupt` for human approval -> on approve: save drafts, move stage to Ready. On edit: store the correction in memory.

State is a typed `TypedDict`/Pydantic model per graph. Checkpointer is Postgres so runs survive restarts and support time-travel debugging.

## 5. Memory design
- Short-term: the LangGraph checkpoint per thread (application id).
- Long-term: `memories` table + Chroma. Written when the user edits or rejects a draft or states a preference. Read at the start of Graph C, top-k by similarity, capped at a fixed token budget.

## 6. LLM abstraction
`llm/provider.py` exposes `get_chat_model(task)`. Task-based routing: cheap/local model for classification and extraction, stronger model for drafting. Every call logs tokens and estimated cost against the application id.

## 7. API surface (v1)
- POST /auth/register, /auth/login, /auth/refresh
- PUT/GET /profile, POST /profile/resume (upload)
- PUT/GET /preferences
- GET /jobs?query=&remote=&cursor= , POST /jobs/paste, POST /jobs/{id}/score
- POST /applications, GET /applications, PATCH /applications/{id}/stage
- POST /applications/{id}/prepare (starts Graph C), GET /applications/{id}/stream (SSE)
- POST /applications/{id}/drafts/{draft_id}/approve | reject | edit
Pagination: cursor-based. Errors: RFC 7807 problem+json.

## 8. Folder structure
```
applyiq/
  app/
    api/            routers, deps, schemas
    core/           config, security, logging, rate_limit
    db/             models, session, migrations/
    llm/            provider, prompts/
    graphs/         resume_ingestion.py, fit_scoring.py, application_prep.py, state.py
    mcp_clients/    adapter to the MCP servers
    services/       business logic
  mcp_servers/
    jobs_server/  resume_server/  tracker_server/
  frontend/         React + Vite app
    src/api/        fetch client + TanStack Query hooks
    src/components/ src/pages/  src/styles/ (tokens.css)  src/lib/
  tests/            unit/, integration/, graphs/, grounding/
  docker/  deploy/
```

## 9. Deployment
docker-compose for local (api, postgres, redis, chroma, mcp servers); run the frontend with `npm run dev` and Vite's proxy to `/api`. Production: the frontend is built with `vite build` and served by Nginx from the same origin as the API (no cross-origin cookies). EC2 + Nginx + Docker, secrets from env/SSM, resumes in S3 with private ACL, nightly Postgres dump to S3.
