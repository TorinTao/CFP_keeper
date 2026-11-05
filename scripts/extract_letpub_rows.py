"""Extract LetPub detail table as label=>value pairs (for designing the parser)."""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HTML = BASE / "data" / "letpub_sample.html"
OUT = BASE / "data" / "letpub_rows.txt"

TAG = re.compile(r"<[^>]+>")


def clean(fragment: str) -> str:
    text = unescape(TAG.sub(" ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    html = HTML.read_text(encoding="utf-8", errors="replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.I | re.S)
    lines = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
        values = [clean(c) for c in cells]
        values = [v for v in values if v]
        if len(values) >= 2 and len(values[0]) <= 14:
            lines.append(f"{values[0]} => {values[1]}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("rows:", len(lines), "->", OUT)


if __name__ == "__main__":
    main()
