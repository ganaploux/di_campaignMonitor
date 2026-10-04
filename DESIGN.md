# Design

## How it works
Two small services, both Python standard library only on the backend:

**Backend (`backend-py/`)** does three jobs:
1. **Poller**: a background thread fetches all campaign pages (`page_size=10`) from the campaign API every 10s, normalizes each row, and computes `spend / budget`. The next run starts 10s after the previous one *finishes*, so runs never overlap.
2. **Alerting**: any campaign (any status) with ratio `> 0.9` and no issue yet in the current session gets a GitHub Issue. Issues are created by calling the GitHub REST API directly with `urllib` and a Personal Access Token (no GitHub SDK).
3. **JSON API** for the UI: `GET /api/campaigns` returns the poller's cached state; `POST /api/next-day` and `POST /api/reset` act and return fresh data. The browser never sees the campaign API key or the GitHub token.

**Frontend (`frontend/`)** is plain HTML/JS with no build step. It polls `GET /api/campaigns` every 5s and renders a table (name, advertiser, budget, spend, % used, status) with status filter, sort by % used, and pagination, plus a list of issues created this session. It is served as a separate static service on port 5500 and calls the backend on port 3000 (`frontend/config.js`). Setting `SERVE_FRONTEND=true` makes the backend serve the folder itself instead, so UI and API share one origin.

## Idempotency and sessions
The poller runs every 10s, so without dedupe a campaign would get ~360 issues per hour. Each run of the monitor has a **session id** (8 hex chars) generated at startup and regenerated whenever the simulation is reset from the UI. Within a session, each campaign gets at most one issue. The set of alerted campaign ids lives in memory and is updated only after GitHub confirms creation, so failed creations retry on the next tick. A new session is a clean slate: campaigns over 90% alert again, and issues from earlier sessions are never read, modified or deleted. Every issue carries the session id in its title, body and a hidden marker (`<!-- campaign-id:X session:Y -->`) so an alert can be traced to a run.

Trade-offs: dedupe is in memory, so a crash mid-session followed by a restart starts a new session and can re-alert campaigns already reported. An earlier design rebuilt dedupe state from GitHub on startup; I gave that up so each run produces its own alerts. A reset can also race with an in-flight poll, so each poll captures the session before fetching and stops creating issues if the session changed meanwhile. Stale data is never attributed to the new session.

Alternative considered: alerting on threshold *crossing* (alert when a campaign goes from at or below 90% to above, and forget it when it drops back). A reset would then clear state on its own, and a manual `docker restart` would also work. I chose per-session dedupe because it is simpler to reason about, and the session id makes each demo run traceable on GitHub. The cost is that a container restarted outside the UI doesn't start a new session, so Reset should be done from the UI.

