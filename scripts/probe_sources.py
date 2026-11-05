"""Diagnose why verification fails: probe which sources are reachable."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.cli_fetcher import CliFetcher  # noqa: E402

URLS = [
    "https://www.baidu.com/s?wd=MICCAI%202027%20important%20dates",
    "https://cn.bing.com/search?q=MICCAI+2027+important+dates",
    "https://duckduckgo.com/html/?q=MICCAI+2027+important+dates",
    "https://ccfddl.github.io/",
    "https://ccfddl.com/",
    "https://www.google.com/search?q=MICCAI+2027+deadline",
]


def main() -> None:
    fetcher = CliFetcher()
    for url in URLS:
        result = fetcher.fetch(url, timeout_s=45)
        head = ((result.data or {}).get("main_text") or "")[:150].replace("\n", " ")
        print(f"{url[:70]:70s} ok={result.ok} code={result.error_code or '-':24s} len={len((result.data or {}).get('main_text') or '')}")
        if head:
            print("    ", head.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
