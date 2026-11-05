"""Mark the four unreachable venues as "deferred" and stop alerting on them.

The sites are either placeholders (EMNLP/ICHI 2027 not built yet) or behind a
Cloudflare challenge (AMIA / ACM DL). Their 2027 CFPs are unpublished anyway, so
retrying every day only produces noise. They are retried after `verify_after`.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.json_store import JsonStore  # noqa: E402

DEFER_DAYS = 14
REASONS = {
    "emnlp-2027": "2027.emnlp.org 目前只是占位页（正文不足 200 字），2027 官网未上线",
    "amia-2027": "amia.org 被 Cloudflare 拦截（HTTP 403），无法读取正文",
    "ichi-2027": "ieee-ichi.org 打开后正文为空（<120 字），2027 站点未上线",
    "bcb-2027": "dl.acm.org 被 Cloudflare 拦截（HTTP 403），无法读取正文",
}
VERIFIABLE = {"abstract", "full_paper", "supplementary", "notification", "camera_ready", "rebuttal"}


def main() -> None:
    store = JsonStore(BASE)
    doc = store.load_venues()
    retry_after = (date.today() + timedelta(days=DEFER_DAYS)).isoformat()
    touched = []
    for venue in doc["venues"]:
        reason = REASONS.get(venue.get("id"))
        if not reason:
            continue
        venue["verify_after"] = retry_after
        for dl in venue.get("deadlines", []):
            if dl.get("kind") in VERIFIABLE and dl.get("source_status") != "confirmed":
                dl["source_status"] = "unpublished"
                dl["note"] = "{}；暂缓核验至 {}".format(reason, retry_after)
        touched.append(venue["abbr"])
    store.save_venues(doc)
    print("deferred until", retry_after, ":", ", ".join(touched))


if __name__ == "__main__":
    main()
