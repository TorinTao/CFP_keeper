"""Service: daily scrape scheduler (timing, dedupe, catch-up, retry)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.services.scheduler import DailyScraper, DailyVerifier, next_run_at, parse_hhmm
from tests.fakes import FakeClock, InMemoryRepository, make_config


def beijing(y, m, d, hh, mm):
    return datetime(y, m, d, hh - 8, mm, tzinfo=timezone.utc)


class ParseTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        self.assertEqual(parse_hhmm("09:00"), (9, 0))
        self.assertEqual(parse_hhmm("9：30"), (9, 30))
        for bad in ("", "9", "24:00", "09:60", "abc"):
            self.assertIsNone(parse_hhmm(bad), bad)


class NextRunTests(unittest.TestCase):
    def test_before_and_after(self):
        clock = FakeClock(beijing(2026, 10, 30, 8, 0))
        cfg = make_config(daily_time="09:00")
        self.assertEqual(next_run_at(clock, cfg), "2026-10-30 09:00")
        clock.set(beijing(2026, 10, 30, 10, 0))
        self.assertEqual(next_run_at(clock, cfg, last_date="2026-10-30"), "2026-10-31 09:00")
        self.assertIn("即将执行", next_run_at(clock, cfg, last_date="2026-10-29"))

    def test_disabled(self):
        clock = FakeClock(beijing(2026, 10, 30, 8, 0))
        self.assertEqual(next_run_at(clock, make_config(auto=False)), "")


class TickTests(unittest.TestCase):
    def build(self, now, **cfg_overrides):
        repo = InMemoryRepository()
        clock = FakeClock(now)
        cfg = make_config(**cfg_overrides)
        calls = []

        def trigger(venue_ids=None):
            calls.append(True)
            return 202, {"status": "started"}

        scraper = DailyScraper(repo, clock, lambda: cfg, trigger)
        return scraper, repo, calls, clock

    def test_waits_for_the_hour(self):
        scraper, _, calls, _ = self.build(beijing(2026, 10, 30, 8, 59))
        self.assertIsNone(scraper.tick())
        self.assertEqual(calls, [])

    def test_triggers_once_after_hour(self):
        scraper, repo, calls, _ = self.build(beijing(2026, 10, 30, 9, 0))
        self.assertIsNotNone(scraper.tick())
        self.assertEqual(calls, [True])
        self.assertEqual(repo.scrape_state["last_auto_date"], "2026-10-30")

    def test_no_second_run_when_record_exists(self):
        scraper, repo, calls, clock = self.build(beijing(2026, 10, 30, 9, 0))
        result = scraper.tick()
        repo.save_run({"run_id": "r1", "started_at": result["last_auto_at"],
                       "summary": {"targets": 1}, "attempts": []})
        clock.set(beijing(2026, 10, 30, 15, 0))
        self.assertIsNone(scraper.tick())
        self.assertEqual(len(calls), 1)

    def test_catch_up_after_missed_slot(self):
        scraper, _, calls, _ = self.build(beijing(2026, 10, 30, 14, 0))
        self.assertIsNotNone(scraper.tick())
        self.assertEqual(len(calls), 1)

    def test_retries_when_previous_attempt_left_no_record(self):
        scraper, repo, calls, _ = self.build(beijing(2026, 10, 30, 12, 0))
        repo.save_scrape_state({"last_auto_date": "2026-10-30",
                                "last_auto_at": "2026-10-30T09:00:05+08:00"})
        self.assertIsNotNone(scraper.tick())
        self.assertEqual(len(calls), 1)

    def test_skips_while_another_scrape_runs(self):
        scraper, _, calls, _ = self.build(beijing(2026, 10, 30, 12, 0))
        self.assertIsNone(scraper.tick(running=True))
        self.assertEqual(calls, [])

    def test_disabled_never_triggers(self):
        scraper, _, calls, _ = self.build(beijing(2026, 10, 30, 23, 0), auto=False)
        self.assertIsNone(scraper.tick())
        self.assertEqual(calls, [])

    def test_invalid_time_is_reported(self):
        scraper, _, calls, _ = self.build(beijing(2026, 10, 30, 12, 0), daily_time="25:99")
        self.assertIsNone(scraper.tick())
        self.assertIn("invalid daily_time", scraper.last_error or "")


if __name__ == "__main__":
    unittest.main()


class VerifySchedulerTests(unittest.TestCase):
    """DailyVerifier reuses the same timing machinery as the scraper."""

    def build(self, now, **verify_overrides):
        repo = InMemoryRepository()
        clock = FakeClock(now)
        cfg = make_config()
        for key, value in verify_overrides.items():
            setattr(cfg.verify, key, value)
        calls = []

        def trigger(venue_ids=None, pending_only=None):
            calls.append(True)
            return 202, {"status": "started"}

        job = DailyVerifier(repo, clock, lambda: cfg, trigger)
        return job, repo, calls, clock

    def test_waits_before_ten(self):
        job, _, calls, _ = self.build(beijing(2026, 10, 30, 9, 59))
        self.assertIsNone(job.tick())
        self.assertEqual(calls, [])

    def test_triggers_at_ten(self):
        job, repo, calls, _ = self.build(beijing(2026, 10, 30, 10, 0))
        self.assertIsNotNone(job.tick())
        self.assertEqual(calls, [True])
        self.assertEqual(repo.verify_state["last_auto_date"], "2026-10-30")
        self.assertIsNone(repo.scrape_state["last_auto_date"])

    def test_no_second_run_when_record_exists(self):
        job, repo, calls, clock = self.build(beijing(2026, 10, 30, 10, 0))
        result = job.tick()
        repo.save_run({"run_id": "verify-1", "kind": "verify",
                       "started_at": result["last_auto_at"], "summary": {}, "checks": []})
        clock.set(beijing(2026, 10, 30, 16, 0))
        self.assertIsNone(job.tick())
        self.assertEqual(len(calls), 1)

    def test_disabled_never_triggers(self):
        job, _, calls, _ = self.build(beijing(2026, 10, 30, 23, 0), enabled=False)
        self.assertIsNone(job.tick())
        self.assertEqual(calls, [])

    def test_next_run_uses_verify_time(self):
        clock = FakeClock(beijing(2026, 10, 30, 8, 0))
        cfg = make_config()
        self.assertEqual(next_run_at(clock, cfg, kind="verify"), "2026-10-30 10:00")
        self.assertEqual(next_run_at(clock, cfg, kind="scrape"), "2026-10-30 09:00")
