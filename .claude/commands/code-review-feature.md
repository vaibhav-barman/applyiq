---
description: Independent code + security review of a feature branch, then open the pull request
argument-hint: <spec number>
disable-model-invocation: true
---

Review spec **$ARGUMENTS** and open its pull request.

1. Make sure I'm on the spec's feature branch and the spec status is `Verified`. If not, stop and tell me.
2. Check that a pull request is possible: `git remote get-url origin` and `gh auth status`. If either fails, tell me now (setup steps are in `docs/tooling.md` section 8). The review can still run; the push and PR in step 8 cannot.
3. Get the change: `git diff main...HEAD`, plus `git status --short` for anything uncommitted or untracked. Uncommitted work is not part of the review; ask me what to do with it.
4. Run two reviews in parallel, each in a fresh context:
   - `code-reviewer` subagent: correctness, spec compliance, RULES.md, design tokens for UI.
   - `security-reviewer` subagent: SECURITY.md checklist, prompt injection, auth scoping, secrets, PII in logs.
5. Combine their findings into one list, ordered Blocker > Major > Minor. Drop anything that isn't real.
6. Ask me which findings to fix. Fix the ones I pick, re-run all checks, commit.
7. When I'm happy, close out the docs on the branch:
   - set the spec status to `Done` (it reaches `main` only when the PR merges) and record the review outcome in "Implementation notes";
   - tick the task `[x]` in TRACKER.md and add a line to its Log;
   - add any new decision or gotcha to MEMORY.md (the file at the repo root);
   - commit `docs: close spec $ARGUMENTS`.
8. Ask me before pushing. Then:
   - `git push -u origin <branch>`;
   - write the PR body to a temporary file outside the repo and open the PR with `gh pr create --base main --head <branch> --title "feat($ARGUMENTS): <spec name>" --body-file <file>`. Body: spec link, summary, acceptance-criteria checklist with results, manual checks I confirmed, test commands run, review findings fixed. No AI attribution lines.
   - write the PR link into the spec's `PR:` field, commit, and push again.
9. Give me the PR link. Tell me to wait for CI and then run `/merge-feature $ARGUMENTS`. Do not merge.
