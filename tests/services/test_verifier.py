"""Service: verification run (re-check stored deadlines against the page)."""

from __future__ import annotations

import unittest

from app.ports import FetchResult
from app.services.verifier import Verifier
from tests.fakes import FakeClock, FakeFetcher, InMemoryRepository, make_config, make_venue


def page(text):
    return FetchResult(True, 900, data={"main_text": text, "status_code": 200,
                                        "engine": "lightmount_lite", "request_id": "req-1",
                                        "quality": {"text_length": len(text), "warnings": []}})


class VerifierTests(unittest.TestCase):
    def build(self, venues, pages, **verify_cfg):
        repo = InMemoryRepository(venues)
        fetcher = FakeFetcher(pages)
        clock = FakeClock()
        config = make_config()
        for key, value in verify_cfg.items():
            setattr(config.verify, key, value)
        return Verifier(repo, fetcher, clock, lambda: config), repo, fetcher

    def test_matching_page_marks_verified(self):
        text = "Paper submission deadline: February 25, 2027 (23:59 AoE)."
        verifier, repo, _ = self.build([make_venue()], {"https://example.org/cfp": page(text)})
        record = verifier.verify()

        self.assertEqual(record["kind"], "verify")
        self.assertEqual(record["summary"]["verified"], 1)
        self.assertEqual(record["summary"]["updated"], 0)
        deadline = repo.venues["venues"][0]["deadlines"][0]
        self.assertEqual(deadline["source_status"], "verified")
        self.assertTrue(deadline["source"]["checked_at"])
        self.assertEqual(repo.saved_venues, 1)

    def test_small_drift_updates_and_audits(self):
        text = "Paper submission deadline: February 20, 2027 (23:59 AoE)."
        verifier, repo, _ = self.build([make_venue()], {"https://example.org/cfp": page(text)})
        record = verifier.verify()

        self.assertEqual(record["summary"]["updated"], 1)
        deadline = repo.venues["venues"][0]["deadlines"][0]
        self.assertEqual(deadline["date"], "2027-02-20")
        self.assertEqual(deadline["source_status"], "scraped")
        self.assertIn("建议确认", deadline["note"])
        self.assertEqual(len(repo.audit), 1)
        self.assertEqual(repo.audit[0]["kind"], "verify")

    def test_big_drift_flags_mismatch_without_writing(self):
        text = "Paper submission deadline: July 01, 2027 (23:59 AoE)."
        verifier, repo, _ = self.build([make_venue()], {"https://example.org/cfp": page(text)})
        record = verifier.verify()

        self.assertEqual(record["summary"]["mismatch"], 1)
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["date"], "2027-02-25")

    def test_mismatch_is_recorded_on_the_deadline(self):
        text = "Paper submission deadline: July 01, 2027 (23:59 AoE)."
        verifier, repo, _ = self.build([make_venue()], {"https://example.org/cfp": page(text)})
        verifier.verify()
        deadline = repo.venues["venues"][0]["deadlines"][0]
        self.assertEqual(deadline["date"], "2027-02-25")  # value untouched
        self.assertEqual(deadline["disputed"]["page_date"], "2027-07-01")
        self.assertGreater(deadline["disputed"]["shift_days"], 30)

    def test_page_without_the_kind_marks_unpublished(self):
        verifier, repo, _ = self.build([make_venue()], {"https://example.org/cfp": page("Welcome to the conference.")})
        record = verifier.verify()
        self.assertEqual(record["summary"]["not_found"], 1)
        self.assertEqual(record["summary"]["marked_unpublished"], 1)
        deadline = repo.venues["venues"][0]["deadlines"][0]
        self.assertEqual(deadline["source_status"], "unpublished")
        self.assertIn("未见该截止日期", deadline["note"])
        # the guessed date is kept, only its status changes
        self.assertEqual(deadline["date"], "2027-02-25")

    def test_confirmed_rows_are_not_marked_unpublished(self):
        venue = make_venue(status="confirmed")
        verifier, repo, _ = self.build([venue], {"https://example.org/cfp": page("Nothing here.")})
        verifier.verify(pending_only=False)
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["source_status"], "confirmed")
        self.assertEqual(repo.saved_venues, 0)

    def test_fetch_failure_marks_blocked(self):
        verifier, repo, _ = self.build([make_venue()], {})
        record = verifier.verify()
        self.assertEqual(record["summary"]["failed"], 1)
        self.assertEqual(record["summary"]["marked_blocked"], 1)
        self.assertEqual(record["checks"][0]["error_code"], "not_configured")
        deadline = repo.venues["venues"][0]["deadlines"][0]
        self.assertEqual(deadline["source_status"], "blocked")
        self.assertIn("官网当前不可访问", deadline["note"])

    def test_pending_only_skips_confirmed(self):
        venue = make_venue(status="confirmed")
        text = "Paper submission deadline: February 25, 2027."
        verifier, repo, fetcher = self.build([venue], {"https://example.org/cfp": page(text)})
        record = verifier.verify()
        self.assertEqual(record["summary"]["verified"], 0)
        self.assertEqual(record["checks"][0]["actions"], [])

    def test_confirmed_is_never_overwritten(self):
        venue = make_venue(status="confirmed")
        text = "Paper submission deadline: February 20, 2027."
        verifier, repo, _ = self.build([venue], {"https://example.org/cfp": page(text)})
        verifier.verify(pending_only=False)
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["date"], "2027-02-25")
        self.assertEqual(repo.saved_venues, 0)

    def test_pending_only_false_rechecks_verified_rows(self):
        venue = make_venue(status="verified")
        text = "Paper submission deadline: February 25, 2027."
        verifier, _, _ = self.build([venue], {"https://example.org/cfp": page(text)})
        self.assertEqual(verifier.verify(pending_only=True)["summary"]["verified"], 0)
        verifier2, _, _ = self.build([venue], {"https://example.org/cfp": page(text)})
        self.assertEqual(verifier2.verify(pending_only=False)["summary"]["verified"], 1)

    def test_follows_important_dates_link_from_homepage(self):
        homepage = FetchResult(True, 100, data={"main_text": "Welcome to the conference.",
                                                "status_code": 200, "quality": {}})
        dates_page = page("Paper submission deadline: February 25, 2027 (23:59 AoE).")
        html = '<html><body><a href="/dates">Important Dates</a></body></html>'
        repo = InMemoryRepository([make_venue()])
        fetcher = FakeFetcher(
            {"https://example.org/cfp": homepage, "https://example.org/dates": dates_page},
            html={"https://example.org/cfp": html},
        )
        config = make_config()
        verifier = Verifier(repo, fetcher, FakeClock(), lambda: config)
        record = verifier.verify()

        self.assertEqual(record["summary"]["followed"], 1)
        self.assertEqual(record["summary"]["verified"], 1)
        self.assertEqual(record["checks"][0]["followed_url"], "https://example.org/dates")
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["source_status"], "verified")

    def test_venue_filter_limits_targets(self):
        venues = [make_venue("a-2027"), make_venue("b-2027")]
        text = "Paper submission deadline: February 25, 2027."
        verifier, _, fetcher = self.build(venues, {"https://example.org/cfp": page(text)})
        record = verifier.verify(["a-2027"])
        self.assertEqual(record["summary"]["targets"], 1)
        self.assertEqual(len(fetcher.calls), 1)


