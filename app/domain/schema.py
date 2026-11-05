"""Domain schema: allowed values and validation for the venue catalog.

Pure functions, no I/O. The adapters call :func:`validate_venues` before writing
so a broken edit can never reach the database.
"""

from __future__ import annotations

from typing import Any

from app.domain import deadlines

VALID_TYPES = {"conference", "journal"}
# confirmed = 人工核验；verified = 自动核验（刚与官网比对过）；scraped = 自动抓取；
# predicted = 按历年规律推测，从未核对
# unpublished = 已查官网，页面上未见该日期（保留推测值）
# blocked = 官网当前不可访问（网络受限），无法核验
# aggregator = 来自第三方数据集（CCFDDL），非官网原文
# manual = 自动核验受阻（Cloudflare/站点未上线），等人工录入
VALID_SOURCE_STATUS = {"confirmed", "verified", "predicted", "scraped", "unpublished",
                       "blocked", "aggregator", "manual"}
VALID_KINDS = {
    "abstract",
    "full_paper",
    "supplementary",
    "rebuttal",
    "notification",
    "camera_ready",
    "conference",
    "registration",
}
VALID_SUBMIT_STATUS = {"", "planning", "submitted", "rejected", "accepted"}
VALID_PREPRINT = {"allowed", "conditional", "restricted", "unknown"}
VALID_CODE = {"required", "encouraged", "optional", "unknown"}
VALID_ACCESS = {"open", "subscription", "hybrid", "registration", "unknown"}
VALID_ATTENDANCE = {"in-person", "hybrid", "virtual", "n/a", "unknown"}

KIND_LABELS = {
    "abstract": "摘要截止",
    "full_paper": "全文截止",
    "supplementary": "补充材料截止",
    "rebuttal": "Rebuttal 截止",
    "notification": "录用通知",
    "camera_ready": "Camera-ready 截止",
    "conference": "会议召开",
    "registration": "论文注册截止",
}


def validate_venues(doc: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems (empty means valid)."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["document must be an object"]
    venues = doc.get("venues")
    if not isinstance(venues, list):
        return ["'venues' must be a list"]

    seen: set[str] = set()
    for index, venue in enumerate(venues):
        where = f"venues[{index}]"
        if not isinstance(venue, dict):
            problems.append(f"{where}: not an object")
            continue

        vid = venue.get("id")
        if not vid or not isinstance(vid, str):
            problems.append(f"{where}: missing id")
        elif vid in seen:
            problems.append(f"{where}: duplicate id {vid!r}")
        else:
            seen.add(vid)
            where = f"venue {vid!r}"

        if not venue.get("abbr"):
            problems.append(f"{where}: missing abbr")
        if venue.get("type") not in VALID_TYPES:
            problems.append(f"{where}: type must be one of {sorted(VALID_TYPES)}")

        areas = venue.get("areas")
        if not isinstance(areas, list) or not areas:
            problems.append(f"{where}: areas must be a non-empty list")

        topics = venue.get("topics")
        if topics is not None and (
            not isinstance(topics, list) or not all(isinstance(t, str) and t for t in topics)
        ):
            problems.append(f"{where}: topics must be a list of non-empty strings")

        tracks = venue.get("tracks")
        if tracks is not None:
            if not isinstance(tracks, list):
                problems.append(f"{where}: tracks must be a list")
            else:
                for i, track in enumerate(tracks):
                    if not isinstance(track, dict) or not track.get("name"):
                        problems.append(f"{where}: tracks[{i}] needs a name")

        submission = venue.get("submission")
        if submission is not None:
            if not isinstance(submission, dict):
                problems.append(f"{where}: submission must be an object")
            else:
                for key, allowed in (
                    ("preprint", VALID_PREPRINT),
                    ("code", VALID_CODE),
                    ("access", VALID_ACCESS),
                    ("attendance", VALID_ATTENDANCE),
                ):
                    value = submission.get(key)
                    if value is not None and value not in allowed:
                        problems.append(f"{where}: submission.{key}={value!r} not in {sorted(allowed)}")

        acceptance = venue.get("acceptance")
        if acceptance is not None:
            if not isinstance(acceptance, dict):
                problems.append(f"{where}: acceptance must be an object")
            else:
                percent = acceptance.get("percent")
                if percent is not None and not isinstance(percent, (int, float)):
                    problems.append(f"{where}: acceptance.percent must be a number or null")
                if percent is not None and not (0 < percent <= 100):
                    problems.append(f"{where}: acceptance.percent out of range: {percent}")

        rolling = bool(venue.get("rolling"))
        deadline_list = venue.get("deadlines") or []
        if not isinstance(deadline_list, list):
            problems.append(f"{where}: deadlines must be a list")
            continue
        if not rolling and not deadline_list:
            problems.append(f"{where}: non-rolling venue needs at least one deadline")

        for dl in deadline_list:
            if not isinstance(dl, dict):
                problems.append(f"{where}: deadline entry is not an object")
                continue
            if dl.get("kind") not in VALID_KINDS:
                problems.append(f"{where}: bad deadline kind {dl.get('kind')!r}")
            if dl.get("source_status") not in VALID_SOURCE_STATUS:
                problems.append(f"{where}: bad source_status {dl.get('source_status')!r}")
            tz_name = dl.get("tz")
            if tz_name not in deadlines.TZ_OFFSETS:
                problems.append(f"{where}: unsupported tz {tz_name!r}")
                continue
            try:
                deadlines.parse_deadline(dl.get("date", ""), dl.get("time", "23:59"), tz_name)
            except deadlines.DeadlineError as exc:
                problems.append(f"{where}: {exc}")
    return problems


def find_venue(doc: dict[str, Any], venue_id: str) -> dict[str, Any] | None:
    for venue in doc.get("venues", []):
        if venue.get("id") == venue_id:
            return venue
    return None
