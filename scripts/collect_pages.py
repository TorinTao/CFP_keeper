"""Collect official pages for every conference via Lexmount Cloud Browser.

Writes data/verify_text/<venue>.json: {url, title, text}. This is the evidence
used to confirm deadlines that automated Web Fetch could not reach.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "verify_text"
CLI = Path(r"C:\Users\Administrator\.dsh\skills\lexmount-browser\bin\browser-cli.exe")


def run(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    proc = subprocess.run([str(CLI)] + args, capture_output=True, timeout=timeout, check=False)
    return (proc.returncode,
            proc.stdout.decode("utf-8", errors="replace"),
            proc.stderr.decode("utf-8", errors="replace"))


def parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return {}
    return {}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))
    venues = [v for v in doc["venues"] if v.get("type") == "conference"]

    code, out, err = run(["session", "create", "--browser-mode", "light"], timeout=120)
    payload = parse_json(out)
    sid = (payload.get("data") or {}).get("session_id")
    if not sid:
        print("cannot create session:", err[:300])
        sys.exit(1)
    print("session:", sid, flush=True)

    try:
        for index, venue in enumerate(venues, 1):
            target = OUT / f"{venue['id']}.json"
            if target.exists():
                print(f"[{index}/{len(venues)}] skip {venue['abbr']}", flush=True)
                continue
            urls = []
            for key in ("cfp_url", "official_url"):
                url = (venue.get(key) or "").strip()
                if url and url not in urls:
                    urls.append(url)
            saved = False
            for url in urls:
                try:
                    code, out, err = run(["action", "open-url", "--session-id", sid,
                                          "--url", url], timeout=90)
                except subprocess.TimeoutExpired:
                    continue
                nav = parse_json(out)
                if not nav.get("ok"):
                    continue
                time.sleep(1.5)
                code, out, err = run(["action", "eval", "--session-id", sid,
                                      "--expression", "document.body.innerText"], timeout=90)
                text = parse_json(out).get("data") or ""
                if not isinstance(text, str) or len(text) < 300:
                    continue
                title = ((nav.get("data") or {}).get("title") or "")
                final = ((nav.get("data") or {}).get("url") or url)
                target.write_text(json.dumps(
                    {"venue_id": venue["id"], "abbr": venue["abbr"], "url": final,
                     "title": title, "text": text}, ensure_ascii=False), encoding="utf-8")
                print(f"[{index}/{len(venues)}] {venue['abbr']}: {len(text)} chars", flush=True)
                saved = True
                break
            if not saved:
                print(f"[{index}/{len(venues)}] {venue['abbr']}: FAILED", flush=True)
    finally:
        run(["session", "close", "--session-id", sid], timeout=60)
        print("closed", flush=True)


if __name__ == "__main__":
    main()
