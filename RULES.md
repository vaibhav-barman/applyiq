# RULES: how Claude Code must work in this repo

## Workflow
1. Work only on the current phase in TRACKER.md. Do not start the next phase without being asked.
2. Every feature follows the spec flow in CLAUDE.md: /create-spec -> /ship-feature -> /test-feature -> /code-review-feature. Specs live in `.claude/specs/`.
3. One spec at a time. TRACKER.md is ticked only by /code-review-feature after review.
4. If a requirement is unclear or docs conflict, stop and ask. Never guess silently.
5. Never mark a task done if tests fail or it is partially implemented.
6. Record any new architectural decision in MEMORY.md (Decisions) before coding it.

## Code standards
- Python 3.12, full type hints, `ruff` + `ruff format`, `mypy --strict` on `app/`.
- Async everywhere in the API and DB layers.
- Pydantic models for every request, response, LLM structured output, and graph state.
- No business logic in routers. Routers -> services -> repositories / MCP clients.
- Config only via `app/core/config.py` (pydantic-settings). No `os.getenv` elsewhere.
- No hard-coded model names, URLs, or secrets outside config.
- Functions short and single-purpose. No dead code, no commented-out code.
- Prompts in `app/llm/prompts/`, never inline strings in logic.

## Frontend standards
- React + Vite, JavaScript (JSX). Function components and hooks only.
- Follow DESIGN.md tokens exactly. Only colors from `tokens.css`; never add a hue.
- CSS Modules + CSS variables. No Tailwind, no component library, no inline style objects except for dynamic values.
- Server data through TanStack Query hooks in `src/api/`; components do not call `fetch` directly.
- Never use `dangerouslySetInnerHTML`. Render LLM text as plain text.
- ESLint + Prettier. Vitest + React Testing Library for components with logic.
- Keep components under ~150 lines; add a short comment explaining any non-obvious React pattern (owner is learning React).
- Check every new screen at 360px width and with keyboard only.

## Testing
- pytest + pytest-asyncio. Every feature ships with tests.
- LLM calls are mocked in unit tests. A small set of marked `@pytest.mark.llm` tests hit a real model and are skipped by default.
- Grounding tests: fixed sample profiles + jobs; assert drafts contain no facts absent from the profile.
- Coverage target: 80% on `app/services` and `app/graphs`.

## Git
- One branch per spec: `feat/NNN-short-name`, created from an up-to-date `main` by /create-spec.
- Never commit directly to `main`. `main` changes only through merged PRs.
- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`). Small commits.
- Never commit `.env`, secrets, resumes, or real personal data.
- Do not add AI co-author or attribution lines to commits or PR descriptions.
- Push and open the PR only in /code-review-feature, after asking. Merge only via /merge-feature, after CI passes and I confirm.
- Merge strategy: squash merge, then delete the remote and local branch.
- Never force-push, bypass failing checks, or merge with conflicts.

## Dependencies
- Ask before adding a new dependency. Prefer the standard library and what is already in the stack.
- Pin versions in `pyproject.toml` (uv).
- Never add TypeScript, Tailwind, Redux, or a UI kit. Frontend deps beyond React, React Router, TanStack Query, and @fontsource need approval.

## Things to never do
- Never implement auto-submission of applications or scraping of sites that forbid it.
- Never let an LLM output trigger a state change (stage move, send, delete) without a human approval step.
- Never log resume contents, tokens, passwords, or API keys.
- Never disable tests, type checks, or lint rules to make something pass.
