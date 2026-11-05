"""Verification service: check stored deadlines against official pages.

Sources, in order of authority:
  1. the venue's own CFP page (fetch → parse → compare);
  2. the exact edition link provided by the CCFDDL dataset (often the 2027 site,
     which our ``cfp_url`` homepage is not);
  3. one/two hops of "important dates" links found in the DOM;
  4. as a last resort, the CCFDDL dataset itself — recorded as ``aggregator``,
     never presented as official.

Statuses written here: ``verified`` (page confirms), ``scraped`` (page disagrees),
``aggregator`` (third-party date), ``unpublished`` (page has no such date),
``blocked`` (page unreachable and no third-party data).
"""

from __future__ import annotations

import time as _time
import uuid
from datetime import datetime
from typing import Any, Callable, Iterable

from urllib.parse import urlparse

from app.domain import cfp_parser, deadlines, verification
from app.ports import AppConfig, Clock, Fetcher, Repository


def _edition_year(venue: dict[str, Any]) -> int:
    edition = str(venue.get("edition") or "")
    if edition.isdigit():
        return int(edition)
    tail = str(venue.get("id") or "").rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _has_deadlines(candidates: list[dict[str, Any]]) -> bool:
    return any(c.get("kind") in verification.VERIFY_KINDS for c in candidates)


class QuotaExhausted(RuntimeError):
    """The fetch service ran out of quota; stop instead of burning browser time."""


