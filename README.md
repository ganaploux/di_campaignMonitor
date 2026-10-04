# Campaign Monitor

Polls the campaign API every 10 seconds, opens a GitHub Issue when a campaign's spend passes 90% of its budget, and shows everything in a browser UI.

- `backend-py/`: Python backend (poller, GitHub issue creation, JSON API). Standard library only.
- `frontend/`: the browser UI (plain HTML/JS, no build step).
- `DESIGN.md`: how it works, failure modes, trade-offs, assumptions.

## Prerequisites
- Python 3.10+
- Docker
- A GitHub repo and a Personal Access Token with *Issues: read & write* on it (a fine-grained token limited to that repo is enough)

No `pip install` is needed.

## Run
Open three terminals, starting from the repo root.

```bash
# Terminal 1: campaign API (leave running)
docker pull didelta50/4289329224:latest
docker run -p 8080:8080 didelta50/4289329224:latest
```

```bash
# Terminal 2: backend (configure once, then start)
cd backend-py
cp .env.example .env        # set GITHUB_TOKEN and GITHUB_REPO=owner/repo
python app.py               # http://localhost:3000
```

```bash
# Terminal 3: frontend
cd frontend
python serve.py             # http://localhost:5500
```

Open **http://localhost:5500**.

Without a token, the UI still works; alerting is just disabled (the backend logs a warning).

## Demo
1. The table shows all campaigns. Any already over 90% get a GitHub Issue within about 10 seconds (see the repo's Issues tab).
2. Click **Advance one day**: a loading overlay appears, then the new values. Newly over-threshold campaigns get issues.
3. Click **Reset campaigns**: the Docker container restarts, data returns to day 0, and a new session starts. Issues from earlier sessions stay on GitHub.

## Troubleshooting
- **UI stuck on "Loading…"**: the backend isn't reachable on port 3000. Check Terminal 2. If you restarted it, make sure no old `python app.py` is still running (on Windows an old process can keep answering requests).
- **Reset fails**: Docker must be running and `docker` on your PATH; the campaign API container must be up.
- **Use a different port or UI origin**: see `backend-py/README.md` (`PORT`, `ALLOWED_ORIGINS`) and `frontend/config.js`.

## Configuration
See `backend-py/README.md` (GitHub repo and token, ports, threshold, allowed origins).
