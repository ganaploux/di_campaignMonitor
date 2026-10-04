# Campaign Monitor: backend-py

Polls the campaign API every 10 seconds, opens a GitHub Issue when a campaign passes 90% of budget, and exposes a small JSON API for the UI. Standard library only.

## Prerequisites
- Python 3.10+
- Docker (only needed for the Reset action)
- A GitHub repo plus a Personal Access Token with Issues: read & write

## Run
```bash
cp .env.example .env
# set GITHUB_TOKEN and GITHUB_REPO=owner/repo
python app.py
```

The API listens on http://127.0.0.1:3000 (loopback only). Run the UI from `../frontend` (`python serve.py`), or set `SERVE_FRONTEND=true` to have this process serve it too.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/campaigns` | Cached campaigns, session id, last poll status, issues created this session |
| POST | `/api/next-day` | Advance the simulation, refresh immediately, return fresh data |
| POST | `/api/reset` | Restart the Docker container, start a new session |

POST requests require the header `X-Requested-With: campaign-ui` and, if an `Origin` header is sent, it must be in `ALLOWED_ORIGINS`; otherwise the server answers 403.

## Config (`.env` or environment)
| Var | Default |
|---|---|
| `GITHUB_TOKEN`, `GITHUB_REPO` | required for alerts |
| `CAMPAIGN_API_URL` | `http://localhost:8080` |
| `CAMPAIGN_API_KEY` | `interview-key-2024` |
| `PORT` | `3000` |
| `POLL_INTERVAL_MS` | `10000` |
| `THRESHOLD` | `0.9` |
| `SERVE_FRONTEND` | `false` (set to `true` to serve `../frontend` from this process) |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:5500,http://127.0.0.1:5500` (exact match) |
