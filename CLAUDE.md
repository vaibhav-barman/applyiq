# ApplyIQ

AI job-application copilot: understands your resume, discovers jobs, scores fit, drafts tailored applications, tracks the pipeline. A human approves everything before it leaves the system.

Read these before doing any work:

@PRD.md
@ARCHITECTURE.md
@RULES.md
@SECURITY.md
@MEMORY.md
@TRACKER.md
@DESIGN.md

`MEMORY.md` here always means the file at the repo root: the project's decision log, tracked in git. It is not Claude Code's own auto-memory.

## Docs to read on demand
These are not loaded automatically. Read the one that matches the work before writing its spec.
- `docs/tooling.md`: layout, commands, environment, CI, pre-commit. For Phase 0 and whenever a command fails.
- `docs/application-prep.md`: Graph C, grounding, review, SSE events, memory. For Phase 4 and the memory work in P1.
- `docs/job-sources.md`: job APIs, their limits and terms, the adapter interface. For Phase 6.

## Spec-driven workflow (every feature goes through this)
One spec = one TRACKER bullet = one branch `feat/NNN-short-name` = one pull request.
1. `/create-spec <tracker task>` in plan mode: research and draft the spec as the plan. After I approve the plan: create the branch from main, save `.claude/specs/NNN-name.md` (status Approved), commit. No code.
2. `/ship-feature NNN` in accept-edits mode: implement the spec's tasks on the branch, with tests and small commits.
3. `/test-feature NNN`: prove every acceptance criterion with a test (test-engineer subagent), and give me the manual checklist for anything only a browser can show.
4. `/code-review-feature NNN`: independent review (code-reviewer + security-reviewer subagents), fix, update docs, push, open the PR.
5. `/merge-feature NNN`: when CI is green and there are no conflicts, squash-merge, delete the remote and local branch, sync main.
`/next` shows where things stand.

Spec status flow: Draft -> Approved -> In progress -> Implemented -> Verified -> Done (set on the branch at PR time; reaches main when merged).

These commands run only when I type them. Do not start one on your own.

## First-time setup (owner, once)
`/code-review-feature` and `/merge-feature` need a GitHub remote and a logged-in `gh`. Steps are in `docs/tooling.md` section 8. Until they are done, those two commands stop and say so.

## Ground rules
- No code without an Approved spec. Small fixes may skip this only if I say so.
- The spec is the contract. If it is wrong, stop and propose a spec edit; don't drift silently.
- Use the project skills in `.claude/skills/` for the area you touch (langgraph-patterns, fastapi-conventions, applyiq-ui, mcp-server).
- Check current library docs before using an API; versions here are newer than your memory (RULES.md, workflow rule 8).
- If a doc and the code disagree, stop and ask.
- When a decision is made, write it in MEMORY.md with the reason, so the next session knows why.
