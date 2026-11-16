# TRACKER: ApplyIQ

Legend: [ ] todo · [~] in progress · [x] done. Claude ticks items only when tests pass.

**Current phase: 0**

## Phase 0: Foundation
- [ ] Repo scaffold per ARCHITECTURE.md folder structure, uv + pyproject, ruff, mypy, pytest, pre-commit (incl. secret scan)
- [ ] docker-compose: api, postgres, redis, chroma
- [ ] Config (pydantic-settings), structured logging with redaction, health endpoint
- [ ] SQLAlchemy async session + Alembic initial migration
- [ ] CI (GitHub Actions): lint, type check, tests, pip-audit, frontend lint + build + vitest
- [ ] Frontend scaffold: Vite + React (JS), React Router, TanStack Query, ESLint/Prettier, Vitest, Vite dev proxy to /api
- [ ] Design system: `tokens.css` (colors, type scale, spacing, radius), self-hosted Schibsted Grotesk + Newsreader, base components (Button, Input, FitBadge, Rule, Rail layout), light/dark

## Phase 1: Auth and users
- [ ] Register/login/refresh with Argon2 + JWT rotation
- [ ] User-scoped repository pattern + IDOR tests
- [ ] SlowAPI rate limiting, security headers, CORS
- [ ] Audit log
- [ ] HttpOnly cookie auth + CSRF; Sign in / Create account pages; protected routes

## Phase 2: LLM layer
- [ ] Provider abstraction (Gemini, Ollama; Anthropic/OpenAI optional), task-based routing
- [ ] Token + cost logging per call
- [ ] Prompt file loader with versions
- [ ] LangSmith tracing with PII masking

## Phase 3: Resume ingestion (Graph A)
- [ ] PDF upload (size/MIME checks) to S3/local storage
- [ ] Parse + structured extraction into `Profile` schema
- [ ] Human review interrupt + profile edit API
- [ ] Profile page (upload, editable sections, low-confidence "Check this" states)
- [ ] Embed profile into Chroma

## Phase 4: MCP servers
- [ ] resume-server (get_profile, render_resume)
- [ ] jobs-server (search_jobs via 1-2 public APIs, get_job, fetch_job_url with SSRF guard, paste JD)
- [ ] tracker-server (create_app, update_stage, list_apps, set_reminder)
- [ ] MCP client adapter in app; tool allow-lists per node

## Phase 5: Job discovery and fit scoring (Graph B)
- [ ] Preferences API/UI
- [ ] Job ingestion + dedupe by content hash
- [ ] Parallel fit nodes + aggregate with reasons
- [ ] Ranked job feed API with cursor pagination
- [ ] Preferences page, Job feed (ruled list + FitBadge), Job detail with fit breakdown, Paste a job

## Phase 6: Application prep (Graph C)  ← core of the project
- [ ] Postgres checkpointer
- [ ] Plan -> parallel drafts -> grounding check -> critic loop (max 2)
- [ ] HITL interrupt: approve / edit / reject
- [ ] SSE streaming of progress
- [ ] Grounding test suite
- [ ] Application workspace: A4 paper view, grounded/flagged underlines, edit on paper, show changes, agent timeline (SSE), Approve / Edit / Reject, the one paper slide-in animation (reduced-motion safe)

## Phase 7: Memory
- [ ] Store corrections/preferences on edit/reject
- [ ] Retrieve top-k memories into Graph C within a token budget
- [ ] Memory view + delete in settings

## Phase 8: Pipeline and UI polish
- [ ] Pipeline board (keyboard-movable), stage moves (human-only), reminders
- [ ] Settings page (provider, memory list, export, delete account); empty and error states on every page; 360px + keyboard pass
- [ ] Company research node (optional tool calls, untrusted handling)
- [ ] Data export + account deletion

## Phase 9: Deploy and showcase
- [ ] Production Dockerfiles (non-root), Nginx serving `frontend/dist` + `/api` proxy, EC2 deploy, S3, backups
- [ ] README with architecture diagram, setup, screenshots
- [ ] 2-minute demo video, live link

## Log
- (date) phase N done: one-line summary
