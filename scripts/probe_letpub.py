"""Inspect LetPub detail-page markup around the fields we want."""
from __future__ import annotations

import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as res:
        return res.read().decode("utf-8", errors="replace")


def main() -> None:
    html = get("https://www.letpub.com.cn/index.php?page=journalapp&view=search&searchname="
               + urllib.parse.quote("IEEE Transactions on Medical Imaging"))
    ids = [i for i in re.findall(r"journalid=(\d+)", html) if i != "0"]
    page = get(f"https://www.letpub.com.cn/index.php?journalid={ids[0]}&page=journalapp&view=detail")

    with open("data/letpub_sample.html", "w", encoding="utf-8") as fh:
        fh.write(page)
    print("saved sample, bytes:", len(page))

    for label in ("审稿周期", "录用比例", "影响因子", "是否OA", "中科院"):
        for match in re.finditer(re.escape(label), page):
            start = max(0, match.start() - 120)
            chunk = page[start:match.start() + 260]
            chunk = re.sub(r"\s+", " ", chunk)
            print(f"--- {label} @ {match.start()}")
            print(chunk.encode("ascii", "replace").decode()[:420])
            break


if __name__ == "__main__":
    main()
