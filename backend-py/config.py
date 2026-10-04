from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:5500,http://127.0.0.1:5500"
)


@dataclass(frozen=True)
class Config:
    api_url: str
    api_key: str
    port: int
    interval_ms: int
    threshold: float
    gh_token: Optional[str]
    gh_repo: Optional[str]
    allowed_origins: set[str]
    serve_frontend: bool

    @staticmethod
    def load() -> "Config":
        env = read_dot_env()
        env.update(os.environ)
        
        # Parse serve_frontend as a boolean
        serve_frontend_str = env.get("SERVE_FRONTEND", "false").lower()
        serve_frontend = serve_frontend_str in ("true", "1", "yes")
        
        # Find frontend dir only if we're serving it
        frontend_dir: Optional[Path] = None
        if serve_frontend:
            frontend_dir = find_frontend_dir(env.get("FRONTEND_DIR"))
        
        return Config(
            api_url=(env.get("CAMPAIGN_API_URL", "http://localhost:8080") or "http://localhost:8080").rstrip("/"),
            api_key=env.get("CAMPAIGN_API_KEY", "interview-key-2024"),
            port=int(env.get("PORT", "3000")),
            interval_ms=int(env.get("POLL_INTERVAL_MS", "10000")),
            threshold=float(env.get("THRESHOLD", "0.9")),
            gh_token=env.get("GITHUB_TOKEN"),
            gh_repo=normalize_repo(env.get("GITHUB_REPO")),
            allowed_origins={
                origin.strip()
                for origin in (env.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS) or DEFAULT_ORIGINS).split(",")
                if origin.strip()
            },
            serve_frontend=serve_frontend,
        )

    def github_enabled(self) -> bool:
        return bool(self.gh_token and self.gh_repo)


def normalize_repo(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    repo = value.strip()
    if not repo:
        return None
    repo = repo.replace("https://", "").replace("http://", "")
    repo = repo.replace("www.github.com/", "github.com/")
    repo = repo.replace("github.com/", "", 1)
    repo = repo.removesuffix(".git")
    return repo.rstrip("/")


def find_frontend_dir(configured: Optional[str]) -> Optional[Path]:
    candidates = [configured] if configured and configured.strip() else ["../frontend", "frontend"]
    for candidate in candidates:
        path = Path(candidate)
        if (path / "index.html").is_file():
            return path
    return None


def read_dot_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for candidate in (Path(".env"), Path("backend/.env")):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            env[key.strip()] = value.strip()
    return env
