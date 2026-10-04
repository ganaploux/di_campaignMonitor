from __future__ import annotations

import json
from typing import Any

from config import Config
from campaign import Campaign
from http_client import HttpClient


class CampaignApi:
    def __init__(self, config: Config):
        self.config = config

    def fetch_all(self) -> list[Campaign]:
        out: dict[str, Campaign] = {}
        seen = 0
        for page in range(1, 1001):
            body = self._get(f"/campaigns?page={page}&page_size=10")
            items = first_array(body, "campaigns", "items", "data")
            for item in items:
                campaign = Campaign.from_payload(item)
                seen += 1
                if campaign.id is not None:
                    out[campaign.id] = campaign
            total = body.get("total", -1) if isinstance(body, dict) else -1
            if len(items) < 10 or (total >= 0 and seen >= total):
                break
        return list(out.values())

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.config.api_url}{path}"
        headers = {"X-API-Key": self.config.api_key}
        raw = HttpClient.send_json(url, method="GET", headers=headers, retries=3)
        return raw if isinstance(raw, dict) else {}


def first_array(body: Any, *names: str) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for name in names:
            value = body.get(name)
            if isinstance(value, list):
                return value
    return []
