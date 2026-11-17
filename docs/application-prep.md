# Application prep: Graph C, grounding, review, memory

Read this before writing any spec in TRACKER Phase 4 (core) or the memory items in P1. It is the contract for the part of ApplyIQ that matters most. If you want to change something here, propose the change first.

Library note: this was written against LangGraph 1.2 (November 2026). Check the current LangGraph docs for every API named here before using it. The list of things to verify is in section 12.

## 1. What a run is

A **run** is one execution of Graph C for one application. It starts when the user clicks "Prepare application" and ends when they approve or reject the drafts.

- One row in `runs` per run. One active run per application (unique partial index on `application_id` where status is `running` or `awaiting_review`).
- LangGraph `thread_id` is the **run id**. A new run after a rejection is a new thread, so history stays readable per run.
- Run statuses: `running`, `awaiting_review`, `completed`, `rejected`, `failed`.

## 2. Where the graph runs

There is no worker process in the MVP.

1. `POST /api/v1/applications/{id}/prepare` (with an `Idempotency-Key` header) creates the run row, moves the application to `Preparing`, starts the graph as an `asyncio` task in the API process, and returns `202` with the run id. If an active run already exists it returns that run instead of starting another.
2. The task streams the graph. For each progress event it appends an entry to a Redis Stream named `run:{run_id}:events` (capped at about 500 entries, 24 hour expiry).
3. `GET /api/v1/applications/{id}/stream` is the SSE endpoint. It checks that the application belongs to the caller, then tails the Redis Stream. On reconnect the browser sends `Last-Event-ID` and the endpoint replays from there. It sends a comment line as a heartbeat every 15 seconds.

Consequences to respect:
- The API runs as **one** uvicorn worker. Do not add workers without moving runs to a real queue.
- The run does not depend on the browser staying connected. Closing the tab does not stop it.
- On startup, any run still marked `running` is marked `failed` with code `run_interrupted`. The user starts a new run. A run in `awaiting_review` is untouched: its state is in the Postgres checkpoint and it resumes normally. Resuming a half-finished run from its checkpoint is a possible later improvement, not MVP.

## 3. State

A `TypedDict` in `app/graphs/state.py`. Small values and ids only, with two deliberate exceptions noted below.

| Key | Type | Written by | Notes |
|---|---|---|---|
| `run_id`, `application_id`, `user_id`, `job_id` | ids | input | |
| `facts` | list of Fact | `load_context` | Snapshot of the profile facts. Kept in state on purpose: a draft must be checked against the profile as it was when the run started, even if the user edits the profile later. |
| `job_brief` | JobBrief | `load_context` | Structured summary of the job. The raw job text never enters this graph. |
| `memories` | list of MemoryItem | `load_context` | Empty list until P1. |
| `plan` | TailoringPlan | `plan_tailoring` | |
| `resume_draft`, `cover_draft` | Draft or None | one draft node each | Two separate keys, so the two parallel nodes never write the same key. |
| `grounding` | dict kind -> GroundingReport | `ground` | |
| `critique` | dict kind -> Critique | `critique` | |
| `needs_redraft` | dict kind -> bool | `ground`, `critique`, `apply_decision` | Written by one node per step, never by the parallel nodes. |
| `round` | int | `critique` only | Automatic redraft rounds used. Maximum 2. |
| `human_rounds` | int | `apply_decision` only | "Request changes" rounds used. Maximum 2. |
| `feedback` | str or None | `apply_decision` | The user's change request. |
| `decision` | ReviewDecision or None | `human_review` | |

There is **no event list in state**. Progress goes out through the stream writer (section 7). An event list would be copied into every checkpoint.

## 4. Nodes and edges

```
load_context
    -> plan_tailoring
        -> draft_resume_bullets --+
        -> draft_cover_letter   --+--> ground -> critique -> (route)
                                                              |-- redraft needed and round < 2 --> both draft nodes
                                                              |-- otherwise --> persist_drafts -> human_review -> apply_decision -> (route)
                                                                                                                     |-- approve or reject --> END
                                                                                                                     |-- request changes and human_rounds < 2 --> both draft nodes
```

