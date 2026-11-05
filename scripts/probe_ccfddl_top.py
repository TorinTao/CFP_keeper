"""Inspect ccfddl.top homepage to find how it loads data."""
from __future__ import annotations

import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
BASE = "https://ccfddl.top/"

CANDIDATES = [
    "https://ccfddl.top/allconf.json",
    "https://ccfddl.top/conference/allconf.json",
    "https://ccfddl.top/data/allconf.json",
    "https://ccfddl.top/data.json",
    "https://ccfddl.top/conferences.json",
    "https://ccfddl.top/api/allconf",
    "https://ccfddl.top/api/v1/conferences",
]


def fetch(url: str, limit: int = 4000) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read(limit).decode("utf-8", errors="replace")


def main() -> None:
    html = fetch(BASE, 60000)
    print("homepage bytes:", len(html))
    for pattern in (r"<script[^>]+src=[\"']([^\"']+)", r"href=[\"']([^\"']*\.(?:json|yml|yaml))",
                    r"[\"'](/[^\"']*\.(?:json|js))[\"']"):
        for match in re.findall(pattern, html)[:8]:
            print("  asset:", match[:90])
    print("\nendpoint probes:")
    for url in CANDIDATES:
        try:
            body = fetch(url, 300)
            kind = "json" if body.strip().startswith(("{", "[")) else "other"
            print(f"  {url:52s} OK  {kind}  {body[:80]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {url:52s} FAIL {type(exc).__name__} {str(exc)[:60]}")


if __name__ == "__main__":
    main()
