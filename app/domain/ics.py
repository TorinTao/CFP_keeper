"""RFC 5545 export: VEVENT + VALARM, CRLF, 75-octet folding, TEXT escaping."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Iterable

from app.domain import deadlines as timeutil

KIND_LABELS = {
    "abstract": "摘要截止",
    "full_paper": "全文截止",
    "supplementary": "补充材料截止",
    "rebuttal": "Rebuttal 截止",
    "notification": "录用通知",
    "camera_ready": "Camera-ready 截止",
    "conference": "会议召开",
}
REMIND_TRIGGERS = ("-P7D", "-P3D", "-P1D")


def escape_text(value: str) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\")
    text = text.replace("\n", "\\n").replace("\r", "")
    text = text.replace(";", "\\;").replace(",", "\\,")
    return text


def fold_line(line: str) -> str:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts: list[str] = []
    current = bytearray()
    limit = 75
    for char in line:
        chunk = char.encode("utf-8")
        if len(current) + len(chunk) > limit:
            parts.append(current.decode("utf-8"))
            current = bytearray()
            limit = 74
        current.extend(chunk)
    if current:
        parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _uid(venue_id: str, kind: str) -> str:
    digest = hashlib.sha1(f"{venue_id}:{kind}".encode("utf-8")).hexdigest()[:12]
    return f"{venue_id}-{kind}-{digest}@cfp-keeper.local"


def build_calendar(
    venues: Iterable[dict[str, Any]],
    now: datetime | None = None,
    include_predicted: bool = True,
    within_days: int = 365,
    include_passed: bool = False,
) -> str:
    now = now or timeutil.utc_now()
    horizon = now + timedelta(days=within_days)
    events: list[tuple[datetime, list[str]]] = []

    for venue in venues:
        if venue.get("type") == "journal" or venue.get("rolling"):
            continue
        for dl in venue.get("deadlines") or []:
            if not include_predicted and dl.get("source_status") == "predicted":
                continue
            try:
                when = timeutil.parse_deadline(
                    dl.get("date", ""), dl.get("time", "23:59"), dl.get("tz", "AoE")
                )
            except timeutil.DeadlineError:
                continue
            if timeutil.deadline_state(when, now) == "passed" and not include_passed:
                continue
            if when > horizon:
                continue

            bj = timeutil.to_display(when)
            label = KIND_LABELS.get(dl.get("kind", ""), dl.get("kind", "deadline"))
            status = dl.get("source_status", "predicted")
            status_note = {"confirmed": "已核验", "scraped": "自动抓取"}.get(status, "按历年规律推测，需复核")
            lines = [
                "BEGIN:VEVENT",
                f"UID:{_uid(venue['id'], dl.get('kind', 'deadline'))}",
                f"DTSTAMP:{timeutil.iso_utc(now)}",
                f"DTSTART:{when.strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{(when + timedelta(minutes=30)).strftime('%Y%m%dT%H%M%SZ')}",
                "SUMMARY:" + escape_text("[{}] {}".format(venue.get("abbr"), label)),
                "DESCRIPTION:"
                + escape_text(
                    "\n".join(
                        [
                            f"会议：{venue.get('name', '')} ({venue.get('edition', '')})",
                            f"原始时区：{dl.get('date')} {dl.get('time', '23:59')} {dl.get('tz')}",
                            f"北京时间：{bj.strftime('%Y-%m-%d %H:%M')}",
                            f"数据状态：{status_note}",
                            f"材料：{'、'.join(venue.get('materials') or []) or '-'}",
                            f"官网：{venue.get('official_url', '')}",
                        ]
                    )
                ),
                f"URL:{escape_text(venue.get('official_url', ''))}",
                "STATUS:CONFIRMED",
                "TRANSP:TRANSPARENT",
            ]
            for trigger in REMIND_TRIGGERS:
                lines += [
                    "BEGIN:VALARM",
                    f"TRIGGER:{trigger}",
                    "ACTION:DISPLAY",
                    "DESCRIPTION:" + escape_text("{} {}".format(venue.get("abbr"), label)),
                    "END:VALARM",
                ]
            lines.append("END:VEVENT")
            events.append((when, lines))

    events.sort(key=lambda item: item[0])
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CFP Keeper//Deadline Calendar//ZH-CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:科研会议截稿日历",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]
    for _, lines in events:
        out.extend(lines)
    out.append("END:VCALENDAR")
    return "\r\n".join(fold_line(line) for line in out) + "\r\n"
