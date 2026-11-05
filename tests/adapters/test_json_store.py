"""Adapters: JSON store (atomic writes, backup recovery, validation)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.adapters.json_store import JsonStore, StoreError


def venue(vid="demo-2027"):
    return {"id": vid, "name": "Demo", "abbr": "DEMO", "edition": "2027", "type": "conference",
            "rolling": False, "areas": ["ai"], "topics": ["多模态融合"], "tracks": [],
            "submission": {"preprint": "allowed"}, "acceptance": {"display": "约 23%", "percent": 23.0},
            "deadlines": [{"kind": "full_paper", "date": "2027-02-25", "time": "23:59",
                           "tz": "AoE", "source_status": "predicted"}]}


class JsonStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = JsonStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        self.store.save_venues({"schema_version": 1, "venues": [venue()]})
        self.assertEqual(len(self.store.load_venues()["venues"]), 1)

    def test_backup_on_overwrite(self):
        self.store.save_venues({"schema_version": 1, "venues": [venue("a")]})
        self.store.save_venues({"schema_version": 1, "venues": [venue("b")]})
        self.assertTrue((self.store.data_dir / "venues.json.bak").exists())

    def test_corrupt_file_recovers_from_backup(self):
        self.store.save_venues({"schema_version": 1, "venues": [venue("a")]})
        self.store.save_venues({"schema_version": 1, "venues": [venue("b")]})
        self.store.venues_path.write_text("{not json", encoding="utf-8")
        recovered = self.store.load_venues()
        self.assertEqual(recovered["venues"][0]["id"], "a")
        self.assertTrue(any("recovered" in note for note in self.store.degraded))

    def test_rejects_invalid_document(self):
        bad = {"schema_version": 1, "venues": [{"id": "x", "abbr": "", "type": "blog", "areas": []}]}
        with self.assertRaises(StoreError):
            self.store.save_venues(bad)

    def test_candidates_state_and_reminders(self):
        self.store.save_state({"venues": {"demo-2027": {"watching": True}}})
        self.assertTrue(self.store.load_state()["venues"]["demo-2027"]["watching"])
        self.store.save_candidates({"candidates": [{"venue_id": "x"}]})
        self.assertEqual(len(self.store.load_candidates()["candidates"]), 1)
        self.store.append_reminder({"type": "threshold"})
        self.store.append_reminder({"type": "digest"})
        self.assertEqual(self.store.read_reminders(10)[0]["type"], "digest")

    def test_runs_and_audit(self):
        self.store.save_run({"run_id": "r1", "summary": {"targets": 1}, "attempts": []})
        self.assertEqual(self.store.list_runs(1)[0]["run_id"], "r1")
        self.store.append_audit({"venue_id": "demo", "after": {"date": "2027-02-20"}})
        self.assertEqual(self.store.read_audit(1)[0]["venue_id"], "demo")

    def test_scrape_state_defaults(self):
        state = self.store.load_scrape_state()
        self.assertIsNone(state["last_auto_date"])
        self.store.save_scrape_state({"last_auto_date": "2026-10-30", "last_auto_at": "x"})
        self.assertEqual(self.store.load_scrape_state()["last_auto_date"], "2026-10-30")


if __name__ == "__main__":
    unittest.main()
