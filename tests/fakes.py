"""Test doubles implementing the ports. No filesystem, no network, no threads."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.domain import deadlines
from app.ports import AppConfig, FetchResult


class FakeClock:
    def __init__(self, moment: datetime | None = None) -> None:
        self._now = moment or datetime(2026, 10, 30, 3, 0, tzinfo=deadlines.timezone.utc)

    def now(self) -> datetime:
        return self._now

    def to_local(self, moment: datetime) -> datetime:
        return deadlines.to_display(moment)

    def advance(self, **kwargs: float) -> None:
        self._now = self._now + timedelta(**kwargs)

    def set(self, moment: datetime) -> None:
        self._now = moment


class FakeFetcher:
    def __init__(self, pages: dict[str, FetchResult] | None = None,
                 html: dict[str, str] | None = None) -> None:
        self.pages = pages or {}
        self.html = html or {}
        self.calls: list[str] = []
        self.html_calls: list[str] = []

    def fetch(self, url: str, timeout_s: int = 120) -> FetchResult:
        self.calls.append(url)
        return self.pages.get(url, FetchResult(False, 1, error_code="not_configured"))

    def fetch_html(self, url: str, timeout_s: int = 120) -> FetchResult:
        self.html_calls.append(url)
        if url in self.html:
            return FetchResult(True, 1, data={"html": self.html[url], "status_code": 200})
        return FetchResult(False, 1, error_code="html_not_configured")


class FakeNotifier:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> tuple[bool, str]:
        self.sent.append((title, message))
        return self.ok, "fake"


class InMemoryRepository:
    """Implements the Repository port entirely in memory."""

    def __init__(self, venues: list[dict[str, Any]] | None = None) -> None:
        self.venues = {"schema_version": 1, "venues": venues or []}
        self.state: dict[str, Any] = {"schema_version": 1, "venues": {}}
        self.candidates: dict[str, Any] = {"schema_version": 1, "candidates": []}
        self.runs: list[dict[str, Any]] = []
        self.snapshots: dict[str, str] = {}
        self.reminders: list[dict[str, Any]] = []
        self.reminder_state: dict[str, Any] = {"sent": {}}
        self.scrape_state: dict[str, Any] = {"last_auto_date": None, "last_auto_at": None}
        self.verify_state: dict[str, Any] = {"last_auto_date": None, "last_auto_at": None}
        self.audit: list[dict[str, Any]] = []
        self.saved_venues = 0

    # catalog ---------------------------------------------------------------
    def load_venues(self) -> dict[str, Any]:
        return self.venues

    def save_venues(self, doc: dict[str, Any]) -> None:
        self.venues = doc
        self.saved_venues += 1

    def load_state(self) -> dict[str, Any]:
        return self.state

    def save_state(self, doc: dict[str, Any]) -> None:
        self.state = doc

    # candidates ------------------------------------------------------------
    def load_candidates(self) -> dict[str, Any]:
        return self.candidates

    def save_candidates(self, doc: dict[str, Any]) -> None:
        self.candidates = doc

    # evidence --------------------------------------------------------------
    def save_run(self, record: dict[str, Any]) -> str:
        self.runs = [r for r in self.runs if r.get("run_id") != record.get("run_id")]
        self.runs.insert(0, record)
        return record.get("run_id", "")

    def save_snapshot(self, run_id: str, text: str) -> str:
        self.snapshots[run_id] = text
        return run_id

    def list_runs(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        items = [r for r in self.runs if not kind or r.get("kind", "scrape") == kind]
        return items[:limit]

    # reminders -------------------------------------------------------------
    def append_reminder(self, entry: dict[str, Any]) -> None:
        self.reminders.append(entry)

    def read_reminders(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.reminders[-limit:][::-1]

    def load_reminder_state(self) -> dict[str, Any]:
        return self.reminder_state

    def save_reminder_state(self, doc: dict[str, Any]) -> None:
        self.reminder_state = doc

    # scrape state ----------------------------------------------------------
    def load_scrape_state(self) -> dict[str, Any]:
        return self.scrape_state

    def save_scrape_state(self, doc: dict[str, Any]) -> None:
        self.scrape_state = doc

    def load_verify_state(self) -> dict[str, Any]:
        return self.verify_state

    def save_verify_state(self, doc: dict[str, Any]) -> None:
        self.verify_state = doc

    # audit -----------------------------------------------------------------
    def append_audit(self, entry: dict[str, Any]) -> None:
        self.audit.append(entry)

    def read_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.audit[-limit:][::-1]


def make_venue(vid: str = "demo-2027", *, status: str = "predicted", date: str = "2027-02-25",
               kinds=("full_paper",), cfp_url: str = "https://example.org/cfp",
               rolling: bool = False) -> dict[str, Any]:
    return {
        "id": vid, "name": f"{vid} conference", "abbr": vid.split("-")[0].upper(),
        "edition": "2027", "type": "conference", "rolling": rolling, "areas": ["ai"],
        "topics": ["多模态融合"], "tracks": [], "submission": {}, "acceptance": {},
        "tier": {"ccf": "B"}, "official_url": "https://example.org",
        "cfp_url": cfp_url, "materials": [], "page_limit": None, "blind": "double",
        "notes": "", "review_cycle_weeks": None,
        "deadlines": [{"kind": k, "date": date, "time": "23:59", "tz": "AoE",
                       "source_status": status, "note": ""} for k in kinds],
    }


def make_candidate(date: str, *, kind: str = "full_paper", vid: str = "demo-2027",
                   tz: str = "AoE") -> dict[str, Any]:
    return {"venue_id": vid, "kind": kind, "date": date, "time": "23:59", "tz": tz,
            "source_url": "https://example.org/cfp",
            "extracted_at": "2026-10-30T11:00:00+08:00",
            "snippet": f"Full paper submission deadline: {date}",
            "status": "candidate", "confidence": "medium"}


def make_config(**scrape_overrides) -> AppConfig:
    cfg = AppConfig()
    cfg.scrape.pace_seconds = 0.0
    cfg.scrape.quota_backoff_seconds = 0
    for key, value in scrape_overrides.items():
        setattr(cfg.scrape, key, value)
    return cfg
