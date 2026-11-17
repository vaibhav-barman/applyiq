---
description: Research a feature, create its branch, and write a spec in .claude/specs (use in plan mode)
argument-hint: <tracker task or feature description>
disable-model-invocation: true
---

Write a feature spec for: **$ARGUMENTS**

Use plan mode for research and drafting. Do not write any application code. Steps 1 to 6 are read-only and happen in plan mode. Step 7 changes files and git, so it runs only after I approve the plan (approval ends plan mode).

1. Run `git status` and `git branch --show-current`. If there are uncommitted changes, or the current branch is not `main`, stop and tell me.
2. Read CLAUDE.md and every doc it imports. Find the matching bullet in TRACKER.md (if none matches, say so and ask before continuing). If that phase names a `docs/` file, read it too.
3. Read `.claude/specs/_TEMPLATE.md`. Pick the next number (`NNN`, zero-padded) by looking at both the specs in `.claude/specs/` and the branches from `git branch -a --list '*feat/*'`, so a number used by an unmerged branch is not reused.
4. Explore the relevant code so the spec matches what actually exists. Use the skills that apply (langgraph-patterns, fastapi-conventions, applyiq-ui, mcp-server). For any library API the spec depends on, check its current documentation.
5. If anything important is ambiguous, ask me up to 3 questions before drafting.
6. Present the full spec as your plan, including the branch name `feat/NNN-short-name`, any new dependency (with its licence), and any manual check I will have to do.
7. After I approve:
   - update main: `git pull --ff-only` (skip if no remote is set);
   - create the branch from main: `git switch -c feat/NNN-short-name`;
   - save the spec to `.claude/specs/NNN-short-name.md` with `Status: Approved` and the branch name filled in;
   - mark the TRACKER.md bullet as `[~]` and add the spec path next to it;
   - commit on the branch: `docs(spec): NNN short-name` (no co-author lines).
8. Stop. Do not start implementing. Tell me to switch to accept-edits mode and run `/ship-feature NNN`.

A good spec is small enough to ship in one session and one PR. If it isn't, split the TRACKER bullet into several, say so, and write the spec for the first one only.
