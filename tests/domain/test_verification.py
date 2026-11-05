"""Domain: verification verdicts (page vs stored deadline)."""

from __future__ import annotations

import unittest
from datetime import date

from app.domain import verification

TODAY = date(2026, 10, 30)


def venue(date="2027-02-25", status="predicted", kinds=("full_paper", "notification")):
    return {"id": "demo", "deadlines": [
        {"kind": k, "date": date, "time": "23:59", "tz": "AoE",
         "source_status": status, "source": {}} for k in kinds]}


def cand(day, kind="full_paper"):
    return {"venue_id": "demo", "kind": kind, "date": day, "time": "23:59", "tz": "AoE",
            "source_url": "https://e.org", "snippet": "deadline " + day}


class VerdictTests(unittest.TestCase):
    def plan(self, venue_doc, candidates, **kwargs):
        return verification.plan_verification(venue_doc, candidates, **kwargs)

    def test_exact_match_is_verified(self):
        actions = self.plan(venue(), [cand("2027-02-25")])
        self.assertEqual(actions[0]["verdict"], "verified")
        self.assertEqual(actions[0]["shift_days"], 0)

    def test_small_drift_is_updated(self):
        actions = self.plan(venue(), [cand("2027-02-20")])
        self.assertEqual(actions[0]["verdict"], "updated")
        self.assertEqual(actions[0]["shift_days"], 5)

    def test_big_drift_is_mismatch_not_written(self):
        actions = self.plan(venue(), [cand("2027-06-01")])
        self.assertEqual(actions[0]["verdict"], "mismatch")

    def test_missing_kind_reports_not_found(self):
        actions = self.plan(venue(), [cand("2027-02-25")])
        by_kind = {a["kind"]: a["verdict"] for a in actions}
        self.assertEqual(by_kind["notification"], "not_found")

    def test_pending_only_skips_settled_rows(self):
        for status in ("confirmed", "verified"):
            actions = self.plan(venue(status=status), [cand("2027-02-25")])
            self.assertEqual(actions, [], status)

    def test_confirmed_is_never_touched_even_when_disabled(self):
        actions = self.plan(venue(status="confirmed"), [cand("2027-02-25")], pending_only=False)
        self.assertEqual(actions, [])

    def test_pending_only_false_rechecks_already_verified_rows(self):
        actions = self.plan(venue(status="verified"), [cand("2027-02-25")], pending_only=False)
        self.assertEqual(len(actions), 2)  # full_paper + notification

    def test_conference_kind_is_not_verified(self):
        actions = self.plan(venue(kinds=("conference",)), [])
        self.assertEqual(actions, [])

    def test_closest_candidate_wins(self):
        actions = self.plan(venue(), [cand("2027-02-10"), cand("2027-02-25")])
        self.assertEqual(actions[0]["verdict"], "verified")


class ApplyVerdictTests(unittest.TestCase):
    def test_verified_marks_status_and_source(self):
        deadline = {"kind": "full_paper", "date": "2027-02-25", "time": "23:59", "tz": "AoE",
                    "source_status": "predicted"}
        action = {"verdict": "verified", "candidate": cand("2027-02-25")}
        updated = verification.apply_verdict(deadline, action, "2026-11-04T12:00:00+08:00",
                                             "https://e.org/cfp")
        self.assertEqual(updated["source_status"], "verified")
        self.assertIn("自动核验", updated["note"])
        self.assertEqual(updated["source"]["url"], "https://e.org")

    def test_updated_takes_page_date(self):
        deadline = {"kind": "full_paper", "date": "2027-02-25", "time": "23:59", "tz": "AoE",
                    "source_status": "scraped"}
        action = {"verdict": "updated", "candidate": cand("2027-02-20")}
        updated = verification.apply_verdict(deadline, action, "2026-11-04T12:00:00+08:00", "u")
        self.assertEqual(updated["date"], "2027-02-20")
        self.assertEqual(updated["source_status"], "scraped")
        self.assertIn("原 2027-02-25", updated["note"])

    def test_mismatch_leaves_record_untouched(self):
        deadline = {"kind": "full_paper", "date": "2027-02-25", "source_status": "predicted"}
        action = {"verdict": "mismatch", "candidate": cand("2027-06-01")}
        self.assertEqual(verification.apply_verdict(deadline, action, "t", "u"), deadline)


if __name__ == "__main__":
    unittest.main()
