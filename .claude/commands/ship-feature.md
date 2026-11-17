---
description: Implement an approved spec on its feature branch, task by task, with tests
argument-hint: <spec number, e.g. 004>
disable-model-invocation: true
---

Implement spec **$ARGUMENTS** from `.claude/specs/`.

1. Open the spec file starting with `$ARGUMENTS`. If its status is not `Approved` or `In progress`, stop and tell me.
2. Switch to the branch named in the spec (`git switch feat/$ARGUMENTS-...`). If it doesn't exist or I'm on `main`, stop and tell me. Never implement on `main`.
3. Set the spec status to `In progress`.
4. Work through the spec's Implementation Tasks in order. For each task:
   - implement it, following RULES.md, SECURITY.md, and the relevant skill;
   - before using a library API, check its current documentation (RULES.md, workflow rule 8);
   - write or update its tests;
   - run the checks that apply:
     - backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy app mcp_servers && uv run pytest -q` (leave out a directory that does not exist yet);
     - frontend, once `frontend/` exists: `npm --prefix frontend run lint && npm --prefix frontend test -- --run`;
   - tick the task in the spec;
   - commit with a conventional message (no co-author lines).
5. A dependency that is not listed in the spec needs my approval before you add it. Tell me the package, why, and its licence.
6. If the spec turns out to be wrong or incomplete, stop and explain. Do not silently change the design. Propose a spec edit and wait for my approval.
7. When all tasks are done and checks pass, set status to `Implemented`, fill in the spec's "Implementation notes", and commit.
8. Do not push. Finish with a short summary: what changed, files touched, anything left. Tell me to run `/test-feature $ARGUMENTS`.
