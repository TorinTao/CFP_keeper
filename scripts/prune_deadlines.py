"""Strip deadlines that have no source from the kept venues.

Keeps only confirmed / verified / aggregator deadlines; drops predicted,
unpublished and blocked ones (those were hand-written guesses).
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


def main() -> None:
    store = JsonStore(BASE)
    backup = BASE / "data" / "backups" / f"venues-{datetime.now():%Y%m%d-%H%M%S}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BASE / "data" / "venues.json", backup)
    print("backup:", backup.name)

    doc = store.load_venues()
    kept, dropped = 0, []
    for venue in doc["venues"]:
        if venue.get("type") == "journal" or venue.get("rolling"):
            continue
        before = venue.get("deadlines") or []
        after = [dl for dl in before if dl.get("source_status") in EVIDENCE]
        if len(after) != len(before):
            dropped.extend(f"{venue['abbr']}:{dl['kind']}({dl['source_status']})" for dl in before if dl not in after)
            venue["deadlines"] = after
            kept += 1

    store.save_venues(doc)
    print(f"cleaned {kept} venues, removed {len(dropped)} unsourced deadlines")
    print("  " + ", ".join(dropped))


if __name__ == "__main__":
    main()
