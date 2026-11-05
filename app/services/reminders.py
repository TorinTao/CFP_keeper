"""Reminder service: threshold alerts plus a daily digest.

Depends on ``Repository``, ``Notifier`` and ``Clock`` ports only. Runs as a
daemon thread in production; ``tick()`` is pure enough to test with fakes.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from app.domain import deadlines, schema
from app.ports import AppConfig, Clock, Notifier, Repository


class ReminderService(threading.Thread):
    def __init__(
        self,
        repo: Repository,
        notifier: Notifier,
        clock: Clock,
        get_config: Callable[[], AppConfig],
    ) -> None:
        super().__init__(name="cfp-reminder", daemon=True)
        self.repo = repo
        self.notifier = notifier
        self.clock = clock
        self.get_config = get_config
        self.stop_event = threading.Event()
        self.last_tick: str | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------ thread
    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:  # pragma: no cover - integration loop
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
            self.stop_event.wait(self.get_config().reminders.tick_seconds)

    # -------------------------------------------------------------------- tick
    def tick(self, now=None) -> list[dict[str, Any]]:
        now = now or self.clock.now()
        cfg = self.get_config()
        self.last_tick = deadlines.iso_local(now)
        venues = self.repo.load_venues().get("venues", [])
        state = self.repo.load_reminder_state()
        sent: dict[str, Any] = state.setdefault("sent", {})
        emitted: list[dict[str, Any]] = []

        for venue in venues:
            if venue.get("type") == "journal" or venue.get("rolling"):
                continue
            for dl in venue.get("deadlines") or []:
                if dl.get("kind") == "conference":
                    continue
                try:
                    when = deadlines.parse_deadline(dl.get("date", ""), dl.get("time", "23:59"),
                                                    dl.get("tz", "AoE"))
                except deadlines.DeadlineError:
                    continue
                left_hours = deadlines.hours_left(when, now)
                if left_hours < 0:
                    continue
                days = left_hours / 24.0
                applicable = [t for t in cfg.reminders.thresholds if days <= t]
                if not applicable:
                    continue
                threshold = min(applicable)
                key = "{}:{}:{}:{}".format(venue.get("id"), dl.get("kind"), threshold,
                                           deadlines.iso_utc(when)[:10])
                if key in sent:
                    continue
                entry = self._emit(venue, dl, when, left_hours, threshold)
                sent[key] = entry["ts"]
                for bigger in applicable:
                    sent["{}:{}:{}:{}".format(venue.get("id"), dl.get("kind"), bigger,
                                              deadlines.iso_utc(when)[:10])] = entry["ts"]
                emitted.append(entry)

        digest = self._maybe_digest(venues, now, sent, cfg)
        if digest:
            emitted.append(digest)
        if emitted:
            self.repo.save_reminder_state(state)
        return emitted

    def _maybe_digest(self, venues, now, sent, cfg: AppConfig) -> dict[str, Any] | None:
        local_now = self.clock.to_local(now)
        if local_now.hour < cfg.reminders.digest_hour:
            return None
        day_key = "digest:" + local_now.strftime("%Y-%m-%d")
        if day_key in sent:
            return None
        soon: list[str] = []
        for venue in venues:
            if venue.get("type") == "journal" or venue.get("rolling"):
                continue
            for dl in venue.get("deadlines") or []:
                try:
                    when = deadlines.parse_deadline(dl.get("date", ""), dl.get("time", "23:59"),
                                                    dl.get("tz", "AoE"))
                except deadlines.DeadlineError:
                    continue
                hours = deadlines.hours_left(when, now)
                if 0 <= hours <= 24 * 7:
                    soon.append("{} {}（{} 天）".format(
                        venue.get("abbr"),
                        schema.KIND_LABELS.get(dl.get("kind"), dl.get("kind")),
                        int(hours // 24)))
        if not soon:
            return None
        message = "本周 {} 场截稿：{}".format(len(soon), "；".join(soon[:4]))
        entry = {"ts": deadlines.iso_local(now), "type": "digest",
                 "title": "CFP Keeper 周报", "message": message, "count": len(soon)}
        sent[day_key] = entry["ts"]
        self.repo.append_reminder(entry)
        self._notify(entry["title"], message, cfg)
        return entry

    def _emit(self, venue, dl, when, left_hours, threshold) -> dict[str, Any]:
        bj = self.clock.to_local(when)
        label = schema.KIND_LABELS.get(dl.get("kind"), dl.get("kind", ""))
        title = "[{}] {} · 剩 {} 天".format(venue.get("abbr"), label, int(left_hours // 24))
        message = "北京时间 {} · 原始 {} {} {}".format(
            bj.strftime("%m-%d %H:%M"), dl.get("date"), dl.get("time", "23:59"), dl.get("tz", "AoE"))
        entry = {"ts": deadlines.iso_local(), "type": "threshold", "venue_id": venue.get("id"),
                 "abbr": venue.get("abbr"), "deadline_kind": dl.get("kind"),
                 "deadline_beijing": bj.strftime("%Y-%m-%d %H:%M"),
                 "days_left": int(left_hours // 24), "threshold": threshold,
                 "title": title, "message": message}
        self.repo.append_reminder(entry)
        self._notify(title, message, self.get_config())
        return entry

    def _notify(self, title: str, message: str, cfg: AppConfig) -> None:
        if not cfg.reminders.toast:
            return
        ok, detail = self.notifier.notify(title, message)
        if not ok:
            self.last_error = "notify failed: " + detail[:200]

    def status(self) -> dict[str, Any]:
        cfg = self.get_config()
        return {"running": self.is_alive(), "last_tick": self.last_tick,
                "last_error": self.last_error, "thresholds": list(cfg.reminders.thresholds),
                "tick_seconds": cfg.reminders.tick_seconds, "toast_enabled": cfg.reminders.toast}
