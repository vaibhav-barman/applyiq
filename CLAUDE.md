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

## Spec-driven workflow (every feature goes through this)
One spec = one branch `feat/NNN-short-name` = one pull request.
1. `/create-spec <tracker task>` in plan mode: research, create the branch from main, save `.claude/specs/NNN-name.md` (status Approved), commit. No code.
2. `/ship-feature NNN` in accept-edits mode: implement the spec's tasks on the branch, with tests and small commits.
3. `/test-feature NNN`: prove every acceptance criterion with a test (test-engineer subagent).
4. `/code-review-feature NNN`: independent review (code-reviewer + security-reviewer subagents), fix, update docs, push, open the PR.
5. `/merge-feature NNN`: when CI is green and there are no conflicts, squash-merge, delete the remote and local branch, sync main.
`/next` shows where things stand.

Spec status flow: Draft -> Approved -> In progress -> Implemented -> Verified -> Done (set on the branch at PR time; reaches main when merged).

## Ground rules
- No code without an Approved spec. Small fixes may skip this only if I say so.
- The spec is the contract. If it is wrong, stop and propose a spec edit; don't drift silently.
- Use the project skills in `.claude/skills/` for the area you touch (langgraph-patterns, fastapi-conventions, applyiq-ui, mcp-server).
- If a doc and the code disagree, stop and ask.