## Failure modes
| Failure | Handling |
|---|---|
| Campaign API 5xx / timeout / network ("may occasionally return errors") | 5s timeout, up to 3 retries with exponential backoff (300ms, 600ms, 1.2s), then skip the tick. The last good data stays cached and is still served. |
| 429 / rate limit (either API) | Retried; honors `Retry-After` (capped at 30s), otherwise backoff. |
| 4xx | Not retried (won't fix itself); surfaced as the poll error. |
| Pagination | Loops until `total` is reached or a short page arrives; de-dupes by id in case pages shift. Capped at 1000 pages. |
| Malformed row (missing/zero budget, non-numeric spend) | `pct` is null: shown as n/a, never alerts, never crashes the loop. |
| GitHub down or token invalid | Per-campaign try/except; the loop continues and the campaign is retried next tick (it is only marked alerted after success). |
| Slow run overlapping the next tick | The loop sleeps *after* each poll finishes, and fetch/alert work is guarded by locks, so runs never overlap. |
| Uncaught exception in the poll thread | `poll_once` catches everything, so the loop survives and logs the error. |
| Restart | New session; no state is carried over and earlier issues are left alone. |
| Cross-origin calls from other websites | CORS allow-list (`ALLOWED_ORIGINS`, exact match); POSTs must carry `X-Requested-With`, which forces a preflight that a disallowed origin fails. POSTs lacking the header, or from an unlisted origin, get 403. |
| Backend unreachable while the UI is open | UI keeps the last data on screen and turns the "updated HH:MM" timestamp red (tooltip explains), so it is clear the data is stale. It reverts on the next successful fetch. |
| Campaign API error | The backend keeps serving its last good data with `lastError` set; the UI shows the same red timestamp until a poll succeeds. |
| Missing GitHub token | Poller and UI still work; alerting is disabled with one log line. |
| Reset: Docker missing, container not found, or slow restart | Returns a 502 with the reason; after restart the backend polls `/health` for up to 30s before reporting success. |

## Security notes
This is built to run locally for a demo. Choices made:
- **Both servers bind to `127.0.0.1`**, so nothing is reachable from the network.
- **CORS is an exact allow-list**, not a wildcard. `POST /api/reset` and `/api/next-day` additionally require `X-Requested-With` and a permitted `Origin`, so a malicious web page can't trigger a container restart through the user's browser.
- **Secrets stay server-side**: the GitHub token and campaign API key are in `backend-py/.env` (gitignored), never sent to the browser.
- The UI escapes every API-supplied value before inserting it into the page.
- Static file serving resolves paths and refuses anything outside the frontend folder.

Known limitations: `/api/reset` has no authentication. It runs `docker restart` on the host, so it relies on the loopback binding. It must not be exposed to a network without adding auth.

## Known gaps / with more time
- **Create is not atomic**: if GitHub creates an issue but the response is lost and we retry, there can be a duplicate. Fix: search for the hidden marker before retrying the POST.
- Dedupe is once per campaign per session. I would add per-threshold alerts (e.g. 90% and 100%) and persist the session id so a crash does not start a new one.
- **UI refresh is polling**: the browser re-reads the backend's cached snapshot every 5s while the backend refreshes every 10s, so some requests return unchanged data and a change can appear up to 5s late (Advance and Reset return fresh data immediately). With more time I'd push updates to the UI over Server-Sent Events, so it updates the moment a poll finishes. SSE suits one-way updates, is built into browsers, and works with the standard-library server. I'd keep polling as a fallback if the stream drops. A cheaper step would be `ETag`/`304` responses.
- The stale-data indicator is just a red timestamp; a production UI would use a more prominent banner and grey out the table.
- Response schema is assumed (see below); I'd validate with a schema library and alert on drift.
- Single process using the standard library's `ThreadingHTTPServer`. In production: a real framework, the poller as its own worker, authentication on the control endpoints, a `/healthz`, structured logs and metrics (poll latency, failures, issues created).
- **No automated tests yet**: I would add unit tests for `Campaign.from_payload`, the threshold logic and retry behaviour (against a fake server).
- The alerts list in memory is unbounded; cap it, and persist alert history.
- A real scheduler (cron / queue worker) instead of an in-process loop, and polling the API's `status` filter server-side.
- Pin Docker image by digest and restart the container by name rather than by image ancestor.

## Assumptions
- Campaign fields and list shape, confirmed against a real response: `{page, page_size, total, campaigns: [{id, name, advertiser, status, budget, spend, start_date, end_date, impressions, clicks, cpm}]}`. All mapping lives in `Campaign.from_payload` and `CampaignApi.fetch_all`.
- "Exceeded 90%" means strictly `> 0.9`.
- Every campaign over the threshold gets an issue regardless of status, per the brief ("any campaign"). For a `completed` or `paused` campaign this is informational; a production version might skip or down-rank those.
- One issue per campaign per session is sufficient.
- The campaign API key defaults to `interview-key-2024` and can be overridden with `CAMPAIGN_API_KEY`.
- `/next-day` and reset are proxied through the UI as demo conveniences only.
- `/api/reset` runs `docker restart` on the host (matching the brief: "restarting the container resets it"), so the backend is meant to run locally next to the container with `docker` on the PATH.
