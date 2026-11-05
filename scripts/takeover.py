"""Human-in-the-loop takeover for Cloudflare-protected sites.

Creates a persistent Lexmount context + a long-lived browser session, opens the
site and prints the live `inspect_url`. The user solves the CAPTCHA / login in
that live view; this script watches the page and, once the real content appears,
saves it to data/verify_text/<venue>.json so verification can continue.

    python scripts/takeover.py --venue amia-2027 --url https://amia.org/ --watch
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CLI = Path(r"C:\Users\Administrator\.dsh\skills\lexmount-browser\bin\browser-cli.exe")
OUT = BASE / "data" / "verify_text"
TAKEOVER_DIR = BASE / "data" / "takeover"
TEXT_JS = "document.body.innerText"
CHALLENGE_MARKERS = ("just a moment", "checking your browser", "verify you are human",
                     "verifying you are human", "attention required", "security service",
                     "enable javascript and cookies", "please wait", "ddos protection")
MIN_REAL_CONTENT = 1200  # a real conference homepage is far bigger than a challenge page


def run(args: list[str], timeout: int = 120) -> dict:
    proc = subprocess.run([str(CLI)] + args, capture_output=True, timeout=timeout, check=False)
    out = proc.stdout.decode("utf-8", errors="replace")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        start, end = out.find("{"), out.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(out[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {"ok": False, "raw": out[:400]}


def find_or_create_context(description: str) -> str:
    listing = run(["context", "list"])
    for ctx in ((listing.get("data") or {}).get("contexts") or []):
        if (ctx.get("description") or "").lower() == description.lower():
            return ctx["context_id"]
    created = run(["context", "create", "--description", description])
    data = created.get("data") or {}
    return data.get("context_id") or (data.get("context") or {}).get("context_id") or ""


def page_state(session_id: str) -> tuple[str, str]:
    result = run(["action", "eval", "--session-id", session_id, "--expression", TEXT_JS])
    text = result.get("data") or ""
    if not isinstance(text, str):
        text = ""
    return text, result.get("title") or ""


def looks_like_challenge(text: str) -> bool:
    low = (text or "").lower()
    if len(low) < MIN_REAL_CONTENT:
        return True
    return any(marker in low[:600] for marker in CHALLENGE_MARKERS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venue", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--max-wait", type=int, default=1500)
    args = parser.parse_args()

    TAKEOVER_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    context_desc = args.context or f"cfp-keeper: {args.venue}"
    context_id = find_or_create_context(context_desc)
    print(f"context: {context_id or '(none)'}  [{context_desc}]", flush=True)

    created = run(["session", "create", "--browser-mode", "light",
                   "--context-id", context_id, "--context-mode", "read_write",
                   "--timeout-seconds", "1800"], timeout=180) if context_id else \
              run(["session", "create", "--browser-mode", "light", "--timeout-seconds", "1800"],
                  timeout=180)
    session_id = ((created.get("data") or {}).get("session_id") or "")
    inspect_url = ((created.get("data") or {}).get("inspect_url") or "")
    if not session_id:
        print("session create failed:", json.dumps(created)[:300])
        return 1

    state = {"venue": args.venue, "url": args.url, "session_id": session_id,
             "inspect_url": inspect_url, "context_id": context_id,
             "started_at": datetime.now().isoformat(timespec="seconds"),
             "status": "opened", "text_length": 0}
    (TAKEOVER_DIR / f"{args.venue}.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run(["action", "open-url", "--session-id", session_id, "--url", args.url], timeout=180)
    time.sleep(2)
    text, title = page_state(session_id)
    print(f"title: {title!r}  text={len(text)} chars", flush=True)
    print(f"LIVE VIEW: {inspect_url}", flush=True)

    if not args.watch:
        return 0
    if not looks_like_challenge(text):
        print("page already has content, saving", flush=True)

    deadline = time.time() + args.max_wait
    while time.time() < deadline:
        time.sleep(6)
        text, title = page_state(session_id)
        state["text_length"] = len(text)
        state["title"] = title
        if not looks_like_challenge(text):
            (OUT / f"{args.venue}.json").write_text(
                json.dumps({"venue_id": args.venue, "abbr": args.venue,
                            "url": args.url, "text": text,
                            "taken_over_at": datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False), encoding="utf-8")
            state["status"] = "captured"
            (TAKEOVER_DIR / f"{args.venue}.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"CAPTURED {len(text)} chars -> data/verify_text/{args.venue}.json", flush=True)
            run(["session", "close", "--session-id", session_id], timeout=60)
            return 0
        if int(time.time()) % 60 < 7:
            print(f"...waiting for takeover (text={len(text)})", flush=True)

    state["status"] = "timeout"
    (TAKEOVER_DIR / f"{args.venue}.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("timed out waiting for takeover; session left open:", session_id, flush=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
