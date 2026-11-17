# TRACKER: ApplyIQ

Legend: [ ] todo · [~] in progress · [x] done. Claude ticks items only when tests pass.

One bullet = one spec = one branch = one pull request. Each bullet is a vertical slice that can ship in one session. If a bullet turns out too big while writing its spec, split it there and update this file on the spec's branch.

Hours are estimates at about 15 hours a week. Total to the MVP line: about 170 hours, 12 to 14 weeks with slack for coursework.

**Current phase: 0**

## Phase 0: Foundation (about 18 h)
Read `docs/tooling.md` first.
- [x] Backend scaffold: flat layout per ARCHITECTURE.md section 8 (delete `src/`, fix `pyproject.toml` per `docs/tooling.md`), uv dependency groups, ruff, mypy, pytest, config (pydantic-settings), allow-list structured logging, `GET /api/v1/health` (spec: `.claude/specs/001-backend-scaffold.md`)
- [ ] Local services and database: docker-compose (postgres, redis), SQLAlchemy async session on psycopg 3, Alembic baseline migration
- [ ] CI and pre-commit: GitHub Actions (lint, format check, types, tests, lock check, pip-audit, gitleaks), pre-commit config including the secret scan and no-commit-to-main
- [ ] Frontend scaffold: Vite + React (JS), React Router, TanStack Query, ESLint/Prettier, Vitest, Vite dev proxy to /api, frontend job added to CI
- [ ] Design system: `tokens.css` (colors, type scale, spacing, radius), self-hosted Schibsted Grotesk + Newsreader, base components (Button, Input, FitBadge, Rule, Rail layout). Light theme only.

## Phase 1: Auth and first deploy (about 30 h)
- [ ] Auth API: users + refresh_tokens tables, register/login/refresh/logout/me, Argon2id, access JWT + rotating refresh with reuse detection, HttpOnly cookies
- [ ] Request hardening: signed double-submit CSRF + Origin check, SlowAPI limits in Redis, trusted proxy headers, problem+json error handler (it must also set `X-Request-ID` on 500s from unhandled exceptions, which Starlette builds outside `RequestContextMiddleware`), audit log table and helper
- [ ] User-scoped repository pattern with a reusable "another user's resource" test helper
- [ ] Sign in and Create account pages, protected routes, fetch client with CSRF header and single-flight refresh
- [ ] First deploy: production Dockerfiles (non-root), Nginx serving `frontend/dist` and proxying `/api` (SSE-safe, security headers), TLS, deploy script, on the chosen host

## Phase 2: LLM layer (about 10 h)
- [ ] Provider abstraction (Ollama, Groq; Gemini optional), task routing, structured output with one validated retry, client-side rate limiter, retry on 429, fake model for tests, prompt file loader with versions
- [ ] Usage and budgets: `llm_calls` table, per-user and global daily token budgets, optional LangSmith tracing with inputs and outputs hidden

## Phase 3: Profile (about 18 h)
- [ ] Resume upload: size, page and magic-byte checks, storage interface with a local backend, pypdf parsing in a subprocess with a timeout
- [ ] Extraction into the `Profile` schema with stable fact ids and low-confidence marks; profile GET/PUT API; `needs_review` and `confirmed` status
- [ ] Profile page: upload, editable sections, dashed "Check this" states

## Phase 4: Core, prepare one application (about 53 h)  ← the centre of the project
Read `docs/application-prep.md` first.
- [ ] Paste a job (private to the user) + job-brief extraction (no tools, untrusted handling) + minimal job detail page
- [ ] Preferences API and page; Graph B fit scoring (two LLM nodes + a code constraints node in parallel, join, deal-breaker cap); fit breakdown on the job detail page
- [ ] Graph C part 1: state, Postgres checkpointer, load_context, plan, parallel draft nodes returning cited segments; run row, background runner, Redis event stream, SSE endpoint
- [ ] Graph C part 2: grounding (rule-based guard + support judge), critic, redraft loop (max 2); grounding fixtures and the guard test suite
- [ ] Graph C part 3: persist pending drafts, human_review interrupt, `POST /review` (approve, request changes, reject, edits, flag resolutions), stage moves, audit rows
- [ ] Application workspace: A4 paper view, solid and dashed underlines with source facts, agent timeline over SSE, Approve / Edit / Reject, edit as a paper-styled textarea, the one paper slide-in animation (reduced-motion safe)
- [ ] Injection red-team fixtures (poisoned jobs) and the `llm`-marked end-to-end grounding evaluation

## Phase 5: Pipeline (about 10 h)
- [ ] Applications API (create, list, get, human-only stage moves) and the pipeline board: seven columns, "Move to" buttons, "Follow up" computed from days since Applied

## Phase 6: Job discovery (about 20 h)
Read `docs/job-sources.md` first.
- [ ] `jobs_server` (FastMCP): Himalayas and Jobicy adapters behind one interface, per-source rate limits and caching; MCP client adapter in the app
- [ ] Ingestion with dedupe by content hash, brief extraction for new jobs, ranked feed API with cursor pagination, budget-aware scoring
- [ ] Job feed page: ruled list, FitBadge, top two reasons, filters, source credit, "Paste a job"
- [ ] Company boards: Greenhouse and Ashby adapters, "Follow a company board" in the feed

## Phase 7: Showcase (about 14 h)
- [ ] Demo readiness: seeded demo account with a synthetic resume and prepared results, registration flag, global budget kill switch, account deletion
- [ ] Polish pass: empty and error states on every page, 360px and keyboard pass (owner-confirmed), copy check against DESIGN.md section 5
- [ ] README with architecture diagram, setup, screenshots and the grounding evaluation table; 2-minute demo video; live link

---------- MVP line: everything above is the finished, deployed product ----------

## P1: after the MVP (about 60 h, pick in this order)
- [ ] Long-term memory: pgvector, human-confirmed memories from edits and feedback, retrieval into Graph C within a token budget, memory list and delete in Settings
- [ ] Company research node: the one tool-calling node, tools from `jobs_server` under an allow-list, no profile data in its context
- [ ] `fetch_job_url` with the full SSRF guard (SECURITY.md section 7)
- [ ] `applyiq_server`: read-only MCP server over the services, usable from Claude Desktop
- [ ] "Show changes" diff on the paper; dark mode
- [ ] Settings page extras: provider choice, data export
- [ ] Embedding pre-filter for the feed, to score fewer jobs

## P2: later
- [ ] Remote MCP server with OAuth 2.1
- [ ] Interview-prep notes, email-draft export
- [ ] S3 storage backend, nightly encrypted Postgres dump

## Log
- 2026-11-17 Fable design review applied: docs and Claude Code config corrected, scope cut and reordered. No code yet.
- 2026-11-17 Spec 001 backend scaffold done: flat layout, pinned dependencies, typed settings, allow-list JSON logging, request-id middleware, `GET /api/v1/health`. 132 tests, reviewed by a code and a security reviewer. Pending merge.
