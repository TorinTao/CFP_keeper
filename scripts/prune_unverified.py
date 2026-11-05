"""Prune conferences that have no evidence-backed deadline.

Kept: every venue with at least one deadline carrying a source
(confirmed / verified / aggregator) plus all rolling journals.
Removed: conferences whose deadlines are only predicted / unpublished / blocked.

Run once after a verification pass:  python scripts/prune_unverified.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.json_store import JsonStore  # noqa: E402

EVIDENCE = {"confirmed", "verified", "aggregator"}


def has_evidence(venue: dict) -> bool:
    if venue.get("type") == "journal" or venue.get("rolling"):
        return True
    return any(dl.get("source_status") in EVIDENCE for dl in venue.get("deadlines") or [])


def main() -> None:
    store = JsonStore(BASE)
    backup_dir = BASE / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"venues-{stamp}.json"
    shutil.copyfile(BASE / "data" / "venues.json", backup)
    print("backup:", backup.name)

    doc = store.load_venues()
    keep, drop = [], []
    for venue in doc["venues"]:
        (keep if has_evidence(venue) else drop).append(venue)

    doc["venues"] = keep
    store.save_venues(doc)

    dropped_ids = {v["id"] for v in drop}
    state = store.load_state()
    for vid in list((state.get("venues") or {}).keys()):
        if vid in dropped_ids:
            state["venues"].pop(vid, None)
    store.save_state(state)

    candidates = store.load_candidates()
    before = len(candidates.get("candidates") or [])
    candidates["candidates"] = [c for c in candidates.get("candidates") or []
                                if c.get("venue_id") not in dropped_ids]
    if len(candidates["candidates"]) != before:
        store.save_candidates(candidates)

    print(f"kept {len(keep)} / removed {len(drop)}")
    print("kept   :", ", ".join(v["abbr"] for v in keep if v["type"] == "conference"))
    print("removed:", ", ".join(v["abbr"] for v in drop))
    print("journals kept:", sum(1 for v in keep if v["type"] == "journal"))


if __name__ == "__main__":
    main()
