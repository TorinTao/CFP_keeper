"""CCFDDL dataset adapter (ccfddl.github.io).

The site is a JS app, but its data file `conference/allconf.yml` is a plain YAML
that lists every CCF conference with, per edition: official link, timezone and a
timeline (`abstract_deadline` / `deadline` / `rebuttal_deadline` / ...).

Used as:
  * a **discovery source** — it gives the exact URL of the 2027 page, which is
    far better than the homepage we had;
  * a **second source** — when the official page is silent, its dates are
    recorded with status ``aggregator`` (never presented as official).
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import yaml

DATASET_URL = "https://ccfddl.github.io/conference/allconf.yml"
CACHE_TTL_SECONDS = 24 * 3600

# our abbr -> CCFDDL title, when they differ
ALIASES = {"ACM BCB": "BCB", "SPIE MI": "SPIE"}

# CCFDDL timeline field -> our deadline kind
FIELD_KINDS = {
    "abstract_deadline": "abstract",
    "deadline": "full_paper",
    "rebuttal_deadline": "rebuttal",
    "decision_deadline": "notification",
    "camera_ready_deadline": "camera_ready",
}

# CCFDDL timezone strings -> our table
TZ_MAP = {"UTC-12": "AoE", "AoE": "AoE", "UTC-8": "PST", "UTC+0": "UTC", "UTC": "UTC"}


def parse_dataset(text: str) -> dict[str, dict[int, dict[str, Any]]]:
    """YAML text -> {title: {year: {link, tz, deadlines, comment}}}."""
    raw = yaml.safe_load(text) or []
    out: dict[str, dict[int, dict[str, Any]]] = {}
    for item in raw:
        title = item.get("title")
        if not title:
            continue
        editions: dict[int, dict[str, Any]] = {}
        for conf in item.get("confs") or []:
            year = conf.get("year")
            if not year:
                continue
            tz = TZ_MAP.get(str(conf.get("timezone") or ""), "AoE")
            deadlines: dict[str, str] = {}
            comment = ""
            for entry in conf.get("timeline") or []:
                comment = entry.get("comment") or comment
                for field, kind in FIELD_KINDS.items():
                    value = entry.get(field)
                    if isinstance(value, str) and value[:2] == "20" and len(value) >= 10:
                        deadlines.setdefault(kind, value[:10])
            editions[int(year)] = {"link": conf.get("link") or "",
                                   "tz": tz, "deadlines": deadlines,
                                   "comment": comment}
        out[title] = editions
    return out


class CcfddlSource:
    def __init__(self, cache_path: Path, url: str = DATASET_URL,
                 ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self.cache_path = Path(cache_path)
        self.url = url
        self.ttl = ttl_seconds
        self._data: dict[str, dict[int, dict[str, Any]]] | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------ load
    def _download(self) -> str:
        req = urllib.request.Request(self.url, headers={"User-Agent": "cfp-keeper/1.0"})
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.read().decode("utf-8", errors="replace")

    def load(self, force: bool = False) -> dict[str, dict[int, dict[str, Any]]]:
        if self._data is not None and not force:
            return self._data

        text: str | None = None
        from_cache = False
        if self.cache_path.exists() and not force:
            age = time.time() - self.cache_path.stat().st_mtime
            if age < self.ttl:
                text = self.cache_path.read_text(encoding="utf-8", errors="replace")
                from_cache = text is not None

        parsed: dict[str, dict[int, dict[str, Any]]] = {}
        if text is not None:
            parsed = self._parse_or_empty(text)
        if not parsed:
            # Missing, corrupt, or empty cache → download the real dataset.
            try:
                text = self._download()
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(text, encoding="utf-8")
                parsed = self._parse_or_empty(text)
            except Exception as exc:  # noqa: BLE001 - dataset is optional
                self.last_error = f"{type(exc).__name__}: {exc}"
                if from_cache and text is not None:
                    parsed = parsed or {}

        self._data = parsed
        return self._data

    def _parse_or_empty(self, text: str) -> dict[str, dict[int, dict[str, Any]]]:
        try:
            return parse_dataset(text)
        except yaml.YAMLError as exc:
            self.last_error = f"yaml: {str(exc)[:160]}"
            return {}

    # ---------------------------------------------------------------- lookup
    def lookup(self, abbr: str, year: int) -> dict[str, Any] | None:
        data = self.load()
        title = ALIASES.get(abbr, abbr)
        editions = data.get(title)
        if not editions:
            return None
        edition = editions.get(int(year))
        if edition is None:
            return None
        return edition

    def link_for(self, abbr: str, year: int) -> str:
        edition = self.lookup(abbr, year)
        return (edition or {}).get("link", "")

    def status(self) -> dict[str, Any]:
        data = self.load()
        return {"conferences": len(data), "cached": self.cache_path.exists(),
                "error": self.last_error}
