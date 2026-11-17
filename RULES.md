# RULES: how Claude Code must work in this repo

## Workflow
1. Work only on the current phase in TRACKER.md. Do not start the next phase without being asked.
2. Every feature follows the spec flow in CLAUDE.md: /create-spec -> /ship-feature -> /test-feature -> /code-review-feature -> /merge-feature. Specs live in `.claude/specs/`.
3. One spec at a time. One spec covers one TRACKER bullet, which is one vertical slice. TRACKER.md is ticked only by /code-review-feature after review.
4. If a requirement is unclear or docs conflict, stop and ask. Never guess silently.
5. Never mark a task done if tests fail or it is partially implemented.
6. Record any new architectural decision in MEMORY.md (Decisions) before coding it. MEMORY.md means the file at the repo root.
7. Before a spec in a phase that names a `docs/` file in TRACKER.md, read that file.
8. The libraries here are newer than a model's memory (see `docs/tooling.md` section 3). Before using a LangGraph, LangChain, FastMCP, SQLAlchemy or uv API, check its current documentation. Do not write an API call from memory.
9. Claude cannot see the browser. Never report a visual, 360px, keyboard or reduced-motion check as passed unless the owner confirmed it. Write the automated tests you can, then hand the owner a checklist.

## Code standards
- Python 3.14, full type hints, `ruff` + `ruff format`, `mypy --strict` on `app/` and `mcp_servers/`.
- Async everywhere in the API and DB layers.
- Pydantic models for every request, response, LLM structured output, and graph state.
- No business logic in routers. Routers -> services -> repositories / MCP client.
- Graph nodes never import a DB session or a repository. They call services through the injected deps object.
- One Postgres driver: psycopg 3.
- Config only via `app/core/config.py` (pydantic-settings). No `os.getenv` elsewhere. A new variable is added to `.env.example` in the same commit.
- No hard-coded model names, URLs, or secrets outside config.
- Functions short and single-purpose. No dead code, no commented-out code.
- Prompts in `app/llm/prompts/`, never inline strings in logic.

## Frontend standards
- React + Vite, JavaScript (JSX). Function components and hooks only.
- Follow DESIGN.md tokens exactly. Only colors from `tokens.css`; never add a hue.
- CSS Modules + CSS variables. No Tailwind, no component library, no inline style objects except for dynamic values.
- Server data through TanStack Query hooks in `src/api/`; components do not call `fetch` directly.
- Never use `dangerouslySetInnerHTML` or `contentEditable`. Render LLM text and job text as plain text.
- ESLint + Prettier. Vitest + React Testing Library for components with logic.
- Keep components under ~150 lines; add a short comment explaining any non-obvious React pattern (owner is learning React).
- Every new screen must work at 360px width and with keyboard only. See workflow rule 9 for who verifies it.

## Testing
- pytest + pytest-asyncio. Every feature ships with tests.
- LLM calls are mocked in unit tests. A small set of marked `@pytest.mark.llm` tests hit a real model and are skipped by default.
- Grounding tests: fixed synthetic profiles + jobs; the rule-based guard must catch every seeded fabrication. See `docs/application-prep.md` section 8.
- Every route has a test for another user's resource.
- Test fixtures are synthetic. No real resume, name, email or phone number in the repo.
- Coverage target: 80% on `app/services`, `app/graphs` and `app/grounding`.

## Git
- The default branch is `main`.
- One branch per spec: `feat/NNN-short-name`, created from an up-to-date `main` by /create-spec.
- Never commit directly to `main`. `main` changes only through merged PRs.
- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`). Small commits.
- Never commit `.env`, secrets, resumes, or real personal data.
- `.claude/` (commands, agents, skills, hooks, specs, settings.json) and MEMORY.md are tracked. Only `.claude/settings.local.json` is ignored.
- Do not add AI co-author or attribution lines to commits or PR descriptions.
- Push and open the PR only in /code-review-feature, after asking. Merge only via /merge-feature, after CI passes and I confirm.
- Merge strategy: squash merge, then delete the remote and local branch.
- Never force-push, bypass failing checks, skip hooks with `--no-verify`, or merge with conflicts.

## Dependencies
- Ask before adding a new dependency. Prefer the standard library and what is already in the stack.
- Pin exact versions (`==`) in `pyproject.toml` and commit `uv.lock`.
- No AGPL or GPL dependencies. Check the licence before proposing a package (for example use pypdf, not PyMuPDF).
- Never add TypeScript, Tailwind, Redux, a drag-and-drop library, or a UI kit. Frontend deps beyond React, React Router, TanStack Query, and @fontsource need approval.

## Things to never do
- Never implement auto-submission of applications or scraping of sites that forbid it.
- Never let an LLM output trigger a state change (stage move, draft approval, profile fact, memory, send, delete) without a human approval step.
- Never give tools to a drafting, scoring or judging node. Never put profile data in the context of a node that has network tools.
- Never send a real resume to an LLM provider or tracing service whose terms allow training on it or human review of it.
- Never log resume contents, job text, prompts, model output, tokens, passwords, or API keys.
- Never disable tests, type checks, or lint rules to make something pass.
