---
name: applyiq-ui
description: Build ApplyIQ React screens and components in the black-and-white "paper and desk" design system. Use for any work in frontend/, including new pages, components, styling, or UI copy.
---

# ApplyIQ UI

DESIGN.md is the source of truth. This skill is the short checklist.

## Stack
React + Vite in JavaScript (JSX). Function components and hooks. CSS Modules + variables from `src/styles/tokens.css`. TanStack Query hooks in `src/api/`. No TypeScript, Tailwind, UI kits, or drag-and-drop libraries. The owner is learning React: add a one-line comment for any non-obvious pattern (effects, query invalidation, refs).

## Visual rules
- Colors: only `--ink`, `--paper`, `--desk`, `--rule`, `--graphite`, `--smudge`. Never introduce a hue.
- Light theme only for now. Every color goes through a CSS variable so the dark theme (P1) is a small change.
- State is shown by weight, fill, outline, or dashed vs solid lines, never by color alone.
- Fonts: Schibsted Grotesk for UI; Newsreader only inside the Paper component. Tabular numbers for scores and dates.
- Sentence case. No all-caps labels, no letter-spaced eyebrows, no arrows in button text.
- Radius: 0 for Paper, 6px inputs/buttons, pill only for FitBadge. Only Paper has a shadow; elsewhere use 1px rules.
- Lists are ruled rows, not grids of identical cards.
- Motion: only the Paper slide-in plus underline draw. Everything else responds to user actions. Honour `prefers-reduced-motion`.

## The paper
- A supported claim has a solid underline; selecting it shows the profile facts it cites.
- A flagged claim has a dashed underline and a note, with "Remove", "Edit", and "This is true, add to my profile". "Approve draft" stays disabled until every flagged claim is resolved, and says how many are left.
- Editing swaps the document for a textarea styled exactly like the paper. Never use `contentEditable`.

## Other screens
- Pipeline cards move with a "Move to" button that lists the stages. No drag and drop.
- Every job row and job detail shows the listing's source as a link ("Remote, India · Himalayas", "Listing from Himalayas"). The job APIs require it.
- "Apply" opens the source's link in a new tab. Nothing in the UI submits an application.

## Data and streaming
- Components never call `fetch`. Use the hooks in `src/api/`. The fetch client adds the CSRF header and runs at most one token refresh at a time.
- Progress comes over `EventSource`. Each event has a `code`; map it to the fixed copy in DESIGN.md section 5. If the stream errors, refresh the session once and reconnect.

## Every screen needs
Loading, empty (says what to do next), and error (what happened and how to fix it) states; keyboard navigation with visible 2px ink focus; labels on inputs; works at 360px.

## Copy
Buttons say exactly what happens ("Prepare application", "Approve draft"); the toast uses the same words ("Draft approved").

## Safety
Render LLM output and job text as plain text. Never `dangerouslySetInnerHTML`. No Markdown rendering and no auto-linking of text that came from a model or a job listing.

## What you cannot verify
You cannot see the browser. Write tests for labels, keyboard operation and states. For layout at 360px, visual match to DESIGN.md, and reduced motion, give the owner a short checklist and wait for their answer. Never write that these passed on your own.
