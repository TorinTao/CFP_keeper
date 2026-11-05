"""Domain: iCalendar export."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.domain import ics


def venue(vid="miccai-2027", date="2027-02-25", tz="AoE", status="predicted"):
    return {"id": vid, "name": "Medical Image Computing", "abbr": "MICCAI", "edition": "2027",
            "type": "conference", "rolling": False, "materials": ["摘要"],
            "official_url": "https://www.miccai.org/",
            "deadlines": [{"kind": "full_paper", "date": date, "time": "23:59", "tz": tz,
                           "source_status": status, "note": ""}]}


class ICSTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, tzinfo=timezone.utc)

    def test_envelope(self):
        text = ics.build_calendar([venue()], now=self.now)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))

    def test_utc_conversion(self):
        text = ics.build_calendar([venue()], now=self.now)
        self.assertIn("DTSTART:20270226T115900Z", text)  # 2027-02-25 23:59 AoE

    def test_alarms(self):
        text = ics.build_calendar([venue()], now=self.now)
        self.assertEqual(text.count("BEGIN:VALARM"), 3)

    def test_skips_journal_and_past(self):
        journal = venue("media")
        journal.update(type="journal", rolling=True, deadlines=[])
        past = venue("old", date="2026-01-01")
        text = ics.build_calendar([venue(), journal, past], now=self.now)
        self.assertEqual(text.count("BEGIN:VEVENT"), 1)

    def test_folding_and_escaping(self):
        long_venue = venue()
        long_venue["name"] = "超长会议名称" * 20
        text = ics.build_calendar([long_venue], now=self.now)
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75)
        self.assertEqual(ics.escape_text("a,b;c\\d"), "a\\,b\\;c\\\\d")


if __name__ == "__main__":
    unittest.main()
