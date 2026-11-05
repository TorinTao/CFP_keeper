"""Analyse the collected Cloud Browser pages offline (no network)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.domain import cfp_parser, deadlines  # noqa: E402

TEXT_DIR = BASE / "data" / "verify_text"
NOW = datetime.now(deadlines.timezone.utc)


def main() -> None:
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))
    for venue in doc["venues"]:
        if venue.get("type") != "conference":
            continue
        path = TEXT_DIR / f"{venue['id']}.json"
        if not path.exists():
            print(f"== {venue['abbr']}: NO PAGE")
            continue
        page = json.loads(path.read_text(encoding="utf-8"))
        cands = cfp_parser.parse_candidates(page["text"], venue["id"], page["url"], now=NOW)
        print(f"== {venue['abbr']}  ({len(page['text'])} chars) {page['url']}")
        print("   stored:", "; ".join(
            f"{d['kind']}={d['date']}({d['source_status']})" for d in venue.get("deadlines", [])
            if d["kind"] in ("abstract", "full_paper")))
        for cand in cands:
            print(f"   cand  : {cand['kind']}={cand['date']} {cand['tz']}  <- {cand['snippet'][:110]}")
        if not cands:
            print("   (no candidates)")


if __name__ == "__main__":
    main()
