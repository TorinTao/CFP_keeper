"""Second pass: follow each conference's "dates / CFP / submission" link in the
Cloud Browser and save that page as evidence."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
TEXT_DIR = BASE / "data" / "verify_text"
SITE_DIR = BASE / "data" / "verify_site"
CLI = Path(r"C:\Users\Administrator\.dsh\skills\lexmount-browser\bin\browser-cli.exe")

LINK_JS = ("JSON.stringify(Array.from(document.querySelectorAll('a[href]'))"
           ".map(a=>({h:a.href,t:(a.innerText||'').trim().replace(/\\s+/g,' ').slice(0,90)})))")
TEXT_JS = "document.body.innerText"

WORDS = ("important dates", "important-dates", "dates", "deadline", "call for paper",
         "call-for-paper", "cfp", "submission", "author", "paper")
SKIP = re.compile(r"\.(pdf|css|js|png|jpe?g|svg|zip|xml)(\?|$)|mailto:|javascript:", re.I)


def run(args: list[str], timeout: int = 90) -> tuple[int, str, str]:
    proc = subprocess.run([str(CLI)] + args, capture_output=True, timeout=timeout, check=False)
    return (proc.returncode,
            proc.stdout.decode("utf-8", errors="replace"),
            proc.stderr.decode("utf-8", errors="replace"))


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def score(link: dict) -> int:
    text = (link.get("t") or "").lower()
    href = (link.get("h") or "").lower()
    if not href or SKIP.search(href):
        return 0
    total = 0
    for word in WORDS:
        if word in text:
            total += 6
        elif word.replace(" ", "-") in href or word.replace(" ", "") in href:
            total += 4
    return total


def main() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))
    venues = [v for v in doc["venues"] if v.get("type") == "conference"]
    code, out, err = run(["session", "create", "--browser-mode", "light"], timeout=120)
    sid = (parse_json(out).get("data") or {}).get("session_id")
    if not sid:
        print("cannot create session:", err[:300])
        sys.exit(1)
    print("session:", sid, flush=True)

    try:
        for index, venue in enumerate(venues, 1):
            out_path = SITE_DIR / f"{venue['id']}.json"
            if out_path.exists():
                print(f"[{index}/{len(venues)}] skip {venue['abbr']}", flush=True)
                continue
            base = (venue.get("cfp_url") or venue.get("official_url") or "").strip()
            if not base:
                print(f"[{index}/{len(venues)}] {venue['abbr']}: no url", flush=True)
                continue
            try:
                run(["action", "open-url", "--session-id", sid, "--url", base], timeout=90)
            except subprocess.TimeoutExpired:
                print(f"[{index}/{len(venues)}] {venue['abbr']}: nav timeout", flush=True)
                continue
            time.sleep(1.2)
            _, raw, _ = run(["action", "eval", "--session-id", sid, "--expression", LINK_JS])
            payload = parse_json(raw).get("data") or "[]"
            try:
                links = json.loads(payload) if isinstance(payload, str) else payload
            except json.JSONDecodeError:
                links = []
            ranked = sorted((l for l in links if score(l) > 0), key=score, reverse=True)[:3]
            saved = []
            for link in ranked:
                try:
                    nav = run(["action", "open-url", "--session-id", sid, "--url", link["h"]], timeout=90)
                except subprocess.TimeoutExpired:
                    continue
                if not parse_json(nav[1]).get("ok"):
                    continue
                time.sleep(1.2)
                text = parse_json(run(["action", "eval", "--session-id", sid,
                                       "--expression", TEXT_JS])[1]).get("data") or ""
                if isinstance(text, str) and len(text) > 400:
                    saved.append({"url": link["h"], "text": text})
            if saved:
                out_path.write_text(json.dumps({"venue_id": venue["id"], "abbr": venue["abbr"],
                                                "pages": saved}, ensure_ascii=False),
                                    encoding="utf-8")
                print(f"[{index}/{len(venues)}] {venue['abbr']}: {len(saved)} page(s)", flush=True)
            else:
                print(f"[{index}/{len(venues)}] {venue['abbr']}: no link page", flush=True)
            run(["action", "open-url", "--session-id", sid, "--url", base], timeout=90)
    finally:
        run(["session", "close", "--session-id", sid], timeout=60)
        print("closed", flush=True)


if __name__ == "__main__":
    main()
