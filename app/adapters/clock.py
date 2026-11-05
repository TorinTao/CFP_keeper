"""System clock adapter (UTC now + Beijing display conversion)."""

from __future__ import annotations

from datetime import datetime

from app.domain import deadlines


class SystemClock:
    def now(self) -> datetime:
        return deadlines.utc_now()

    def to_local(self, moment: datetime) -> datetime:
        return deadlines.to_display(moment)
