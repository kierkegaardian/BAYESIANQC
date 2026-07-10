from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlmodel import Session

from app.db_models import DEFAULT_RULE_SET, QCRecord, StreamConfig
from app.domain import SignalSeverity
from app.math.validation import finite_float, finite_float_tuple, positive_finite_float
from app.models import FrequentistSignal
from app.storage import baseline_stats, get_recent_records
from app.timeutils import as_utc

_ONE_SD = 1.0
_TWO_SD = 2.0
_THREE_SD = 3.0


def _recent_values_for_config(records: Sequence[QCRecord], config: StreamConfig) -> list[float]:
    """Exclude observations from earlier config versions at a rule boundary."""
    effective_from = as_utc(config.effective_from)
    return [record.result_value for record in records if as_utc(record.timestamp) >= effective_from]


def evaluate_rules_for_values(
    *,
    record_value: float,
    target: float,
    sigma: float,
    recent_values: Sequence[float],
    config: StreamConfig,
) -> list[FrequentistSignal]:
    value = finite_float("record_value", record_value)
    center = finite_float("target", target)
    standard_deviation = positive_finite_float("sigma", sigma)
    history = finite_float_tuple("recent_values", recent_values)
    z_score = (value - center) / standard_deviation
    signals: list[FrequentistSignal] = []
    configured_rules = (config.rule_set or DEFAULT_RULE_SET).get("rules", [])
    rules = {str(rule) for rule in configured_rules}

    def _signal(rule: str, severity: SignalSeverity, evidence: str) -> None:
        signals.append(FrequentistSignal(rule=rule, severity=severity, evidence=evidence))

    if "1-3s" in rules and abs(z_score) >= _THREE_SD:
        _signal("1-3s", SignalSeverity.ACTION, f"|z|={abs(z_score):.2f} is at or beyond 3 SD")

    recent_z = [((historical_value - center) / standard_deviation, historical_value) for historical_value in history]

    if "2-2s" in rules and abs(z_score) >= _TWO_SD and recent_z:
        prev_z = recent_z[-1][0]
        if (z_score >= _TWO_SD and prev_z >= _TWO_SD) or (
            z_score <= -_TWO_SD and prev_z <= -_TWO_SD
        ):
            direction = "high" if z_score > 0 else "low"
            _signal(
                "2-2s",
                SignalSeverity.WARN,
                f"Two consecutive results are at or beyond 2 SD on the {direction} side",
            )

    # R-4s is intentionally not evaluated. It is a within-run rule, while this
    # evaluator receives a single result and only cross-run history.

    if "4-1s" in rules:
        last_four = recent_z[-3:] + [(z_score, value)]
        if len(last_four) == 4:
            if all(z >= _ONE_SD for z, _ in last_four) or all(z <= -_ONE_SD for z, _ in last_four):
                _signal("4-1s", SignalSeverity.WARN, "Four consecutive results exceed 1 SD on the same side")

    if "10x" in rules:
        last_ten = recent_z[-9:] + [(z_score, value)]
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
) -> list[FrequentistSignal]:
    target, sigma = baseline_stats(session, config, record_timestamp)
    recent = get_recent_records(session, stream_id, record_timestamp, limit=9)
    return evaluate_rules_for_values(
        record_value=record_value,
        target=target,
        sigma=sigma,
        recent_values=_recent_values_for_config(recent, config),
        config=config,
    )
