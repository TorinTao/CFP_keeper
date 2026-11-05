"""Probe sources that could verify journal metadata."""
from __future__ import annotations

import json
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}

PROBES = [
    ("openalex", "https://api.openalex.org/sources?search=IEEE%20Transactions%20on%20Medical%20Imaging&per_page=1"),
    ("crossref", "https://api.crossref.org/journals/0278-0062"),
    ("doaj", "https://doaj.org/api/search/journals/issn%3A0278-0062"),
    ("letpub", "https://www.letpub.com.cn/index.php?page=journalapp"),
    ("ieee-insights", "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=42"),
    ("elsevier-insights", "https://www.sciencedirect.com/journal/medical-image-analysis/about/insights"),
]


def probe(name: str, url: str) -> None:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as res:
            body = res.read(400)
            ctype = res.headers.get("content-type", "")[:30]
            print(f"{name:18s} OK   status={res.status} type={ctype} head={body[:90]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"{name:18s} FAIL {type(exc).__name__}: {str(exc)[:90]}")


def main() -> None:
    for name, url in PROBES:
        probe(name, url)


if __name__ == "__main__":
    main()
