"""Service: reminders (thresholds, dedupe, daily digest)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.services.reminders import ReminderService
from tests.fakes import FakeClock, FakeNotifier, InMemoryRepository, make_config, make_venue

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)  # 11:00 Beijing


def venue_with(days: int, vid="demo-2027", kind="full_paper"):
    date = (NOW + __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    venue = make_venue(vid, date=date, kinds=(kind,))
    return venue


class ReminderTests(unittest.TestCase):
    def build(self, venues, thresholds=None, digest_hour=23, toast=True):
        repo = InMemoryRepository(venues)
        notifier = FakeNotifier()
        clock = FakeClock(NOW)
        config = make_config()
        config.reminders.thresholds = thresholds or [30, 14, 7, 3, 1]
        config.reminders.digest_hour = digest_hour
        config.reminders.toast = toast
        service = ReminderService(repo, notifier, clock, lambda: config)
        return service, repo, notifier, clock

    def test_fires_threshold_and_notifies(self):
        service, repo, notifier, _ = self.build([venue_with(5)])
        entries = service.tick()
        thresholds = [e for e in entries if e["type"] == "threshold"]
        self.assertEqual(len(thresholds), 1)
        self.assertEqual(thresholds[0]["threshold"], 7)  # tightest bucket that covers 5 days
        self.assertEqual(len(notifier.sent), 1)
        self.assertEqual(len(repo.reminders), 1)

    def test_does_not_repeat_on_second_tick(self):
        service, repo, notifier, _ = self.build([venue_with(5)])
        service.tick()
        service.tick()
        self.assertEqual(len(notifier.sent), 1)
        self.assertEqual(len(repo.reminders), 1)

    def test_marks_wider_thresholds_sent_to_avoid_spam(self):
        service, repo, _, _ = self.build([venue_with(5)])
        service.tick()
        sent = repo.reminder_state["sent"]
        # 7/14/30 are all recorded as sent for this deadline, so it cannot re-fire
        self.assertEqual(len(sent), 3)
        self.assertTrue(all(key.startswith("demo-2027:full_paper:") for key in sent))

    def test_far_deadline_does_not_fire(self):
        service, _, notifier, _ = self.build([venue_with(120)])
        self.assertEqual(service.tick(), [])
        self.assertEqual(notifier.sent, [])

    def test_digest_only_after_hour(self):
        early = datetime(2026, 10, 30, 0, 30, tzinfo=timezone.utc)  # 08:30 Beijing
        service, repo, _, clock = self.build([venue_with(3)], digest_hour=9)
        clock.set(early)
        self.assertEqual([e for e in service.tick() if e["type"] == "digest"], [])
        clock.set(NOW)  # 11:00 Beijing
        entries = service.tick()
        self.assertTrue(any(e["type"] == "digest" for e in entries))

    def test_journal_is_skipped(self):
        journal = make_venue("media", rolling=True)
        journal["type"] = "journal"
        journal["deadlines"] = []
        service, _, notifier, _ = self.build([journal])
        self.assertEqual(service.tick(), [])
        self.assertEqual(notifier.sent, [])

    def test_notifier_failure_degrades_to_log(self):
        repo = InMemoryRepository([venue_with(5)])
        notifier = FakeNotifier(ok=False)
        cfg = make_config()
        cfg.reminders.digest_hour = 23  # isolate the threshold path
        service = ReminderService(repo, notifier, FakeClock(NOW), lambda: cfg)
        service.tick()
        self.assertEqual(len(repo.reminders), 1)
        self.assertIn("notify failed", service.last_error or "")

    def test_toast_disabled_skips_notifier(self):
        service, repo, notifier, _ = self.build([venue_with(5)], toast=False)
        service.tick()
        self.assertEqual(notifier.sent, [])
        self.assertEqual(len(repo.reminders), 1)


if __name__ == "__main__":
    unittest.main()
