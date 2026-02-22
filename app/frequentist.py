from __future__ import annotations

from datetime import datetime
from typing import List, Sequence

from sqlmodel import Session

from app.db_models import DEFAULT_RULE_SET, StreamConfig
from app.domain import SignalSeverity
from app.models import FrequentistSignal
from app.storage import baseline_stats, get_recent_records


def evaluate_rules_for_values(
    *,
    record_value: float,
    target: float,
    sigma: float,
    recent_values: Sequence[float],
    config: StreamConfig,
) -> List[FrequentistSignal]:
    z_score = (record_value - target) / sigma
    signals: List[FrequentistSignal] = []
    rules = (config.rule_set or DEFAULT_RULE_SET).get("rules", [])

    def _signal(rule: str, severity: SignalSeverity, evidence: str) -> None:
        signals.append(FrequentistSignal(rule=rule, severity=severity, evidence=evidence))

    warn_limit = config.warning_limit_sd
    action_limit = config.action_limit_sd

    if "1-3s" in rules and abs(z_score) >= action_limit:
        _signal("1-3s", SignalSeverity.ACTION, f"|z|={abs(z_score):.2f} exceeds action limit")

    recent_z = [((v - target) / sigma, v) for v in recent_values]

    if "2-2s" in rules and abs(z_score) >= warn_limit and recent_z:
        prev_z = recent_z[-1][0]
        if (z_score >= warn_limit and prev_z >= warn_limit) or (z_score <= -warn_limit and prev_z <= -warn_limit):
            direction = "high" if z_score > 0 else "low"
            _signal(
                "2-2s",
                SignalSeverity.WARN,
                f"Consecutive warning-level deviations in same direction ({direction})",
            )

    if "R-4s" in rules and recent_z:
        prev_z = recent_z[-1][0]
        if (z_score >= warn_limit and prev_z <= -warn_limit) or (z_score <= -warn_limit and prev_z >= warn_limit):
            _signal(
                "R-4s",
                SignalSeverity.ACTION,
                "Consecutive results exceed 4 SD range in opposite directions",
            )

    if "4-1s" in rules:
        last_four = recent_z[-3:] + [(z_score, record_value)]
        if len(last_four) == 4:
            if all(z >= 1 for z, _ in last_four) or all(z <= -1 for z, _ in last_four):
                _signal("4-1s", SignalSeverity.WARN, "Four consecutive results exceed 1 SD on the same side")

    if "10x" in rules:
        last_ten = recent_z[-9:] + [(z_score, record_value)]
        if len(last_ten) == 10:
            if all(z > 0 for z, _ in last_ten) or all(z < 0 for z, _ in last_ten):
                _signal("10x", SignalSeverity.WARN, "Ten consecutive results on the same side of the mean")

    return signals


def evaluate_rules(
    session: Session,
    record_value: float,
    record_timestamp: datetime,
    stream_id: str,
    config: StreamConfig,
) -> List[FrequentistSignal]:
    target, sigma = baseline_stats(session, config, record_timestamp)
    recent = get_recent_records(session, stream_id, record_timestamp, limit=9)
    return evaluate_rules_for_values(
        record_value=record_value,
        target=target,
        sigma=sigma,
        recent_values=[r.result_value for r in recent],
        config=config,
    )
