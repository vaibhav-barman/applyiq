# Spec NNN: <feature name>

Status: Draft | Approved | In progress | Implemented | Verified | Done
Tracker task: <phase N, bullet text>
Branch: feat/NNN-short-name
Depends on: <spec numbers that must be merged first, or "none">
Docs read: <the docs/ file for this phase, and the library docs checked>
PR: <link, filled in by /code-review-feature>

## 1. Goal
One or two sentences: what the user can do after this ships.

## 2. Scope
In scope:
-
Out of scope (explicitly not doing):
-

## 3. Design
### Backend
Endpoints (method, path, request/response schema), services, DB changes + migration, MCP tools touched.

### Agents (if any)
Graph name, state fields added, nodes, edges, interrupts, tools allowed per node (usually none), prompts added (file names).
LLM calls added: which task (`extract`, `score`, `draft`, `judge`), how many per user action, and what is cached.

### Frontend (if any)
Pages/components, which DESIGN.md tokens and components, loading/empty/error states, copy for buttons and messages.

### New dependencies (need approval)
Package, exact version, licence, why the standard library or the current stack is not enough. "None" if none.

## 4. Security
Trusted vs untrusted inputs, auth scoping, rate limits, CSRF, PII handling, new log lines. Reference SECURITY.md sections.

## 5. Acceptance criteria
Each one must be testable.
- [ ] AC1:
- [ ] AC2:

## 6. Implementation tasks
Ordered, each small.
- [ ] T1:
- [ ] T2:

## 7. Test plan
Unit, integration, graph, grounding. Which test proves which AC.

## 8. Manual checks (owner)
What only a person in a browser can confirm: 360px, keyboard only, reduced motion, visual match to DESIGN.md. Filled with the owner's confirmations by /test-feature. "None" for backend-only specs.

## 9. Open questions
-

## 10. Implementation notes
(Filled in by /ship-feature: decisions made, deviations, follow-ups.)
