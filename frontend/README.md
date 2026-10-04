# Frontend

Plain HTML, CSS and JavaScript: no build step, no Node needed.

## Run

```bash
python serve.py
# Serves on http://localhost:5500 (loopback only)
```

Or choose a different port:
```bash
python serve.py 8000
```

`serve.py` uses only the standard library. `app.py` is an equivalent Flask version (`pip install flask` first).

Requires the backend API running on `http://localhost:3000` (change `API_BASE_URL` in `config.js`). If you serve the UI from a port other than 5500 or 5173, add that origin to `ALLOWED_ORIGINS` in `backend-py/.env`.
