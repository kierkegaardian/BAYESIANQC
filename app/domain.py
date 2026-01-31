from __future__ import annotations

from enum import Enum


class SignalSeverity(str, Enum):
    ACTION = "action"
    WARN = "warn"


class Disposition(str, Enum):
    ACCEPT = "accept"
    MONITOR = "monitor"
    HOLD_FOR_REVIEW = "hold-for-review"
    REJECT = "reject"

