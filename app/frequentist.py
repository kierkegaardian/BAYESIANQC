from __future__ import annotations

from typing import List

from sqlmodel import Session

from app.db_models import DEFAULT_RULE_SET, StreamConfig
from app.models import FrequentistSignal
from app.storage import baseline_stats, get_recent_records


def evaluate_rules(
    session: Session,
    record_value: float,
    record_timestamp,
    stream_id: str,
    config: StreamConfig,
) -> List[FrequentistSignal]:
    baseline = baseline_stats(session, config, record_timestamp)
    if baseline is None:
        return [FrequentistSignal(rule="no-baseline", severity="warn", evidence="No baseline available for stream")]

    target, sigma = baseline
    z_score = (record_value - target) / sigma
    signals: List[FrequentistSignal] = []
    rules = (config.rule_set or DEFAULT_RULE_SET).get("rules", [])

    def _signal(rule: str, severity: str, evidence: str) -> None:
        signals.append(FrequentistSignal(rule=rule, severity=severity, evidence=evidence))

    warn_limit = config.warning_limit_sd
    action_limit = config.action_limit_sd

    if "1-3s" in rules and abs(z_score) >= action_limit:
        _signal("1-3s", "action", f"|z|={abs(z_score):.2f} exceeds action limit")

    recent = get_recent_records(session, stream_id, record_timestamp, limit=9)
    recent_z = [((r.result_value - target) / sigma, r) for r in recent]

    if "2-2s" in rules and abs(z_score) >= warn_limit and recent_z:
        prev_z = recent_z[-1][0]
        if (z_score >= warn_limit and prev_z >= warn_limit) or (z_score <= -warn_limit and prev_z <= -warn_limit):
            direction = "high" if z_score > 0 else "low"
            _signal("2-2s", "warn", f"Consecutive warning-level deviations in same direction ({direction})")

    if "R-4s" in rules and recent_z:
        prev_z = recent_z[-1][0]
        if (z_score >= warn_limit and prev_z <= -warn_limit) or (z_score <= -warn_limit and prev_z >= warn_limit):
            _signal("R-4s", "action", "Consecutive results exceed 4 SD range in opposite directions")

    if "4-1s" in rules:
        last_four = recent_z[-3:] + [(z_score, None)]
        if len(last_four) == 4:
            if all(z >= 1 for z, _ in last_four) or all(z <= -1 for z, _ in last_four):
                _signal("4-1s", "warn", "Four consecutive results exceed 1 SD on the same side")

    if "10x" in rules:
        last_ten = recent_z[-9:] + [(z_score, None)]
        if len(last_ten) == 10:
            if all(z > 0 for z, _ in last_ten) or all(z < 0 for z, _ in last_ten):
                _signal("10x", "warn", "Ten consecutive results on the same side of the mean")

    return signals
