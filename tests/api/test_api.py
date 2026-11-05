"""HTTP boundary: routing over a real server with fake adapters."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from app.adapters.json_store import JsonStore
from app.api.application import Application
from app.api.handlers import Handler
from app.ports import AppConfig
from tests.fakes import FakeFetcher, make_venue


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        JsonStore(root).save_venues({"schema_version": 1, "venues": [make_venue()]})

        config = AppConfig()
        cls.app = Application(config, root, fetcher=FakeFetcher())
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        Handler.app = cls.app
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path):
        try:
            with urllib.request.urlopen(self.url(path), timeout=10) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, json.loads(body) if body else {}

    def send(self, path, method, payload=None):
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(self.url(path), data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, json.loads(body) if body else {}

    def test_health(self):
        status, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("schedule", body)

    def test_venues_and_counts(self):
        status, body = self.get("/api/venues")
        self.assertEqual(status, 200)
        self.assertEqual(body["venues"][0]["abbr"], "DEMO")
        self.assertIn("beijing", body["venues"][0]["next"])
        self.assertEqual(body["counts"]["total"], 1)

    def test_venue_detail_and_404(self):
        status, body = self.get("/api/venues/demo-2027")
        self.assertEqual(status, 200)
        self.assertEqual(body["venue"]["id"], "demo-2027")
        self.assertEqual(self.get("/api/venues/nope")[0], 404)

    def test_watch_toggle_and_filter(self):
        self.assertEqual(self.send("/api/venues/demo-2027/state", "PATCH", {"watching": True})[0], 200)
        _, body = self.get("/api/venues?watching=1")
        self.assertEqual(len(body["venues"]), 1)

    def test_settings_validation(self):
        status, body = self.get("/api/settings")
        self.assertEqual(status, 200)
        status, body = self.send("/api/settings", "PATCH", {"scrape": {"daily_time": "09:15"}})
        self.assertEqual(status, 200)
        self.assertEqual(body["settings"]["scrape"]["daily_time"], "09:15")
        self.assertEqual(self.send("/api/settings", "PATCH", {"scrape": {"daily_time": "99:99"}})[0], 400)

    def test_verify_status_endpoint(self):
        status, body = self.get("/api/verify/status")
        self.assertEqual(status, 200)
        self.assertIn("running", body)
        self.assertIn("schedule", body)

    def test_verify_kickoff(self):
        status, body = self.send("/api/verify", "POST", {"venue_ids": ["demo-2027"]})
        self.assertEqual(status, 202)
        self.assertEqual(body["status"], "started")

    def test_settings_expose_verify_block(self):
        status, body = self.get("/api/settings")
        self.assertEqual(status, 200)
        self.assertIn("verify", body)
        self.assertIn("daily_time", body["verify"])

    def test_verify_settings_validation(self):
        self.assertEqual(self.send("/api/settings", "PATCH", {"verify": {"daily_time": "11:30"}})[0], 200)
        self.assertEqual(self.send("/api/settings", "PATCH", {"verify": {"daily_time": "99:99"}})[0], 400)
        self.assertEqual(self.send("/api/settings", "PATCH", {"verify": {"max_shift_days": 999}})[0], 400)



    def test_ics(self):
        with urllib.request.urlopen(self.url("/api/ics"), timeout=10) as res:
            self.assertIn("text/calendar", res.headers.get("Content-Type", ""))
            text = res.read().decode("utf-8")
        self.assertTrue(text.startswith("BEGIN:VCALENDAR"))

    def test_static_and_traversal(self):
        with urllib.request.urlopen(self.url("/"), timeout=10) as res:
            self.assertIn("CFP Keeper", res.read().decode("utf-8"))
        self.assertEqual(self.get("/static/../config.json")[0], 404)


if __name__ == "__main__":
    unittest.main()
