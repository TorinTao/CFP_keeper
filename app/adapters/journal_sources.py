"""Journal metadata sources.

Crossref  → authoritative identity (title / publisher / ISSN). Official registry.
LetPub    → third-party metrics (review cycle, acceptance, OA, IF) for Chinese users.

Both are parsed by pure functions so the logic is testable without network.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
CROSSREF = "https://api.crossref.org/journals"
LETPUB_SEARCH = "https://www.letpub.com.cn/index.php?page=journalapp&view=search&searchname="
LETPUB_DETAIL = "https://www.letpub.com.cn/index.php?journalid={jid}&page=journalapp&view=detail"

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG.sub(" ", fragment))).strip()


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def title_similarity(a: str, b: str) -> float:
    """Cheap token overlap score in [0,1] — enough to match journal titles."""
    left, right = set(_norm(a).split()), set(_norm(b).split())
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


# --------------------------------------------------------------------- Crossref
def parse_crossref_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = ((payload.get("message") or {}).get("items")) or []
    out = []
    for item in items:
        out.append({
            "title": (item.get("title") or "").strip(),
            "publisher": (item.get("publisher") or "").strip(),
            "issn": item.get("ISSN") or [],
            "url": item.get("URL") or "",
        })
    return out


class CrossrefClient:
    def __init__(self, timeout: int = 25, mailto: str = "") -> None:
        self.timeout = timeout
        self.mailto = mailto

    def _get(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"User-Agent": f"cfp-keeper/1.0 ({self.mailto})"})
        with urllib.request.urlopen(req, timeout=self.timeout) as res:
            return json.loads(res.read().decode("utf-8", errors="replace"))

    def find_by_title(self, title: str) -> dict[str, Any] | None:
        query = urllib.parse.quote(title)
        payload = self._get(f"{CROSSREF}?query={query}&rows=5")
        candidates = parse_crossref_search(payload)
        best, best_score = None, 0.0
        for cand in candidates:
            score = title_similarity(title, cand["title"])
            if score > best_score:
                best, best_score = cand, score
        if best and best_score >= 0.6:
            best = dict(best)
            best["score"] = round(best_score, 2)
            return best
        return None


# ---------------------------------------------------------------------- LetPub
LABELS = {
    "期刊名字": "name",
    "期刊ISSN": "issn",
    "E-ISSN": "eissn",
    "出版商": "publisher",
    "是否OA开放访问": "open_access",
    "期刊官方网站": "official_url",
    "期刊投稿网址": "submission_url",
    "平均审稿速度": "review_cycle",
    "平均录用比例": "acceptance",
    "Gold OA文章占比": "gold_oa_share",
    "出版国家或地区": "country",
    "出版周期": "frequency",
    "涉及的研究方向": "scope",
}


def parse_letpub_detail(html: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    title_match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if title_match:
        title_text = _clean(title_match.group(1))
        if_match = re.search(r"影响因子\s*([\d.]+)", title_text)
        if if_match:
            result["impact_factor"] = if_match.group(1)
        result["title"] = re.sub(r"^.*?LetPub", "", title_text)[:120]

    for row in _ROW.findall(html):
        cells = [_clean(c) for c in _CELL.findall(row)]
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        label = cells[0].rstrip(":： ").strip()
        field = LABELS.get(label)
        if not field:
            continue
        value = cells[1]
        if field in {"review_cycle", "acceptance"}:
            value = re.sub(r"^(网友分享经验|网友分享)\s*", "", value).strip()
            parts = [p.strip() for p in re.split(r"[:：]", value) if p.strip()]
            value = parts[-1] if parts else value
            # LetPub shows "<b>网友分享经验：</b>" with no value for journals
            # without crowd-sourced data — treat that as "unknown", not as "：".
            if not re.search(r"[0-9A-Za-z\u4e00-\u9fff%]", value):
                value = ""
        if not value:
            continue
        result.setdefault(field, value)
    return result


class LetpubClient:
    """LetPub throttles hard: it answers with a tiny "访问速度过快" page when hit
    too fast. Every request is paced and retried with a growing backoff."""

    def __init__(self, timeout: int = 25, pause: float = 3.0, retries: int = 3) -> None:
        self.timeout = timeout
        self.pause = pause
        self.retries = retries

    def _get(self, url: str) -> str:
        last = ""
        for attempt in range(self.retries):
            time.sleep(self.pause if attempt == 0 else self.pause * (attempt + 2))
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as res:
                    body = res.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - retry on transient errors
                continue
            if len(body) > 5000 and "访问速度过快" not in body:
                return body
            last = body
        return last

    def find_id(self, title: str) -> str:
        html = self._get(LETPUB_SEARCH + urllib.parse.quote(title))
        ids = [i for i in re.findall(r"journalid=(\d+)", html) if i not in {"0", ""}]
        return ids[0] if ids else ""

    def lookup(self, title: str) -> dict[str, Any] | None:
        journal_id = self.find_id(title)
        if not journal_id:
            return None
        time.sleep(self.pause)
        html = self._get(LETPUB_DETAIL.format(jid=journal_id))
        data = parse_letpub_detail(html)
        if not data:
            return None
        data["source_url"] = LETPUB_DETAIL.format(jid=journal_id)
        data["journal_id"] = journal_id
        return data
