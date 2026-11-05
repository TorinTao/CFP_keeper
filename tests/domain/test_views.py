"""Domain: venue view models (next deadline, freshness, filtering helpers)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.domain import views

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)


def venue(date="2027-02-25", status="predicted", kinds=("full_paper", "notification")):
    return {
        "id": "demo", "name": "Demo", "abbr": "DEMO", "edition": "2027", "type": "conference",
        "rolling": False, "areas": ["ai"], "topics": ["多模态融合"], "tracks": [], "materials": [],
        "deadlines": [{"kind": k, "date": date, "time": "23:59", "tz": "AoE",
                       "source_status": status} for k in kinds],
    }


class VenueViewTests(unittest.TestCase):
    def test_next_is_earliest_upcoming(self):
        view = views.venue_view(venue(), {"venues": {}}, NOW)
        self.assertEqual(view["next"]["kind"], "full_paper")
        self.assertGreater(view["next"]["days_left"], 0)
        self.assertEqual(len(view["deadlines"]), 2)

    def test_needs_review_when_any_predicted(self):
        self.assertTrue(views.venue_view(venue(status="predicted"), {"venues": {}}, NOW)["needs_review"])
        self.assertFalse(views.venue_view(venue(status="confirmed"), {"venues": {}}, NOW)["needs_review"])

    def test_watching_comes_from_state(self):
        view = views.venue_view(venue(), {"venues": {"demo": {"watching": True}}}, NOW)
        self.assertTrue(view["watching"])

    def test_invalid_deadline_is_reported_not_raised(self):
        bad = venue()
        bad["deadlines"][0]["date"] = "2027-02-30"
        view = views.venue_view(bad, {"venues": {}}, NOW)
        self.assertEqual(view["deadlines"][0]["state"], "invalid")

    def test_sort_key_puts_items_without_deadline_last(self):
        with_next = views.venue_view(venue(), {"venues": {}}, NOW)
        rolling = {"id": "j", "type": "journal", "rolling": True, "areas": ["ai"], "abbr": "J",
                   "deadlines": []}
        without = views.venue_view(rolling, {"venues": {}}, NOW)
        ordered = sorted([without, with_next], key=views.sort_key)
        self.assertEqual(ordered[0]["id"], "demo")

    def test_summarize_counts(self):
        items = [views.venue_view(venue(), {"venues": {}}, NOW),
                 views.venue_view(venue(status="confirmed"), {"venues": {}}, NOW)]
        counts = views.summarize(items)
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["conference"], 2)
        self.assertEqual(counts["needs_review"], 1)


if __name__ == "__main__":
    unittest.main()
