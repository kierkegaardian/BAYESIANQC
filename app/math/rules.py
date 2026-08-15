from __future__ import annotations

from collections.abc import Sequence

from app.domain import SignalSeverity
from app.evaluation_models import ResolvedControlLimits
from app.models import FrequentistSignal


LEGACY_R4S_VARIANT = "legacy_sequential_opposite_warning_limits"


def evaluate_rule_set(
    *,
    record_value: float,
    recent_values: Sequence[float],
    limits: ResolvedControlLimits,
    rule_ids: Sequence[str],
) -> list[FrequentistSignal]:
    z_score = (record_value - limits.centerline) / limits.sigma
    recent_z = [(value - limits.centerline) / limits.sigma for value in recent_values]
    signals: list[FrequentistSignal] = []

    def signal(rule: str, severity: SignalSeverity, evidence: str, rule_variant: str | None = None) -> None:
        signals.append(
            FrequentistSignal(rule=rule, severity=severity, evidence=evidence, rule_variant=rule_variant)
        )

    if "1-3s" in rule_ids and abs(z_score) >= limits.action_limit_sd:
        signal("1-3s", SignalSeverity.ACTION, f"|z|={abs(z_score):.2f} exceeds action limit")

    if "2-2s" in rule_ids and abs(z_score) >= limits.warning_limit_sd and recent_z:
        previous = recent_z[-1]
        same_high = z_score >= limits.warning_limit_sd and previous >= limits.warning_limit_sd
        same_low = z_score <= -limits.warning_limit_sd and previous <= -limits.warning_limit_sd
        if same_high or same_low:
            direction = "high" if z_score > 0 else "low"
            signal("2-2s", SignalSeverity.WARN, f"Consecutive warning-level deviations ({direction})")

    if "R-4s" in rule_ids and recent_z:
        previous = recent_z[-1]
        opposite_warning_limits = (
            z_score >= limits.warning_limit_sd and previous <= -limits.warning_limit_sd
        ) or (z_score <= -limits.warning_limit_sd and previous >= limits.warning_limit_sd)
        if opposite_warning_limits:
            signal(
                "R-4s",
                SignalSeverity.ACTION,
                (
                    "Legacy sequential variant: consecutive results crossed opposite "
                    f"warning limits; observed span={abs(z_score - previous):.2f} SD"
                ),
                LEGACY_R4S_VARIANT,
            )

    if "4-1s" in rule_ids:
        last_four = recent_z[-3:] + [z_score]
        if len(last_four) == 4 and (all(z >= 1 for z in last_four) or all(z <= -1 for z in last_four)):
            signal("4-1s", SignalSeverity.WARN, "Four consecutive results exceed fixed 1 SD on one side")

    if "10x" in rule_ids:
        last_ten = recent_z[-9:] + [z_score]
        if len(last_ten) == 10 and (all(z > 0 for z in last_ten) or all(z < 0 for z in last_ten)):
            signal("10x", SignalSeverity.WARN, "Ten consecutive results on the same side of centerline")

    return signals
