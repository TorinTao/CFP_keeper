"""JSON config adapter: config.json ↔ :class:`app.ports.AppConfig`."""

from __future__ import annotations

import json
from pathlib import Path

from app.ports import AppConfig

DEFAULTS: dict = {
    "port": 8770,
    "scrape": {
        "cli_path": r"C:\Users\Administrator\.dsh\skills\lexmount-webfetch\bin\webfetch-cli.exe",
        "timeout_seconds": 120,
        "auto": True,
        "daily_time": "09:00",
        "auto_apply": True,
        "auto_apply_guard_days": 90,
        "protect_confirmed": True,
    },
    "reminders": {"thresholds": [30, 14, 7, 3, 1], "tick_seconds": 900, "digest_hour": 9, "toast": True},
}


class JsonConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> AppConfig:
        raw: dict = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                print(f"[warn] config.json invalid ({exc}); using defaults")
                raw = {}
        merged = json.loads(json.dumps(DEFAULTS))
        for key, value in raw.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        return AppConfig.from_dict(merged)

    def save(self, config: AppConfig) -> None:
        payload = config.to_dict()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)
