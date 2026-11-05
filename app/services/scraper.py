"""Scrape service: fetch pages → extract candidates → guard → write → audit.

Depends on the ``Fetcher`` port (not subprocess) and the ``Repository`` port (not
JSON files), so it can be tested with fakes and re-pointed at another backend.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Iterable

from app.domain import cfp_parser, deadlines, guards, schema
from app.ports import AppConfig, Clock, Fetcher, Repository


class Scraper:
    def __init__(
        self,
        repo: Repository,
        fetcher: Fetcher,
        clock: Clock,
        get_config: Callable[[], AppConfig],
    ) -> None:
        self.repo = repo
        self.fetcher = fetcher
        self.clock = clock
        self.get_config = get_config

    def run(self, venue_ids: Iterable[str] | None = None) -> dict[str, Any]:
        cfg = self.get_config()
        run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        started_at = deadlines.iso_local(self.clock.now())

        doc = self.repo.load_venues()
        targets = [v for v in doc.get("venues", []) if (v.get("cfp_url") or "").strip()]
        if venue_ids:
            wanted = set(venue_ids)
            targets = [v for v in targets if v.get("id") in wanted]

        attempts: list[dict[str, Any]] = []
        all_candidates: list[dict[str, Any]] = []

        for venue in targets:
            url = venue["cfp_url"].strip()
            result = self.fetcher.fetch(url, timeout_s=cfg.scrape.timeout_seconds)
            attempt: dict[str, Any] = {
                "venue_id": venue.get("id"), "abbr": venue.get("abbr"), "url": url,
                "ok": result.ok, "elapsed_ms": result.elapsed_ms,
            }
            if result.ok:
                data = result.data or {}
                text = data.get("main_text") or ""
                quality = data.get("quality") or {}
                candidates = cfp_parser.parse_candidates(text, venue.get("id", ""), url,
                                                         now=self.clock.now())
                attempt.update({
                    "http_status": data.get("status_code"),
                    "engine": data.get("engine"),
                    "request_id": data.get("request_id"),
                    "text_length": quality.get("text_length"),
                    "warnings": quality.get("warnings") or [],
                    "candidates": len(candidates),
                    "needs_browser": "thin_content" in (quality.get("warnings") or []),
                })
                if candidates:
                    all_candidates.extend(candidates)
                    self.repo.save_snapshot(run_id, text)
            else:
                attempt.update({
                    "error_code": result.error_code,
                    "upstream_status": result.upstream_status,
                    "stderr": result.detail,
                    "needs_browser": result.error_code == "browser_fetch_failed",
                })
            attempts.append(attempt)

        summary = {
            "targets": len(targets),
            "succeeded": sum(1 for a in attempts if a["ok"]),
            "failed": sum(1 for a in attempts if not a["ok"]),
            "candidates": len(all_candidates),
            "error_codes": sorted({a.get("error_code") for a in attempts if a.get("error_code")}),
        }
        record: dict[str, Any] = {
            "run_id": run_id, "started_at": started_at,
            "finished_at": deadlines.iso_local(self.clock.now()),
            "summary": summary, "attempts": attempts,
        }
        self.repo.save_run(record)

        if not all_candidates:
            return record

        if cfg.scrape.auto_apply:
            applied, rejected = self._apply(all_candidates, run_id, cfg)
            summary["auto_applied"] = len(applied)
            summary["auto_rejected"] = len(rejected)
            record["auto_applied"] = [
                {"venue_id": a["venue_id"], "abbr": a.get("abbr"), "kind": a["after"]["kind"],
                 "date": a["after"]["date"], "before_date": (a["before"] or {}).get("date")}
                for a in applied
            ]
            record["auto_rejected_detail"] = [
                {"venue_id": r["candidate"].get("venue_id"), "kind": r["candidate"].get("kind"),
                 "date": r["candidate"].get("date"), "reason": r["reason"]}
                for r in rejected[:100]
            ]
            self.repo.save_run(record)
            leftovers = [r["candidate"] for r in rejected]
        else:
            leftovers = all_candidates

        if leftovers:
            doc = self.repo.load_candidates()
            existing = {(c.get("venue_id"), c.get("kind"), c.get("date"))
                        for c in doc.get("candidates", [])}
            added = [c for c in leftovers
                     if (c["venue_id"], c["kind"], c["date"]) not in existing]
            doc.setdefault("candidates", []).extend(added)
            doc["last_run_id"] = run_id
            self.repo.save_candidates(doc)
            summary["candidates_added"] = len(added)

        return record

    # ------------------------------------------------------------- internals
    def _apply(self, candidates: list[dict[str, Any]], run_id: str,
               cfg: AppConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        by_venue: dict[str, list[dict[str, Any]]] = {}
        for cand in candidates:
            by_venue.setdefault(cand.get("venue_id", ""), []).append(cand)

        doc = self.repo.load_venues()
        today = self.clock.now().date()
        applied: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for venue_id, cands in by_venue.items():
            venue = schema.find_venue(doc, venue_id)
            if not venue:
                continue
            updates, venue_rejected = guards.plan_auto_apply(
                venue, cands, today=today,
                guard_days=cfg.scrape.guard_days,
                protect_confirmed=cfg.scrape.protect_confirmed,
            )
            for cand in updates:
                deadline_list = venue.setdefault("deadlines", [])
                target = next((d for d in deadline_list if d.get("kind") == cand["kind"]), None)
                entry = guards.build_deadline_entry(cand)
                before = dict(target) if target else None
                if target:
                    deadline_list[deadline_list.index(target)] = entry
                else:
                    deadline_list.append(entry)
                record = {"ts": deadlines.iso_local(self.clock.now()), "run_id": run_id,
                          "venue_id": venue_id, "abbr": venue.get("abbr"),
                          "before": before, "after": entry}
                applied.append(record)
                self.repo.append_audit(record)
            rejected.extend(venue_rejected)

        if applied:
            self.repo.save_venues(doc)
        return applied, rejected
