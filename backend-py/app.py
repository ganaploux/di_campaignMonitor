from __future__ import annotations

import json
import logging
import signal
import socket
import subprocess
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from campaign_api import CampaignApi
from config import Config, find_frontend_dir
from github_client import GitHubClient
from poller import Poller

logger = logging.getLogger("campaign_backend.app")


class App:
    def __init__(self) -> None:
        base_config = Config.load()
        port = self._find_free_port(base_config.port)
        if port != base_config.port:
            logger.warning(
                "Port %s is busy, using %s instead. The frontend (frontend/config.js) still points at %s, "
                "so stop whatever is on port %s or update API_BASE_URL.",
                base_config.port, port, base_config.port, base_config.port,
            )
        self.config = Config(
            api_url=base_config.api_url,
            api_key=base_config.api_key,
            port=port,
            interval_ms=base_config.interval_ms,
            threshold=base_config.threshold,
            gh_token=base_config.gh_token,
            gh_repo=base_config.gh_repo,
            allowed_origins=base_config.allowed_origins,
            serve_frontend=base_config.serve_frontend,
        )
        self.poller = Poller(self.config, CampaignApi(self.config), GitHubClient(self.config))
        self.server = ThreadingHTTPServer(("127.0.0.1", self.config.port), self._create_handler())

    def start(self) -> None:
        self.poller.start()
        logger.info("API on http://localhost:%s | polling %s every %sms", self.config.port, self.config.api_url, self.config.interval_ms)
        self.server.serve_forever()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.poller.stop()

    def _find_free_port(self, preferred: int) -> int:
        for port in (preferred, *range(preferred + 1, preferred + 50)):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                # No SO_REUSEADDR: on Windows it lets a second process bind a busy port.
                try:
                    sock.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        raise OSError(f"No free port found starting from {preferred}")

    def _create_handler(self):
        config = self.config
        poller = self.poller

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._send_cors_headers()
                self.send_header("Access-Control-Max-Age", "600")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                self._handle_request()

            def do_POST(self) -> None:
                self._handle_request()

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _handle_request(self) -> None:
                try:
                    path = self.path.split("?", 1)[0]
                    method = self.command

                    if method == "POST" and not self._post_allowed():
                        self._send_json(403, {"error": "forbidden"})
                        return

                    if path == "/api/campaigns" and method == "GET":
                        self._send_json(200, poller.snapshot())
                        return

                    if path == "/api/next-day" and method == "POST":
                        try:
                            next_day = self._call_campaign_api("/next-day")
                        except Exception as exc:
                            logger.exception("next-day request failed")
                            self._send_json(502, {"error": str(exc)})
                            return
                        poller.refresh_now()
                        payload = dict(poller.snapshot())
                        payload["nextDay"] = next_day
                        self._send_json(200, payload)
                        return

                    if path == "/api/reset" and method == "POST":
                        try:
                            message = restart_campaign_container(config.api_url)
                        except Exception as exc:
                            logger.exception("reset request failed")
                            self._send_json(502, {"error": str(exc)})
                            return
                        poller.on_reset()
                        poller.refresh_now()
                        payload = dict(poller.snapshot())
                        payload["message"] = message
                        self._send_json(200, payload)
                        return

                    if config.serve_frontend and method == "GET" and self._serve_static(path):
                        return

                    if path == "/" and method == "GET":
                        self._send_json(200, {"service": "campaign-monitor-backend", "status": "ok"})
                        return

                    self._send_json(404, {"error": "not found"})
                except Exception as exc:
                    logger.exception("request failed: %s %s", self.command, self.path)
                    self._send_json(502, {"error": str(exc)})

            def _send_json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(body)

            def _post_allowed(self) -> bool:
                # Custom header forces a CORS preflight for browsers; a cross-site page
                # can't set it unless the allow-list approves its origin.
                if not self.headers.get("X-Requested-With"):
                    return False
                origin = self.headers.get("Origin")
                if not origin:
                    return True
                same_origin = origin == f"http://{self.headers.get('Host', '')}"
                return same_origin or _origin_allowed(origin, config.allowed_origins)

            def _send_cors_headers(self) -> None:
                self.send_header("Vary", "Origin")
                origin = self.headers.get("Origin")
                if not origin:
                    return
                if _origin_allowed(origin, config.allowed_origins):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Requested-With")
                else:
                    logger.warning(
                        "CORS: rejected origin %r. Open the UI from http://localhost:<port> "
                        "or add it to ALLOWED_ORIGINS in backend-py/.env", origin
                    )

            def _call_campaign_api(self, path: str) -> Any:
                request = urllib.request.Request(f"{config.api_url}{path}", method="POST")
                request.add_header("X-API-Key", config.api_key)
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.loads(response.read().decode("utf-8"))

            def _serve_static(self, file_path: str) -> bool:
                if not config.serve_frontend:
                    return False
                
                frontend_dir = find_frontend_dir(None)
                if frontend_dir is None:
                    return False

                root = Path(frontend_dir).resolve()
                try:
                    if file_path == "/":
                        target = root / "index.html"
                    else:
                        target = (root / file_path.lstrip("/")).resolve()

                    if not str(target).startswith(str(root)):
                        return False
                    if not target.is_file():
                        return False

                    data = target.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", _content_type(target))
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return True
                except Exception:
                    return False

        return Handler


def _origin_allowed(origin: str, allowed: set[str]) -> bool:
    return origin in allowed


def _content_type(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".html"):
        return "text/html; charset=utf-8"
    if name.endswith(".js"):
        return "text/javascript; charset=utf-8"
    if name.endswith(".css"):
        return "text/css; charset=utf-8"
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".svg"):
        return "image/svg+xml"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".ico"):
        return "image/x-icon"
    return "application/octet-stream"


def restart_campaign_container(api_url: str) -> str:
    image = "didelta50/4289329224:latest"
    result = subprocess.run(
        ["docker", "ps", "-q", "--filter", f"ancestor={image}"],
        capture_output=True,
        text=True,
        check=False,
    )
    container_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not container_ids:
        raise RuntimeError(f"No running container found for image {image}")

    try:
        subprocess.run(["docker", "restart", *container_ids], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to restart containers: {exc.stderr or exc.stdout}") from exc

    deadline = time.time() + 30
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{api_url}/health", timeout=5) as response:
                if response.status == 200:
                    return f"Restarted {len(container_ids)} container(s); campaigns are back to day 0."
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            last_error = str(exc.reason) if hasattr(exc, "reason") else str(exc)
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)

    raise RuntimeError(f"Container restarted but health check failed: {last_error or 'timeout after 30s'}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = App()

    def shutdown(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, shutdown)

    try:
        app.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        app.stop()
