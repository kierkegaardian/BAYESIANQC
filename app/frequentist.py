from __future__ import annotations

from typing import List

from app.models import FrequentistSignal, QCRecordIn
from app.storage import storage


def evaluate_rules(record: QCRecordIn) -> List[FrequentistSignal]:
    baseline = storage.baseline_stats(record.stream_id)
    if baseline is None:
        return [FrequentistSignal(rule="no-baseline", severity="warn", evidence="No baseline available for stream")]

    target, sigma = baseline
    z_score = (record.result_value - target) / sigma
    signals: List[FrequentistSignal] = []

    if abs(z_score) >= storage.get_stream(record.stream_id).action_limit_sd:
        signals.append(
            FrequentistSignal(
                rule="1-3s", severity="action", evidence=f"|z|={abs(z_score):.2f} exceeds action limit"
            )
        )

    if abs(z_score) >= storage.get_stream(record.stream_id).warning_limit_sd:
        recent = [r for r in storage.get_recent_for_stream(record.stream_id) if r.timestamp < record.timestamp]
        if recent and all((r.result_value - target) / sigma >= storage.get_stream(record.stream_id).warning_limit_sd for r in recent[-1:]):
            direction = "high" if z_score > 0 else "low"
            signals.append(
                FrequentistSignal(
                    rule="2-2s",
                    severity="warn",
                    evidence=f"Consecutive warning-level deviations in same direction ({direction})",
                )
            )

    return signals
