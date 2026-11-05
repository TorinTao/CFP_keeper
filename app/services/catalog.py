"""Catalog service: reading and mutating the venue list.

Depends only on :class:`app.ports.Repository` and :class:`app.ports.Clock`, so it
can be unit-tested with an in-memory fake and reused by any interface.
"""

from __future__ import annotations

from typing import Any

from app.domain import deadlines, schema, views as view_models
from app.ports import Clock, Repository


class CatalogService:
    def __init__(self, repo: Repository, clock: Clock) -> None:
        self.repo = repo
        self.clock = clock

    # ------------------------------------------------------------------ reads
    def all_views(self, now=None) -> list[dict[str, Any]]:
        now = now or self.clock.now()
        doc = self.repo.load_venues()
        state = self.repo.load_state()
        items = [view_models.venue_view(v, state, now) for v in doc.get("venues", [])]
        items.sort(key=view_models.sort_key)
        return items

    def query(self, filters: dict[str, str], include_passed: bool = False) -> dict[str, Any]:
        all_views = self.all_views()
        views = list(all_views)

        topic_counts: dict[str, int] = {}
        for item in all_views:
            for name in item.get("topics", []):
                topic_counts[name] = topic_counts.get(name, 0) + 1
        topics = sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))

        area = filters.get("area") or ""
        topic = filters.get("topic") or ""
        vtype = filters.get("type") or ""
        search = (filters.get("q") or "").strip().lower()
        within = filters.get("within") or ""
        watching_only = filters.get("watching") in {"1", "true", "yes"}

        if area:
            views = [v for v in views if area in v["areas"]]
        if topic:
            views = [v for v in views if topic in v.get("topics", [])]
        if vtype:
            views = [v for v in views if v["type"] == vtype]
        if watching_only:
            views = [v for v in views if v.get("watching")]
        if search:
            views = [v for v in views if search in (v["abbr"] or "").lower()
                     or search in (v["name"] or "").lower()
                     or any(search in a for a in v["areas"])]
        if within.isdigit():
            days = int(within)
            views = [v for v in views if v.get("next") and v["next"].get("days_left", 9999) <= days]
        if not include_passed:
            views = [v for v in views if v["rolling"] or (v.get("next") is not None)]

        return {
            "venues": views,
            "counts": view_models.summarize(all_views),
            "topics": [{"name": name, "count": count} for name, count in topics],
            "generated_at": deadlines.iso_local(self.clock.now()),
        }

    def get(self, venue_id: str) -> dict[str, Any] | None:
        for view in self.all_views():
            if view["id"] == venue_id:
                return view
        return None

    # ----------------------------------------------------------------- writes
    def set_state(self, venue_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        doc = self.repo.load_venues()
        if not schema.find_venue(doc, venue_id):
            return 404, {"error": {"code": "venue_not_found", "message": venue_id}}
        state = self.repo.load_state()
        entry = state.setdefault("venues", {}).setdefault(venue_id, {})
        if "watching" in body:
            entry["watching"] = bool(body["watching"])
        if "submit_status" in body:
            status = body["submit_status"] or ""
            if status not in schema.VALID_SUBMIT_STATUS:
                return 400, {"error": {"code": "invalid_status", "message": status}}
            entry["submit_status"] = status
        entry["updated_at"] = deadlines.iso_local(self.clock.now())
        self.repo.save_state(state)
        return 200, {"ok": True, "venue": venue_id, "state": entry}

    def confirm_deadline(self, venue_id: str, kind: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        doc = self.repo.load_venues()
        venue = schema.find_venue(doc, venue_id)
        if not venue:
            return 404, {"error": {"code": "venue_not_found", "message": venue_id}}
        payload = {
            "kind": kind,
            "date": body.get("date"),
            "time": body.get("time", "23:59"),
            "tz": body.get("tz", "AoE"),
            "source_status": "confirmed",
            "note": body.get("note", ""),
            "source": {
                "url": body.get("source_url") or venue.get("cfp_url") or "",
                "checked_at": deadlines.iso_local(self.clock.now()),
                "snippet": (body.get("snippet") or "")[:400],
            },
        }
        try:
            deadlines.parse_deadline(payload["date"], payload["time"], payload["tz"])
        except deadlines.DeadlineError as exc:
            return 400, {"error": {"code": "invalid_deadline", "message": str(exc)}}

        replaced = False
        for index, dl in enumerate(venue.get("deadlines") or []):
            if dl.get("kind") == kind:
                venue["deadlines"][index] = payload
                replaced = True
                break
        if not replaced:
            venue.setdefault("deadlines", []).append(payload)

        try:
            self.repo.save_venues(doc)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            return 500, {"error": {"code": "save_failed", "message": str(exc)}}

        candidates = self.repo.load_candidates()
        before = len(candidates.get("candidates", []))
        candidates["candidates"] = [
            c for c in candidates.get("candidates", [])
            if not (c.get("venue_id") == venue_id and c.get("kind") == kind
                    and c.get("date") == payload["date"])
        ]
        if len(candidates["candidates"]) != before:
            self.repo.save_candidates(candidates)
        return 200, {"ok": True, "venue": venue_id, "kind": kind, "deadline": payload}
