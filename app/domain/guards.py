"""Auto-apply guards: the policy deciding what a scrape may overwrite.

Pure decision logic — no I/O. Returns the candidates to write plus every rejected
one *with a reason*, so the UI and the run record can explain themselves.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

AUTO_KINDS = {"abstract", "full_paper", "supplementary", "notification", "camera_ready"}
DEFAULT_GUARD_DAYS = 90


def _as_date(value: Any):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def plan_auto_apply(
    venue: dict[str, Any],
    candidates: list[dict[str, Any]],
    today: Any,
    guard_days: int = DEFAULT_GUARD_DAYS,
    protect_confirmed: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Decide which candidates may be written automatically.

    Guards:
      1. the date must be in the future (homepage news items are usually past);
      2. the kind must already be declared by the venue;
      3. a human-verified (``confirmed``) deadline is never touched;
      4. the new date must sit within ``guard_days`` of the current one;
      5. only the kinds in :data:`AUTO_KINDS` are eligible;
      6. if a kind has several distinct candidate dates it is ambiguous → skip;
      7. an unchanged scraped value is skipped.
    """
    existing = {dl.get("kind"): dl for dl in (venue.get("deadlines") or [])}
    rejected: list[dict[str, Any]] = []
    valid: dict[str, list[tuple[int, dict[str, Any]]]] = {}

    for cand in candidates:
        kind = cand.get("kind")
        cand_date = _as_date(cand.get("date"))
        reason = None

        if kind not in AUTO_KINDS:
            reason = "kind_not_auto"
        elif cand_date is None:
            reason = "bad_date"
        elif cand_date <= today:
            reason = "not_in_future"
        elif kind not in existing:
            reason = "kind_not_declared"
        else:
            current = existing[kind]
            cur_date = _as_date(current.get("date"))
            if protect_confirmed and current.get("source_status") == "confirmed":
                reason = "human_verified"
            elif current.get("source_status") == "scraped" and cur_date == cand_date:
                reason = "unchanged"
            elif cur_date and guard_days and abs((cand_date - cur_date).days) > guard_days:
                reason = "outside_guard_window"
            else:
                distance = abs((cand_date - cur_date).days) if cur_date else 0
                valid.setdefault(kind, []).append((distance, cand))
                continue

        rejected.append({"candidate": cand, "reason": reason})

    updates: list[dict[str, Any]] = []
    for _kind, items in valid.items():
        if len({c.get("date") for _, c in items}) > 1:
            for _, cand in items:
                rejected.append({"candidate": cand, "reason": "ambiguous"})
            continue
        updates.append(items[0][1])

    return updates, rejected


def build_deadline_entry(candidate: dict[str, Any]) -> dict[str, Any]:
    """Shape a candidate into a stored deadline record (status=scraped)."""
    return {
        "kind": candidate["kind"],
        "date": candidate["date"],
        "time": candidate.get("time", "23:59"),
        "tz": candidate.get("tz", "AoE"),
        "track": candidate.get("track", "主会"),
        "source_status": "scraped",
        "note": "自动抓取（{}），未人工复核".format(str(candidate.get("extracted_at", ""))[:16]),
        "source": {
            "url": candidate.get("source_url", ""),
            "checked_at": candidate.get("extracted_at", ""),
            "snippet": (candidate.get("snippet") or "")[:400],
        },
    }
