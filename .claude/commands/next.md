---
description: Show where the project stands and what to do next
---

Read TRACKER.md, the specs in `.claude/specs/`, `git status`, `git branch`, `git remote -v`, and (if `gh auth status` succeeds) `gh pr list`. In under 10 lines tell me:
- the current branch and whether there are uncommitted changes;
- the current phase and how many bullets are left in it;
- any unfinished spec (status `In progress`, `Implemented`, or `Verified`, or `Done` with an open PR) and its branch/PR; unfinished work comes first;
- leftover feature branches that are already merged and can be deleted;
- anything missing for the workflow itself: no `origin` remote, `gh` not logged in, or no CI workflow yet;
- the next command to run, e.g. `/create-spec <task>`, `/ship-feature 007`, or `/merge-feature 006`.
Don't change any files.