| Node | LLM | Tools | Does |
|---|---|---|---|
| `load_context` | no | none | Loads facts, job brief, memories through the injected deps object. |
| `plan_tailoring` | yes | none | Picks the facts that matter for this job, the angle, the length. Returns fact ids, not prose about the candidate. |
| `draft_resume_bullets` | yes | none | Returns a Draft made of segments (section 8). Returns `{}` at once if `needs_redraft["resume"]` is false and a draft exists. |
| `draft_cover_letter` | yes | none | Same for the letter. |
| `ground` | one call | none | Rule-based guard on both drafts, then one batched judge call. Sets `needs_redraft` for kinds with flags. |
| `critique` | one call at most | none | Judges tone, relevance, length and stated preferences for kinds that passed grounding. Skips the call if every kind is already flagged. Increments `round`. |
| `persist_drafts` | no | none | Saves both drafts as `pending` through deps. An upsert keyed by run, kind and version, so re-running it is harmless. |
| `human_review` | no | none | Contains only the interrupt. |
| `apply_decision` | no | none | Applies the human's decision through deps: marks drafts, moves the stage, writes the audit row. |

Rules that are easy to get wrong:

1. **Always run both draft nodes.** A fan-in edge from two nodes waits for both. If a redraft sent only one of them, the join would never fire. So the router always sends both, and a node whose draft is fine returns immediately without calling the model.
2. **Grounding runs after every draft, including the last.** A draft never reaches the human without a grounding report.
3. **One writer per key per step.** `round` and `needs_redraft` are never written by the parallel nodes.
4. **The loop always ends.** `round` stops automatic redrafts at 2. When the limit is hit with flags remaining, the draft goes to the human with those flags shown. Flags are never dropped silently.
5. **Drafting nodes get no tools and never see raw job text.**

## 5. The interrupt

- `human_review` holds nothing but the `interrupt(...)` call. LangGraph restarts the whole node when the run resumes, so anything placed before the call would run twice.
- The interrupt payload is small and serialisable: run id, draft ids, versions. The browser loads the drafts with a normal GET.
- Drafts are saved (`persist_drafts`) before the interrupt, with status `pending`. Saving a pending draft is not an external effect. Nothing the user has not approved is marked approved, and the stage does not move to `Ready` until `apply_decision`.
- Do not wrap `interrupt()` in a broad `try/except`.

## 6. Review and resume

One endpoint: `POST /api/v1/applications/{id}/review`. Per-draft approve, reject and edit endpoints do not exist.

Request body:

| Field | Meaning |
|---|---|
| `action` | `approve`, `request_changes`, or `reject` |
| `draft_versions` | The versions the user was looking at. A mismatch returns `409` (protects against a double click or a stale tab). |
| `edits` | Optional new text per kind, when the user edited on the paper. |
| `resolutions` | For each flagged segment: `removed`, `edited`, or `confirmed_true`. |
| `feedback` | Required for `request_changes`. |

The service, before resuming the graph:
1. Checks ownership and that the run is `awaiting_review`.
2. For `approve`: refuses with `422` and code `unresolved_flags` if any flagged segment has no resolution.
3. For `confirmed_true`: adds the statement to the profile as a new fact with `source = user` (a profile change, so it gets an audit row). This is how the profile grows without the model inventing anything.
4. For `edits`: stores the new text as a new draft version with `author = user`. The rule-based guard runs on it and its findings are shown as warnings. They do not block: the human is the authority on their own history.
5. Resumes with `Command(resume=decision)` inside a background task, then returns `202`.

After resume, `apply_decision` does the writes:
- approve: drafts `approved`, application stage `Ready`, run `completed`.
- reject: drafts `rejected`, application stage back to `Saved`, run `rejected`.
- request changes: `feedback` set, `needs_redraft` true for the named kinds, `human_rounds` plus one, back to the draft nodes. After 2 human rounds the action is refused with a plain message.

## 7. Progress events (the SSE contract)

Nodes emit progress with LangGraph's stream writer. The runner copies each one to the Redis Stream. The SSE endpoint sends:

```
id: <redis stream id>
event: progress
data: {"run_id": "...", "node": "draft_cover_letter", "code": "drafting_cover_letter", "round": 0, "ts": "2026-11-17T10:00:00Z"}
```

