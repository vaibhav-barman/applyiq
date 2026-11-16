# Design: ApplyIQ

## 1. Concept: "the paper and the desk"
ApplyIQ produces documents: resumes and cover letters. So the interface is a quiet black-and-white desk, and the one memorable element is **the paper**: every draft renders as a real A4 page sitting on the desk, set in a book serif, with each claim underlined and linked to the profile fact it came from. Everything else stays out of the way so the page carries the identity.

Spend boldness in one place (the paper). Keep the rest disciplined.

## 2. Tokens

### Color (strictly monochrome)
| Name | Hex | Use |
|---|---|---|
| ink | #000000 | Text, primary buttons, the fit numeral, focus rings |
| paper | #FFFFFF | Pages, cards, inputs |
| desk | #F2F2F2 | App background behind the paper |
| rule | #D4D4D4 | Borders and dividers (1px) |
| graphite | #6B6B6B | Secondary text, metadata |
| smudge | #E6E6E6 | Hover and selected states |

No accent color. State is shown with weight, fill, and pattern, never hue:
- Fit score: strong = solid black badge with white number; medium = black outline; weak = graphite text. Number always shown.
- Grounded claim: solid underline. Ungrounded or flagged claim: dashed underline plus an inline note.
- Errors: black text with a 2px left rule, plain explanation, and the fix.

Dark mode inverts ink and paper; desk becomes #141414 only in dark mode.

### Type
- **UI: Schibsted Grotesk** (400, 500, 700). Labels, navigation, tables, buttons. Tabular figures for scores and dates (`font-variant-numeric: tabular-nums`).
- **Documents: Newsreader** (400, 400 italic, 600). Only inside the paper: resume bullets and cover letters, so drafts look like documents.
- Self-host both via `@fontsource`. No monospace anywhere.
- Scale (1.25 ratio, 16px base): 12.8 / 16 / 20 / 25 / 31.25 / 39. Body line-height 1.5 for sans, 1.65 for serif. Line length under 72ch.
- Sentence case everywhere. No all-caps labels, no letter-spaced eyebrows, no single-word highlights in headings.

### Space and shape
- 4px base grid: 4, 8, 12, 16, 24, 32, 48, 64.
- Radius: 0 on the paper (it is a sheet), 6px on inputs and buttons, 999px only on fit badges. Hierarchy decides radius; there is no single radius for everything.
- Shadow: only the paper gets one (a soft two-layer page shadow) to lift it off the desk. Nothing else has a shadow; panels use 1px rules.

### Motion
- One orchestrated moment: when a draft finishes, the paper slides up onto the desk and the grounding underlines draw in one by one (about 600ms total).
- Everything else moves only in response to the user (opening a panel, moving a pipeline card).
- Respect `prefers-reduced-motion`: no slide, underlines appear instantly.

## 3. Layout
Left-aligned throughout. A narrow left rail for navigation; content on a 12-column grid with a 1200px max width.

```
+------+----------------------------------------------+
| rail |  Job feed                       [Paste a job] |
|      |  ------------------------------------------- |
| Feed |  ( 86 ) ML Engineer, Remote · Acme            |
| Pipe |         Matches LangGraph, FastAPI, remote    |
| Prof |  ------------------------------------------- |
| Pref |  ( 64 ) AI Engineer · Beta Labs               |
|      |         Missing: Kubernetes in production     |
+------+----------------------------------------------+
```
Feed is a list with rules between rows, not a grid of identical cards.

Application workspace (the signature screen):
```
+------+-----------+---------------------------+---------+
| rail | job + fit |        [ A4 paper ]       | agent   |
|      | breakdown |   Dear hiring team,       | timeline|
|      |           |   ___claim___ (source)    | ------- |
|      |           |                           | facts   |
|      |           |   [Approve] [Edit] [Reject]  used  |
+------+-----------+---------------------------+---------+
```
On mobile the three columns stack: job summary, paper, then timeline in a collapsible section.

## 4. Screens
1. **Sign in / Create account**: one centered column, the wordmark set in Newsreader, two fields.
2. **Profile**: parsed resume as editable sections. Low-confidence fields show a dashed outline and "Check this".
3. **Preferences**: roles, remote only, locations, salary floor, deal-breakers.
4. **Job feed**: ruled list, fit badge, top two reasons, filters, "Paste a job".
5. **Job detail**: description plus fit breakdown (skills, seniority, constraints) with reasons for and against.
6. **Application workspace**: described above. Edits happen on the paper directly. "Show changes" toggles a diff against the previous version (strikethrough for removed, underline for added).
7. **Pipeline**: columns Saved, Preparing, Ready, Applied, Interview, Offer, Rejected. Overdue follow-ups get a solid black dot and "Follow up".
8. **Settings**: model provider, memory list with delete, data export, delete account.

## 5. Copy rules
- Name things by what the user does: "Prepare application", "Approve draft", "Move to Applied".
- The same action keeps its name: "Approve draft" gives the toast "Draft approved".
- Progress lines are plain: "Reading the job", "Drafting cover letter", "Checking every claim against your profile".
- Empty states say what to do next: "No jobs yet. Set your preferences or paste a job description."
- Errors say what happened and how to fix it, with no apologies.
- No arrows appended to button text, no middle-dot meta strings except job location lines.

## 6. Accessibility floor
WCAG AA contrast (graphite on paper passes at body size), visible 2px ink focus rings, full keyboard navigation including the pipeline (move with buttons, not only drag), labels on every input, live region for streaming progress, responsive to 360px.

## 7. Frontend architecture
- React 18 + Vite, **JavaScript (JSX), not TypeScript**.
- React Router for pages; TanStack Query for server state; no global state library.
- Plain CSS with CSS variables for tokens (`src/styles/tokens.css`) and CSS Modules per component. No Tailwind, no UI kit.
- Streaming via `EventSource` (SSE) from `/api/v1/applications/{id}/stream`.
- Components small and presentational; data fetching lives in `src/api/` hooks.
- Folder: `frontend/src/{api, components, pages, styles, lib}`.

## 8. API conventions
- JSON, snake_case, ISO-8601 UTC timestamps, UUID ids, versioned under `/api/v1`.
- Cursor pagination: `?limit=&cursor=` returning `next_cursor`.
- Errors use problem+json with a stable `code`; the frontend maps codes to plain messages.
- Idempotency-Key header on `POST /applications/{id}/prepare`.

## 9. Prompt design
- Prompts live in `app/llm/prompts/` as versioned files, never inline.
- Structured output via Pydantic for every extraction and scoring call.
- Drafting prompts receive only profile facts, job text, and memories, each labeled by source.
- Job text is wrapped in untrusted-content delimiters (see SECURITY.md).
- Low temperature for extraction and scoring, moderate for drafting.
