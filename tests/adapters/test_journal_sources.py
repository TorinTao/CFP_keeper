"""Adapters: journal metadata parsing (Crossref + LetPub)."""

from __future__ import annotations

import unittest

from app.adapters.journal_sources import (parse_crossref_search, parse_letpub_detail,
                                          title_similarity)

CROSSREF_PAYLOAD = {
    "message": {
        "items": [
            {"title": "IEEE Transactions on Medical Imaging",
             "publisher": "Institute of Electrical and Electronics Engineers",
             "ISSN": ["0278-0062", "1558-254X"], "URL": "https://doi.org/10.1109/tmi"},
            {"title": "Journal of Medical Imaging", "publisher": "SPIE",
             "ISSN": ["2329-4302"], "URL": "https://doi.org/10.1117/jmi"},
        ]
    }
}

LETPUB_HTML = """
<html><head><title>LetPub IEEE TRANSACTIONS ON MEDICAL IMAGING 影响因子12.400
中科院分区: 2区</title></head><body>
<table>
<tr><td>期刊ISSN</td><td>0278-0062</td></tr>
<tr><td>E-ISSN</td><td>1558-0062</td></tr>
<tr><td>出版商</td><td>Institute of Electrical and Electronics Engineers Inc.</td></tr>
<tr><td>是否OA开放访问</td><td>No</td></tr>
<tr><td>期刊官方网站</td><td>http://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=42</td></tr>
<tr><td>期刊投稿网址</td><td>http://mc.manuscriptcentral.com/tmi-ieee</td></tr>
<tr><td>平均审稿速度</td><td>网友分享经验： 平均5.4个月</td></tr>
<tr><td>平均录用比例</td><td>网友分享经验： 很难</td></tr>
<tr><td>Gold OA文章占比</td><td>10.40%</td></tr>
<tr><td>出版国家或地区</td><td>UNITED STATES</td></tr>
<tr><td>出版周期</td><td>Monthly</td></tr>
</table></body></html>
"""


class CrossrefParseTests(unittest.TestCase):
    def test_parses_items(self):
        items = parse_crossref_search(CROSSREF_PAYLOAD)
        self.assertEqual(items[0]["title"], "IEEE Transactions on Medical Imaging")
        self.assertIn("0278-0062", items[0]["issn"])

    def test_similarity(self):
        self.assertGreater(title_similarity("IEEE Transactions on Medical Imaging",
                                            "IEEE transactions on medical imaging"), 0.95)
        self.assertLess(title_similarity("Medical Image Analysis", "Radiology"), 0.2)


class LetpubParseTests(unittest.TestCase):
    def setUp(self):
        self.data = parse_letpub_detail(LETPUB_HTML)

    def test_identity_fields(self):
        self.assertEqual(self.data["issn"], "0278-0062")
        self.assertEqual(self.data["eissn"], "1558-0062")
        self.assertIn("Electrical", self.data["publisher"])

    def test_metrics(self):
        self.assertEqual(self.data["impact_factor"], "12.400")
        self.assertIn("5.4", self.data["review_cycle"])
        self.assertEqual(self.data["acceptance"], "很难")
        self.assertEqual(self.data["open_access"], "No")

    def test_empty_metric_is_dropped_not_colon(self):
        html = "<table><tr><td>平均审稿速度</td><td><b>网友分享经验：</b><br><br></td></tr></table>"
        data = parse_letpub_detail(html)
        self.assertNotIn("review_cycle", data)

    def test_urls(self):
        self.assertIn("ieeexplore", self.data["official_url"])
        self.assertIn("manuscriptcentral", self.data["submission_url"])


if __name__ == "__main__":
    unittest.main()
