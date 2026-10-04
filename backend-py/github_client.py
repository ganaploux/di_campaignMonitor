from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from config import Config
from http_client import HttpClient

LABEL = "budget-alert"


class GitHubClient:
    def __init__(self, config: Config):
        self.config = config

    def ensure_label(self) -> None:
        if not self.config.github_enabled():
            return
        try:
            payload = {"name": LABEL, "color": "d93f0b", "description": "Campaign spend over threshold"}
            self._request("/labels", method="POST", payload=payload)
        except Exception:
            pass

    def create_issue(self, campaign: Any, session_id: str) -> str:
        if not self.config.github_enabled():
            raise RuntimeError("GitHub not configured")
        pct = f"{campaign.pct * 100:.1f}"
        body = "\n".join([
            f"Campaign **{campaign.name}** (`{campaign.id}`) has spent **{pct}%** of its budget.",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Advertiser | {or_na(campaign.advertiser)} |",
            f"| Status | {or_na(campaign.status)} |",
            f"| Budget | {usd(campaign.budget)} |",
            f"| Spend | {usd(campaign.spend)} |",
            f"| Remaining | {usd((campaign.budget or 0) - (campaign.spend or 0))} |",
            f"| Flight dates | {or_na(campaign.start_date)} to {or_na(campaign.end_date)} |",
            f"| Impressions / clicks | {or_na(campaign.impressions)} / {or_na(campaign.clicks)} |",
            f"| Session | `{session_id}` |",
            f"| Detected at | {datetime.now(timezone.utc).isoformat()} |",
            "",
            "**Suggested action:** review pacing, then raise the budget, pause the campaign, or confirm it should run out.",
            "",
            f"<!-- campaign-id:{campaign.id} session:{session_id} -->",
        ])
        response = self._request(
            "/issues",
            method="POST",
            payload={
                "title": f"[Budget alert] {campaign.name} at {pct}% of budget (session {session_id})",
                "body": body,
                "labels": [LABEL],
            },
        )
        return response.get("html_url") or ""

    def _request(self, path: str, *, method: str = "GET", payload: Optional[dict[str, Any]] = None) -> Any:
        url = f"https://api.github.com/repos/{self.config.gh_repo}{path}"
        headers = {
            "Authorization": f"Bearer {self.config.gh_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "campaign-monitor",
        }
        return HttpClient.send_json(url, method=method, headers=headers, payload=payload, retries=2)


def or_na(value: Any) -> str:
    return "n/a" if value is None else str(value)


def usd(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"
