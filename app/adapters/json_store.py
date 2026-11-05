"""JSON-file repository adapter.

Implements :class:`app.ports.Repository` with plain files: atomic writes, a
``.bak`` copy of the previous version, and graceful degradation when a file is
corrupt. Swap this for SQLite or a remote store without touching the services.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from app.domain import deadlines, schema

SNAPSHOT_LIMIT = 200_000


class StoreError(RuntimeError):
    pass


class JsonStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.data_dir = self.root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "runs").mkdir(exist_ok=True)
        (self.data_dir / "snapshots").mkdir(exist_ok=True)
        self.venues_path = self.data_dir / "venues.json"
        self.state_path = self.data_dir / "user_state.json"
        self.candidates_path = self.data_dir / "candidates.json"
        self.reminders_path = self.data_dir / "reminders.jsonl"
        self.reminder_state_path = self.data_dir / "state_reminders.json"
        self.scrape_state_path = self.data_dir / "state_scrape.json"
        self.verify_state_path = self.data_dir / "state_verify.json"
        self.audit_path = self.data_dir / "auto_applied.jsonl"
        self._lock = threading.RLock()
        self.degraded: list[str] = []

    # ---------------------------------------------------------------- helpers
    def _atomic_write(self, path: Path, payload: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        if path.exists():
            try:
                shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
            except OSError:
                pass
        os.replace(tmp, path)

    def write_json_atomic(self, path: Path, doc: dict[str, Any]) -> None:
        with self._lock:
            self._atomic_write(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            backup = path.with_suffix(path.suffix + ".bak")
            if backup.exists():
                try:
                    with open(backup, "r", encoding="utf-8") as fh:
                        restored = json.load(fh)
                    self.degraded.append(f"{path.name}: recovered from .bak ({exc})")
                    return restored
                except Exception as inner:  # noqa: BLE001
                    raise StoreError(f"{path.name} corrupt and backup unusable: {inner}") from inner
            raise StoreError(f"{path.name} corrupt and no backup: {exc}") from exc

    # ---------------------------------------------------------------- catalog
    def load_venues(self) -> dict[str, Any]:
        with self._lock:
            doc = self._read_json(self.venues_path, {"schema_version": 1, "venues": []})
        if not isinstance(doc, dict) or not isinstance(doc.get("venues"), list):
            raise StoreError("venues.json must be an object with a 'venues' list")
        return doc

    def save_venues(self, doc: dict[str, Any]) -> None:
        problems = schema.validate_venues(doc)
        if problems:
            raise StoreError("refusing to save invalid venues: " + "; ".join(problems[:5]))
        doc["updated_at"] = deadlines.iso_local()
        with self._lock:
            self._atomic_write(self.venues_path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    def find_venue(self, doc: dict[str, Any], venue_id: str) -> dict[str, Any] | None:
        return schema.find_venue(doc, venue_id)

    def load_state(self) -> dict[str, Any]:
        with self._lock:
            doc = self._read_json(self.state_path, {"schema_version": 1, "venues": {}})
        doc.setdefault("venues", {})
        return doc

    def save_state(self, doc: dict[str, Any]) -> None:
        doc["updated_at"] = deadlines.iso_local()
        with self._lock:
            self._atomic_write(self.state_path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    # ------------------------------------------------------------- candidates
    def load_candidates(self) -> dict[str, Any]:
        with self._lock:
            doc = self._read_json(self.candidates_path, {"schema_version": 1, "candidates": []})
        doc.setdefault("candidates", [])
        return doc

    def save_candidates(self, doc: dict[str, Any]) -> None:
        doc["updated_at"] = deadlines.iso_local()
        with self._lock:
            self._atomic_write(self.candidates_path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    # ----------------------------------------------------------------- evidence
    def save_run(self, record: dict[str, Any]) -> Path:
        path = self.data_dir / "runs" / f"{record['run_id']}.json"
        with self._lock:
            self._atomic_write(path, json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        return path

    def save_snapshot(self, run_id: str, text: str) -> Path:
        path = self.data_dir / "snapshots" / f"{run_id}.txt"
        with self._lock:
            self._atomic_write(path, text[:SNAPSHOT_LIMIT])
        return path

    def list_runs(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        runs = sorted((self.data_dir / "runs").glob("*.json"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for path in runs:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    record = json.load(fh)
            except Exception:  # noqa: BLE001
                continue
            if kind and record.get("kind", "scrape") != kind:
                continue
            items.append(record)
            if len(items) >= limit:
                break
        return items

    # ---------------------------------------------------------------- reminders
    def append_reminder(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock:
            with open(self.reminders_path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line)

    def read_reminders(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.reminders_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self._lock:
            with open(self.reminders_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries[-limit:][::-1]

    def load_reminder_state(self) -> dict[str, Any]:
        with self._lock:
            return self._read_json(self.reminder_state_path, {"sent": {}})

    def save_reminder_state(self, doc: dict[str, Any]) -> None:
        with self._lock:
            self._atomic_write(self.reminder_state_path,
                               json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    # ------------------------------------------------------------ scrape state
    def load_scrape_state(self) -> dict[str, Any]:
        with self._lock:
            return self._read_json(self.scrape_state_path, {"last_auto_date": None, "last_auto_at": None})

    def save_scrape_state(self, doc: dict[str, Any]) -> None:
        with self._lock:
            self._atomic_write(self.scrape_state_path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    # ------------------------------------------------------------ verify state
    def load_verify_state(self) -> dict[str, Any]:
        with self._lock:
            return self._read_json(self.verify_state_path, {"last_auto_date": None, "last_auto_at": None})

    def save_verify_state(self, doc: dict[str, Any]) -> None:
        with self._lock:
            self._atomic_write(self.verify_state_path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    # ------------------------------------------------------------------- audit
    def append_audit(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._lock:
            with open(self.audit_path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line)

    def read_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self._lock:
            with open(self.audit_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries[-limit:][::-1]