class ThirdPartyTests(unittest.TestCase):
    """CCFDDL fallback: used for discovery and as an explicitly-labelled source."""

    class FakeDataset:
        def __init__(self, link="", dates=None):
            self._entry = {"link": link, "dates": dates or {}}

        def lookup(self, abbr, year):
            return {"link": self._entry["link"], "tz": "AoE",
                    "deadlines": dict(self._entry["dates"])}

    def build(self, pages, link="", dates=None, html=None):
        repo = InMemoryRepository([make_venue()])
        fetcher = FakeFetcher(pages, html=html or {})
        clock = FakeClock()
        config = make_config()
        dataset = self.FakeDataset(link, dates)
        verifier = Verifier(repo, fetcher, clock, lambda: config, third_party=dataset)
        return verifier, repo, fetcher

    def test_uses_dataset_date_when_page_has_none(self):
        verifier, repo, _ = self.build(
            {"https://example.org/cfp": page("Welcome.")},
            dates={"full_paper": "2027-02-18"},
        )
        record = verifier.verify()
        self.assertEqual(record["summary"]["aggregated"], 1)
        deadline = repo.venues["venues"][0]["deadlines"][0]
        self.assertEqual(deadline["date"], "2027-02-18")
        self.assertEqual(deadline["source_status"], "aggregator")
        self.assertIn("CCFDDL", deadline["note"])

    def test_edition_link_is_tried_for_discovery(self):
        dates_page = page("Paper submission deadline: February 25, 2027.")
        verifier, repo, fetcher = self.build(
            {"https://example.org/home": page("Home."),
             "https://example.org/2027": dates_page},
            link="https://example.org/2027",
        )
        record = verifier.verify()
        self.assertEqual(record["summary"]["followed"], 1)
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["source_status"], "verified")

    def test_blocked_site_uses_dataset_instead_of_blocked(self):
        verifier, repo, _ = self.build({}, dates={"full_paper": "2027-02-20"})
        record = verifier.verify()
        self.assertEqual(record["summary"]["failed"], 1)
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["source_status"], "aggregator")

    def test_no_dataset_keeps_blocked(self):
        repo = InMemoryRepository([make_venue()])
        verifier = Verifier(repo, FakeFetcher({}), FakeClock(), lambda: make_config())
        verifier.verify()
        self.assertEqual(repo.venues["venues"][0]["deadlines"][0]["source_status"], "blocked")


if __name__ == "__main__":
    unittest.main()
