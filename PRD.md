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
Public APIs and feeds (e.g. Remotive, Adzuna), company career-page URLs the user pastes, and pasted job descriptions. Each source is an adapter behind one interface.

## 6. User stories
- Upload a PDF resume and review/edit the extracted profile.
- Set preferences: roles, remote only, locations, salary floor, deal-breakers.
- See a ranked job feed with fit score (0-100) and reasons for and against.
- Open a job, run "Prepare application", watch progress stream, review the draft, edit, approve or reject.
- Move applications across stages: Saved, Preparing, Ready, Applied, Interview, Offer, Rejected.
- Get a follow-up reminder after N days of silence.
- The system remembers my preferences and past corrections ("never mention X", "prefer short letters").

## 7. Features by priority
- P0 (MVP): auth, resume ingestion, profile, job search + paste-JD, fit scoring, application drafting with approval gate, pipeline tracker.
- P1: company research agent, long-term memory of preferences, reflection loop on drafts, streaming UI, LangSmith traces.
- P2: remote MCP server with OAuth, interview-prep notes, email-draft export.

## 8. Success criteria
- End-to-end demo: upload resume, see 10+ scored jobs, prepare one application, approve, track it. Under 5 minutes.
- Draft contains zero facts absent from the profile (checked by an automated grounding test on a fixed sample set).
- Fit-score reasons are specific to the job text, not generic.
- Runs on free-tier or local LLMs; cost per prepared application is logged.
- Live deployment, README with architecture diagram, 2-minute demo video.

## 9. Constraints
- Budget: free-tier LLM APIs or local Ollama by default. Provider-swappable.
- Solo developer alongside coursework: scope to P0 + P1.
- Backend stack limited to what the author knows (see ARCHITECTURE.md). Frontend is a minimal React (JavaScript) app; no TypeScript. The author is new to React, so frontend code must stay simple and well commented.
- Visual direction: minimal, aesthetic, black and white (see DESIGN.md).
