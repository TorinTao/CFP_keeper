"""Domain: candidate extraction from page text."""

from __future__ import annotations

import unittest
from datetime import date

from app.domain import cfp_parser

TODAY = date(2026, 10, 30)


class ParserTests(unittest.TestCase):
    def parse(self, text):
        return cfp_parser.parse_candidates(text, "demo-2027", "https://e.org", today=TODAY)

    def test_english_full_paper_with_aoe(self):
        got = self.parse("Paper submission deadline: March 15, 2027 (23:59 AoE).")
        self.assertEqual(got[0]["date"], "2027-03-15")
        self.assertEqual(got[0]["kind"], "full_paper")
        self.assertEqual(got[0]["tz"], "AoE")
        self.assertEqual(got[0]["status"], "candidate")

    def test_chinese_date(self):
        got = self.parse("全文截稿：2027年3月15日")
        self.assertEqual(got[0]["date"], "2027-03-15")

    def test_workshop_is_not_main_track(self):
        got = self.parse("Workshop Paper Submission Tuesday 26 January 2027. "
                         "Main paper submission deadline: 26 February 2027")
        kinds = {c["date"]: c["kind"] for c in got}
        self.assertEqual(kinds.get("2027-01-26"), "workshop")
        self.assertEqual(kinds.get("2027-02-26"), "full_paper")

    def test_drops_dates_without_deadline_keywords(self):
        self.assertEqual(self.parse("News: 2026-10-20 workshop recap"), [])

    def test_drops_dates_far_in_the_past(self):
        self.assertEqual(self.parse("Submission deadline: 2025-01-01"), [])

    def test_timezone_detection(self):
        self.assertEqual(self.parse("Deadline 2027-05-01 23:59 PST")[0]["tz"], "PST")
        self.assertEqual(self.parse("Deadline 2027-05-01 23:59 北京时间")[0]["tz"], "Asia/Shanghai")
        self.assertEqual(self.parse("Deadline 2027-05-01")[0]["tz"], "AoE")

    def test_enrollment_deadline_is_not_the_paper_deadline(self):
        got = self.parse(
            "Important Dates Paper Enrollment Deadline* Nov 10, 2026 11:59 PM AOE. "
            "Paper Submission Deadline Nov 13, 2026 11:59 PM AOE.")
        kinds = {c["date"]: c["kind"] for c in got}
        self.assertEqual(kinds.get("2026-11-10"), "registration")
        self.assertEqual(kinds.get("2026-11-13"), "full_paper")

    def test_registration_deadline_is_not_the_paper_deadline(self):
        got = self.parse(
            "Paper Registration Deadline Nov 11, 2026 11:59 PM AOE. "
            "Paper Submission Deadline Nov 13, 2026 11:59 PM AOE.")
        kinds = {c["date"]: c["kind"] for c in got}
        self.assertEqual(kinds.get("2026-11-11"), "registration")
        self.assertEqual(kinds.get("2026-11-13"), "full_paper")

    def test_date_without_keyword_is_dropped(self):
        got = self.parse(
            "Important Dates OpenReview accounts created for all authors Friday, January 15, 2027 "
            "Submissions due Wednesday, February 3, 2027")
        dates = {c["date"]: c["kind"] for c in got}
        self.assertNotIn("2027-01-15", dates)
        self.assertEqual(dates.get("2027-02-03"), "full_paper")

    def test_deduplicates_same_kind_and_date(self):
        got = self.parse("Full paper deadline: 2027-02-01. Full paper deadline: 2027-02-01.")
        self.assertEqual(len(got), 1)


if __name__ == "__main__":
    unittest.main()
