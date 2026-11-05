"""Lexmount Web Fetch CLI adapter (subprocess).

Implements :class:`app.ports.Fetcher`. Never raises: every failure is mapped to
an ``error_code`` so the service layer can record evidence instead of crashing.
"""

from __future__ import annotations

import json
import re
import subprocess
import time

from app.ports import FetchResult

ERROR_CODE_RE = re.compile(r'"code"\s*:\s*"([a-z_]+)"')
STATUS_RE = re.compile(r"unexpected status code:\s*(\d{3})")

DEFAULT_CLI = r"C:\Users\Administrator\.dsh\skills\lexmount-webfetch\bin\webfetch-cli.exe"


def parse_error_code(stderr: str) -> str:
    match = ERROR_CODE_RE.search(stderr or "")
    if match:
        return match.group(1)
    if "timed out" in (stderr or "").lower():
        return "timeout"
    return "unknown_error"


def parse_upstream_status(stderr: str) -> int | None:
    match = STATUS_RE.search(stderr or "")
    return int(match.group(1)) if match else None


class CliFetcher:
    def __init__(self, cli_path: str = DEFAULT_CLI) -> None:
        self.cli_path = cli_path

    def fetch(self, url: str, timeout_s: int = 120) -> FetchResult:
        started = time.time()
        cmd = [self.cli_path, "extract", "--url", url, "--format", "json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            return FetchResult(False, int((time.time() - started) * 1000), error_code="cli_timeout",
                               detail=f"subprocess exceeded {timeout_s}s")
        except FileNotFoundError:
            return FetchResult(False, int((time.time() - started) * 1000), error_code="cli_missing",
                               detail=f"executable not found: {self.cli_path}")

        elapsed_ms = int((time.time() - started) * 1000)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            return FetchResult(False, elapsed_ms, error_code=parse_error_code(stderr),
                               upstream_status=parse_upstream_status(stderr), detail=stderr.strip()[:800])
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return FetchResult(False, elapsed_ms, error_code="parse_error",
                               detail=f"{exc}; head={stdout[:200]!r}")
        return FetchResult(True, elapsed_ms, data=payload)

    def fetch_html(self, url: str, timeout_s: int = 120) -> FetchResult:
        """Raw DOM (`dump-dom`). Used to discover the "important dates" link."""
        started = time.time()
        cmd = [self.cli_path, "dump-dom", "--url", url, "--format", "json",
               "--filter-scripts-styles"]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            return FetchResult(False, int((time.time() - started) * 1000), error_code="cli_timeout",
                               detail=f"subprocess exceeded {timeout_s}s")
        except FileNotFoundError:
            return FetchResult(False, int((time.time() - started) * 1000), error_code="cli_missing",
                               detail=f"executable not found: {self.cli_path}")

        elapsed_ms = int((time.time() - started) * 1000)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            return FetchResult(False, elapsed_ms, error_code=parse_error_code(stderr),
                               upstream_status=parse_upstream_status(stderr), detail=stderr.strip()[:800])
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return FetchResult(False, elapsed_ms, error_code="parse_error",
                               detail=f"{exc}; head={stdout[:200]!r}")
        if not payload.get("html"):
            return FetchResult(False, elapsed_ms, error_code="empty_dom", detail="no html in payload")
        return FetchResult(True, elapsed_ms, data=payload)
