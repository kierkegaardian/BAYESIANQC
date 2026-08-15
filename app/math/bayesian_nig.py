from __future__ import annotations

import math
from dataclasses import dataclass

from app.evaluation_models import ResolvedControlLimits
from app.math.student_t import student_t_interval_quantile, student_t_probability_outside_bounds
from app.models import BayesianRisk

INTERVAL_LEVEL = 0.95


@dataclass(frozen=True)
class PosteriorParameters:
    mu: float
    kappa: float
    alpha: float
    beta: float


@dataclass(frozen=True)
class BayesianPolicy:
    risk_threshold_warn: int
    risk_threshold_hold: int
    warn_probability_threshold: float | None
    warn_consecutive: int
    hold_probability_threshold: float | None
    hold_consecutive: int


def update_posterior(state: PosteriorParameters, value: float) -> PosteriorParameters:
    next_kappa = state.kappa + 1
    next_mu = (state.kappa * state.mu + value) / next_kappa
    next_alpha = state.alpha + 0.5
    next_beta = state.beta + 0.5 * state.kappa * ((value - state.mu) ** 2) / next_kappa
    return PosteriorParameters(mu=next_mu, kappa=next_kappa, alpha=next_alpha, beta=next_beta)


def risk_from_posterior(
    state: PosteriorParameters,
    limits: ResolvedControlLimits,
    *,
    warn_streak: int = 0,
    hold_streak: int = 0,
) -> BayesianRisk:
    posterior_sigma = math.sqrt(state.beta / (state.alpha - 1)) if state.alpha > 1 else None
    degrees_of_freedom = 2.0 * state.alpha
    mu_scale = (
        math.sqrt(state.beta / (state.alpha * state.kappa))
        if state.alpha > 0 and state.kappa > 0
        else None
    )
    predictive_sigma = (
        math.sqrt(state.beta * (state.kappa + 1) / (state.alpha * state.kappa))
        if state.alpha > 0 and state.kappa > 0
        else None
    )

    probability_warning = 0.0
    probability_action = 0.0
    if predictive_sigma is not None and predictive_sigma > 0:
        probability_warning = student_t_probability_outside_bounds(
            mean=state.mu,
            scale=predictive_sigma,
            degrees_of_freedom=degrees_of_freedom,
            lower=limits.warning_lower,
            upper=limits.warning_upper,
        )
        probability_action = student_t_probability_outside_bounds(
            mean=state.mu,
            scale=predictive_sigma,
            degrees_of_freedom=degrees_of_freedom,
            lower=limits.action_lower,
            upper=limits.action_upper,
        )

    quantile = student_t_interval_quantile(degrees_of_freedom, INTERVAL_LEVEL)
    credible_interval = (
        (state.mu - quantile * mu_scale, state.mu + quantile * mu_scale)
        if mu_scale is not None and quantile > 0
        else None
    )
    predictive_interval = (
        (state.mu - quantile * predictive_sigma, state.mu + quantile * predictive_sigma)
        if predictive_sigma is not None and quantile > 0
        else None
    )
    return BayesianRisk(
        probability_outside_limits=probability_action,
        probability_outside_warning=probability_warning,
        risk_score=int(min(100, max(0, round(probability_action * 100)))),
        posterior_mean=state.mu,
        posterior_sigma=posterior_sigma,
        predictive_sigma=predictive_sigma,
        credible_interval=credible_interval,
        predictive_interval=predictive_interval,
        warn_streak=warn_streak,
        hold_streak=hold_streak,
    )


def update_policy_streaks(
    *,
    policy: BayesianPolicy,
    previous_warn_streak: int,
    previous_hold_streak: int,
    probability_warning: float,
    probability_action: float,
) -> tuple[int, int]:
    p_warning = max(0.0, min(1.0, probability_warning))
    p_action = max(0.0, min(1.0, probability_action))
    warn_hit = (
        p_warning >= policy.warn_probability_threshold
        if policy.warn_probability_threshold is not None
        else p_action >= policy.risk_threshold_warn / 100.0
    )
    hold_hit = (
        p_action >= policy.hold_probability_threshold
        if policy.hold_probability_threshold is not None
        else p_action >= policy.risk_threshold_hold / 100.0
    )
    warn_streak = previous_warn_streak + 1 if warn_hit else 0
    hold_streak = previous_hold_streak + 1 if hold_hit else 0
    return min(warn_streak, policy.warn_consecutive), min(hold_streak, policy.hold_consecutive)

