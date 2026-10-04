from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from campaign import Campaign
from campaign_api import CampaignApi
from config import Config
from github_client import GitHubClient

logger = logging.getLogger("campaign_backend.poller")


@dataclass
class Session:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    alerted: set[str] = field(default_factory=set)


class Poller:
    def __init__(self, config: Config, campaign_api: CampaignApi, github_client: GitHubClient) -> None:
        self.config = config
        self.api = campaign_api
        self.github = github_client
        self.session = Session()
        self.lock = threading.Lock()
        self.fetch_lock = threading.Lock()
        self.alert_lock = threading.Lock()
        self.label_ensured = False
        self.warned_no_github = False
        self.campaigns: list[Campaign] = []
        self.last_poll: Optional[str] = None
        self.last_error: Optional[str] = None
        self.alerts: deque[dict[str, str]] = deque()
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, name="campaign-poller", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2)

    def _run_loop(self) -> None:
        while not self.stop_event.is_set():
            self.poll_once()
            time.sleep(self.config.interval_ms / 1000.0)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "sessionId": self.session.id,
                "lastPoll": self.last_poll,
                "lastError": self.last_error,
                "campaigns": [campaign.to_dict() for campaign in self.campaigns],
                "alerts": list(self.alerts),
                "threshold": self.config.threshold,
                "intervalMs": self.config.interval_ms,
            }

    def on_reset(self) -> None:
        with self.lock:
            self.session = Session()
            self.alerts.clear()

    def refresh_now(self) -> None:
        session = self.session
        campaigns = self.fetch_and_store()
        if campaigns is not None:
            threading.Thread(
                target=self.alert_safely,
                args=(campaigns, session),
                name="campaign-alerts",
                daemon=True,
            ).start()

    def poll_once(self) -> None:
        try:
            session = self.session
            campaigns = self.fetch_and_store()
            if campaigns is not None:
                self.alert_safely(campaigns, session)
        except Exception:
            logger.exception("poll loop failed")

    def fetch_and_store(self) -> Optional[list[Campaign]]:
        with self.fetch_lock:
            try:
                campaigns = self.api.fetch_all()
                self._set_ok(campaigns)
                return campaigns
            except Exception as exc:
                self._set_error(str(exc))
                return None

    def alert_safely(self, campaigns: list[Campaign], session: Session) -> None:
        with self.alert_lock:
            try:
                self.alert_over_budget(campaigns, session)
            except Exception:
                logger.exception("alerting failed")

    def alert_over_budget(self, campaigns: list[Campaign], session: Session) -> None:
        if not self.config.github_enabled():
            if not self.warned_no_github:
                logger.warning("GitHub is not configured; alerting disabled")
                self.warned_no_github = True
            return

        if not self.label_ensured:
            self.github.ensure_label()
            self.label_ensured = True

        for campaign in campaigns:
            if not campaign.exceeds(self.config.threshold) or campaign.id in session.alerted:
                continue
            if session is not self.session:
                return
            try:
                issue_url = self.github.create_issue(campaign, session.id)
                session.alerted.add(campaign.id or "")
                self.record_alert(campaign, issue_url)
                logger.info("Issue created: %s (%s) -> %s", campaign.name, campaign.id, issue_url)
            except Exception:
                logger.exception("Issue creation failed for %s", campaign.id)

    def _set_ok(self, campaigns: list[Campaign]) -> None:
        with self.lock:
            self.campaigns = list(campaigns)
            self.last_poll = datetime.now(timezone.utc).isoformat()
            self.last_error = None

    def _set_error(self, message: str) -> None:
        with self.lock:
            self.last_error = message

    def record_alert(self, campaign: Campaign, url: str) -> None:
        with self.lock:
            self.alerts.appendleft(
                {
                    "id": campaign.id or "",
                    "name": str(campaign.name or "n/a"),
                    "url": url,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            )
