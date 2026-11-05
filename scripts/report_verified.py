"""Report which venues currently have verifiable, evidence-backed deadlines."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.domain import deadlines, schema  # noqa: E402

EVIDENCE = {"confirmed", "verified"}


def main() -> None:
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))
    rows = []
    for venue in doc["venues"]:
        for dl in venue.get("deadlines") or []:
            if dl.get("source_status") in EVIDENCE:
                source = dl.get("source") or {}
                try:
                    when = deadlines.parse_deadline(dl["date"], dl.get("time", "23:59"),
                                                    dl.get("tz", "AoE"))
                    beijing = deadlines.to_display(when).strftime("%Y-%m-%d %H:%M")
                    days = deadlines.days_left(when)
                except deadlines.DeadlineError:
                    beijing, days = "—", None
                rows.append({
                    "abbr": venue["abbr"],
                    "name": venue.get("name", ""),
                    "kind": schema.KIND_LABELS.get(dl["kind"], dl["kind"]),
                    "raw": f'{dl["date"]} {dl.get("time","23:59")} {dl.get("tz","AoE")}',
                    "beijing": beijing,
                    "days": days,
                    "status": dl["source_status"],
                    "url": source.get("url") or "",
                    "checked": (source.get("checked_at") or "")[:16],
                    "note": dl.get("note") or "",
                })

    rows.sort(key=lambda r: (r["beijing"], r["abbr"]))
    print(f"有官网证据的截止：{len(rows)} 条，涉及 {len({r['abbr'] for r in rows})} 个会议\n")
    for row in rows:
        flag = "人工" if row["status"] == "confirmed" else "自动"
        print(f"{row['abbr']:10s} {row['kind']:10s} {row['beijing']}（{row['days']:>4} 天） {flag}")
        print(f"           原始 {row['raw']}")
        print(f"           来源 {row['url']}")
        print(f"           核验于 {row['checked']} · {row['note'][:60]}")
        print()

    out = BASE / "docs" / "verified-sources.md"
    lines = ["# 已核验的截止日期（有官网/来源证据）", "",
             f"共 {len(rows)} 条，涉及 {len({r['abbr'] for r in rows})} 个会议。"
             "「人工核验」= 我们读过官网并记录；「自动核验」= 程序抓取官网并比对通过。", "",
             "| 会议 | 截止类型 | 原始时间 | 北京时间 | 剩余 | 状态 | 来源 |",
             "|---|---|---|---|---|---|---|"]
    for row in rows:
        status = "人工核验" if row["status"] == "confirmed" else "自动核验"
        lines.append(f"| {row['abbr']} | {row['kind']} | {row['raw']} | {row['beijing']} | "
                     f"{row['days']} 天 | {status} | {row['url']} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("written:", out)


if __name__ == "__main__":
    main()
