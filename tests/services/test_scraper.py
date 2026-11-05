"""Service: scrape orchestration (fetch → parse → guard → write → record)."""

from __future__ import annotations

import unittest

from app.ports import FetchResult
from app.services.scraper import Scraper
from tests.fakes import (FakeClock, FakeFetcher, InMemoryRepository, make_candidate,
                         make_config, make_venue)

PAGE = "Paper submission deadline: February 20, 2027 (23:59 AoE). "


def ok_page(text=PAGE):
    return FetchResult(True, 1200, data={"main_text": text, "status_code": 200,
                                         "engine": "lightmount_dcl", "request_id": "req-1",
                                         "quality": {"text_length": len(text), "warnings": []}})


class ScraperRunTests(unittest.TestCase):
    def build(self, venues, pages, **cfg):
        repo = InMemoryRepository(venues)
        fetcher = FakeFetcher(pages)
        clock = FakeClock()
        config = make_config(**cfg)
        return Scraper(repo, fetcher, clock, lambda: config), repo, fetcher

    def test_successful_run_records_evidence_and_applies(self):
        scraper, repo, fetcher = self.build([make_venue()], {"https://example.org/cfp": ok_page()})
        record = scraper.run()

        self.assertEqual(record["summary"]["targets"], 1)
        self.assertEqual(record["summary"]["succeeded"], 1)
        self.assertEqual(record["summary"]["candidates"], 1)
        self.assertEqual(record["summary"]["auto_applied"], 1)
        self.assertEqual(repo.runs[0]["run_id"], record["run_id"])
        self.assertEqual(len(repo.audit), 1)

        deadline = repo.venues["venues"][0]["deadlines"][0]
        self.assertEqual(deadline["source_status"], "scraped")
        self.assertEqual(deadline["date"], "2027-02-20")
        self.assertEqual(repo.audit[0]["before"]["date"], "2027-02-25")

    def test_fetch_failure_is_recorded_not_raised(self):
        scraper, repo, _ = self.build([make_venue()], {})
        record = scraper.run()
        attempt = record["attempts"][0]
        self.assertFalse(attempt["ok"])
        self.assertEqual(attempt["error_code"], "not_configured")
        self.assertEqual(record["summary"]["failed"], 1)
        # catalog untouched
        self.assertEqual(repo.saved_venues, 0)

    def test_auto_apply_off_keeps_candidates_for_review(self):
        scraper, repo, _ = self.build([make_venue()], {"https://example.org/cfp": ok_page()},
                                      auto_apply=False)
        record = scraper.run()
        self.assertNotIn("auto_applied", record["summary"])
        self.assertEqual(len(repo.candidates["candidates"]), 1)
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["source_status"], "predicted")

    def test_confirmed_deadline_is_protected(self):
        venue = make_venue(status="confirmed")
        scraper, repo, _ = self.build([venue], {"https://example.org/cfp": ok_page()})
        record = scraper.run()
        self.assertEqual(record["summary"]["auto_applied"], 0)
        self.assertEqual(record["summary"]["auto_rejected"], 1)
        self.assertEqual(record["auto_rejected_detail"][0]["reason"], "human_verified")
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["date"], "2027-02-25")

    def test_venue_filter(self):
        venues = [make_venue("a-2027"), make_venue("b-2027")]
        pages = {"https://example.org/cfp": ok_page()}
        scraper, _, fetcher = self.build(venues, pages)
        record = scraper.run(["a-2027"])
        self.assertEqual(record["summary"]["targets"], 1)
        self.assertEqual(len(fetcher.calls), 1)

    def test_venue_without_cfp_url_is_skipped(self):
        scraper, _, fetcher = self.build([make_venue(cfp_url="")], {})
        record = scraper.run()
        self.assertEqual(record["summary"]["targets"], 0)
        self.assertEqual(fetcher.calls, [])


class ScraperGuardIntegrationTests(unittest.TestCase):
    def test_ambiguous_page_writes_nothing(self):
        text = ("Paper submission deadline: February 20, 2027. "
                "Paper submission deadline: March 10, 2027.")
        repo = InMemoryRepository([make_venue()])
        scraper = Scraper(repo, FakeFetcher({"https://example.org/cfp":
                                             FetchResult(True, 1, data={"main_text": text,
                                                                        "quality": {},
                                                                        "status_code": 200})}),
                          FakeClock(), lambda: make_config())
        record = scraper.run()
        self.assertEqual(record["summary"]["auto_applied"], 0)
        reasons = [r["reason"] for r in record["auto_rejected_detail"]]
        self.assertIn("ambiguous", reasons)
        self.assertEqual(len(repo.candidates["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
