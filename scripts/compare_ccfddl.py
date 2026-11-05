"""Compare our catalog with the CCFDDL dataset (ccfddl.github.io)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# Our abbr -> CCFDDL title
MAP = {
    "CVPR": "CVPR", "ICCV": "ICCV", "MICCAI": "MICCAI", "IPMI": "IPMI", "MIDL": "MIDL",
    "ISBI": "ISBI", "SPIE MI": "SPIE", "ICML": "ICML", "NeurIPS": "NeurIPS", "ICLR": "ICLR",
    "AAAI": "AAAI", "IJCAI": "IJCAI", "ACM MM": "ACM MM", "ACL": "ACL", "EMNLP": "EMNLP",
    "ICASSP": "ICASSP", "ICIP": "ICIP", "CHIL": "CHIL", "MLHC": "MLHC", "ML4H": "ML4H",
    "AMIA": "AMIA", "ICHI": "ICHI", "BIBM": "BIBM", "ACM BCB": "BCB",
}


def main() -> None:
    raw = Path(BASE / "data" / "ccfddl_raw.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    by_title = {item["title"]: item for item in data}
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))

    print(f"CCFDDL: {len(data)} conferences\n")
    for venue in doc["venues"]:
        if venue.get("type") != "conference":
            continue
        title = MAP.get(venue["abbr"])
        item = by_title.get(title) if title else None
        stored = [f"{d['kind']}={d['date']}" for d in venue.get("deadlines", [])
                  if d["kind"] in ("abstract", "full_paper")]
        if not item:
            print(f"{venue['abbr']:10s} NOT IN CCFDDL   stored={stored}")
            continue
        confs = item.get("confs") or []
        years = sorted({c.get("year") for c in confs if c.get("year")})
        latest = max(confs, key=lambda c: c.get("year") or 0) if confs else {}
        timeline = latest.get("timeline") or []
        print(f"{venue['abbr']:10s} years={years}  latest={latest.get('year')} link={latest.get('link')}")
        print(f"           stored={stored}")
        for entry in timeline:
            print(f"           timeline: {entry.get('deadline')} {entry.get('timezone')} {entry.get('comment')}")


if __name__ == "__main__":
    main()
