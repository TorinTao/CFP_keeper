"""Candidate extraction from fetched page text.

Pure text processing: given a page's ``main_text``, propose deadline candidates
(date + kind + timezone + the sentence they came from). No network, no I/O, so
this module is trivially unit-testable and replaceable (swap in an LLM extractor
without touching anything else).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from app.domain import deadlines

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

DATE_PATTERNS = [
    ("ymd", re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")),
    ("cn", re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")),
    ("mdy", re.compile(r"\b(" + _MONTH_ALT + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b", re.I)),
    ("dmy", re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + _MONTH_ALT + r")\.?,?\s+(20\d{2})\b", re.I)),
]

KEYWORD_KINDS: list[tuple[str, str]] = [
    ("camera ready", "camera_ready"),
    ("camera-ready", "camera_ready"),
    ("supplementary", "supplementary"),
    ("supplemental", "supplementary"),
    ("full paper", "full_paper"),
    ("full-paper", "full_paper"),
    ("paper submission", "full_paper"),
    ("submission deadline", "full_paper"),
    ("submissions due", "full_paper"),
    ("submission", "full_paper"),
    ("abstract", "abstract"),
    ("notification", "notification"),
    ("rebuttal", "rebuttal"),
    ("conference", "conference"),
    # Chinese
    ("全文截稿", "full_paper"),
    ("全文截止", "full_paper"),
    ("论文截稿", "full_paper"),
    ("摘要截稿", "abstract"),
    ("摘要截止", "abstract"),
    ("提交截止", "full_paper"),
    ("截稿", "full_paper"),
    ("录用通知", "notification"),
    ("会议日期", "conference"),
    # generic, lowest priority: a bare "deadline" line is usually the paper deadline
    ("deadline", "full_paper"),
]

ANCHOR_WINDOW = 160
SNIPPET_BEFORE = 90
SNIPPET_AFTER = 110

STRONG_KEYWORDS = tuple(
    [k for k, _ in KEYWORD_KINDS if k != "conference"]
    + ["deadline", "due", "submit", "截止", "截稿", "提交"]
)


def classify_kind(sentence: str, date_pos: int | None = None) -> str | None:
    """Identify the deadline kind from the clause right before the date.

    Returns ``None`` when no keyword applies: a date next to "Important Dates"
    but without its own keyword (e.g. "OpenReview accounts created Friday,
    January 15") must not be misread as the paper deadline.
    """
    low = sentence.lower()
    if date_pos is None:
        date_pos = len(low) // 2

    raw_prefix = low[max(0, date_pos - 160): date_pos]
    cut = max(raw_prefix.rfind("."), raw_prefix.rfind(";"), raw_prefix.rfind("|"), raw_prefix.rfind("!"))
    clause = raw_prefix[cut + 1:] if cut >= 0 else raw_prefix

    if "workshop" in clause:
        return "workshop"
    if "registration" in clause or "enrollment" in clause:
        # "Paper Registration / Enrollment Deadline" is a different milestone
        # than the paper submission deadline (CVPR has all three).
        return "registration"
    if "bidding" in clause or "reviewer" in clause:
        return "other"
    if any(word in clause for word in ("application", "award", "grant", "membership",
                                       "autumn school", "summer school", "symposium")):
        return "other"
    if "one page" in clause or "one-page" in clause:
        return "abstract"
    if "four page" in clause or "4-page" in clause:
        return "workshop"

    best: tuple[int, str] | None = None
    for keyword, kind in KEYWORD_KINDS:
        idx = low.rfind(keyword, 0, date_pos)
        if idx < 0:
            continue
        distance = date_pos - idx
        if best is None or distance < best[0]:
            best = (distance, kind)
    return best[1] if best else None


def pick_timezone(context: str) -> str:
    low = context.lower()
    if "aoe" in low or "anywhere on earth" in low:
        return "AoE"
    for token, name in (("pdt", "PDT"), ("pst", "PST"), ("edt", "EDT"), ("est", "EST")):
        if re.search(rf"\b{token}\b", low):
            return name
    if "utc" in low:
        return "UTC"
    if re.search(r"\bcst\b|北京时间", low):
        return "Asia/Shanghai"
    return "AoE"


def _to_iso(year: int, month: int, day: int) -> str | None:
    try:
        return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _has_strong_keyword(context: str, date_pos: int, before: int = 120, after: int = 50) -> bool:
    window = context.lower()[max(0, date_pos - before): date_pos + after]
    return any(keyword in window for keyword in STRONG_KEYWORDS)


_LINK_RE = re.compile(r'<a\b[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_SKIP_HREF = re.compile(r"\.(?:pdf|css|js|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|zip|xml|json)(?:[?#]|$)"
                        r"|^(?:mailto:|javascript:|#|tel:)", re.I)
_SKIP_HOST_PART = re.compile(r"(?:facebook|twitter|x\.com|linkedin|youtube|instagram|wp-json|/feed|"
                             r"google-analytics|gstatic|fonts\.)", re.I)

# Words that usually mark a page containing the actual deadlines.
_DATE_LINK_WORDS = (
    "important dates", "important-dates", "importantdates", "key dates", "dates",
    "deadline", "call for papers", "call-for-papers", "call for paper", "cfp",
    "submission", "submit", "author", "paper submission", "timeline",
)


def find_date_links(html: str, base_url: str, limit: int = 3) -> list[str]:
    """Pick the most likely "important dates / submission" links from a page.

    Used when a venue's stored URL is the homepage: one hop to the dates page is
    usually enough to find a real deadline. Pure string work, no network.
    """
    from urllib.parse import urljoin, urlparse

    if not html or not base_url:
        return []

    base_host = urlparse(base_url).netloc.lower()
    seen: set[str] = set()
    scored: list[tuple[int, int, str]] = []

    for order, match in enumerate(_LINK_RE.finditer(html)):
        href = match.group(1).strip()
        text = _TAG_RE.sub(" ", match.group(2))
        text = re.sub(r"\s+", " ", text).strip().lower()[:80]
        if not href or _SKIP_HREF.search(href) or _SKIP_HOST_PART.search(href + " " + text):
            continue

        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or url in seen:
            continue
        if url.rstrip("/") == base_url.rstrip("/"):
            continue
        seen.add(url)

        haystack = f"{parsed.path.lower()} {text} {parsed.query.lower()}"
        score = 0
        for word in _DATE_LINK_WORDS:
            if word in text:
                score += 6
            elif word.replace(" ", "-") in parsed.path.lower() or word.replace(" ", "") in parsed.path.lower():
                score += 4
        if not score:
            continue
        if parsed.netloc.lower() == base_host:
            score += 2
        if len(text) > 40:
            score -= 1
        scored.append((-score, order, url))

    scored.sort()
    picked: list[str] = []
    for _score, _order, url in scored:
        if url not in picked:
            picked.append(url)
        if len(picked) >= limit:
            break
    return picked


def parse_candidates(
    text: str,
    venue_id: str = "",
    source_url: str = "",
    today: Any = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Extract deadline candidates from page text."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    if not text:
        return []

    reference = today or (now or deadlines.utc_now()).date()

    for name, pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            if name in {"ymd", "cn"}:
                iso = _to_iso(match.group(1), match.group(2), match.group(3))
            elif name == "mdy":
                iso = _to_iso(match.group(3), MONTHS[match.group(1).lower()], match.group(2))
            else:
                iso = _to_iso(match.group(3), MONTHS[match.group(2).lower()], match.group(1))
            if not iso:
                continue

            parsed = datetime.strptime(iso, "%Y-%m-%d").date()
            if parsed < reference - timedelta(days=7) or parsed > reference + timedelta(days=3 * 365):
                continue

            start = max(0, match.start() - ANCHOR_WINDOW)
            end = min(len(text), match.end() + 40)
            context = re.sub(r"\s+", " ", text[start:end]).strip()
            date_pos = len(re.sub(r"\s+", " ", text[start: match.start()]))
            if not _has_strong_keyword(context, date_pos):
                continue

            kind = classify_kind(context, date_pos)
            if kind is None:
                continue  # a date, but no deadline keyword next to it
            snippet = re.sub(
                r"\s+", " ", text[max(0, match.start() - SNIPPET_BEFORE): match.end() + SNIPPET_AFTER]
            ).strip()
            key = (kind, iso)
            if key in found:
                continue
            found[key] = {
                "venue_id": venue_id,
                "kind": kind,
                "date": iso,
                "time": "23:59",
                "tz": pick_timezone(context),
                "snippet": snippet,
                "source_url": source_url,
                "extracted_at": deadlines.iso_local(now),
                "status": "candidate",
                "confidence": "medium" if len(context) > 60 else "low",
            }
    return list(found.values())
