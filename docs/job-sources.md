# Job sources

Read this before writing any spec in TRACKER Phase 6 (job discovery). Everything here was checked on 2026-11-17. Terms and limits change: re-read each source's page before building its adapter, and again before the public demo goes live.

## The rule

ApplyIQ uses public APIs that allow this use, and text the user pastes. It does not scrape, and it never re-publishes listings to other job boards. Each listing is shown with a visible credit and a link to its source, and "Apply" always goes to the link the source provides.

## Chosen sources

### 1. Himalayas (primary)
- Docs: https://himalayas.app/docs/remote-jobs-api
- Endpoints: browse `https://himalayas.app/jobs/api`, search `https://himalayas.app/jobs/api/search`.
- Key: not required. A free key gives 60 requests a minute and 10,000 a day. Without a key you share one public allowance with everyone. Keep the key server-side.
- Search parameters: `q`, `country`, `worldwide`, `seniority`, `employment_type`, `company`, `timezone`, `sort`, `page`. Browse returns at most 20 per request.
- Fields: full description (HTML), excerpt, seniority, salary range, categories, location and timezone restrictions, `applicationLink`, publish and expiry dates.
- Freshness: the feed refreshes every 24 hours. Polling more than daily gains nothing.
- Terms: show a visible credit with a link to himalayas.app; use the API's `applicationLink` for Apply, not a direct employer link; do not pass listings to other job boards, aggregators, Google Jobs or LinkedIn Jobs. Applies to personal and commercial use.
- Measured: a search for "machine learning" returned 4,477 matches and "AI engineer" 5,000, with descriptions averaging 4,000 to 5,600 characters. Search matching is loose (the first hit for "machine learning" was a React role), so filter again on our side.

### 2. Jobicy (secondary)
- Docs: https://jobicy.com/jobs-rss-feed
- Endpoint: `https://jobicy.com/api/jobs` with `count` (1 to 100), `geo`, `industry`, `tag`, `cursor`.
- Key: none for the public tier.
- Fields: full description (HTML), excerpt, level, type, region, salary range, publish date.
- Freshness: last 7 days only, published with a 3 hour delay.
- Limits: no published number. Start an automated pass at most once an hour, avoid minute 00, cache responses, back off on 429.
- Terms: credit Jobicy as the source; keep Apply links pointing to the Jobicy page; mark closed jobs as unavailable. Storing, caching and analysing listings with AI models are explicitly allowed.
- Measured: `industry=data-science` returned 63 jobs with full descriptions. The `tag` filter matches loosely (a search for "AI" returned unrelated roles), so filter again on our side. Fetch industry slugs from `?get=industries` instead of hard-coding them.

### 3. Company job boards (for companies the user follows)
Many AI companies publish their openings through an applicant-tracking system that has a public, documented, read-only JSON endpoint. The user gives a board address; the adapter extracts the board name and calls a fixed host. This is not arbitrary URL fetching, so it needs no SSRF machinery beyond a strict pattern match on the board name.

| System | Endpoint | Notes |
|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` | Docs say job board data is public and GET needs no authentication. `content=true` returns the full description, HTML-escaped. Measured: one AI lab's board returned 660 jobs. Docs: https://docs.greenhouse.io/job-board.html |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true` | Returns `descriptionPlain`, `descriptionHtml`, `isRemote`, `workplaceType`, location, compensation. Measured: one AI lab's board returned 833 jobs. Docs: https://developers.ashbyhq.com/docs/public-job-posting-api |
| Lever (optional) | `https://api.lever.co/v0/postings/{site}?mode=json` | Documented as public. Not measured in this review. Add only if a followed company uses it. |

Board names must match `^[a-z0-9][a-z0-9-]{0,62}$`. Anything else is rejected before a request is made.

### 4. Pasted job text
Always available, needs no network, and is the only source in the core phase. A pasted job is private to the user who pasted it (`jobs.owner_user_id`).

## Considered and dropped

| Source | Why |
|---|---|
| Remotive | The public feed returned 17 jobs in total on 2026-11-17. It is delayed 24 hours and asks for at most 4 calls a day. Too thin to be a primary source. |
| Adzuna | Needs a key. Its terms say the free tier "is intended for evaluating the API", and any use that generates revenue or leads needs a licence. Not remote-focused. Its search results carry a shortened description, which fit scoring cannot use (not re-checked in this review; confirm before reconsidering). |
| Remote OK | Usable as a third source: about 100 jobs in one call, 16 of them AI or ML on the day measured. It requires a followed link back and a mention of Remote OK, and some descriptions arrive cut short. Not needed for the MVP. |
| Arbeitnow | Free and keyless, but Europe and Germany focused: 22 of 300 jobs on the first page were remote. |
| LinkedIn, Indeed, Glassdoor | Their terms forbid scraping. Never. |

## Adapter interface

Each source is a small class inside `mcp_servers/jobs_server/sources/`. All of them return the same shape, so the rest of the app never knows which source a job came from except for the credit line.

| Field | Notes |
|---|---|
| `source` | `himalayas`, `jobicy`, `greenhouse`, `ashby`, `paste` |
| `external_id` | The source's own id. Unique together with `source`. |
| `title`, `company` | |
| `location_text`, `remote`, `regions` | `regions` is the list of allowed countries or regions when the source gives one. |
| `seniority` | When the source gives one. |
| `salary_min`, `salary_max`, `salary_currency`, `salary_period` | Nullable. |
| `description_text` | Plain text. HTML is stripped inside the adapter. Capped in length. Untrusted. |
| `apply_url` | Exactly the link the source says to use. |
| `source_url`, `credit_label` | For the credit line, for example "Source: Himalayas". |
| `posted_at`, `expires_at` | UTC. |

Rules for every adapter:
- A fixed base URL from config. HTTPS only. A timeout and a response size cap.
- A per-source rate limiter set below the published limit, and a cache so a repeated search inside the refresh window makes no request.
- Descriptions are untrusted text. Strip HTML to plain text, drop anything that is not text, cap the length. Never render the source's HTML in the browser.
- A source that fails or returns 429 is skipped for that request and reported in the response. One broken source must not break the feed.
- `content_hash` is computed in the app from normalised title, company and description, and is used to drop duplicates across sources.

## Credit wording in the interface

- Job row: the location line ends with the source, for example "Remote, India · Himalayas", linked to the listing's page on the source.
- Job detail: a line reading "Listing from Himalayas" with the link, placed under the title.
- The Apply button opens `apply_url` in a new tab. ApplyIQ never submits anything.