| `event` | When | `data` adds |
|---|---|---|
| `progress` | A node starts | `node`, `code`, `round` |
| `review` | The run reached the interrupt | `draft_ids` |
| `done` | Run completed or rejected | `status` |
| `error` | Run failed | `code` (a stable error code, never a stack trace) |

`code` is a fixed identifier such as `reading_job`, `planning`, `drafting_resume`, `drafting_cover_letter`, `checking_claims`, `reviewing_quality`, `redrafting`. The frontend maps each code to the copy in DESIGN.md section 5. Model-written text is never sent as a progress line.

`EventSource` cannot read HTTP status codes. If the stream errors, the frontend calls the refresh endpoint once and reopens the stream.

## 8. Grounding: cite, then verify

Goal: a draft may state only what the profile supports. The approach has two halves. The drafter must cite, and a checker that does not trust the drafter verifies.

### Facts
The profile is stored as structured data. Every atomic statement in it is a **Fact** with a stable id that is assigned once and kept across edits.

| Field | Example |
|---|---|
| `id` | `f_3k9x2a` |
| `kind` | `experience`, `project`, `education`, `skill`, `certification`, `summary` |
| `text` | "Built a retrieval pipeline over 40k support tickets with LangChain and Chroma" |
| `org`, `title`, `start`, `end` | set where they apply |
| `numbers`, `skills` | extracted lists: `["40k"]`, `["LangChain", "Chroma"]` |
| `source` | `resume` or `user` |

### Segments
A drafting node returns a list of **Segments**, not a block of prose.

| Field | Meaning |
|---|---|
| `id` | position in the draft |
| `text` | one sentence or one bullet |
| `kind` | `claim` (says something about the candidate), `job_reference` (says something about the job or company), `connective` (greeting, transition, sign-off) |
| `fact_ids` | required for `claim` |
| `job_quote` | required for `job_reference`: the words from the job brief it relies on |

### Step 1: rule-based guard (no model)
Runs on every segment. Any failure flags the segment.

| Rule | Check |
|---|---|
| G1 | Every cited `fact_id` exists in the run's fact snapshot. |
| G2 | Every number and every date in a `claim` appears in a cited fact. |
| G3 | Every organisation name and job title in a `claim` appears in a cited fact. |
| G4 | Every skill term in a `claim` appears in a cited fact. Skill terms come from a lexicon built from the profile's skills plus the job brief's skills, with a small alias map (for example Postgres and PostgreSQL). |
| G5 | A skill that is in the job brief but not in the profile must never appear in a `claim`. This is the commonest fabrication: repeating the job's requirements as experience. |
| G6 | A `connective` contains no number, no lexicon skill, no organisation name. If it does, it is treated as an uncited claim. |
| G7 | A `job_reference` quote is found in the job brief. |
| G8 | No URL or email address that is absent from both the profile and the job. |

### Step 2: support judge (one model call for both drafts)
Input: each `claim` segment with the full text of its cited facts. Output per segment: `supported`, `overstated`, or `unsupported`, with a one-line reason. Temperature 0, structured output. The rubric names the usual inflations: ownership ("led" where the fact says "worked on"), scale, duration, seniority, and two facts merged into a claim that neither supports.

The judge uses the `judge` task model, which should differ from the drafting model when the provider offers a second one.

### Verdicts and the interface
Final verdict per segment: `supported`, `overstated`, `unsupported`, or `uncited`.
- `supported`: solid underline. Selecting it shows the cited facts.
- anything else: dashed underline and an inline note with the reason. The user must resolve it (remove, edit, or confirm as true) before "Approve draft" works.

### Redraft
When segments are flagged and rounds remain, the drafter receives only the flagged segments with their reasons and is told to fix or drop them. It does not rewrite the whole document.

