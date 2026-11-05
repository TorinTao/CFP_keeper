"""Dump raw LetPub rows for the fields that parse badly."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.journal_sources import LetpubClient, _ROW  # noqa: E402

OUT = BASE / "data" / "letpub_row_debug.txt"


def main() -> None:
    client = LetpubClient(pause=5.0, retries=3)
    jid = client.find_id("Nature Machine Intelligence")
    if not jid:
        print("no id")
        return
    html = client._get(f"https://www.letpub.com.cn/index.php?journalid={jid}&page=journalapp&view=detail")
    keep = []
    for row in _ROW.findall(html):
        if "平均审稿速度" in row or "平均录用比例" in row:
            keep.append(row.strip()[:1200])
    OUT.write_text("\n\n=====\n\n".join(keep), encoding="utf-8")
    print("rows:", len(keep), "->", OUT)


if __name__ == "__main__":
    main()