class Verifier:
    def __init__(self, repo: Repository, fetcher: Fetcher, clock: Clock,
                 get_config: Callable[[], AppConfig], third_party=None,
                 sleep: Callable[[float], None] = _time.sleep,
                 on_progress: Callable[[int, int], None] | None = None) -> None:
        self.repo = repo
        self.fetcher = fetcher
        self.clock = clock
        self.get_config = get_config
        self.third_party = third_party  # CcfddlSource | None
        self.sleep = sleep
        self.on_progress = on_progress
        self._last_fetch = 0.0

    def _fetch(self, url: str, timeout: int, cfg: AppConfig):
        """Fetch with pacing + one quota backoff, so a big run does not truncate."""
        pace = max(0.0, float(getattr(cfg.scrape, "pace_seconds", 0) or 0))
        if pace:
            wait = pace - (_time.monotonic() - self._last_fetch)
            if wait > 0:
                self.sleep(wait)
        result = self.fetcher.fetch(url, timeout_s=timeout)
        self._last_fetch = _time.monotonic()
        if result.error_code == "webfetch_quota_exhausted":
            backoff = int(getattr(cfg.scrape, "quota_backoff_seconds", 0) or 0)
            if backoff > 0:
                self.sleep(backoff)
                result = self.fetcher.fetch(url, timeout_s=timeout)
                self._last_fetch = _time.monotonic()
        return result

    # ------------------------------------------------------------------ entry
    def verify(self, venue_ids: Iterable[str] | None = None,
               pending_only: bool | None = None) -> dict[str, Any]:
        cfg = self.get_config()
        pending_only = cfg.verify.pending_only if pending_only is None else pending_only
        run_id = "verify-" + datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
        checked_at = deadlines.iso_local(self.clock.now())

        doc = self.repo.load_venues()
        targets = [v for v in doc.get("venues", []) if (v.get("cfp_url") or "").strip()]
        if venue_ids:
            wanted = set(venue_ids)
            targets = [v for v in targets if v.get("id") in wanted]

        checks: list[dict[str, Any]] = []
        changed = False
        aborted = ""
        counters = {"followed": 0, "aggregated": 0, "unpublished": 0, "blocked": 0, "skipped": 0}

        today = self.clock.now().date().isoformat()
        total = len(targets)
        for index, venue in enumerate(targets, 1):
            if self.on_progress is not None:
                self.on_progress(index, total)
            retry_after = (venue.get("verify_after") or "").strip()
            if retry_after and today < retry_after:
                checks.append({"venue_id": venue.get("id"), "abbr": venue.get("abbr"),
                               "ok": False, "skipped": True, "reason": "verify_after",
                               "retry_after": retry_after, "actions": []})
                counters["skipped"] += 1
                continue
            try:
                entry, changed_here, counters = self._check_venue(
                    venue, cfg, pending_only, checked_at, run_id, counters)
            except QuotaExhausted:
                aborted = f"quota_exhausted after {len(checks)} venues"
                break
            changed = changed or changed_here
            checks.append(entry)

        if changed:
            self.repo.save_venues(doc)

        summary = {
            "targets": len(targets),
            "fetched": sum(1 for c in checks if c.get("ok")),
            "failed": sum(1 for c in checks if not c.get("ok")),
            "followed": counters["followed"],
            "verified": sum(1 for c in checks for a in c["actions"] if a["verdict"] == "verified"),
            "updated": sum(1 for c in checks for a in c["actions"] if a["verdict"] == "updated"),
            "mismatch": sum(1 for c in checks for a in c["actions"] if a["verdict"] == "mismatch"),
            "not_found": sum(1 for c in checks for a in c["actions"] if a["verdict"] == "not_found"),
            "marked_unpublished": counters["unpublished"],
            "marked_blocked": counters["blocked"],
            "aggregated": counters["aggregated"],
            "aborted": aborted,
            "skipped": counters["skipped"],
        }
        record = {
            "run_id": run_id, "kind": "verify",
            "started_at": checked_at, "finished_at": deadlines.iso_local(self.clock.now()),
            "summary": summary, "checks": checks,
        }
        self.repo.save_run(record)
        return record

    # --------------------------------------------------------------- per venue
    def _check_venue(self, venue: dict[str, Any], cfg: AppConfig, pending_only: bool,
                     checked_at: str, run_id: str,
                     counters: dict[str, int]) -> tuple[dict[str, Any], bool, dict[str, int]]:
        timeout = cfg.scrape.timeout_seconds
        url = (venue.get("cfp_url") or "").strip()
        edition = _edition_year(venue)
        entry: dict[str, Any] = {"venue_id": venue.get("id"), "abbr": venue.get("abbr"),
                                 "url": url, "ok": False, "actions": []}

        third = None
        if self.third_party is not None:
            try:
                third = self.third_party.lookup(venue.get("abbr", ""), edition)
            except Exception:  # noqa: BLE001 - optional source
                third = None
        if third:
            entry["third_party_link"] = third.get("link", "")
            entry["third_party_dates"] = dict(third.get("deadlines") or {})

        # 1) the stored CFP url
        candidates: list[dict[str, Any]] = []
        result = self._fetch(url, timeout, cfg)
        if result.error_code == "webfetch_quota_exhausted":
            raise QuotaExhausted(url)
        if result.ok:
            entry["ok"] = True
            candidates = self._parse(result, venue, url)

        # 2) the edition link from CCFDDL (better than a homepage)
        edition_link = (third or {}).get("link", "")
        if not _has_deadlines(candidates) and edition_link and edition_link != url:
            fetched = self._fetch(edition_link, timeout, cfg)
            if fetched.ok:
                entry["ok"] = True
                found = self._parse(fetched, venue, edition_link)
                if _has_deadlines(found):
                    candidates = found
                    entry["followed_url"] = edition_link
                    counters["followed"] += 1

        # 3) crawl "important dates" links
        if not _has_deadlines(candidates) and entry["ok"]:
            followed, found = self._deep_discover(venue, url, cfg)
            if _has_deadlines(found):
                candidates = found
                entry["followed_url"] = followed
                counters["followed"] += 1

        # 4) nothing reachable → third-party or blocked
        if not entry["ok"]:
            entry.update({"error_code": result.error_code, "detail": result.detail[:300]})
            wrote = 0
            if third and third.get("deadlines"):
                wrote = self._apply_third_party(venue, third, checked_at, entry, only_kinds=None)
                counters["aggregated"] += wrote
            if not wrote:
                wrote = self._mark_blocked(venue, checked_at, url, entry)
                counters["blocked"] += wrote
            return entry, wrote > 0, counters

        actions = verification.plan_verification(
            venue, candidates,
            max_shift_days=cfg.verify.max_shift_days,
            pending_only=pending_only,
        )
        # A homepage often lists other people's deadlines (endorsed events,
        # workshops). Trust it only for exact matches, never for "update" or
        # "disagree" verdicts.
        page_path = urlparse(url).path.strip("/")
        homepage_only = page_path == "" and not entry.get("followed_url")
        if homepage_only:
            actions = [a for a in actions if a["verdict"] == "verified"]
            for dropped in [a for a in actions if a["verdict"] != "verified"]:
                pass

        # A date taken from the *edition-specific* page (CCFDDL link, e.g.
        # 2027.aclweb.org) is authoritative even when it differs a lot from the
        # old guess: the shift guard exists to filter random crawler hits only.
        trusted_edition = bool(edition_link) and entry.get("followed_url") == edition_link
        if trusted_edition:
            for action in actions:
                if action["verdict"] == "mismatch" and not homepage_only:
                    action["verdict"] = "updated"
        entry["actions"] = [
            {"kind": a["kind"], "verdict": a["verdict"], "shift_days": a["shift_days"],
             "date": (a["candidate"] or {}).get("date"),
             "current": (a["current"] or {}).get("date")}
            for a in actions
        ]

        changed = False
        not_found_kinds: list[str] = []
        for action in actions:
            kind = action["kind"]
            target = self._find_kind(venue, kind)
            if target is None:
                continue
            if action["verdict"] == "not_found":
                not_found_kinds.append(kind)
                continue
            if action["verdict"] == "mismatch" and not homepage_only:
                # Keep the value, but remember that the official page disagreed so
                # the UI can show "数据不一致" instead of pretending all is well.
                target = dict(target)
                target["disputed"] = {
                    "page_date": (action.get("candidate") or {}).get("date"),
                    "shift_days": action.get("shift_days"),
                    "checked_at": checked_at,
                    "url": (action.get("candidate") or {}).get("source_url") or url,
                }
                self._replace_kind(venue, action["kind"], target)
                changed = True
                continue
            before = dict(target)
            updated = verification.apply_verdict(target, action, checked_at, url, trusted=trusted_edition)
            self._replace_kind(venue, kind, updated)
            changed = True
            if action["verdict"] == "updated":
                self.repo.append_audit({
                    "ts": checked_at, "run_id": run_id, "kind": "verify",
                    "venue_id": venue.get("id"), "abbr": venue.get("abbr"),
                    "before": before, "after": updated,
                })

        if not_found_kinds:
            if third and third.get("deadlines"):
                counters["aggregated"] += self._apply_third_party(
                    venue, third, checked_at, entry, only_kinds=set(not_found_kinds))
                changed = True
                still_unpublished = [k for k in not_found_kinds
                                     if k not in (third.get("deadlines") or {})]
            else:
                still_unpublished = not_found_kinds
            for kind in still_unpublished:
                counters["unpublished"] += self._mark_unpublished(venue, kind, checked_at, url, entry)
            changed = changed or bool(still_unpublished)
        return entry, changed, counters

    # ---------------------------------------------------------------- helpers
    def _parse(self, result, venue: dict[str, Any], url: str) -> list[dict[str, Any]]:
        text = (result.data or {}).get("main_text") or ""
        return cfp_parser.parse_candidates(text, venue.get("id", ""), url, now=self.clock.now())

    @staticmethod
    def _find_kind(venue: dict[str, Any], kind: str) -> dict[str, Any] | None:
        return next((d for d in venue.get("deadlines") or [] if d.get("kind") == kind), None)

    @staticmethod
    def _replace_kind(venue: dict[str, Any], kind: str, value: dict[str, Any]) -> None:
        deadlines_list = venue.setdefault("deadlines", [])
        for index, dl in enumerate(deadlines_list):
            if dl.get("kind") == kind:
                deadlines_list[index] = value
                return
        deadlines_list.append(value)

    def _apply_third_party(self, venue: dict[str, Any], third: dict[str, Any],
                           checked_at: str, entry: dict[str, Any],
                           only_kinds: set[str] | None) -> int:
        """Write CCFDDL dates as ``aggregator``; returns how many were written."""
        written = 0
        marked = entry.setdefault("marked_aggregator", [])
        for kind, date in (third.get("deadlines") or {}).items():
            if only_kinds is not None and kind not in only_kinds:
                continue
            target = self._find_kind(venue, kind)
            if target is None:
                continue
            if target.get("source_status") in {"confirmed", "verified"}:
                continue
            updated = dict(target)
            old_date = updated.get("date")
            updated["date"] = date
            updated["tz"] = third.get("tz") or updated.get("tz", "AoE")
            updated["source_status"] = "aggregator"
            updated["note"] = "第三方来源 CCFDDL（{}），官网未见/未公布，日期 {} {}".format(
                third.get("link") or "ccfddl", "由 " + str(old_date) + " 改为" if old_date != date else "与推测一致",
                date)
            updated["source"] = {"url": (third.get("link") or "https://ccfddl.github.io/"),
                                 "checked_at": checked_at}
            self._replace_kind(venue, kind, updated)
            marked.append(kind)
            written += 1
        return written

    def _mark_unpublished(self, venue: dict[str, Any], kind: str, checked_at: str,
                          url: str, entry: dict[str, Any]) -> int:
        target = self._find_kind(venue, kind)
        if target is None or target.get("source_status") not in {"predicted", "scraped", "unpublished", "blocked"}:
            return 0
        marked = dict(target)
        marked["source_status"] = "unpublished"
        marked["note"] = "已查官网页面（{}）未见该截止日期，保留推测值".format(checked_at[:10])
        marked["source"] = {"url": url, "checked_at": checked_at}
        self._replace_kind(venue, kind, marked)
        entry.setdefault("marked_unpublished", []).append(kind)
        return 1

    def _mark_blocked(self, venue: dict[str, Any], checked_at: str, url: str,
                      entry: dict[str, Any]) -> int:
        count = 0
        for dl in venue.get("deadlines") or []:
            if dl.get("kind") not in verification.VERIFY_KINDS:
                continue
            if dl.get("source_status") not in {"predicted", "scraped", "unpublished", "blocked"}:
                continue
            dl["source_status"] = "blocked"
            dl["note"] = "官网当前不可访问（{}），保留推测值，下次再试".format(checked_at[:10])
            dl["source"] = {"url": url, "checked_at": checked_at}
            entry.setdefault("marked_blocked", []).append(dl["kind"])
            count += 1
        return count

    def _deep_discover(self, venue: dict[str, Any], start_url: str,
                       cfg: AppConfig, max_pages: int = 8) -> tuple[str, list[dict[str, Any]]]:
        # Crawling is exploratory: use the cheap Web Fetch side of the chain only.
        # Opening a cloud browser per link would turn one venue into minutes.
        explorer = getattr(self.fetcher, "primary", self.fetcher)
        fetch_html = getattr(explorer, "fetch_html", None)
        if fetch_html is None:
            return "", []

        timeout = cfg.scrape.timeout_seconds
        seen: set[str] = {start_url}
        budget = max_pages

        def candidates_from(url: str) -> list[dict[str, Any]]:
            nonlocal budget
            if budget <= 0:
                return []
            budget -= 1
            fetched = explorer.fetch(url, timeout_s=timeout)
            if not fetched.ok:
                return []
            return self._parse(fetched, venue, url)

        def links_of(url: str, limit: int) -> list[str]:
            nonlocal budget
            if budget <= 0:
                return []
            budget -= 1
            html_result = fetch_html(url, timeout_s=timeout)
            if not html_result.ok:
                return []
            html = (html_result.data or {}).get("html") or ""
            return cfp_parser.find_date_links(html, url, limit=limit)

        entry_points = [start_url]
        for extra in ((venue.get("official_url") or "").strip(),):
            if extra and extra not in seen:
                entry_points.append(extra)

        for base in entry_points:
            for link in links_of(base, limit=3):
                if link in seen:
                    continue
                seen.add(link)
                found = candidates_from(link)
                if _has_deadlines(found):
                    return link, found
                for deeper in links_of(link, limit=2):
                    if deeper in seen:
                        continue
                    seen.add(deeper)
                    found = candidates_from(deeper)
                    if _has_deadlines(found):
                        return deeper, found
        return "", []
