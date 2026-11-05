"""Fetcher chain: cheap Web Fetch first, cloud browser only when needed.

``thin_content`` (or a fetch failure) means the page is JS-only or unreachable
through the lightweight path; then the browser adapter gets one attempt.
"""

from __future__ import annotations

from typing import Any

from app.ports import FetchResult, Fetcher

THIN_TEXT_THRESHOLD = 200


def _is_thin(result: FetchResult) -> bool:
    """True when the lightweight fetch produced a JS-less shell instead of content."""
    if not result.ok:
        return False
    data = result.data or {}
    quality = data.get("quality") or {}
    warnings = quality.get("warnings") or []
    text = data.get("main_text") or ""
    return "thin_content" in warnings or len(text) < THIN_TEXT_THRESHOLD


class FallbackFetcher:
    """Implements the Fetcher port by chaining two fetchers.

    By default the browser is only used for *thin* pages: hard network failures
    (blocked overseas hosts, 20s timeouts) are returned as-is, because paying a
    browser session for them just doubles the wait without changing the outcome.
    Set ``on_failure=True`` to retry hard failures too.
    """

    def __init__(self, primary: Fetcher, fallback: Fetcher, enabled: bool = True,
                 on_failure: bool = False) -> None:
        self.primary = primary
        self.fallback = fallback
        self.enabled = enabled
        self.on_failure = on_failure

    def fetch(self, url: str, timeout_s: int = 120) -> FetchResult:
        first = self.primary.fetch(url, timeout_s=timeout_s)
        if not self.enabled:
            return first
        if not first.ok:
            if not self.on_failure:
                return first
        elif not _is_thin(first):
            return first

        second = self.fallback.fetch(url, timeout_s=timeout_s)
        if not second.ok:
            # keep the original evidence, but say the fallback also failed
            detail = f"{first.error_code or 'thin_content'}; fallback: {second.error_code} {second.detail}"
            return FetchResult(False, first.elapsed_ms + second.elapsed_ms,
                               error_code=first.error_code or "thin_content",
                               upstream_status=first.upstream_status, detail=detail[:500])

        merged: dict[str, Any] = dict(second.data or {})
        merged["via"] = "browser_fallback"
        merged["primary_engine"] = ((first.data or {}).get("engine") if first.ok else None)
        return FetchResult(True, first.elapsed_ms + second.elapsed_ms, data=merged)

    def fetch_html(self, url: str, timeout_s: int = 120) -> FetchResult:
        """Raw DOM is only available through the Web Fetch adapter."""
        for candidate in (self.primary, self.fallback):
            fetch_html = getattr(candidate, "fetch_html", None)
            if fetch_html is not None:
                return fetch_html(url, timeout_s=timeout_s)
        return FetchResult(False, 0, error_code="fetch_html_unsupported")
