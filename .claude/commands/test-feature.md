---
description: Verify a feature against every acceptance criterion in its spec
argument-hint: <spec number>
disable-model-invocation: true
---

Verify spec **$ARGUMENTS** is really done.

1. Make sure I'm on the spec's feature branch (not `main`). Read the spec. List every acceptance criterion.
2. Use the `test-engineer` subagent to:
   - map each criterion to at least one test, and write missing tests (happy path, edge cases, errors, another user's resource);
   - run the full suite for backend and, once it exists, frontend.
3. For LangGraph features, also run the graph tests and the grounding tests (`uv run pytest tests/graphs tests/grounding -q`).
4. For UI features, you cannot see the browser, so split the checks:
   - automated, written as tests: labels on inputs, focus order and keyboard operation of each control, the disabled and error states, that no animation class is applied under `prefers-reduced-motion`;
   - manual, for me: give me a short numbered checklist (what to open, what to do, what I should see) covering 360px width, keyboard-only use, and reduced motion as DESIGN.md requires. Wait for me to confirm each item. Do not mark these as passed yourself.
5. Report a table: criterion | test(s) or manual check | pass/fail/waiting for owner.
6. If anything fails, fix it (or ask, if the fix changes the spec), then re-run.
7. When every automated check passes and I have confirmed the manual ones, set the spec status to `Verified`, record my confirmations under "Manual checks" in the spec, commit the new tests, and tell me to run `/code-review-feature $ARGUMENTS`.
