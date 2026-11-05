"""Timezone, countdown, and freshness helpers.

* AoE (Anywhere on Earth, UTC-12) is not in the IANA database, so it is a fixed
  offset here — this is the single most common source of missed deadlines.
* DST is never inferred: ``PST`` is always UTC-8; tag ``PDT`` explicitly.
* All arithmetic happens in UTC; Beijing time is display-only.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

TZ_OFFSETS: dict[str, float] = {
    "AoE": -12.0,
    "UTC": 0.0,
    "GMT": 0.0,
    "PST": -8.0,
    "PDT": -7.0,
    "MST": -7.0,
    "EST": -5.0,
    "EDT": -4.0,
    "CET": 1.0,
    "CEST": 2.0,
    "JST": 9.0,
    "KST": 9.0,
    "Asia/Shanghai": 8.0,
    "CST": 8.0,
}

DISPLAY_OFFSET = 8.0
DISPLAY_NAME = "Asia/Shanghai"

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y")


class DeadlineError(ValueError):
    """Raised when a deadline date/time/timezone cannot be interpreted."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value: str) -> tuple[int, int, int]:
    text = (value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.year, dt.month, dt.day
        except ValueError:
            continue
    raise DeadlineError(f"unrecognised date: {value!r}")


def parse_time(value: str) -> tuple[int, int]:
    text = (value or "").strip().replace("：", ":")
    if not text:
        return 23, 59
    if ":" not in text and len(text) == 4 and text.isdigit():
        text = f"{text[:2]}:{text[2:]}"
    parts = text.split(":")
    if len(parts) < 2:
        raise DeadlineError(f"unrecognised time: {value!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise DeadlineError(f"unrecognised time: {value!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise DeadlineError(f"time out of range: {value!r}")
    return hour, minute


def parse_deadline(date_str: str, time_str: str = "23:59", tz_name: str = "AoE") -> datetime:
    if tz_name not in TZ_OFFSETS:
        raise DeadlineError(
            f"unsupported timezone {tz_name!r}; known: {', '.join(sorted(TZ_OFFSETS))}"
        )
    year, month, day = parse_date(date_str)
    hour, minute = parse_time(time_str)
    offset = timedelta(hours=TZ_OFFSETS[tz_name])
    local = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    return local - offset


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise DeadlineError("naive datetime is not accepted")
    return dt.astimezone(timezone.utc)


def to_display(dt: datetime) -> datetime:
    return to_utc(dt).astimezone(timezone(timedelta(hours=DISPLAY_OFFSET)))


def hours_left(deadline_utc: datetime, now: datetime | None = None) -> float:
    now = now or utc_now()
    return (to_utc(deadline_utc) - to_utc(now)).total_seconds() / 3600.0


def days_left(deadline_utc: datetime, now: datetime | None = None) -> int:
    return int(math.floor(hours_left(deadline_utc, now) / 24.0))


def deadline_state(deadline_utc: datetime, now: datetime | None = None) -> str:
    return "passed" if hours_left(deadline_utc, now) <= 0 else "upcoming"


def parse_iso(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        raise DeadlineError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DeadlineError(f"unrecognised timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def freshness(checked_at: Any, now: datetime | None = None) -> str:
    now = now or utc_now()
    if not checked_at:
        return "unknown"
    try:
        dt = parse_iso(str(checked_at))
    except DeadlineError:
        return "unknown"
    age_days = (to_utc(now) - to_utc(dt)).total_seconds() / 86400.0
    if age_days < 30:
        return "fresh"
    if age_days < 90:
        return "aging"
    return "stale"


def iso_utc(dt: datetime | None = None) -> str:
    dt = to_utc(dt or utc_now()).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_local(dt: datetime | None = None) -> str:
    return to_display(dt or utc_now()).replace(microsecond=0).isoformat()


def urgency(hours: float) -> str:
    if hours <= 0:
        return "passed"
    if hours <= 24:
        return "today"
    if hours <= 24 * 7:
        return "week"
    if hours <= 24 * 30:
        return "month"
    return "later"


def describe(deadline_utc: datetime, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    utc = to_utc(deadline_utc)
    bj = to_display(utc)
    left = hours_left(utc, now)
    return {
        "utc": iso_utc(utc),
        "beijing": bj.strftime("%Y-%m-%d %H:%M"),
        "beijing_iso": bj.isoformat(),
        "days_left": int(math.floor(left / 24.0)),
        "hours_left": round(left, 2),
        "state": "passed" if left <= 0 else "upcoming",
        "urgency": urgency(left),
    }
