"""Domain: discovering the "important dates" page from a homepage."""

from __future__ import annotations

import unittest

from app.domain import cfp_parser

HTML = """
<html><body>
  <a href="/">Home</a>
  <a href="/wp-content/themes/x/style.css">style</a>
  <a href="/feed/">Feed</a>
  <a href="https://twitter.com/conf">Twitter</a>
  <a href="/conferences/2027/important-dates/">Important Dates</a>
  <a href="/sponsors">Sponsors</a>
  <a href="https://example.org/dates">Key dates and deadlines</a>
  <a href="/files/cfp.pdf">Call for papers (PDF)</a>
</body></html>
"""


class FindDateLinksTests(unittest.TestCase):
    def test_picks_dates_pages_first(self):
        links = cfp_parser.find_date_links(HTML, "https://example.org/")
        self.assertTrue(links)
        self.assertIn("https://example.org/conferences/2027/important-dates/", links)
        self.assertIn("https://example.org/dates", links)

    def test_skips_assets_social_and_pdf(self):
        links = cfp_parser.find_date_links(HTML, "https://example.org/")
        joined = " ".join(links)
        self.assertNotIn(".css", joined)
        self.assertNotIn("twitter", joined)
        self.assertNotIn(".pdf", joined)
        self.assertNotIn("/feed", joined)

    def test_relative_links_are_absolutized(self):
        links = cfp_parser.find_date_links(HTML, "https://example.org/conferences/")
        self.assertIn("https://example.org/conferences/2027/important-dates/", links)

    def test_respects_limit(self):
        self.assertLessEqual(len(cfp_parser.find_date_links(HTML, "https://e.org/", limit=1)), 1)

    def test_no_links_returns_empty(self):
        self.assertEqual(cfp_parser.find_date_links("<html><body>none</body></html>", "https://e.org/"), [])
        self.assertEqual(cfp_parser.find_date_links("", "https://e.org/"), [])


if __name__ == "__main__":
    unittest.main()
