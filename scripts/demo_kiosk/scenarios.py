from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoScenario:
    scenario_id: str
    label: str
    offsets: tuple[float, ...]
    marker_point: int
    event_note: str
    weak_prior: bool = False


STABLE = (0.0, 0.1, -0.1, 0.2, -0.2, 0.1, 0.0, -0.1, 0.2, 0.1, -0.2, 0.0, 0.1, -0.1, 0.0, 0.2, -0.2, 0.1, 0.0, -0.1, 0.1, 0.0, -0.2, 0.2, 0.0)
DRIFT_HIGH = (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5, 1.7, 1.9, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4)
DRIFT_LOW = tuple(-value for value in DRIFT_HIGH)
SPIKE_HIGH = (0.0, 0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.2, 3.4, 0.3, 0.0, -0.1, 0.1, 0.0, -0.2, 0.2, 0.1, 0.0, -0.1, 0.1, 0.0, -0.2, 0.1, 0.0, 0.2)
SPIKE_LOW = tuple(-value for value in SPIKE_HIGH)
STEP_HIGH = (0.0, 0.1, -0.1, 0.0, 0.2, 0.1, -0.1, 0.0, 0.1, -0.1, 0.0, 0.2, 0.1, 0.0, -0.1, 1.2, 1.4, 1.5, 1.4, 1.6, 1.5, 1.4, 1.6, 1.5, 1.4)
STEP_LOW = tuple(-value for value in STEP_HIGH)
MAINTENANCE_RECOVERY = (0.0, 0.2, 0.4, 0.7, 1.0, 1.4, 1.8, 2.1, 2.4, 2.8, 3.2, 2.7, 2.1, 1.2, 0.5, 0.2, 0.0, -0.1, 0.1, 0.0, -0.2, 0.1, 0.0, 0.2, -0.1)
LOW_CONFIDENCE = (0.0, 1.4, -1.3, 1.5, -1.4, 1.6, -1.5, 1.7, -1.6, 1.8, -1.7, 1.9, -1.8, 1.7, -1.6, 1.8, -1.7, 1.6, -1.5, 1.4, -1.3, 1.2, -1.1, 0.8, -0.7)
ALTERNATING_VARIABILITY = (0.0, 0.1, 2.2, -2.2, 2.1, -2.1, 1.8, -1.7, 1.5, -1.4, 1.2, -1.1, 0.8, -0.7, 0.4, -0.3, 0.2, -0.2, 0.1, 0.0, -0.1, 0.1, 0.0, -0.1, 0.0)
RETRY_CLUSTER = (0.0, 0.0, 0.1, 0.1, 0.1, -0.1, -0.1, 0.0, 0.2, 0.2, 0.1, 0.0, 0.0, -0.1, 0.0, 0.3, 0.2, 0.3, 0.2, 0.1, 0.2, 0.1, 0.0, 0.1, 0.0)

SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario("high_action_outlier", "single high action outlier", SPIKE_HIGH, 9, "operator rerun after high action point"),
    DemoScenario("stable_baseline", "stable baseline", STABLE, 5, "stable baseline review"),
    DemoScenario("low_confidence", "high scatter with low Bayesian confidence", LOW_CONFIDENCE, 12, "precision review for high scatter", True),
    DemoScenario("step_shift_lot_high", "upward step after lot change", STEP_HIGH, 19, "lot-to-lot high bias review"),
    DemoScenario("slow_drift_high", "slow high drift", DRIFT_HIGH, 21, "drift investigation opened"),
    DemoScenario("low_action_outlier", "single low action outlier", SPIKE_LOW, 9, "operator rerun after low action point"),
    DemoScenario("maintenance_recovery", "maintenance recovery", MAINTENANCE_RECOVERY, 11, "maintenance restored baseline"),
    DemoScenario("step_shift_lot_low", "downward step after lot change", STEP_LOW, 19, "lot-to-lot low bias review"),
    DemoScenario("slow_drift_low", "slow low drift", DRIFT_LOW, 21, "low drift investigation opened"),
    DemoScenario(
        "alternating_variability",
        "alternating high/low variability",
        ALTERNATING_VARIABILITY,
        4,
        "alternating variability review",
    ),
    DemoScenario("duplicate_retry_cluster", "duplicate retry cluster", RETRY_CLUSTER, 6, "duplicate retry cluster reviewed"),
    DemoScenario("stable_lot_b", "stable second-lot baseline", STABLE, 18, "stable lot transition review"),
)


def scenario_for_stream(index: int) -> DemoScenario:
    return SCENARIOS[(index - 1) % len(SCENARIOS)]
