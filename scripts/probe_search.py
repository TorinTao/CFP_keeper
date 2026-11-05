"""Probe Bing search as a discovery channel + CCFDDL data endpoints."""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.cli_fetcher import CliFetcher  # noqa: E402

QUERIES = [
    "MICCAI 2027 important dates submission deadline",
    "ICML 2027 call for papers deadline",
    "AAAI 2027 call for papers deadline",
]

CCFDDL_URLS = [
    "https://ccfddl.github.io/conference/allconf.yml",
    "https://ccfddl.github.io/data/allconf.yml",
    "https://ccfddl.github.io/allconf.yml",
    "https://ccfddl.github.io/conference/conf_cvpr.yml",
]


def search(fetcher: CliFetcher, query: str) -> list[str]:
    url = "https://cn.bing.com/search?q=" + query.replace(" ", "+")
    result = fetcher.fetch(url, timeout_s=60)
    if not result.ok:
        print(f"  [{query}] fetch failed: {result.error_code}")
        return []
    text = (result.data or {}).get("main_text") or ""
    urls = re.findall(r"URL:\s*(https?://\S+)", text)
    print(f"  [{query}] {len(urls)} urls")
    for u in urls[:3]:
        print("     ", u[:100])
    return urls


def main() -> None:
    fetcher = CliFetcher()
    print("== bing search")
    for query in QUERIES:
        search(fetcher, query)

    print("== ccfddl data endpoints")
    for url in CCFDDL_URLS:
        result = fetcher.fetch(url, timeout_s=60)
        text = (result.data or {}).get("main_text") or ""
        print(f"  {url[:60]:60s} ok={result.ok} code={result.error_code or '-':20s} len={len(text)}")
        if result.ok and len(text) > 200:
            print("     head:", text[:200].replace("\n", " ").encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
