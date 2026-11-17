---
description: Check a feature PR is mergeable, merge it, delete the branch, and sync main
argument-hint: <spec number>
disable-model-invocation: true
---

Merge the pull request for spec **$ARGUMENTS**.

1. Find the PR for the spec's branch: `gh pr view <branch> --json number,url,state,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup`.
2. Report its state in a few lines: CI checks (pass/fail/pending/none reported), merge conflicts, review status.
3. Stop if any check failed, there are conflicts, or checks are still running. For failures or conflicts, explain the cause and suggest the fix (for conflicts: `git switch <branch> && git merge main`, resolve, re-run checks, push). Do not force-merge or bypass checks.
4. If no checks are reported at all:
   - if `.github/workflows/` exists on `main`, CI should have run. Treat it as not ready: wait, or tell me why the workflow did not start;
   - if there is no workflow on `main` yet (only before the CI spec has merged), say clearly that this merge has no CI behind it, run the local checks from `/ship-feature` step 4 on the branch, show me the result, and ask whether to go ahead.
5. If everything is green, ask me to confirm the merge. Then:
   - `git switch main`;
   - `gh pr merge <number> --squash --delete-branch` (deletes the remote branch);
   - `git pull --ff-only`;
   - confirm with `gh pr view <number> --json state` that the state is `MERGED`. Only then delete the local branch if it still exists, with `git branch -D <branch>`. (`-d` refuses after a squash merge, because the branch's own commits are not on `main`.)
   - `git fetch --prune`.
6. Do not commit anything to `main`. The spec was already marked `Done` on the branch, so it arrives with the merge.
7. Confirm: PR merged, branches deleted, main up to date. Tell me the next step (`/next`).
