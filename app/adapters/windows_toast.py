"""Windows toast notifier adapter (PowerShell + WinRT).

Implements :class:`app.ports.Notifier`. Never raises: failures are returned so
the reminder service can degrade to logging only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class WindowsToast:
    def __init__(self, script: Path | None = None, enabled: bool = True) -> None:
        default = Path(__file__).resolve().parent.parent / "toast.ps1"
        self.script = Path(script) if script else default
        self.enabled = enabled

    def notify(self, title: str, message: str) -> tuple[bool, str]:
        if not self.enabled:
            return False, "disabled"
        if not self.script.exists():
            return False, "toast script missing"
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.script),
               "-Title", title, "-Message", message]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=25, check=False)
        except Exception as exc:  # noqa: BLE001 - notification must never break the loop
            return False, f"{type(exc).__name__}: {exc}"
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()
            return False, err or f"exit {proc.returncode}"
        return True, (proc.stdout or b"").decode("utf-8", "replace").strip()
