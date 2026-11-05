"""Verification policy: compare a stored deadline with what the page says now.

Pure decision logic — no network, no writes. The service layer executes the
verdicts; tests exercise them directly.

Verdicts:
  * ``verified``  — page confirms the stored date;
  * ``updated``   — page disagrees by ≤ ``max_shift_days``; take the page's date;
  * ``mismatch``  — page disagrees a lot; keep ours and flag for a human;
  * ``not_found`` — page no longer mentions this kind.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Kinds that can meaningfully be re-checked against a CFP page.
VERIFY_KINDS = {"abstract", "full_paper", "supplementary", "notification", "camera_ready", "rebuttal"}

# Statuses that are already trustworthy enough to leave alone in "pending only" mode.
SETTLED_STATUSES = {"verified"}


def _as_date(value: Any):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def plan_verification(
    venue: dict[str, Any],
    candidates: list[dict[str, Any]],
    max_shift_days: int = 30,
    pending_only: bool = True,
) -> list[dict[str, Any]]:
    """Return one action per re-checkable deadline of ``venue``."""
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for cand in candidates:
        if cand.get("kind") in VERIFY_KINDS:
            by_kind.setdefault(cand["kind"], []).append(cand)

    actions: list[dict[str, Any]] = []
    for dl in venue.get("deadlines") or []:
        kind = dl.get("kind")
        if kind not in VERIFY_KINDS:
            continue
        status = dl.get("source_status", "predicted")
        if status == "confirmed":
            # A human already checked this one; never let automation touch it.
            continue
        if pending_only and status in SETTLED_STATUSES:
            continue

        cur_date = _as_date(dl.get("date"))
        options = by_kind.get(kind, [])
        if not options:
            actions.append({"kind": kind, "verdict": "not_found", "current": dl,
                            "candidate": None, "shift_days": None})
            continue

        # closest candidate to the stored date wins
        def distance(cand: dict[str, Any]) -> int:
            cand_date = _as_date(cand.get("date"))
            if cur_date is None or cand_date is None:
                return 10 ** 6
            return abs((cand_date - cur_date).days)

        best = min(options, key=distance)
        best_date = _as_date(best.get("date"))
        shift = distance(best)

        if best_date == cur_date:
            verdict = "verified"
        elif shift <= max_shift_days:
            verdict = "updated"
        else:
            verdict = "mismatch"

        actions.append({"kind": kind, "verdict": verdict, "current": dl,
                        "candidate": best, "shift_days": shift})

    return actions


def apply_verdict(deadline: dict[str, Any], action: dict[str, Any],
                  checked_at: str, source_url: str, trusted: bool = False) -> dict[str, Any]:
    """Return the updated deadline record for a verified/updated verdict.

    A matching page confirms the value (``verified``). A page that disagrees is
    written as ``scraped`` — the page is evidence, not proof: the old value is
    quoted in the note so a human can see what changed and why.
    """
    if action["verdict"] not in {"verified", "updated"}:
        return deadline

    candidate = action["candidate"] or {}
    updated = dict(deadline)
    if action["verdict"] == "updated":
        old_date = deadline.get("date")
        updated["date"] = candidate.get("date", deadline.get("date"))
        updated["time"] = candidate.get("time", deadline.get("time", "23:59"))
        updated["tz"] = candidate.get("tz", deadline.get("tz", "AoE"))
        if trusted:
            # The edition-specific official page is authoritative: no need to ask.
            updated["source_status"] = "verified"
            updated["note"] = "官网当届页面核对（原 {}），已更正为 {}".format(old_date, updated["date"])
        else:
            updated["source_status"] = "scraped"
            updated["note"] = "官网与旧值不一致（原 {}），已按官网改为 {}，建议确认".format(
                old_date, updated["date"])
    else:
        updated["source_status"] = "verified"
        updated["note"] = "自动核验（{}）官网日期一致".format(checked_at[:16])

    updated["source"] = {
        "url": candidate.get("source_url") or source_url,
        "checked_at": checked_at,
        "snippet": (candidate.get("snippet") or "")[:400],
    }
    return updated
