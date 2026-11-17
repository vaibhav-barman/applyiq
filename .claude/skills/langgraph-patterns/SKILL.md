---
name: langgraph-patterns
description: How ApplyIQ builds LangGraph agents (state, nodes, interrupts, checkpointer, deps injection, streaming, tests). Use whenever creating or changing anything in app/graphs/ or app/grounding/.
---

# LangGraph patterns for ApplyIQ

`docs/application-prep.md` is the contract for Graph C. Read it before touching that graph. This skill is the short checklist for any graph.

Version note: the project uses LangGraph 1.2 or newer. Its interrupt, streaming and dependency-injection APIs differ from older examples. Check the current LangGraph docs for each API before you write the call.

## State
- One state class per graph in `app/graphs/state.py`, a `TypedDict`.
- Store ids and small values. Load large data inside nodes. The one planned exception is the profile fact snapshot in Graph C.
- Parallel nodes must write different keys. If two nodes can write the same key in one step, that key needs a reducer; prefer separate keys.
- Counters (`round`, `human_rounds`) are written by exactly one node.
- No event list in state. Progress goes through the stream writer.

## Nodes
- One node = one job, a plain async function returning only the keys it changes.
- Nodes never import a DB session, a repository, or `app.db`. They receive a typed deps object (`app/graphs/deps.py`) through LangGraph's runtime context and call services on it. Tests pass fakes.
- LLM calls go through `app/llm/provider.get_chat_model(task)` with structured output on a small flat Pydantic model.
- Prompts load from `app/llm/prompts/<name>.vN.md`.
- Untrusted text (job brief fields, anything from the internet) is wrapped in `<untrusted_..._NONCE>` tags before it reaches a prompt. Raw job text is used only by the job-brief extraction call.

## Tools
- In the MVP no node has tools.
- When a node does get tools (company research, P1), they come only from the MCP client adapter (`app/mcp_clients/`) under a per-node allow-list, and that node's context contains no profile data.

## Control flow
- Parallel work: fan out from one node, join in a node that reads all results.
- A join edge from several nodes waits for all of them. On a loop, send every branch again and let a branch with nothing to do return `{}` at once. Never route to only one branch of a join.
- Loops need a counter in state and a hard maximum (2).
- Human approval uses `interrupt()` in a node that contains nothing else. The node restarts from its first line on resume, so anything before the call would run twice.
- Writes that must happen before the pause (saving pending drafts) go in their own node before it and must be idempotent. Writes that follow the decision go in a node after it.
- Resume with `Command(resume=...)`. Do not wrap `interrupt()` in a broad `try/except`.

## Persistence
- Compile with the Postgres checkpointer (psycopg 3). `thread_id` = run id. Never use the in-memory saver outside tests.
- The checkpointer creates its own tables with its setup call. Alembic must ignore them.
- Deleting an application or account deletes that run's checkpoints.

## Running and streaming
- Graph C runs as an asyncio task in the API process, started by the prepare endpoint. It does not depend on an open browser connection.
- Nodes emit progress with the stream writer as `{node, code, round}`. The runner copies each event to the Redis Stream `run:{run_id}:events`; the SSE endpoint tails that stream. Format: `docs/application-prep.md` section 7.
- Progress `code` values are fixed identifiers. Never stream model-written text as progress.

## Testing
- Use the fake chat model returning fixed structured outputs, and fake deps.
- Test: each node in isolation, the full graph path, the loop limit, that both draft nodes run on a redraft, that the interrupt fires before any approval or stage change, and that resuming with each decision reaches the right end state.
