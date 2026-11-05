"""Composition root: wires adapters to services. This is the only module that
knows which concrete implementations exist."""

from __future__ import annotations

import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from app.adapters.browser_fetcher import DEFAULT_CLI as DEFAULT_BROWSER_CLI
from app.adapters.ccfddl import CcfddlSource
from app.adapters.browser_fetcher import BrowserFetcher
from app.adapters.cli_fetcher import CliFetcher
from app.adapters.clock import SystemClock
from app.adapters.fallback_fetcher import FallbackFetcher
from app.adapters.json_config import JsonConfigStore
from app.adapters.json_store import JsonStore
from app.adapters.windows_toast import WindowsToast
from app.domain import deadlines
from app.ports import AppConfig, FetchResult
from app.adapters.journal_sources import CrossrefClient, LetpubClient
from app.services.catalog import CatalogService
from app.services.journal_verifier import JournalVerifier
from app.services.reminders import ReminderService
from app.services.scheduler import DailyScraper, DailyVerifier, parse_hhmm
from app.services.scraper import Scraper
from app.services.verifier import Verifier

VERSION = "0.3.0"


def _validate_settings(body: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    scrape_patch = body.get("scrape") or {}
    remind_patch = body.get("reminders") or {}
    verify_patch = body.get("verify") or {}
    errors: list[str] = []
    if not all(isinstance(x, dict) for x in (scrape_patch, remind_patch, verify_patch)):
        return {}, ["scrape/reminders/verify 必须是对象"]

    scrape: dict[str, Any] = {}
    reminders: dict[str, Any] = {}
    verify: dict[str, Any] = {}

    if "auto" in scrape_patch:
        scrape["auto"] = bool(scrape_patch["auto"])
    if "daily_time" in scrape_patch:
        if parse_hhmm(str(scrape_patch["daily_time"])) is None:
            errors.append("daily_time 需为 HH:MM")
        else:
            scrape["daily_time"] = str(scrape_patch["daily_time"]).strip()
    if "auto_apply" in scrape_patch:
        scrape["auto_apply"] = bool(scrape_patch["auto_apply"])
    if "protect_confirmed" in scrape_patch:
        scrape["protect_confirmed"] = bool(scrape_patch["protect_confirmed"])
    if "auto_apply_guard_days" in scrape_patch:
        try:
            days = int(scrape_patch["auto_apply_guard_days"])
            if not (1 <= days <= 365):
                raise ValueError
            scrape["auto_apply_guard_days"] = days
        except (TypeError, ValueError):
            errors.append("auto_apply_guard_days 需为 1–365 的整数")
    if "browser_fallback" in scrape_patch:
        scrape["browser_fallback"] = bool(scrape_patch["browser_fallback"])
    if "browser_fallback_on_failure" in scrape_patch:
        scrape["browser_fallback_on_failure"] = bool(scrape_patch["browser_fallback_on_failure"])

    if "thresholds" in remind_patch:
        try:
            values = sorted({int(t) for t in remind_patch["thresholds"]}, reverse=True)
            if not values or any(t < 1 or t > 365 for t in values):
                raise ValueError
            reminders["thresholds"] = values
        except (TypeError, ValueError):
            errors.append("thresholds 需为 1–365 的整数列表")
    if "digest_hour" in remind_patch:
        try:
            hour = int(remind_patch["digest_hour"])
            if not (0 <= hour <= 23):
                raise ValueError
            reminders["digest_hour"] = hour
        except (TypeError, ValueError):
            errors.append("digest_hour 需为 0–23")
    if "toast" in remind_patch:
        reminders["toast"] = bool(remind_patch["toast"])

    if "enabled" in verify_patch:
        verify["enabled"] = bool(verify_patch["enabled"])
    if "daily_time" in verify_patch:
        if parse_hhmm(str(verify_patch["daily_time"])) is None:
            errors.append("核验时间需为 HH:MM")
        else:
            verify["daily_time"] = str(verify_patch["daily_time"]).strip()
    if "max_shift_days" in verify_patch:
        try:
            days = int(verify_patch["max_shift_days"])
            if not (0 <= days <= 365):
                raise ValueError
            verify["max_shift_days"] = days
        except (TypeError, ValueError):
            errors.append("max_shift_days 需为 0–365 的整数")
    if "pending_only" in verify_patch:
        verify["pending_only"] = bool(verify_patch["pending_only"])

    return {"scrape": scrape, "reminders": reminders, "verify": verify}, errors


class Application:
    def __init__(self, config: AppConfig, root: Path, *, fetcher=None) -> None:
        self.root = Path(root)
        self.config = config
        self.config_store = JsonConfigStore(self.root / "config.json")
        self.repo = JsonStore(self.root)
        self.clock = SystemClock()
        # Lexmount chain: Web Fetch first, Cloud Browser only for thin pages.
        self.fetcher = fetcher or FallbackFetcher(
            CliFetcher(config.scrape.cli_path),
            BrowserFetcher(config.scrape.browser_cli_path or DEFAULT_BROWSER_CLI,
                           context_id=config.scrape.browser_context_id),
            enabled=config.scrape.browser_fallback,
            on_failure=config.scrape.browser_fallback_on_failure,
        )
        self.notifier = WindowsToast(self.root / "app" / "toast.ps1", enabled=config.reminders.toast)

        self.catalog = CatalogService(self.repo, self.clock)
        self.scraper = Scraper(self.repo, self.fetcher, self.clock, lambda: self.config)
        self.dataset = CcfddlSource(self.root / "data" / "ccfddl.yml")
        self.verify_progress = {"done": 0, "total": 0}
        self.journal_progress = {"done": 0, "total": 0}
        self.journal_verifier = JournalVerifier(
            self.repo, self.clock, CrossrefClient(), LetpubClient(),
            on_progress=lambda done, total: setattr(self, "journal_progress", {"done": done, "total": total}),
        )
        self.verifier = Verifier(self.repo, self.fetcher, self.clock, lambda: self.config,
                                 third_party=self.dataset,
                                 on_progress=self._on_verify_progress)
        self.reminders = ReminderService(self.repo, self.notifier, self.clock, lambda: self.config)
        self.scheduler = DailyScraper(
            self.repo, self.clock, lambda: self.config, self.start_scrape,
            tick_seconds=30,
        )
        self.verifier_job = DailyVerifier(
            self.repo, self.clock, lambda: self.config, self.start_verify,
            tick_seconds=30,
        )

        self.scrape_lock = threading.Lock()
        self.scraping = False
        self.verify_lock = threading.Lock()
        self.verifying = False
        self.journal_lock = threading.Lock()
        self.verifying_journals = False
        self.last_journal_verify_id: str | None = None
        self.last_run_id: str | None = None
        self.last_verify_id: str | None = None
        self.started_at = deadlines.iso_local(self.clock.now())

    # ------------------------------------------------------------------ scrape
    def start_scrape(self, venue_ids: list[str] | None = None) -> tuple[int, dict[str, Any]]:
        with self.scrape_lock:
            if self.scraping:
                return 409, {"error": {"code": "scrape_in_progress", "message": "已有抓取任务在运行"}}
            self.scraping = True

        def worker() -> None:
            try:
                record = self.scraper.run(venue_ids)
                self.last_run_id = record.get("run_id")
            except Exception:  # noqa: BLE001 - worker must never kill the server
                traceback.print_exc()
            finally:
                with self.scrape_lock:
                    self.scraping = False

        threading.Thread(target=worker, name="cfp-scrape", daemon=True).start()
        return 202, {"status": "started", "message": "抓取已在后台开始"}

    def _on_verify_progress(self, done: int, total: int) -> None:
        self.verify_progress = {"done": done, "total": total}

    # -------------------------------------------------------------- verification
    def start_verify(self, venue_ids: list[str] | None = None,
                     pending_only: bool | None = None) -> tuple[int, dict[str, Any]]:
        """Re-check stored deadlines against the official page (Lexmount fetch)."""
        with self.verify_lock:
            if self.verifying:
                return 409, {"error": {"code": "verify_in_progress", "message": "已有核验任务在运行"}}
            self.verifying = True

        self.verify_progress = {"done": 0, "total": 0}
        self.journal_progress = {"done": 0, "total": 0}
        self.journal_verifier = JournalVerifier(
            self.repo, self.clock, CrossrefClient(), LetpubClient(),
            on_progress=lambda done, total: setattr(self, "journal_progress", {"done": done, "total": total}),
        )

        def worker() -> None:
            try:
                record = self.verifier.verify(venue_ids, pending_only)
                self.last_verify_id = record.get("run_id")
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            finally:
                with self.verify_lock:
                    self.verifying = False

        threading.Thread(target=worker, name="cfp-verify", daemon=True).start()
        return 202, {"status": "started", "message": "核验已在后台开始"}

    # ------------------------------------------------------------- journals
    def start_journal_verify(self) -> tuple[int, dict[str, Any]]:
        with self.journal_lock:
            if self.verifying_journals:
                return 409, {"error": {"code": "verify_in_progress", "message": "期刊核验已在运行"}}
            self.verifying_journals = True
        self.journal_progress = {"done": 0, "total": 0}

        def worker() -> None:
            try:
                record = self.journal_verifier.verify()
                self.last_journal_verify_id = record.get("run_id")
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            finally:
                with self.journal_lock:
                    self.verifying_journals = False

        threading.Thread(target=worker, name="cfp-journal-verify", daemon=True).start()
        return 202, {"status": "started", "message": "期刊核验已在后台开始"}

    # ---------------------------------------------------------------- settings
    def public_settings(self) -> dict[str, Any]:
        return {
            "scrape": {
                "auto": self.config.scrape.auto,
                "daily_time": self.config.scrape.daily_time,
                "auto_apply": self.config.scrape.auto_apply,
                "auto_apply_guard_days": self.config.scrape.guard_days,
                "protect_confirmed": self.config.scrape.protect_confirmed,
                "browser_fallback": self.config.scrape.browser_fallback,
                "browser_fallback_on_failure": self.config.scrape.browser_fallback_on_failure,
            },
            "reminders": {
                "thresholds": list(self.config.reminders.thresholds),
                "digest_hour": self.config.reminders.digest_hour,
                "toast": self.config.reminders.toast,
            },
            "verify": {
                "enabled": self.config.verify.enabled,
                "daily_time": self.config.verify.daily_time,
                "max_shift_days": self.config.verify.max_shift_days,
                "pending_only": self.config.verify.pending_only,
            },
            "schedule": self.scheduler.status(),
            "verify_schedule": self.verifier_job.status(),
            "journal_progress": self.journal_progress,
            "verifying_journals": self.verifying_journals,
            "version": VERSION,
        }

    def update_settings(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        patch, errors = _validate_settings(body)
        if errors:
            return 400, {"error": {"code": "invalid_settings", "message": "；".join(errors)}}

        scrape_patch = patch["scrape"]
        remind_patch = patch["reminders"]
        verify_patch = patch.get("verify", {})
        if "auto" in scrape_patch:
            self.config.scrape.auto = scrape_patch["auto"]
        if "daily_time" in scrape_patch:
            self.config.scrape.daily_time = scrape_patch["daily_time"]
        if "auto_apply" in scrape_patch:
            self.config.scrape.auto_apply = scrape_patch["auto_apply"]
        if "protect_confirmed" in scrape_patch:
            self.config.scrape.protect_confirmed = scrape_patch["protect_confirmed"]
        if "auto_apply_guard_days" in scrape_patch:
            self.config.scrape.guard_days = scrape_patch["auto_apply_guard_days"]
        if "browser_fallback" in scrape_patch:
            self.config.scrape.browser_fallback = scrape_patch["browser_fallback"]
            if hasattr(self.fetcher, "enabled"):
                self.fetcher.enabled = self.config.scrape.browser_fallback
        if "browser_fallback_on_failure" in scrape_patch:
            self.config.scrape.browser_fallback_on_failure = scrape_patch["browser_fallback_on_failure"]
            if hasattr(self.fetcher, "on_failure"):
                self.fetcher.on_failure = self.config.scrape.browser_fallback_on_failure
        if "thresholds" in remind_patch:
            self.config.reminders.thresholds = remind_patch["thresholds"]
        if "digest_hour" in remind_patch:
            self.config.reminders.digest_hour = remind_patch["digest_hour"]
        if "toast" in remind_patch:
            self.config.reminders.toast = remind_patch["toast"]
            self.notifier.enabled = self.config.reminders.toast
        if "enabled" in verify_patch:
            self.config.verify.enabled = verify_patch["enabled"]
        if "daily_time" in verify_patch:
            self.config.verify.daily_time = verify_patch["daily_time"]
        if "max_shift_days" in verify_patch:
            self.config.verify.max_shift_days = verify_patch["max_shift_days"]
        if "pending_only" in verify_patch:
            self.config.verify.pending_only = verify_patch["pending_only"]

        try:
            self.config_store.save(self.config)
        except OSError as exc:
            return 500, {"error": {"code": "save_failed", "message": str(exc)}}
        return 200, {"ok": True, "settings": self.public_settings()}

    # ------------------------------------------------------------------ health
    def health(self) -> dict[str, Any]:
        doc = self.repo.load_venues()
        runs = self.repo.list_runs(1, kind="scrape")
        verify_runs = self.repo.list_runs(1, kind="verify")
        return {
            "ok": True, "version": VERSION, "started_at": self.started_at,
            "venues": len(doc.get("venues", [])), "degraded": self.repo.degraded,
            "last_scrape": runs[0]["run_id"] if runs else None,
            "last_verify": verify_runs[0]["run_id"] if verify_runs else None,
            "scraping": self.scraping,
            "verifying": self.verifying,
            "reminders": self.reminders.status(),
            "schedule": self.scheduler.status(),
            "verify_schedule": self.verifier_job.status(),
            "journal_progress": self.journal_progress,
            "verifying_journals": self.verifying_journals,
        }
