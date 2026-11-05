"""View models for the HTTP layer: venue → JSON-ready dict.

Kept in the domain layer because it encodes business rules (what "next
deadline" means, how freshness is derived), while knowing nothing about HTTP.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.domain import deadlines, schema

# Only these can be re-checked against an official CFP page; the conference
# dates (会期) and rolling-journal facts are not part of verification, so they
# must not make a venue look "待复核".
VERIFIABLE_KINDS = {"abstract", "full_paper", "supplementary", "notification",
                    "camera_ready", "rebuttal"}
SETTLED_STATUSES = {"confirmed", "verified", "unpublished", "blocked", "aggregator", "manual"}


def _fuzzy_label(date_str: str) -> str:
    """Coarse label for a guessed deadline: exact days are not trustworthy."""
    try:
        day = datetime.strptime(str(date_str), "%Y-%m-%d")
    except (ValueError, TypeError):
        return ""
    segment = "上旬" if day.day <= 10 else ("中旬" if day.day <= 20 else "下旬")
    return f"约 {day.year} 年 {day.month} 月{segment}"


def deadline_view(dl: dict[str, Any], now: datetime) -> dict[str, Any]:
    status = dl.get("source_status", "predicted")
    view: dict[str, Any] = {
        "kind": dl.get("kind"),
        "label": schema.KIND_LABELS.get(dl.get("kind", ""), dl.get("kind", "")),
        "date": dl.get("date"),
        "time": dl.get("time", "23:59"),
        "tz": dl.get("tz"),
        "track": dl.get("track", ""),
        "source_status": status,
        "note": dl.get("note", ""),
        "source": dl.get("source") or {},
        # approximate = guessed / not yet published: the UI greys out the
        # remaining days and shows a coarse date instead of a precise one.
        "approximate": status in {"predicted", "unpublished", "manual", "blocked"},
        "fuzzy": _fuzzy_label(dl.get("date", "")),
        "disputed": dl.get("disputed") or None,
        "checked_at": (dl.get("source") or {}).get("checked_at") or "",
    }
    try:
        when = deadlines.parse_deadline(dl.get("date", ""), dl.get("time", "23:59"), dl.get("tz", "AoE"))
    except deadlines.DeadlineError as exc:
        view["error"] = str(exc)
        view["state"] = "invalid"
        return view
    view.update(deadlines.describe(when, now))
    view["freshness"] = deadlines.freshness((dl.get("source") or {}).get("checked_at"), now)
    return view


def venue_view(venue: dict[str, Any], state: dict[str, Any], now: datetime) -> dict[str, Any]:
    views = [deadline_view(dl, now) for dl in (venue.get("deadlines") or [])]
    upcoming = [d for d in views if d.get("state") == "upcoming"]
    next_dl = min(upcoming, key=lambda d: d.get("hours_left", 1e9), default=None)
    state_entry = (state.get("venues") or {}).get(venue.get("id"), {})
    checked = [d.get("checked_at") for d in views if d.get("checked_at")]
    return {
        "last_checked": max(checked) if checked else "",
        "disputed_kinds": [d["kind"] for d in views if d.get("disputed")],
        "id": venue.get("id"),
        "name": venue.get("name"),
        "abbr": venue.get("abbr"),
        "edition": venue.get("edition"),
        "type": venue.get("type"),
        "rolling": bool(venue.get("rolling")),
        "areas": venue.get("areas") or [],
        "topics": venue.get("topics") or [],
        "tracks": venue.get("tracks") or [],
        "submission": venue.get("submission") or {},
        "acceptance": venue.get("acceptance") or {},
        "tier": venue.get("tier") or {},
        "official_url": venue.get("official_url"),
        "cfp_url": venue.get("cfp_url"),
        "materials": venue.get("materials") or [],
        "page_limit": venue.get("page_limit"),
        "blind": venue.get("blind"),
        "notes": venue.get("notes"),
        "review_cycle_weeks": venue.get("review_cycle_weeks"),
        "identity": venue.get("identity") or {},
        "metrics": venue.get("metrics") or {},
        "verified_at": venue.get("verified_at", ""),
        "deadlines": views,
        "next": next_dl,
        "watching": bool(state_entry.get("watching")),
        "submit_status": state_entry.get("submit_status", ""),
        "needs_review": any(
            d.get("source_status") not in SETTLED_STATUSES and d.get("kind") in VERIFIABLE_KINDS
            for d in views
        ),
    }


def sort_key(view: dict[str, Any]) -> tuple[int, float, str]:
    nxt = view.get("next")
    if not nxt:
        return (1, 1e9, view.get("abbr") or "")
    return (0, nxt.get("hours_left", 1e9), view.get("abbr") or "")


def summarize(views: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(views),
        "conference": sum(1 for v in views if v["type"] == "conference"),
        "journal": sum(1 for v in views if v["type"] == "journal"),
        "week": sum(1 for v in views if v.get("next") and v["next"]["days_left"] <= 7),
        "month": sum(1 for v in views if v.get("next") and v["next"]["days_left"] <= 30),
        "needs_review": sum(1 for v in views if v["needs_review"]),
        "watching": sum(1 for v in views if v.get("watching")),
    }