### How this fails, and what limits the damage
| Failure | Mitigation |
|---|---|
| The drafter cites a real fact but the sentence says more than the fact. | G2 to G5 catch added entities. The judge catches inflation of degree. Neither is perfect, which is why the human sees every underline. |
| An alias is missing ("JS" against "JavaScript") and a true claim is flagged. | A false flag costs the user one click. Failing closed is the right direction. Grow the alias map from real false flags. |
| Soft claims that cannot be checked ("strong communicator"). | Allowed only as `connective` text with no entities. The critic is told to keep them rare. |
| The judge agrees with the drafter too easily (same model family). | A different judge model where possible, temperature 0, and the evaluation in the next section measures it instead of assuming it. |
| A small local model returns broken structure or made-up fact ids. | Validate, retry once with the error, then fail the node. G1 flags made-up ids. Record which models pass the evaluation. |
| Sentence-by-sentence output reads stiffly. | The critic judges flow. Segments are joined into paragraphs for display. |
| The profile itself is wrong. | Out of scope. The profile review screen is the control. |

### Test plan (`tests/grounding/`)
1. **Fixtures.** Three synthetic profiles and four synthetic jobs. No real personal data.
2. **Guard tests (no model, run always).** A hand-written set of drafts with seeded fabrications in six classes: invented employer, inflated number, changed date, inflated title, job-skill echo, merged facts. The guard must flag every seeded fabrication in the first five classes. A set of clean drafts must pass with no more than the agreed number of false flags.
3. **Judge evaluation (`@pytest.mark.llm`, skipped by default).** The same set, measuring how many overstated and merged-fact cases the judge catches, per model. Target at least 90 percent. The numbers go in the README.
4. **End-to-end evaluation (`@pytest.mark.llm`).** Run Graph C on each profile and job pair. Assert that no segment marked `supported` in the final draft violates G1 to G8.

The honest claim for the README is: zero guard-level violations on the fixed set, plus a measured judge rate. Not "the model never hallucinates".

## 9. Prompt-injection controls inside this graph

- Raw job text is never in a Graph C prompt. It is reduced to a `JobBrief` once, at ingestion, by a model call with no tools (see SECURITY.md).
- Brief fields are short, typed, length-capped strings. They are still attacker-controlled, so they are wrapped in untrusted delimiters with a per-call nonce wherever they enter a prompt.
- No node in this graph has tools. The company research node (P1) is the only tool-using node in the system, and it never receives profile data.
- `tests/graphs/` includes poisoned job fixtures (instructions to add a URL, to claim a skill, to score 100). The tests assert that the final drafts contain no attacker text and that every guard rule still holds.

## 10. Model calls per run

| Path | Calls | Rough tokens |
|---|---|---|
| Passes first time | plan 1, drafts 2, judge 1, critic 1 = 5 | 12k to 15k |
| Worst case (2 automatic redraft rounds) | 1 + 3 x (2 + 1 + 1) = 13 | about 35k |

The provider layer rate-limits below the hosted limit (Groq's free tier allowed about 8k tokens a minute per model when this was written), so a typical run takes one to two minutes on the hosted free tier and a worst-case run about five. Fit scoring is separate: two calls per job, cached by job content hash, profile version, prompt version and model.

## 11. Memory (P1, not MVP)

- Kinds: `preference` ("prefer short letters") and `correction` ("never mention the gap year"). There is no `fact` kind. A fact belongs in the profile, where grounding can see it.
- Written only after the human confirms. When the user edits a draft or requests changes, a model call proposes at most two memories from the user's own diff and feedback. That call never sees job text. The interface asks "Remember this?" with Save and Dismiss.
- Limits: 200 characters per memory, 30 active memories per user. A new memory that is nearly identical to an existing one (cosine similarity above 0.9) replaces it.
- Read in `load_context`: all pinned preferences, plus the 5 corrections most similar to the job brief, within a 400 token budget.
- Stored in Postgres with a pgvector column. The embedding model and its dimension are fixed in config; changing them is a migration.
- In prompts, memories appear in a labelled block as the user's preferences. They can shape style and what to leave out. They can never add a claim.

## 12. Verify against current LangGraph docs before coding

- `interrupt()`, `Command(resume=...)`, and the `response_schema` option that validates the resume value.
- How to inject dependencies into nodes (runtime context). Nodes must not import a DB session.
- The stream writer for custom progress events, and whether to stream with `astream(stream_mode=[...])` or the newer `stream_events` API.
- `AsyncPostgresSaver`: its `setup()` call, its connection pool settings with psycopg 3, and how to delete a thread's checkpoints when a user deletes an application or their account.
- Fan-out and fan-in edge behaviour, to confirm rule 1 in section 4.
