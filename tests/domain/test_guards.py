"""Domain: auto-apply guards (the policy deciding what may be overwritten)."""

from __future__ import annotations

import unittest
from datetime import date

from app.domain import guards

TODAY = date(2026, 10, 30)


def venue(status="predicted", day="2027-02-25", kinds=("full_paper",)):
    return {"id": "demo", "deadlines": [
        {"kind": k, "date": day, "time": "23:59", "tz": "AoE", "source_status": status}
        for k in kinds]}


def cand(day, kind="full_paper"):
    return {"venue_id": "demo", "kind": kind, "date": day, "time": "23:59", "tz": "AoE",
            "source_url": "https://e.org", "extracted_at": "2026-10-30T11:00:00+08:00",
            "snippet": f"deadline {day}"}


class GuardTests(unittest.TestCase):
    def plan(self, venue_doc, candidates, **kwargs):
        return guards.plan_auto_apply(venue_doc, candidates, today=TODAY, **kwargs)

    def test_accepts_nearby_future_date(self):
        updates, rejected = self.plan(venue(), [cand("2027-02-20")])
        self.assertEqual(len(updates), 1)
        self.assertEqual(rejected, [])

    def test_rejects_past_and_today(self):
        updates, rejected = self.plan(venue(), [cand("2026-09-01"), cand("2026-10-30")])
        self.assertEqual(updates, [])
        self.assertTrue(all(r["reason"] == "not_in_future" for r in rejected))

    def test_never_overwrites_human_verified(self):
        updates, rejected = self.plan(venue(status="confirmed"), [cand("2027-02-20")])
        self.assertEqual(updates, [])
        self.assertEqual(rejected[0]["reason"], "human_verified")

    def test_guard_window(self):
        updates, rejected = self.plan(venue(), [cand("2026-11-12")])
        self.assertEqual(updates, [])
        self.assertEqual(rejected[0]["reason"], "outside_guard_window")

    def test_kind_must_be_declared(self):
        updates, rejected = self.plan(venue(kinds=("full_paper",)), [cand("2027-02-20", kind="notification")])
        self.assertEqual(updates, [])
        self.assertEqual(rejected[0]["reason"], "kind_not_declared")

    def test_ambiguous_is_skipped(self):
        updates, rejected = self.plan(venue(), [cand("2027-01-10"), cand("2027-02-20")])
        self.assertEqual(updates, [])
        self.assertTrue(all(r["reason"] == "ambiguous" for r in rejected))

    def test_unchanged_scraped_value(self):
        updates, rejected = self.plan(venue(status="scraped", day="2027-02-20"), [cand("2027-02-20")])
        self.assertEqual(updates, [])
        self.assertEqual(rejected[0]["reason"], "unchanged")

    def test_build_deadline_entry_marks_scraped(self):
        entry = guards.build_deadline_entry(cand("2027-02-20"))
        self.assertEqual(entry["source_status"], "scraped")
        self.assertEqual(entry["date"], "2027-02-20")
        self.assertIn("自动抓取", entry["note"])


if __name__ == "__main__":
    unittest.main()
