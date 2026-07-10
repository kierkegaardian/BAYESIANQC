from __future__ import annotations

from app.db_models import StreamConfig
from app.math import distributions
from app.math.nig import summarize_normal_inverse_gamma
from app.math.nig import update_normal_inverse_gamma as _update_posterior
from app.math.validation import clamp_probability as _clamp01
from app.math.validation import finite_float, positive_finite_float
from app.models import BayesianRisk, BayesianRiskStatus, BayesianRiskUnavailableReason

ENGINE_ID = "nig-student-t-v1"
_probability_inside_bounds = distributions.probability_inside_student_t_bounds
_student_t_cdf = distributions.student_t_cdf
_student_t_interval_quantile = distributions.student_t_interval_quantile
_student_t_ppf = distributions.student_t_ppf


def unavailable_missing_prior() -> BayesianRisk:
    return BayesianRisk(
        status=BayesianRiskStatus.UNAVAILABLE,
        unavailable_reason=BayesianRiskUnavailableReason.MISSING_EFFECTIVE_PRIOR,
    )


def available_probabilities(risk: BayesianRisk) -> tuple[float, float]:
    warning = risk.probability_outside_warning
    action = risk.probability_outside_limits
    if warning is None or action is None:
        raise RuntimeError("available Bayesian risk is missing probabilities")
    return warning, action


def interval_quantile(degrees_of_freedom: float) -> float:
    return _student_t_interval_quantile(degrees_of_freedom)


def update_policy_streaks(
    *,
    config: StreamConfig,
    prev_warn_streak: int,
    prev_hold_streak: int,
    probability_outside_warning: float,
    probability_outside_action: float,
) -> tuple[int, int]:
    p_warning = _clamp01(probability_outside_warning)
    p_action = _clamp01(probability_outside_action)

    warn_threshold = config.bayes_warn_prob_threshold
    warn_consecutive = config.bayes_warn_consecutive or 1
    hold_threshold = config.bayes_hold_prob_threshold
    hold_consecutive = config.bayes_hold_consecutive or 1

    # Preserve the original risk-score thresholds when explicit Bayesian
    # probability thresholds are not configured.
    warn_hit = (
        (p_warning >= warn_threshold)
        if warn_threshold is not None
        else (p_action >= float(config.risk_threshold_warn) / 100.0)
    )
    hold_hit = (
        (p_action >= hold_threshold)
        if hold_threshold is not None
        else (p_action >= float(config.risk_threshold_hold) / 100.0)
    )

    next_warn_streak = (prev_warn_streak + 1) if warn_hit else 0
    next_hold_streak = (prev_hold_streak + 1) if hold_hit else 0
    if warn_consecutive > 0:
        next_warn_streak = min(next_warn_streak, warn_consecutive)
    if hold_consecutive > 0:
        next_hold_streak = min(next_hold_streak, hold_consecutive)
    return next_warn_streak, next_hold_streak


def risk_from_posterior(
    *,
    mu_n: float,
    kappa_n: float,
    alpha_n: float,
    beta_n: float,
    config: StreamConfig,
    warn_streak: int = 0,
    hold_streak: int = 0,
) -> BayesianRisk:
    posterior = summarize_normal_inverse_gamma(mu_n, kappa_n, alpha_n, beta_n)
    target = finite_float("target_value", config.target_value)
    sigma = positive_finite_float("sigma", config.sigma)
    warning_limit_sd = positive_finite_float("warning_limit_sd", config.warning_limit_sd)
    action_limit_sd = positive_finite_float("action_limit_sd", config.action_limit_sd)
    if action_limit_sd < warning_limit_sd:
        raise ValueError("action_limit_sd must be >= warning_limit_sd")

    warn_inside = _probability_inside_bounds(
        mean=mu_n,
        scale=posterior.predictive_scale,
        degrees_of_freedom=posterior.degrees_of_freedom,
        lower=target - warning_limit_sd * sigma,
        upper=target + warning_limit_sd * sigma,
    )
    action_inside = _probability_inside_bounds(
        mean=mu_n,
        scale=posterior.predictive_scale,
        degrees_of_freedom=posterior.degrees_of_freedom,
        lower=target - action_limit_sd * sigma,
        upper=target + action_limit_sd * sigma,
    )
    probability_outside_warning = _clamp01(1.0 - warn_inside)
    probability_outside_action = _clamp01(1.0 - action_inside)
    risk_score = int(min(100, max(0, round(probability_outside_action * 100))))

    q = interval_quantile(posterior.degrees_of_freedom)
    credible_interval = (
        mu_n - q * posterior.mean_scale,
        mu_n + q * posterior.mean_scale,
    )
    predictive_interval = (
        mu_n - q * posterior.predictive_scale,
        mu_n + q * posterior.predictive_scale,
    )

    return BayesianRisk(
        engine_id=ENGINE_ID,
        probability_outside_limits=probability_outside_action,
        probability_outside_warning=probability_outside_warning,
        risk_score=risk_score,
        posterior_mean=mu_n,
        posterior_sigma=posterior.posterior_sigma,
        predictive_sigma=posterior.predictive_scale,
        credible_interval=credible_interval,
        predictive_interval=predictive_interval,
        warn_streak=warn_streak,
        hold_streak=hold_streak,
    )


def update_posterior_and_infer_risk(
    *,
    mu0: float,
    kappa0: float,
    alpha0: float,
    beta0: float,
    record_value: float,
    config: StreamConfig,
    warn_streak: int = 0,
    hold_streak: int = 0,
) -> tuple[BayesianRisk, tuple[float, float, float, float]]:
    posterior = _update_posterior(mu0, kappa0, alpha0, beta0, record_value)
    base_risk = risk_from_posterior(
        mu_n=posterior[0],
        kappa_n=posterior[1],
        alpha_n=posterior[2],
        beta_n=posterior[3],
        config=config,
    )
    warning_probability, action_probability = available_probabilities(base_risk)
    next_streaks = update_policy_streaks(
        config=config,
        prev_warn_streak=warn_streak,
        prev_hold_streak=hold_streak,
        probability_outside_warning=warning_probability,
        probability_outside_action=action_probability,
    )
    risk = base_risk.model_copy(
        update={"warn_streak": next_streaks[0], "hold_streak": next_streaks[1]}
    )
    return risk, posterior
