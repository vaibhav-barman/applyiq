# PRD: ApplyIQ

## 1. Problem
Applying for jobs is repetitive: find roles, judge fit, rewrite the resume and cover letter per role, and track where each application stands. Existing tools either spam applications (low quality, can get accounts banned) or only track them (no intelligence).

## 2. Target user
A job seeker (first user: the author, an AI-engineer fresher targeting remote roles) who wants quality over volume and keeps final control.

## 3. Goals
- G1: Turn a resume into a structured, editable profile.
- G2: Find relevant jobs from legal sources and score fit with a clear explanation.
- G3: Draft tailored resume bullets and a cover letter per job, grounded only in the user's real experience.
- G4: Track every application through a pipeline with follow-up reminders.
- G5: Be deployable, observable, and safe enough to show as a production-style system.

## 4. Non-goals (do not build)
- No auto-submitting applications. No browser automation against job sites.
- No scraping LinkedIn, Indeed, or any site whose terms forbid it.
- No inventing skills, employers, or dates. Drafts may only use facts in the profile.
- No multi-tenant billing, no mobile app.

## 5. Job sources (MVP)
Pasted job descriptions; two public job APIs (Himalayas and Jobicy); and public company job boards hosted on Greenhouse and Ashby, for companies the user chooses to follow. Each source is an adapter behind one interface, and every listing is shown with a credit and link to its source. Details, limits and terms: `docs/job-sources.md`. Fetching an arbitrary URL the user pastes is P1.

## 6. User stories
- Upload a PDF resume and review/edit the extracted profile.
- Set preferences: roles, remote only, locations, salary floor, deal-breakers.
- See a ranked job feed with fit score (0-100) and reasons for and against.
- Open a job, run "Prepare application", watch progress stream, review the draft, edit, approve or reject.
- Move applications across stages: Saved, Preparing, Ready, Applied, Interview, Offer, Rejected.
- See "Follow up" on an application after N days of silence.
- Resolve every flagged claim in a draft before approving: remove it, edit it, or confirm it is true and add it to my profile.
- (P1) The system remembers my preferences and past corrections ("never mention X", "prefer short letters"), after I confirm each one.

## 7. Features by priority
- P0 (MVP): auth, resume ingestion, profile, paste a job, fit scoring, application drafting with grounding check, critic loop and approval gate, streamed progress, pipeline tracker, job feed from two APIs and followed company boards, deployed demo with a seeded account.
- P1: long-term memory of preferences, company research agent, fetching a pasted URL, a read-only MCP server for external clients, "Show changes" diff, dark mode, data export, embedding pre-filter for the feed.
- P2: remote MCP server with OAuth, interview-prep notes, email-draft export, S3 storage and backups.

Build order is not priority order: the core (paste a job, score it, prepare and approve one application) is built before the job feed, and the first deploy happens right after auth. TRACKER.md has the order.

## 8. Success criteria
- End-to-end demo: upload resume, see 10+ scored jobs, prepare one application, approve, track it. Under 5 minutes on the seeded demo account (hosted free-tier rate limits can make a fresh run slower; the live run is shown as it streams).
- Grounding, measured on a fixed set of synthetic profiles and jobs: zero segments marked supported that contain a name, number, date or skill absent from their cited profile facts (rule-based guard), every seeded fabrication of those kinds caught, and the support judge's catch rate for overstated claims reported per model with a 90 percent target.
- Fit-score reasons are specific to the job text, not generic.
- Runs on a local model or a hosted free tier whose terms are acceptable for personal data; tokens and estimated cost per prepared application are logged.
- Live deployment, README with architecture diagram, 2-minute demo video.

## 9. Constraints
- Budget: local Ollama for development and a hosted free tier (Groq) for the demo. Provider-swappable. A free tier that trains on inputs or lets reviewers read them may not receive real resumes.
- Solo developer alongside coursework, about 15 hours a week: finish and deploy P0 first (about 170 hours), then take P1 items one at a time.
- Backend stack limited to what the author knows (see ARCHITECTURE.md). Frontend is a minimal React (JavaScript) app; no TypeScript. The author is new to React, so frontend code must stay simple and well commented.
- Visual direction: minimal, aesthetic, black and white (see DESIGN.md).
