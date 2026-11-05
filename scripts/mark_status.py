"""Mark deadline statuses with evidence (used for manual, page-backed updates).

Usage:
    python scripts/mark_status.py <venue_id> <kind> <status> "<note>" "<source_url>"
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.json_store import JsonStore  # noqa: E402

VALID = {"confirmed", "verified", "predicted", "scraped", "unpublished", "blocked"}


def main(argv: list[str]) -> int:
    if len(argv) < 6:
        print(__doc__)
        return 2
    venue_id, kind, status, note, url = argv[1:6]
    if status not in VALID:
        print(f"bad status {status!r}; one of {sorted(VALID)}")
        return 2

    store = JsonStore(BASE)
    doc = store.load_venues()
    for venue in doc["venues"]:
        if venue["id"] != venue_id:
            continue
        for dl in venue.get("deadlines", []):
            if dl.get("kind") == kind:
                dl["source_status"] = status
                dl["note"] = note
                dl["source"] = {"url": url, "checked_at": "2026-11-04T18:30:00+08:00"}
                store.save_venues(doc)
                print(f"{venue['abbr']} {kind} -> {status}")
                return 0
        print(f"{venue['abbr']}: no deadline of kind {kind}")
        return 1
    print(f"venue not found: {venue_id}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
