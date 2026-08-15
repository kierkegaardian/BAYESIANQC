from __future__ import annotations

from dataclasses import dataclass

from app.domain import Disposition, SignalSeverity
from app.evaluation_models import ResolvedControlLimits
from app.math.bayesian_nig import (
    BayesianPolicy,
    PosteriorParameters,
    risk_from_posterior,
    update_policy_streaks,
    update_posterior,
)
from app.math.rules import evaluate_rule_set
from app.models import BayesianRisk, FrequentistSignal

EVALUATION_ENGINE_VERSION = "qc-evaluation-v2"
FREQUENTIST_METHOD = "single-level-westgard-like-v2"
BAYESIAN_METHOD = "nig-student-t-v1"
RISK_SEMANTICS = "post-update-next-observation-v1"


@dataclass(frozen=True)
class EvaluationPointInput:
    value: float
    include_in_stats: bool
    recent_values: tuple[float, ...]
    rule_ids: tuple[str, ...]
    limits: ResolvedControlLimits
    posterior: PosteriorParameters | None
    policy: BayesianPolicy
    warn_streak: int = 0
    hold_streak: int = 0


@dataclass(frozen=True)
class EvaluationPointOutput:
    signals: tuple[FrequentistSignal, ...]
    risk: BayesianRisk | None
    disposition: Disposition
    posterior: PosteriorParameters | None
    warn_streak: int
    hold_streak: int


def determine_disposition(
    signals: tuple[FrequentistSignal, ...],
    risk: BayesianRisk | None,
    policy: BayesianPolicy,
) -> Disposition:
    if any(signal.severity == SignalSeverity.ACTION for signal in signals):
        return Disposition.REJECT
    if risk is not None and risk.hold_streak >= policy.hold_consecutive:
        return Disposition.HOLD_FOR_REVIEW
    if signals or (risk is not None and risk.warn_streak >= policy.warn_consecutive):
        return Disposition.MONITOR
    return Disposition.ACCEPT


def evaluate_point(point: EvaluationPointInput) -> EvaluationPointOutput:
    signals = tuple(
        evaluate_rule_set(
            record_value=point.value,
            recent_values=point.recent_values,
            limits=point.limits,
            rule_ids=point.rule_ids,
        )
    )
    posterior = point.posterior
    risk: BayesianRisk | None = None
    warn_streak = point.warn_streak
    hold_streak = point.hold_streak
    if point.include_in_stats and posterior is not None:
        posterior = update_posterior(posterior, point.value)
        base_risk = risk_from_posterior(posterior, point.limits)
        warn_streak, hold_streak = update_policy_streaks(
            policy=point.policy,
            previous_warn_streak=point.warn_streak,
            previous_hold_streak=point.hold_streak,
            probability_warning=base_risk.probability_outside_warning,
            probability_action=base_risk.probability_outside_limits,
        )
        risk = base_risk.model_copy(update={"warn_streak": warn_streak, "hold_streak": hold_streak})
    elif point.include_in_stats:
        risk = BayesianRisk(probability_outside_limits=0.0, risk_score=0)

    disposition = determine_disposition(signals, risk, point.policy)
    return EvaluationPointOutput(
        signals=signals,
        risk=risk,
        disposition=disposition,
        posterior=posterior,
        warn_streak=warn_streak,
        hold_streak=hold_streak,
    )
