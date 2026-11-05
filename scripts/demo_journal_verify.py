"""Demo: can we verify journal fields from Crossref (authoritative) + LetPub (third party)?"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}

JOURNALS = [
    ("TMI", "IEEE Transactions on Medical Imaging", "0278-0062"),
    ("MedIA", "Medical Image Analysis", "1361-8415"),
    ("Radiology", "Radiology", "0033-8419"),
]


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as res:
        return json.loads(res.read().decode("utf-8", errors="replace"))


def get_text(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as res:
        return res.read().decode("utf-8", errors="replace")


def letpub(name: str) -> dict:
    html = get_text("https://www.letpub.com.cn/index.php?page=journalapp&view=search&searchname="
                    + urllib.parse.quote(name))
    ids = [i for i in re.findall(r"journalid=(\d+)", html) if i != "0"]
    if not ids:
        return {"found": False}
    page = get_text(f"https://www.letpub.com.cn/index.php?journalid={ids[0]}&page=journalapp&view=detail")
    text = re.sub(r"<[^>]+>", " ", page)
    text = re.sub(r"\s+", " ", text)
    out = {"found": True, "url": f"https://www.letpub.com.cn/index.php?journalid={ids[0]}&page=journalapp&view=detail"}

    match = re.search(r"影响因子[^0-9]{0,20}(\d+\.\d+)", text)
    if match:
        out["impact_factor"] = match.group(1)
    match = re.search(r"审稿周期[^。]{0,10}?[:：]?\s*([^ ]{1,18})", text)
    if match:
        out["review_cycle_raw"] = match.group(1)[:20]
    match = re.search(r"录用比例[^。]{0,10}?[:：]?\s*([^ ]{1,14})", text)
    if match:
        out["acceptance_raw"] = match.group(1)[:16]
    match = re.search(r"是否OA[^。]{0,20}?[:：]?\s*(是|否|未知)", text)
    if match:
        out["open_access"] = match.group(1)
    return out


def main() -> None:
    for abbr, title, issn in JOURNALS:
        print(f"== {abbr}: {title}")
        try:
            data = get_json(f"https://api.crossref.org/journals/{issn}")
            msg = data["message"]
            print(f"   crossref : {msg.get('title')} | publisher={msg.get('publisher')} | ISSN={msg.get('ISSN')}")
        except Exception as exc:  # noqa: BLE001
            print(f"   crossref : FAIL {type(exc).__name__} {str(exc)[:60]}")
        try:
            info = letpub(title)
            print(f"   letpub   : {json.dumps(info, ensure_ascii=True)}")
        except Exception as exc:  # noqa: BLE001
            print(f"   letpub   : FAIL {type(exc).__name__} {str(exc)[:60]}")


if __name__ == "__main__":
    main()
