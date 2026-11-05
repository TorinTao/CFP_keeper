"""Offline analysis of all collected evidence (no network).

Produces data/verify_report.json with, per conference, the candidates found on
the official pages and what the stored (predicted) deadlines currently say.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.domain import cfp_parser, deadlines  # noqa: E402

TEXT_DIR = BASE / "data" / "verify_text"
SITE_DIR = BASE / "data" / "verify_site"
NOW = datetime.now(deadlines.timezone.utc)
WANT = {"abstract", "full_paper", "supplementary", "notification", "camera_ready", "rebuttal"}


def pages_for(venue_id: str) -> list[dict]:
    pages: list[dict] = []
    single = TEXT_DIR / f"{venue_id}.json"
    if single.exists():
        data = json.loads(single.read_text(encoding="utf-8"))
        pages.append({"url": data["url"], "text": data["text"]})
    multi = SITE_DIR / f"{venue_id}.json"
    if multi.exists():
        data = json.loads(multi.read_text(encoding="utf-8"))
        pages.extend(data.get("pages", []))
    return pages


def main() -> None:
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))
    report = {}
    for venue in doc["venues"]:
        if venue.get("type") != "conference":
            continue
        stored = [{"kind": d["kind"], "date": d["date"], "status": d["source_status"]}
                  for d in venue.get("deadlines", []) if d["kind"] in WANT]
        seen: dict[tuple[str, str], dict] = {}
        for page in pages_for(venue["id"]):
            cands = cfp_parser.parse_candidates(page["text"], venue["id"], page["url"], now=NOW)
            for cand in cands:
                if cand["kind"] not in WANT:
                    continue
                key = (cand["kind"], cand["date"])
                if key not in seen:
                    seen[key] = {**cand, "url": page["url"]}
        report[venue["id"]] = {"abbr": venue["abbr"], "stored": stored,
                               "candidates": list(seen.values())}

    out = BASE / "data" / "verify_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for vid, item in report.items():
        print(f"== {item['abbr']}")
        print("   stored:", "; ".join(f"{d['kind']}={d['date']}({d['status']})" for d in item["stored"]))
        for cand in item["candidates"]:
            print(f"   cand  : {cand['kind']}={cand['date']}  <- {cand['snippet'][:95]}")
        if not item["candidates"]:
            print("   (nothing found)")


if __name__ == "__main__":
    main()
