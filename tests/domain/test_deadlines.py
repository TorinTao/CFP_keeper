"""Domain: deadline parsing, conversion and countdown."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.domain import deadlines


class ParseTests(unittest.TestCase):
    def test_aoe_is_next_day_evening_in_beijing(self):
        when = deadlines.parse_deadline("2026-12-07", "23:59", "AoE")
        self.assertEqual(when, datetime(2026, 12, 8, 11, 59, tzinfo=timezone.utc))
        self.assertEqual(deadlines.to_display(when).strftime("%Y-%m-%d %H:%M"), "2026-12-08 19:59")

    def test_pst(self):
        when = deadlines.parse_deadline("2026-12-07", "23:59", "PST")
        self.assertEqual(deadlines.to_display(when).strftime("%Y-%m-%d %H:%M"), "2026-12-08 15:59")

    def test_compact_time_and_midnight_crossing(self):
        self.assertEqual(deadlines.parse_time("2359"), (23, 59))
        when = deadlines.parse_deadline("2027-01-01", "00:30", "Asia/Shanghai")
        self.assertEqual(when, datetime(2026, 12, 31, 16, 30, tzinfo=timezone.utc))

    def test_rejects_bad_input(self):
        for args in (("2027-02-30", "23:59", "AoE"), ("2027-01-01", "25:00", "AoE"),
                     ("2027-01-01", "23:59", "Mars/Base"), ("", "23:59", "AoE")):
            with self.assertRaises(deadlines.DeadlineError):
                deadlines.parse_deadline(*args)


class CountdownTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc)

    def test_days_floor_and_passed(self):
        self.assertEqual(deadlines.days_left(self.now + timedelta(days=7, hours=23), self.now), 7)
        past = self.now - timedelta(hours=1)
        self.assertEqual(deadlines.days_left(past, self.now), -1)
        self.assertEqual(deadlines.deadline_state(past, self.now), "passed")

    def test_describe_exposes_both_timezones(self):
        view = deadlines.describe(deadlines.parse_deadline("2026-12-07", "23:59", "AoE"), self.now)
        self.assertEqual(view["beijing"], "2026-12-08 19:59")
        self.assertIn("utc", view)
        self.assertEqual(view["urgency"], "later")  # ~38 days out

    def test_freshness_buckets(self):
        now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        self.assertEqual(deadlines.freshness((now - timedelta(days=3)).isoformat(), now), "fresh")
        self.assertEqual(deadlines.freshness((now - timedelta(days=60)).isoformat(), now), "aging")
        self.assertEqual(deadlines.freshness((now - timedelta(days=200)).isoformat(), now), "stale")
        self.assertEqual(deadlines.freshness(None, now), "unknown")


if __name__ == "__main__":
    unittest.main()
