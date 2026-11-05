"""HTTP boundary: routing and JSON encoding only.

All business decisions live in the services; this module translates HTTP in and
out and nothing else.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.domain import ics as ics_mod
from app.api.application import Application

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


class Handler(BaseHTTPRequestHandler):
    server_version = "CFP-Keeper/0.2"
    app: Application

    # ---------------------------------------------------------------- plumbing
    def log_message(self, fmt: str, *args: Any) -> None:
        if self.path.startswith("/api/"):
            sys.stderr.write("[api] %s %s\n" % (self.command, self.path))

    def _send(self, status: int, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # -------------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            if path in {"/", "/index.html"}:
                return self._serve_static("index.html")
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")

            if path == "/api/health":
                return self._json(200, self.app.health())
            if path == "/api/settings":
                return self._json(200, self.app.public_settings())
            if path == "/api/venues":
                include_passed = query.get("include_passed") in {"1", "true", "yes"}
                return self._json(200, self.app.catalog.query(query, include_passed))
            if path == "/api/candidates":
                return self._json(200, self.app.repo.load_candidates())
            if path == "/api/scrape/runs":
                kind = query.get("kind") or None
                return self._json(200, {"runs": self.app.repo.list_runs(int(query.get("limit", 20)), kind=kind)})
            if path == "/api/scrape/status":
                return self._json(200, {"running": self.app.scraping,
                                        "last_run_id": self.app.last_run_id})
            if path == "/api/journals/verify/status":
                return self._json(200, {"running": self.app.verifying_journals,
                                        "last_run_id": self.app.last_journal_verify_id,
                                        "progress": self.app.journal_progress})
            if path == "/api/verify/status":
                return self._json(200, {"running": self.app.verifying,
                                        "last_run_id": self.app.last_verify_id,
                                        "progress": self.app.verify_progress,
                                        "schedule": self.app.verifier_job.status()})
            if path == "/api/reminders":
                return self._json(200, {"reminders": self.app.repo.read_reminders(int(query.get("limit", 50)))})
            if path == "/api/ics":
                return self._api_ics(query)

            match = re.fullmatch(r"/api/venues/([A-Za-z0-9_.-]+)", path)
            if match:
                view = self.app.catalog.get(match.group(1))
                if view:
                    return self._json(200, {"venue": view})
                return self._json(404, {"error": {"code": "venue_not_found", "message": match.group(1)}})

            self._json(404, {"error": {"code": "not_found", "message": path}})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": {"code": "internal", "message": str(exc)}})

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    # ------------------------------------------------------------------ PATCH
    def do_PATCH(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        if path == "/api/settings":
            status, payload = self.app.update_settings(self._read_json())
            return self._json(status, payload)
        match = re.fullmatch(r"/api/venues/([A-Za-z0-9_.-]+)/state", path)
        if not match:
            return self._json(404, {"error": {"code": "not_found", "message": path}})
        status, payload = self.app.catalog.set_state(match.group(1), self._read_json())
        self._json(status, payload)

    # ------------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/scrape/run":
                body = self._read_json()
                status, payload = self.app.start_scrape(body.get("venue_ids"))
                return self._json(status, payload)
            if path == "/api/journals/verify":
                status, payload = self.app.start_journal_verify()
                return self._json(status, payload)
            if path == "/api/verify":
                body = self._read_json()
                status, payload = self.app.start_verify(body.get("venue_ids"),
                                                        body.get("pending_only"))
                return self._json(status, payload)
            match = re.fullmatch(r"/api/venues/([A-Za-z0-9_.-]+)/deadlines/([a-z_]+)/confirm", path)
            if match:
                status, payload = self.app.catalog.confirm_deadline(
                    match.group(1), match.group(2), self._read_json())
                return self._json(status, payload)
            self._json(404, {"error": {"code": "not_found", "message": path}})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._json(500, {"error": {"code": "internal", "message": str(exc)}})

    # --------------------------------------------------------------- internals
    def _serve_static(self, name: str) -> None:
        target = (WEB_DIR / name).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            return self._json(404, {"error": {"code": "not_found", "message": name}})
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in {"application/javascript", "application/json"}:
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def _api_ics(self, query: dict[str, str]) -> None:
        within = int(query.get("within", 365))
        include_predicted = query.get("include_predicted", "1") not in {"0", "false"}
        doc = self.app.repo.load_venues()
        body = ics_mod.build_calendar(doc.get("venues", []),
                                      include_predicted=include_predicted,
                                      within_days=within).encode("utf-8")
        self._send(200, body, "text/calendar; charset=utf-8",
                   {"Content-Disposition": 'attachment; filename="cfp-keeper.ics"'})
