"""Offline verification: reuse the real policy on browser-collected pages.

Web Fetch quota is a hard limit, so the evidence is collected once with the
Cloud Browser (scripts/collect_editions.py) and the decision logic runs offline
here. Nothing is written to the catalog that this script cannot point at a saved
page or the CCFDDL dataset.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.ccfddl import CcfddlSource  # noqa: E402
from app.adapters.clock import SystemClock  # noqa: E402
from app.adapters.json_config import JsonConfigStore  # noqa: E402
from app.adapters.json_store import JsonStore  # noqa: E402
from app.ports import FetchResult  # noqa: E402
from app.services.verifier import Verifier  # noqa: E402

TEXT_DIR = BASE / "data" / "verify_text"


class LocalFetcher:
    """Serves pages saved by the browser collector; never touches the network."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls = 0

    def fetch(self, url: str, timeout_s: int = 120) -> FetchResult:
        self.calls += 1
        text = self.pages.get(url)
        if text is None:
            return FetchResult(False, 0, error_code="not_collected", detail=f"no saved page for {url}")
        return FetchResult(True, 0, data={"main_text": text, "engine": "browser_collected",
                                          "status_code": 200, "quality": {"text_length": len(text)}})


def main() -> None:
    store = JsonStore(BASE)
    doc = store.load_venues()
    pages: dict[str, str] = {}
    for venue in doc["venues"]:
        if venue.get("type") != "conference":
            continue
        path = TEXT_DIR / f"{venue['id']}.json"
        if not path.exists():
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))
        text = saved.get("text") or ""
        if not text:
            continue
        # Only the URL that was actually collected: aliasing the venue's homepage
        # to a different page would hide the "edition link" evidence path.
        if saved.get("url"):
            pages.setdefault(saved["url"].strip(), text)

    config = JsonConfigStore(BASE / "config.json").load()
    dataset = CcfddlSource(BASE / "data" / "ccfddl.yml")
    verifier = Verifier(store, LocalFetcher(pages), SystemClock(), lambda: config,
                        third_party=dataset)
    record = verifier.verify()

    print("summary:", json.dumps(record["summary"], ensure_ascii=False))
    for check in record["checks"]:
        acts = ", ".join(f"{a['kind']}={a['verdict']}" for a in check.get("actions") or [])
        marks = {k: v for k, v in check.items() if k.startswith("marked")}
        print(f"  {check['abbr']:10s} ok={check['ok']!s:5s} {acts} {marks or ''}")


if __name__ == "__main__":
    main()
