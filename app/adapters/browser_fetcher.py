"""Lexmount Cloud Browser adapter — the rendering fallback.

Web Fetch (``lightmount_*`` engines) reads static/SSR pages cheaply but returns
``thin_content`` for JS-only pages. When that happens the fetcher falls back to a
real cloud browser session: create → open-url → read ``innerText`` → close.

Every step is best-effort; the adapter never raises, it returns an error code.
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from app.ports import FetchResult

DEFAULT_CLI = r"C:\Users\Administrator\.dsh\skills\lexmount-browser\bin\browser-cli.exe"

READ_TEXT_JS = "document.body && document.body.innerText"


class BrowserFetcher:
    def __init__(self, cli_path: str = DEFAULT_CLI, browser_mode: str = "light",
                 context_id: str = "") -> None:
        self.cli_path = cli_path
        self.browser_mode = browser_mode
        # A persistent context keeps cookies after a human solves a CAPTCHA.
        self.context_id = context_id

    # ------------------------------------------------------------------ helper
    def _run(self, args: list[str], timeout_s: int) -> tuple[int, str, str]:
        cmd = [self.cli_path] + args
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
        return (proc.returncode,
                proc.stdout.decode("utf-8", errors="replace"),
                proc.stderr.decode("utf-8", errors="replace"))

    @staticmethod
    def _json_or_none(text: str) -> dict[str, Any] | None:
        text = (text or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    return None
        return None

    # ------------------------------------------------------------------- fetch
    def fetch(self, url: str, timeout_s: int = 120) -> FetchResult:
        started = time.time()
        session_id: str | None = None
        try:
            create_args = ["session", "create", "--browser-mode", self.browser_mode]
            if self.context_id:
                create_args += ["--context-id", self.context_id, "--context-mode", "read_write"]
            code, out, err = self._run(create_args, timeout_s=min(60, timeout_s))
            payload = self._json_or_none(out)
            if code != 0 or not payload or not payload.get("data"):
                return FetchResult(False, int((time.time() - started) * 1000),
                                   error_code="browser_session_failed",
                                   detail=(err or out)[:300])
            session_id = payload["data"].get("session_id")
            if not session_id:
                return FetchResult(False, int((time.time() - started) * 1000),
                                   error_code="browser_session_failed", detail="no session_id")

            code, out, err = self._run(["action", "open-url", "--session-id", session_id,
                                        "--url", url], timeout_s=timeout_s)
            payload = self._json_or_none(out) or {}
            navigation = ((payload.get("data") or {}).get("navigation") or {})
            if code != 0 or navigation.get("errorText"):
                return FetchResult(False, int((time.time() - started) * 1000),
                                   error_code="browser_navigation_failed",
                                   detail=str(navigation.get("errorText") or err or out)[:300])

            code, out, err = self._run(["action", "eval", "--session-id", session_id,
                                        "--expression", READ_TEXT_JS], timeout_s=timeout_s)
            payload = self._json_or_none(out) or {}
            text = (payload.get("data") or "") if code == 0 else ""
            if not isinstance(text, str) or not text.strip():
                return FetchResult(False, int((time.time() - started) * 1000),
                                   error_code="browser_empty_page",
                                   detail=str(err or out)[:300])

            return FetchResult(
                True,
                int((time.time() - started) * 1000),
                data={
                    "main_text": text,
                    "status_code": 200,
                    "engine": "lexmount-browser",
                    "request_id": session_id,
                    "quality": {"text_length": len(text), "warnings": [],
                                "images_count": 0, "links_count": 0},
                },
            )
        except subprocess.TimeoutExpired:
            return FetchResult(False, int((time.time() - started) * 1000),
                               error_code="browser_timeout", detail=f"exceeded {timeout_s}s")
        except FileNotFoundError:
            return FetchResult(False, int((time.time() - started) * 1000),
                               error_code="browser_cli_missing", detail=self.cli_path)
        finally:
            if session_id:
                try:
                    self._run(["session", "close", "--session-id", session_id], timeout_s=30)
                except Exception:  # noqa: BLE001 - closing is best effort
                    pass
