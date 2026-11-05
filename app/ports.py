"""Ports: the interfaces the application core depends on.

Everything below is a ``typing.Protocol`` so any implementation (JSON files,
SQLite, a remote API, a fake in tests) can be swapped in without touching the
services. Services must never import from ``app.adapters``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


# --------------------------------------------------------------------- clock
@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current instant, timezone-aware (UTC)."""

    def to_local(self, moment: datetime) -> datetime:
        """Convert to the display timezone (Beijing)."""


# ------------------------------------------------------------------- fetcher
@dataclass
class FetchResult:
    """Outcome of one page fetch — never raises, always inspectable."""

    ok: bool
    elapsed_ms: int = 0
    data: dict[str, Any] | None = None
    error_code: str = ""
    upstream_status: int | None = None
    detail: str = ""


@runtime_checkable
class Fetcher(Protocol):
    def fetch(self, url: str, timeout_s: int = 120) -> FetchResult:
        """Fetch a URL and return extracted page data."""


# ------------------------------------------------------------------ notifier
@runtime_checkable
class Notifier(Protocol):
    def notify(self, title: str, message: str) -> tuple[bool, str]:
        """Best-effort user notification. Returns (ok, detail)."""


# ---------------------------------------------------------------- repository
@runtime_checkable
class Repository(Protocol):
    """Persistence boundary for both catalog data and operational logs."""

    # catalog
    def load_venues(self) -> dict[str, Any]: ...
    def save_venues(self, doc: dict[str, Any]) -> None: ...
    def load_state(self) -> dict[str, Any]: ...
    def save_state(self, doc: dict[str, Any]) -> None: ...

    # scrape candidates
    def load_candidates(self) -> dict[str, Any]: ...
    def save_candidates(self, doc: dict[str, Any]) -> None: ...

    # run evidence
    def save_run(self, record: dict[str, Any]) -> Any: ...
    def save_snapshot(self, run_id: str, text: str) -> Any: ...
    def list_runs(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]: ...

    # reminders
    def append_reminder(self, entry: dict[str, Any]) -> None: ...
    def read_reminders(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def load_reminder_state(self) -> dict[str, Any]: ...
    def save_reminder_state(self, doc: dict[str, Any]) -> None: ...

    # daily-scrape bookkeeping
    def load_scrape_state(self) -> dict[str, Any]: ...
    def save_scrape_state(self, doc: dict[str, Any]) -> None: ...

    # daily-verification bookkeeping
    def load_verify_state(self) -> dict[str, Any]: ...
    def save_verify_state(self, doc: dict[str, Any]) -> None: ...

    # audit of automatic writes
    def append_audit(self, entry: dict[str, Any]) -> None: ...
    def read_audit(self, limit: int = 50) -> list[dict[str, Any]]: ...


# -------------------------------------------------------------------- config
@dataclass
class ScrapeConfig:
    cli_path: str = ""
    timeout_seconds: int = 120
    auto: bool = True
    daily_time: str = "09:00"
    auto_apply: bool = True
    guard_days: int = 90
    protect_confirmed: bool = True
    browser_fallback: bool = True
    browser_fallback_on_failure: bool = True
    browser_cli_path: str = ""
    browser_context_id: str = ""       # persists cookies after a human takeover
    pace_seconds: float = 1.2          # pause between Web Fetch calls (rate limit)
    quota_backoff_seconds: int = 25    # wait once and retry on quota errors


@dataclass
class ReminderConfig:
    thresholds: list[int] = field(default_factory=lambda: [30, 14, 7, 3, 1])
    digest_hour: int = 9
    tick_seconds: int = 900
    toast: bool = True


@dataclass
class VerifyConfig:
    """Background re-check of stored deadlines against the official page."""

    enabled: bool = True
    daily_time: str = "10:00"
    max_shift_days: int = 30          # tolerate this much drift before flagging
    pending_only: bool = True         # only predicted / scraped / stale rows


@dataclass
class AppConfig:
    port: int = 8770
    scrape: ScrapeConfig = field(default_factory=ScrapeConfig)
    reminders: ReminderConfig = field(default_factory=ReminderConfig)
    verify: VerifyConfig = field(default_factory=VerifyConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        scrape_raw = raw.get("scrape") or {}
        remind_raw = raw.get("reminders") or {}
        verify_raw = raw.get("verify") or {}
        scrape = ScrapeConfig(
            cli_path=scrape_raw.get("cli_path", ""),
            timeout_seconds=int(scrape_raw.get("timeout_seconds", 120)),
            auto=bool(scrape_raw.get("auto", True)),
            daily_time=str(scrape_raw.get("daily_time", "09:00")),
            auto_apply=bool(scrape_raw.get("auto_apply", True)),
            guard_days=int(scrape_raw.get("auto_apply_guard_days", 90)),
            protect_confirmed=bool(scrape_raw.get("protect_confirmed", True)),
            browser_fallback=bool(scrape_raw.get("browser_fallback", True)),
            browser_fallback_on_failure=bool(scrape_raw.get("browser_fallback_on_failure", True)),
            browser_cli_path=str(scrape_raw.get("browser_cli_path", "")),
            browser_context_id=str(scrape_raw.get("browser_context_id", "")),
            pace_seconds=float(scrape_raw.get("pace_seconds", 1.2)),
            quota_backoff_seconds=int(scrape_raw.get("quota_backoff_seconds", 25)),
        )
        reminders = ReminderConfig(
            thresholds=[int(t) for t in remind_raw.get("thresholds", [30, 14, 7, 3, 1])],
            digest_hour=int(remind_raw.get("digest_hour", 9)),
            tick_seconds=int(remind_raw.get("tick_seconds", 900)),
            toast=bool(remind_raw.get("toast", True)),
        )
        verify = VerifyConfig(
            enabled=bool(verify_raw.get("enabled", True)),
            daily_time=str(verify_raw.get("daily_time", "10:00")),
            max_shift_days=int(verify_raw.get("max_shift_days", 30)),
            pending_only=bool(verify_raw.get("pending_only", True)),
        )
        return cls(port=int(raw.get("port", 8770)), scrape=scrape,
                   reminders=reminders, verify=verify)

    def to_dict(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "scrape": {
                "cli_path": self.scrape.cli_path,
                "timeout_seconds": self.scrape.timeout_seconds,
                "auto": self.scrape.auto,
                "daily_time": self.scrape.daily_time,
                "auto_apply": self.scrape.auto_apply,
                "auto_apply_guard_days": self.scrape.guard_days,
                "protect_confirmed": self.scrape.protect_confirmed,
                "browser_fallback": self.scrape.browser_fallback,
                "browser_fallback_on_failure": self.scrape.browser_fallback_on_failure,
                "browser_cli_path": self.scrape.browser_cli_path,
                "browser_context_id": self.scrape.browser_context_id,
                "pace_seconds": self.scrape.pace_seconds,
                "quota_backoff_seconds": self.scrape.quota_backoff_seconds,
            },
            "reminders": {
                "thresholds": list(self.reminders.thresholds),
                "digest_hour": self.reminders.digest_hour,
                "tick_seconds": self.reminders.tick_seconds,
                "toast": self.reminders.toast,
            },
            "verify": {
                "enabled": self.verify.enabled,
                "daily_time": self.verify.daily_time,
                "max_shift_days": self.verify.max_shift_days,
                "pending_only": self.verify.pending_only,
            },
        }


@runtime_checkable
class ConfigStore(Protocol):
    def load(self) -> AppConfig: ...
    def save(self, config: AppConfig) -> None: ...
