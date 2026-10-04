from __future__ import annotations

import json
import time
from typing import Any, Optional
from urllib import error, request

TIMEOUT_SECONDS = 5


class HttpException(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class HttpClient:
    @staticmethod
    def send_request(url: str, *, method: str = "GET", headers: Optional[dict[str, str]] = None, body: Optional[bytes] = None, retries: int = 3) -> bytes:
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            wait_ms = 300 << attempt
            try:
                req = request.Request(url, data=body, headers=headers or {}, method=method)
                with request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                    return response.read()
            except error.HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    raise HttpException(f"{exc.code} for {method} {url}", exc.code) from exc
                wait_ms = retry_after_ms(exc.headers, wait_ms)
            except Exception as exc:  # includes timeout and connection errors
                last_error = exc
            if attempt < retries:
                time.sleep(wait_ms / 1000.0)
        raise RuntimeError(f"gave up after {retries + 1} attempts: {last_error}") from last_error

    @staticmethod
    def send_json(url: str, *, method: str = "GET", headers: Optional[dict[str, str]] = None, payload: Optional[Any] = None, retries: int = 3) -> Any:
        data = None
        full_headers = dict(headers or {})
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            full_headers.setdefault("Content-Type", "application/json")
        raw = HttpClient.send_request(url, method=method, headers=full_headers, body=data, retries=retries)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))


def retry_after_ms(headers: Any, fallback: int) -> int:
    retry_after = headers.get("Retry-After") if hasattr(headers, "get") else None
    if retry_after:
        try:
            return min(int(str(retry_after).strip()) * 1000, 30_000)
        except ValueError:
            pass
    return fallback
