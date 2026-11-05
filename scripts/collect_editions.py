"""Browser-based verification pass.

Web Fetch quota can run out (it did: `webfetch_quota_exhausted`). The Cloud
Browser has its own quota and one session can visit many pages, so this script:

  1. creates ONE browser session;
  2. for each conference, opens the edition link from CCFDDL first (that is the
     2027 site), then the stored cfp_url / official_url;
  3. follows one "important dates"-ish link if the page has no dates;
  4. saves every page to data/verify_text/<venue>.json (url + text).

Verification itself is then done offline by scripts/verify_offline.py, so the
same policy code is reused and nothing depends on network during analysis.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.adapters.ccfddl import CcfddlSource  # noqa: E402
from app.domain import cfp_parser  # noqa: E402

OUT = BASE / "data" / "verify_text"
CLI = Path(r"C:\Users\Administrator\.dsh\skills\lexmount-browser\bin\browser-cli.exe")
TEXT_JS = "document.body.innerText"
LINK_JS = ("JSON.stringify(Array.from(document.querySelectorAll('a[href]'))"
           ".map(a=>({h:a.href,t:(a.innerText||'').trim().replace(/\\s+/g,' ').slice(0,80)})))")


def run(args, timeout=90):
    proc = subprocess.run([str(CLI)] + args, capture_output=True, timeout=timeout, check=False)
    return proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace")


def parse_json(text):
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dataset = CcfddlSource(BASE / "data" / "ccfddl.yml")
    doc = json.loads((BASE / "data" / "venues.json").read_text(encoding="utf-8"))
    venues = [v for v in doc["venues"] if v.get("type") == "conference"]

    out, _ = run(["session", "create", "--browser-mode", "light"], timeout=120)
    sid = (parse_json(out).get("data") or {}).get("session_id")
    if not sid:
        print("cannot create session")
        sys.exit(1)
    print("session:", sid, flush=True)

    try:
        for index, venue in enumerate(venues, 1):
            target = OUT / f"{venue['id']}.json"
            edition = int(venue.get("edition") or 0)
            edition_link = dataset.link_for(venue.get("abbr", ""), edition)
            urls = [u for u in (edition_link,
                                (venue.get("cfp_url") or "").strip(),
                                (venue.get("official_url") or "").strip()) if u]
            deduped, seen = [], set()
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    deduped.append(u)

            saved = None
            for url in deduped:
                try:
                    nav = run(["action", "open-url", "--session-id", sid, "--url", url], timeout=90)
                except subprocess.TimeoutExpired:
                    continue
                if not parse_json(nav[0]).get("ok"):
                    continue
                time.sleep(1.5)
                text = parse_json(run(["action", "eval", "--session-id", sid,
                                       "--expression", TEXT_JS])[0]).get("data") or ""
                if not isinstance(text, str) or len(text) < 200:
                    continue
                candidates = cfp_parser.parse_candidates(text, venue["id"], url)
                saved = {"venue_id": venue["id"], "abbr": venue["abbr"], "url": url,
                         "text": text, "candidates": len(candidates)}
                if candidates:
                    break
                # follow one likely "important dates" link
                try:
                    links = json.loads(parse_json(run(["action", "eval", "--session-id", sid,
                                                       "--expression", LINK_JS])[0]).get("data") or "[]")
                except json.JSONDecodeError:
                    links = []
                html = "".join(f'<a href="{l.get("h","")}">{l.get("t","")}</a>' for l in links)
                for link in cfp_parser.find_date_links(html, url, limit=2):
                    try:
                        nav2 = run(["action", "open-url", "--session-id", sid, "--url", link], timeout=90)
                    except subprocess.TimeoutExpired:
                        continue
                    if not parse_json(nav2[0]).get("ok"):
                        continue
                    time.sleep(1.2)
                    text2 = parse_json(run(["action", "eval", "--session-id", sid,
                                            "--expression", TEXT_JS])[0]).get("data") or ""
                    if isinstance(text2, str) and len(text2) > 200:
                        saved = {"venue_id": venue["id"], "abbr": venue["abbr"], "url": link,
                                 "text": text2,
                                 "candidates": len(cfp_parser.parse_candidates(text2, venue["id"], link))}
                        if saved["candidates"]:
                            break
            if saved:
                target.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
                print(f"[{index}/{len(venues)}] {venue['abbr']}: cand={saved['candidates']} "
                      f"{saved['url'][:60]}", flush=True)
            else:
                print(f"[{index}/{len(venues)}] {venue['abbr']}: FAILED", flush=True)
    finally:
        run(["session", "close", "--session-id", sid], timeout=60)
        print("closed", flush=True)


if __name__ == "__main__":
    main()
