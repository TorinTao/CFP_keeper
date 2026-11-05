"""Fill in LetPub metrics for journals that still lack them (slow, throttled)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.clock import SystemClock  # noqa: E402
from app.adapters.journal_sources import LetpubClient  # noqa: E402
from app.adapters.json_store import JsonStore  # noqa: E402
from app.domain import deadlines  # noqa: E402


def main() -> None:
    store = JsonStore(BASE)
    doc = store.load_venues()
    checked_at = deadlines.iso_local(SystemClock().now())
    client = LetpubClient(pause=3.0, retries=3)
    filled, failed = [], []

    for venue in doc["venues"]:
        if venue.get("type") != "journal" and not venue.get("rolling"):
            continue
        if (venue.get("metrics") or {}).get("impact_factor"):
            continue
        name = venue.get("name", "")
        try:
            data = client.lookup(name)
        except Exception as exc:  # noqa: BLE001
            failed.append((venue["abbr"], f"{type(exc).__name__}"))
            continue
        if not data or not data.get("impact_factor"):
            failed.append((venue["abbr"], "no data"))
            print(f"  {venue['abbr']:12s} FAIL", flush=True)
            continue
        venue["metrics"] = {
            "impact_factor": data.get("impact_factor", ""),
            "review_cycle": data.get("review_cycle", ""),
            "acceptance": data.get("acceptance", ""),
            "open_access": data.get("open_access", ""),
            "gold_oa_share": data.get("gold_oa_share", ""),
            "official_url": data.get("official_url", ""),
            "submission_url": data.get("submission_url", ""),
            "source": "LetPub",
            "url": data.get("source_url", ""),
            "checked_at": checked_at,
            "status": "third_party",
        }
        filled.append(venue["abbr"])
        print(f"  {venue['abbr']:12s} IF={data.get('impact_factor')} "
              f"cycle={data.get('review_cycle')} acc={data.get('acceptance')}", flush=True)
        store.save_venues(doc)

    store.save_venues(doc)
    print(f"\nfilled {len(filled)}: {', '.join(filled)}")
    print(f"failed {len(failed)}: {', '.join(a for a, _ in failed)}")


if __name__ == "__main__":
    main()
