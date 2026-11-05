"""Adapters: Web Fetch → Cloud Browser fallback chain."""

from __future__ import annotations

import unittest

from app.adapters.fallback_fetcher import FallbackFetcher
from app.ports import FetchResult


class StubFetcher:
    def __init__(self, result, name="stub"):
        self.result = result
        self.name = name
        self.calls = 0

    def fetch(self, url, timeout_s=120):
        self.calls += 1
        return self.result


def ok(engine="lightmount_lite", text="x" * 400, warnings=()):
    return FetchResult(True, 100, data={"main_text": text, "engine": engine,
                                        "quality": {"text_length": len(text),
                                                    "warnings": list(warnings)}})


class FallbackTests(unittest.TestCase):
    def test_primary_used_when_content_is_good(self):
        primary, fallback = StubFetcher(ok()), StubFetcher(ok("lexmount-browser"))
        result = FallbackFetcher(primary, fallback).fetch("https://e.org")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["engine"], "lightmount_lite")
        self.assertEqual(fallback.calls, 0)

    def test_thin_content_falls_back_to_browser(self):
        primary = StubFetcher(ok(text="short", warnings=["thin_content"]))
        fallback = StubFetcher(ok("lexmount-browser", text="y" * 3000))
        result = FallbackFetcher(primary, fallback).fetch("https://e.org")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["via"], "browser_fallback")
        self.assertEqual(result.data["engine"], "lexmount-browser")
        self.assertEqual(fallback.calls, 1)

    def test_hard_failure_does_not_open_browser_by_default(self):
        primary = StubFetcher(FetchResult(False, 50, error_code="browser_fetch_failed"))
        fallback = StubFetcher(ok("lexmount-browser"))
        result = FallbackFetcher(primary, fallback).fetch("https://e.org")
        self.assertFalse(result.ok)
        self.assertEqual(fallback.calls, 0)

    def test_failure_falls_back_when_explicitly_enabled(self):
        primary = StubFetcher(FetchResult(False, 50, error_code="browser_fetch_failed"))
        fallback = StubFetcher(ok("lexmount-browser"))
        result = FallbackFetcher(primary, fallback, on_failure=True).fetch("https://e.org")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["engine"], "lexmount-browser")

    def test_both_failing_keeps_original_error(self):
        primary = StubFetcher(FetchResult(False, 50, error_code="browser_fetch_failed"))
        fallback = StubFetcher(FetchResult(False, 60, error_code="browser_timeout"))
        result = FallbackFetcher(primary, fallback, on_failure=True).fetch("https://e.org")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "browser_fetch_failed")
        self.assertIn("fallback", result.detail)

    def test_disabled_chain_never_calls_fallback(self):
        primary = StubFetcher(ok(text="short", warnings=["thin_content"]))
        fallback = StubFetcher(ok("lexmount-browser"))
        result = FallbackFetcher(primary, fallback, enabled=False).fetch("https://e.org")
        self.assertEqual(result.data["engine"], "lightmount_lite")
        self.assertEqual(fallback.calls, 0)


if __name__ == "__main__":
    unittest.main()
