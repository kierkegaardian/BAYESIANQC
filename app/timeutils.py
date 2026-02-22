from __future__ import annotations

from datetime import datetime, timezone


def as_utc(value: datetime) -> datetime:
    """
    Normalize datetimes for safe comparison.

    SQLite commonly returns naive datetimes; we treat them as UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

