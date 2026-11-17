---
name: mcp-server
description: How to build and test ApplyIQ's FastMCP servers and the app's MCP client adapter. Use when adding or changing tools under mcp_servers/ or app/mcp_clients/.
---

# MCP servers for ApplyIQ

Version note: the project uses FastMCP 4 and the MCP SDK 2. Most examples online are for older versions. Check the current FastMCP docs before writing server, client or test code.

## Where MCP is used
MCP sits at the boundary, not inside the app.
- `mcp_servers/jobs_server/`: the only component that calls the open internet. It wraps the job-source adapters (and, in P1, `fetch_job_url`). It has no database credentials and no user data.
- `mcp_servers/applyiq_server/` (P1): read-only tools over the app's services, for external clients such as Claude Desktop.
- Profile, applications, drafts, fit scores and memories are plain services. Do not build MCP tools for the app's own database access.

## Server layout
`mcp_servers/<name>_server/server.py` builds the FastMCP instance. Job sources live in `mcp_servers/jobs_server/sources/`, one small class each behind the shared interface in `docs/job-sources.md`. Tools are small typed functions with clear docstrings (the docstring is what a model reads).

## Tool rules
- Inputs and outputs are Pydantic models or simple typed values. Return structured data, not prose.
- `jobs_server` tools take no user identity. They take a query and filters and return public listings.
- For `applyiq_server` (P1): the server is started for one user, with that user's id fixed in its own configuration. A tool never accepts `user_id` as an argument, because a model fills in tool arguments.
- No tool writes to the app's data, sends email, submits forms, or contacts third parties beyond the configured job APIs.
- Every adapter uses a fixed HTTPS base URL from config, a timeout, a response size cap, a per-source rate limiter set below the published limit, and a cache. Respect each API's terms (`docs/job-sources.md`).
- Company board names are validated against `^[a-z0-9][a-z0-9-]{0,62}$` and placed into a fixed host. That is the only user-supplied part of any outbound URL in the MVP.
- Descriptions are untrusted text: strip HTML to plain text, cap the length, never return raw HTML.
- `fetch_job_url` (P1) ships only with the full guard in SECURITY.md section 7.

## Transport
Local development and the first deployment use stdio: the app starts `jobs_server` as a subprocess. Give that subprocess only the environment variables it needs; never the database URL or auth secrets. The remote server (P2) uses streamable HTTP with OAuth scopes.

## Client adapter
`app/mcp_clients/` opens the session, lists tools, validates each result into the app's own Pydantic models, and exposes a per-node allow-list for the one node that may let a model call tools (company research, P1). In the MVP the app calls tools directly from services; no model chooses tools. Log tool name, duration, and success, never the arguments.

## Tests
Call tools in-process with the FastMCP test client. Mock the HTTP layer; tests never call a real job API. Test validation errors, the board-name pattern, HTML stripping, rate-limit and 429 handling, and that one failing source does not break a search.
