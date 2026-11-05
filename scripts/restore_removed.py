"""Re-check archived (removed) conferences and restore any that now have evidence.

Usage:
    python scripts/restore_removed.py            # dry run, prints what it found
    python scripts/restore_removed.py --apply    # actually add them back
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.ccfddl import CcfddlSource  # noqa: E402
from app.adapters.clock import SystemClock  # noqa: E402
from app.adapters.json_config import JsonConfigStore  # noqa: E402
from app.adapters.json_store import JsonStore  # noqa: E402
from app.services.verifier import Verifier  # noqa: E402

ARCHIVE = BASE / "data" / "removed_venues.json"
EVIDENCE = {"confirmed", "verified", "aggregator"}


def main(apply: bool = False) -> None:
    archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
    removed = archive.get("venues") or []
    if not removed:
        print("archive empty")
        return

    store = JsonStore(BASE)
    config = JsonConfigStore(BASE / "config.json").load()
    dataset = CcfddlSource(BASE / "data" / "ccfddl.yml")
    clock = SystemClock()

    # Verify the archive in a scratch store so the main catalog is untouched.
    scratch = JsonStore(BASE / "data" / "scratch")
    scratch.save_venues({"schema_version": 1, "venues": removed})
    from app.adapters.cli_fetcher import CliFetcher
    from app.adapters.fallback_fetcher import FallbackFetcher

    fetcher = FallbackFetcher(CliFetcher(config.scrape.cli_path), None,
                              enabled=False) if False else CliFetcher(config.scrape.cli_path)
    verifier = Verifier(scratch, fetcher, clock, lambda: config, third_party=dataset)
    record = verifier.verify()
    print("checked:", record["summary"])

    checked = {v["id"]: v for v in scratch.load_venues()["venues"]}
    ready = [v for v in removed
             if any(dl.get("source_status") in EVIDENCE for dl in checked.get(v["id"], {}).get("deadlines", []))]

    if not ready:
        print("nothing to restore yet")
        return

    print("ready to restore:", ", ".join(v["abbr"] for v in ready))
    if not apply:
        print("(dry run; pass --apply to add them back)")
        return

    doc = store.load_venues()
    existing = {v["id"] for v in doc["venues"]}
    doc["venues"].extend(checked[v["id"]] for v in ready if v["id"] not in existing)
    store.save_venues(doc)

    archive["venues"] = [v for v in removed if v["id"] not in {r["id"] for r in ready}]
    archive["restored_at"] = datetime.now().isoformat(timespec="seconds")
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("restored:", len(ready))


if __name__ == "__main__":
    main("--apply" in sys.argv)
