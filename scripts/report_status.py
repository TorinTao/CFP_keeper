"""Per-venue verification status report: what is verified, what cannot be, why."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.domain import deadlines, schema  # noqa: E402

VERIFIABLE = {"abstract", "full_paper", "supplementary", "notification",
              "camera_ready", "rebuttal"}
EVIDENCE = {"confirmed", "verified"}
THIRD = {"aggregator"}
UNVERIFIED = {"unpublished", "blocked", "predicted"}

# Some venues are technically unreachable (Cloudflare / placeholder / empty page);
# the rest are simply "official site has not published the dates yet".
TECH_MARKERS = ("Cloudflare", "占位页", "正文为空", "不可访问", "403")


def classify(dl: dict) -> tuple[str, str]:
    note = dl.get("note") or ""
    if any(marker in note for marker in TECH_MARKERS):
        return "不能核验（站点问题）", note
    if dl.get("source_status") == "unpublished":
        return "能核验，但官网未公布", "已访问官网页面，页面上没有该日期"
    return "尚未核验", "从未成功读取过官网"


def main() -> None:
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))
    rows = []
    for venue in doc["venues"]:
        if venue.get("type") != "conference":
            continue
        dls = [dl for dl in venue.get("deadlines") or [] if dl.get("kind") in VERIFIABLE]
        evidence = [dl for dl in dls if dl["source_status"] in EVIDENCE]
        third = [dl for dl in dls if dl["source_status"] in THIRD]
        missing = [dl for dl in dls if dl["source_status"] in UNVERIFIED]

        if evidence:
            verdict = "已核验"
            detail = "；".join(f"{schema.KIND_LABELS.get(d['kind'], d['kind'])} {d['date']}"
                               f"（{'人工' if d['source_status'] == 'confirmed' else '自动'}）"
                               for d in evidence)
            source = (evidence[0].get("source") or {}).get("url") or venue.get("cfp_url")
        elif third:
            verdict = "第三方来源"
            detail = "；".join(f"{schema.KIND_LABELS.get(d['kind'], d['kind'])} {d['date']}"
                               for d in third)
            source = (third[0].get("source") or {}).get("url") or ""
        else:
            verdict = "未核验"
            detail = ""
            source = venue.get("cfp_url") or ""
        rows.append({"abbr": venue["abbr"], "name": venue.get("name", ""),
                     "verdict": verdict, "detail": detail, "source": source,
                     "missing": missing, "venue": venue})

    order = {"已核验": 0, "第三方来源": 1, "未核验": 2}
    rows.sort(key=lambda r: (order[r["verdict"]], r["abbr"]))

    lines = ["# 核验状态清单", "",
             "「已核验」= 有官网原文证据；「第三方来源」= 来自 CCFDDL 数据集；"
             "「未核验」= 目前拿不到证据，下面写明原因。", ""]

    print("== 已核验 / 第三方来源 ==")
    for row in rows:
        if row["verdict"] == "未核验":
            continue
        print(f"  {row['abbr']:9s} {row['verdict']:5s} {row['detail'][:52]}")
        lines.append(f"- **{row['abbr']}**（{row['verdict']}）：{row['detail']} — {row['source']}")

    print("\n== 未核验 ==")
    lines += ["", "## 未核验的会议（含原因）", "",
              "| 会议 | 结论 | 原因 | 官网地址 |", "|---|---|---|---|"]
    for row in rows:
        if row["verdict"] != "未核验":
            continue
        reasons, categories = [], set()
        for dl in row["missing"]:
            label, note = classify(dl)
            categories.add(label)
            reasons.append(f"{schema.KIND_LABELS.get(dl['kind'], dl['kind'])}：{label}" +
                           (f"（{note[:38]}）" if note else ""))
        reason_text = "；".join(reasons[:2]) or "无数据"
        category = "不能核验（站点问题）" if "不能核验（站点问题）" in categories else "能核验，但官网未公布"
        print(f"  {row['abbr']:9s} [{category}] {reason_text[:100]}")
        lines.append(f"| {row['abbr']} | {category} | {reason_text.replace('|', '/')} | {row['source']} |")

    out = BASE / "docs" / "verification-status.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nwritten:", out)


if __name__ == "__main__":
    main()
