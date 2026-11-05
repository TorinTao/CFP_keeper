"""Daily background jobs: scrape at 09:00, verify at 10:00 (both configurable).

A single generic ``DailyJob`` holds the timing/dedupe/retry logic; the two
concrete jobs only differ in which config field drives them and which state file
they persist. Tests drive ``tick()`` directly — no threads involved.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any, Callable

from app.ports import AppConfig, Clock, Repository

DEFAULT_SCRAPE_TIME = "09:00"
DEFAULT_VERIFY_TIME = "10:00"


def parse_hhmm(value: str) -> tuple[int, int] | None:
    text = (value or "").strip().replace("：", ":")
    parts = text.split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _job_settings(cfg: AppConfig, kind: str) -> tuple[bool, str]:
    if kind == "verify":
        return cfg.verify.enabled, cfg.verify.daily_time
    return cfg.scrape.auto, cfg.scrape.daily_time


def next_run_at(clock: Clock, cfg: AppConfig, last_date: str | None = None,
                now: datetime | None = None, kind: str = "scrape") -> str:
    enabled, daily_time = _job_settings(cfg, kind)
    if not enabled:
        return ""
    hhmm = parse_hhmm(daily_time)
    if not hhmm:
        return ""
    local = clock.to_local(now or clock.now())
    target = local.replace(hour=hhmm[0], minute=hhmm[1], second=0, microsecond=0)
    if local >= target and last_date != local.strftime("%Y-%m-%d"):
        return "即将执行（已过今日计划时间）"
    if local >= target:
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%d %H:%M")


class DailyJob(threading.Thread):
    kind = "job"

    def __init__(
        self,
        repo: Repository,
        clock: Clock,
        get_config: Callable[[], AppConfig],
        trigger: Callable[[], tuple[int, dict[str, Any]]],
        *,
        load_state: Callable[[], dict[str, Any]],
        save_state: Callable[[dict[str, Any]], None],
        tick_seconds: int = 30,
        name: str = "cfp-daily-job",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.repo = repo
        self.clock = clock
        self.get_config = get_config
        self.trigger = trigger
        self._load_state = load_state
        self._save_state = save_state
        self.tick_seconds = tick_seconds
        self.stop_event = threading.Event()
        self.last_check: str | None = None
        self.last_error: str | None = None

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:  # pragma: no cover - integration loop
        while not self.stop_event.is_set():
            try:
                self.tick(running=False)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
            self.stop_event.wait(self.tick_seconds)

    def tick(self, now: datetime | None = None, running: bool | None = None) -> dict[str, Any] | None:
        now = now or self.clock.now()
        cfg = self.get_config()
        self.last_check = self.clock.to_local(now).isoformat()

        enabled, daily_time = _job_settings(cfg, self.kind)
        if not enabled:
            return None
        hhmm = parse_hhmm(daily_time)
        if not hhmm:
            self.last_error = f"invalid daily_time for {self.kind}: {daily_time!r}"
            return None

        local = self.clock.to_local(now)
        if (local.hour, local.minute) < hhmm:
            return None
        if running:
            return None

        today = local.strftime("%Y-%m-%d")
        state = self._load_state()
        if state.get("last_auto_date") == today:
            # A run that died before writing its record leaves no trace, so look
            # for a record of this kind that started today. Comparing local
            # dates (not raw timestamp strings) avoids microsecond mismatches.
            recent = self.repo.list_runs(10, kind=self.kind)
            if any(str(r.get("started_at", ""))[:10] == today for r in recent):
                return None
            state["last_auto_date"] = None

        status, _payload = self.trigger()
        if status != 202:
            return None

        state["last_auto_date"] = today
        state["last_auto_at"] = self.clock.to_local(now).isoformat()
        self._save_state(state)
        return state

    def status(self) -> dict[str, Any]:
        cfg = self.get_config()
        state = self._load_state()
        enabled, daily_time = _job_settings(cfg, self.kind)
        return {
            "kind": self.kind,
            "running": self.is_alive(),
            "enabled": enabled,
            "auto": enabled,
            "daily_time": daily_time,
            "next_run": next_run_at(self.clock, cfg, last_date=state.get("last_auto_date"),
                                    kind=self.kind),
            "last_auto_date": state.get("last_auto_date"),
            "last_auto_at": state.get("last_auto_at"),
            "last_check": self.last_check,
            "last_error": self.last_error,
            "tick_seconds": self.tick_seconds,
        }


class DailyScraper(DailyJob):
    kind = "scrape"

    def __init__(self, repo, clock, get_config, trigger, tick_seconds: int = 30) -> None:
        super().__init__(repo, clock, get_config, trigger,
                         load_state=repo.load_scrape_state, save_state=repo.save_scrape_state,
                         tick_seconds=tick_seconds, name="cfp-daily-scraper")


class DailyVerifier(DailyJob):
    kind = "verify"

    def __init__(self, repo, clock, get_config, trigger, tick_seconds: int = 30) -> None:
        super().__init__(repo, clock, get_config, trigger,
                         load_state=repo.load_verify_state, save_state=repo.save_verify_state,
                         tick_seconds=tick_seconds, name="cfp-daily-verifier")
