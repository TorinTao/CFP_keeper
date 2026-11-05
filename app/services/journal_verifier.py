"""Journal verification service.

Journals have no deadlines, so verification means:
  * identity — Crossref (authoritative): title / publisher / ISSN must match;
  * metrics  — LetPub (third party): impact factor, review cycle, acceptance, OA.

Both results are stored per venue with their source and timestamp, so the UI can
show "who said what, and when we checked" instead of a hand-written guess.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Iterable

from app.domain import deadlines
from app.ports import Clock, Repository


class JournalVerifier:
    def __init__(self, repo: Repository, clock: Clock, crossref, letpub,
                 on_progress: Callable[[int, int], None] | None = None) -> None:
        self.repo = repo
        self.clock = clock
        self.crossref = crossref
        self.letpub = letpub
        self.on_progress = on_progress

    def verify(self, venue_ids: Iterable[str] | None = None) -> dict[str, Any]:
        run_id = "journal-" + datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        checked_at = deadlines.iso_local(self.clock.now())
        doc = self.repo.load_venues()

        targets = [v for v in doc.get("venues", [])
                   if v.get("type") == "journal" or v.get("rolling")]
        if venue_ids:
            wanted = set(venue_ids)
            targets = [v for v in targets if v.get("id") in wanted]

        total = len(targets)
        checks: list[dict[str, Any]] = []
        changed = False

        for index, venue in enumerate(targets, 1):
            if self.on_progress is not None:
                self.on_progress(index, total)
            entry: dict[str, Any] = {"venue_id": venue.get("id"), "abbr": venue.get("abbr"),
                                     "name": venue.get("name", "")}
            try:
                identity = self.crossref.find_by_title(venue.get("name", ""))
            except Exception as exc:  # noqa: BLE001 - source is optional
                identity = None
                entry["crossref_error"] = f"{type(exc).__name__}: {exc}"[:200]
            try:
                metrics = self.letpub.lookup(venue.get("name", ""))
            except Exception as exc:  # noqa: BLE001
                metrics = None
                entry["letpub_error"] = f"{type(exc).__name__}: {exc}"[:200]

            if identity:
                venue["identity"] = {
                    "title": identity.get("title", ""),
                    "publisher": identity.get("publisher", ""),
                    "issn": identity.get("issn") or [],
                    "source": "Crossref",
                    "url": identity.get("url", ""),
                    "match": identity.get("score"),
                    "checked_at": checked_at,
                    "status": "verified",
                }
                entry["identity"] = venue["identity"]["title"]
                changed = True
            else:
                entry["identity"] = None

            if metrics:
                venue["metrics"] = {
                    "impact_factor": metrics.get("impact_factor", ""),
                    "review_cycle": metrics.get("review_cycle", ""),
                    "acceptance": metrics.get("acceptance", ""),
                    "open_access": metrics.get("open_access", ""),
                    "gold_oa_share": metrics.get("gold_oa_share", ""),
                    "official_url": metrics.get("official_url", ""),
                    "submission_url": metrics.get("submission_url", ""),
                    "source": "LetPub",
                    "url": metrics.get("source_url", ""),
                    "checked_at": checked_at,
                    "status": "third_party",
                }
                entry["metrics"] = {k: venue["metrics"][k]
                                    for k in ("impact_factor", "review_cycle", "acceptance")}
                changed = True
            else:
                entry["metrics"] = None

            if identity or metrics:
                venue["verified_at"] = checked_at
            checks.append(entry)

        if changed:
            self.repo.save_venues(doc)

        summary = {
            "targets": total,
            "identity_verified": sum(1 for c in checks if c["identity"]),
            "metrics_found": sum(1 for c in checks if c["metrics"]),
            "failed": sum(1 for c in checks if not c["identity"] and not c["metrics"]),
        }
        record = {
            "run_id": run_id, "kind": "journal-verify",
            "started_at": checked_at, "finished_at": deadlines.iso_local(self.clock.now()),
            "summary": summary, "checks": checks,
        }
        self.repo.save_run(record)
        return record
