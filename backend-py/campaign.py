from __future__ import annotations

from typing import Any, Optional


def text(node: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = node.get(key)
        if value is None or value == "":
            continue
        return str(value)
    return None


def num(node: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = node.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


class Campaign:
    def __init__(
        self,
        *,
        id: Optional[str],
        name: Optional[str],
        advertiser: Optional[str],
        status: Optional[str],
        budget: Optional[float],
        spend: Optional[float],
        start_date: Optional[str],
        end_date: Optional[str],
        impressions: Optional[int],
        clicks: Optional[int],
        pct: Optional[float],
    ) -> None:
        self.id = id
        self.name = name
        self.advertiser = advertiser
        self.status = status
        self.budget = budget
        self.spend = spend
        self.start_date = start_date
        self.end_date = end_date
        self.impressions = impressions
        self.clicks = clicks
        self.pct = pct

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Campaign":
        budget = num(payload, "budget", "total_budget")
        spend = num(payload, "spend", "spent", "total_spend")
        impressions = num(payload, "impressions")
        clicks = num(payload, "clicks")
        ok = budget is not None and spend is not None and budget > 0

        return cls(
            id=text(payload, "id"),
            name=text(payload, "name"),
            advertiser=text(payload, "advertiser"),
            status=text(payload, "status"),
            budget=budget,
            spend=spend,
            start_date=text(payload, "start_date"),
            end_date=text(payload, "end_date"),
            impressions=None if impressions is None else int(impressions),
            clicks=None if clicks is None else int(clicks),
            pct=(spend / budget) if ok else None,
        )

    def exceeds(self, threshold: float) -> bool:
        return self.pct is not None and self.pct > threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "advertiser": self.advertiser,
            "status": self.status,
            "budget": self.budget,
            "spend": self.spend,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "pct": self.pct,
        }
