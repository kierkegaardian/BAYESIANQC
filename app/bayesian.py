from __future__ import annotations

import math
from datetime import datetime
from functools import lru_cache
from typing import Optional

from sqlmodel import Session, col, select

from app.db_models import PosteriorState, PriorConfig, QCRecord, StreamConfig
from app.models import BayesianRisk
from app.storage import get_active_prior

_NORMAL_APPROX_DF_THRESHOLD = 30.0
_DEFAULT_INTERVAL_LEVEL = 0.95
# Normal(0,1) quantile for 0.975 (two-sided 95% interval).
_DEFAULT_NORMAL_Q_975 = 1.959963984540054


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normal_cdf(x: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.5
    return 0.5 * (1 + math.erf((x - mean) / (std * math.sqrt(2))))


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    max_iterations = 200
    epsilon = 3e-12
    fpmin = 1e-300

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0

    c = 1.0
    d = 1.0 - (qab * x / qap)
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d

    for m in range(1, max_iterations + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return h


def _regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    log_bt = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    bt = math.exp(log_bt)

    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _beta_continued_fraction(a, b, x) / a
    return 1.0 - bt * _beta_continued_fraction(b, a, 1.0 - x) / b


def _student_t_cdf(t_value: float, degrees_of_freedom: float) -> float:
    if degrees_of_freedom <= 0:
        return 0.5

    x = degrees_of_freedom / (degrees_of_freedom + t_value * t_value)
    a = degrees_of_freedom / 2.0
    b = 0.5
    ib = _regularized_incomplete_beta(a, b, x)
    if t_value >= 0:
        return 1.0 - 0.5 * ib
    return 0.5 * ib


def _student_t_ppf(probability: float, degrees_of_freedom: float) -> float:
    """
    Inverse CDF (percent point function) for Student-t.

    We only need a handful of quantiles for chart intervals, so a robust bisection
    on the existing CDF is sufficient (no SciPy dependency).
    """
    if degrees_of_freedom <= 0:
        return 0.0
    p = _clamp01(probability)
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -_student_t_ppf(1.0 - p, degrees_of_freedom)

    # Find an upper bracket such that CDF(hi) >= p.
    hi = 1.0
    while _student_t_cdf(hi, degrees_of_freedom) < p:
        hi *= 2.0
        if hi > 1e6:
            break
    lo = 0.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _student_t_cdf(mid, degrees_of_freedom) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


@lru_cache(maxsize=256)
def _student_t_interval_quantile(df_key: float) -> float:
    alpha = (1.0 + _DEFAULT_INTERVAL_LEVEL) / 2.0
    return _student_t_ppf(alpha, df_key)


def _interval_quantile(degrees_of_freedom: float) -> float:
    if degrees_of_freedom >= _NORMAL_APPROX_DF_THRESHOLD:
        return _DEFAULT_NORMAL_Q_975
    df_key = round(degrees_of_freedom, 6)
    if df_key <= 0:
        return 0.0
    return _student_t_interval_quantile(df_key)


def _update_posterior(
    mu0: float,
    kappa0: float,
    alpha0: float,
    beta0: float,
    record_value: float,
) -> tuple[float, float, float, float]:
    kappa_n = kappa0 + 1
    mu_n = (kappa0 * mu0 + record_value) / kappa_n
    alpha_n = alpha0 + 0.5
    beta_n = beta0 + 0.5 * kappa0 * ((record_value - mu0) ** 2) / kappa_n
    return mu_n, kappa_n, alpha_n, beta_n


def _probability_inside_bounds(
    *,
    mean: float,
    scale: float,
    degrees_of_freedom: float,
    lower: float,
    upper: float,
) -> float:
    if scale <= 0:
        return 0.0
    if degrees_of_freedom >= _NORMAL_APPROX_DF_THRESHOLD:
        return _normal_cdf(upper, mean, scale) - _normal_cdf(lower, mean, scale)
    t_upper = (upper - mean) / scale
    t_lower = (lower - mean) / scale
    return _student_t_cdf(t_upper, degrees_of_freedom) - _student_t_cdf(t_lower, degrees_of_freedom)


def _update_policy_streaks(
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

    # Backwards-compatible fallback to the original risk_score thresholds when
    # explicit Bayesian probability thresholds are not configured.
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

    # If a stream is configured with an N-of-N policy, cap streak counts to
    # avoid unbounded growth (useful for UI display and storage).
    if warn_consecutive > 0:
        next_warn_streak = min(next_warn_streak, warn_consecutive)
    if hold_consecutive > 0:
        next_hold_streak = min(next_hold_streak, hold_consecutive)
    return next_warn_streak, next_hold_streak


def _risk_from_posterior(
    *,
    mu_n: float,
    kappa_n: float,
    alpha_n: float,
    beta_n: float,
    config: StreamConfig,
    warn_streak: int = 0,
    hold_streak: int = 0,
) -> BayesianRisk:
    posterior_sigma = math.sqrt(beta_n / (alpha_n - 1)) if alpha_n > 1 else None
    df = 2.0 * alpha_n

    mu_scale = math.sqrt(beta_n / (alpha_n * kappa_n)) if (alpha_n > 0 and kappa_n > 0) else None
    predictive_sigma = (
        math.sqrt(beta_n * (kappa_n + 1) / (alpha_n * kappa_n)) if (alpha_n > 0 and kappa_n > 0) else None
    )

    probability_outside_action = 0.0
    probability_outside_warning = 0.0
    if predictive_sigma and predictive_sigma > 0:
        warn_lower = config.target_value - config.warning_limit_sd * config.sigma
        warn_upper = config.target_value + config.warning_limit_sd * config.sigma
        action_lower = config.target_value - config.action_limit_sd * config.sigma
        action_upper = config.target_value + config.action_limit_sd * config.sigma

        warn_inside = _probability_inside_bounds(
            mean=mu_n,
            scale=predictive_sigma,
            degrees_of_freedom=df,
            lower=warn_lower,
            upper=warn_upper,
        )
        action_inside = _probability_inside_bounds(
            mean=mu_n,
            scale=predictive_sigma,
            degrees_of_freedom=df,
            lower=action_lower,
            upper=action_upper,
        )
        probability_outside_warning = _clamp01(1.0 - warn_inside)
        probability_outside_action = _clamp01(1.0 - action_inside)

    risk_score = int(min(100, max(0, round(probability_outside_action * 100))))

    q = _interval_quantile(df)

    credible_interval = None
    if mu_scale and q > 0:
        credible_interval = (mu_n - q * mu_scale, mu_n + q * mu_scale)

    predictive_interval = None
    if predictive_sigma and q > 0:
        predictive_interval = (mu_n - q * predictive_sigma, mu_n + q * predictive_sigma)

    return BayesianRisk(
        probability_outside_limits=probability_outside_action,
        probability_outside_warning=probability_outside_warning,
        risk_score=risk_score,
        posterior_mean=mu_n,
        posterior_sigma=posterior_sigma,
        predictive_sigma=predictive_sigma,
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
    mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
        mu0,
        kappa0,
        alpha0,
        beta0,
        record_value,
    )
    base_risk = _risk_from_posterior(
        mu_n=mu_n,
        kappa_n=kappa_n,
        alpha_n=alpha_n,
        beta_n=beta_n,
        config=config,
    )
    next_warn_streak, next_hold_streak = _update_policy_streaks(
        config=config,
        prev_warn_streak=warn_streak,
        prev_hold_streak=hold_streak,
        probability_outside_warning=base_risk.probability_outside_warning,
        probability_outside_action=base_risk.probability_outside_limits,
    )
    risk = base_risk.model_copy(update={"warn_streak": next_warn_streak, "hold_streak": next_hold_streak})
    return (risk, (mu_n, kappa_n, alpha_n, beta_n))


def _list_priors(session: Session, stream_id: str) -> list[PriorConfig]:
    return list(
        session.exec(
            select(PriorConfig)
            .where(PriorConfig.stream_id == stream_id)
            .order_by(col(PriorConfig.effective_from).asc(), col(PriorConfig.version).asc())
        ).all()
    )


def _active_prior(priors: list[PriorConfig], at_time: datetime) -> Optional[PriorConfig]:
    if not priors:
        return None
    active: Optional[PriorConfig] = None
    for prior in priors:
        if prior.effective_from <= at_time:
            active = prior
        else:
            break
    return active or priors[0]


def infer_risk_as_of(
    session: Session,
    stream_id: str,
    record_timestamp: datetime,
    config: StreamConfig,
) -> BayesianRisk:
    priors = _list_priors(session, stream_id)
    if not priors:
        return BayesianRisk(probability_outside_limits=0.0, risk_score=0)

    records = session.exec(
        select(QCRecord)
        .where(
            QCRecord.stream_id == stream_id,
            QCRecord.include_in_stats == True,
            QCRecord.timestamp <= record_timestamp,
        )
        .order_by(col(QCRecord.timestamp).asc())
    ).all()
    if not records:
        return BayesianRisk(probability_outside_limits=0.0, risk_score=0)

    configs = list(
        session.exec(
            select(StreamConfig)
            .where(StreamConfig.stream_id == stream_id)
            .order_by(col(StreamConfig.effective_from).asc(), col(StreamConfig.version).asc())
        ).all()
    )

    prior_idx = 0
    while prior_idx + 1 < len(priors) and priors[prior_idx + 1].effective_from <= records[0].timestamp:
        prior_idx += 1
    current_prior = priors[prior_idx]
    if current_prior.id is None:
        raise RuntimeError("Prior config missing id")

    config_idx = 0
    if configs:
        while config_idx + 1 < len(configs) and configs[config_idx + 1].effective_from <= records[0].timestamp:
            config_idx += 1

    mu_n, kappa_n, alpha_n, beta_n = (
        current_prior.mu0,
        current_prior.kappa0,
        current_prior.alpha0,
        current_prior.beta0,
    )
    warn_streak = 0
    hold_streak = 0
    current_config = configs[config_idx] if configs else config
    current_config_id = current_config.id

    last_risk: Optional[BayesianRisk] = None
    for record in records:
        while prior_idx + 1 < len(priors) and priors[prior_idx + 1].effective_from <= record.timestamp:
            prior_idx += 1
        record_prior = priors[prior_idx]
        if record_prior.id is None:
            raise RuntimeError("Prior config missing id")
        if record_prior.id != current_prior.id:
            current_prior = record_prior
            mu_n, kappa_n, alpha_n, beta_n = (
                current_prior.mu0,
                current_prior.kappa0,
                current_prior.alpha0,
                current_prior.beta0,
            )
            warn_streak = 0
            hold_streak = 0

        if configs:
            while config_idx + 1 < len(configs) and configs[config_idx + 1].effective_from <= record.timestamp:
                config_idx += 1
            next_config = configs[config_idx]
            if next_config.id != current_config_id:
                warn_streak = 0
                hold_streak = 0
                current_config_id = next_config.id
            current_config = next_config

        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
            mu_n, kappa_n, alpha_n, beta_n, record.result_value
        )

        base_risk = _risk_from_posterior(
            mu_n=mu_n,
            kappa_n=kappa_n,
            alpha_n=alpha_n,
            beta_n=beta_n,
            config=current_config,
        )
        warn_streak, hold_streak = _update_policy_streaks(
            config=current_config,
            prev_warn_streak=warn_streak,
            prev_hold_streak=hold_streak,
            probability_outside_warning=base_risk.probability_outside_warning,
            probability_outside_action=base_risk.probability_outside_limits,
        )
        last_risk = base_risk.model_copy(update={"warn_streak": warn_streak, "hold_streak": hold_streak})

    return last_risk or BayesianRisk(probability_outside_limits=0.0, risk_score=0)


def rebuild_posterior_state(session: Session, stream_id: str) -> Optional[PosteriorState]:
    records = session.exec(
        select(QCRecord)
        .where(QCRecord.stream_id == stream_id, QCRecord.include_in_stats == True)
        .order_by(col(QCRecord.timestamp).asc())
    ).all()
    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if not records:
        if state:
            session.delete(state)
            session.commit()
        return None

    priors = _list_priors(session, stream_id)
    if not priors:
        if state:
            session.delete(state)
            session.commit()
        return None

    configs = list(
        session.exec(
            select(StreamConfig)
            .where(StreamConfig.stream_id == stream_id)
            .order_by(col(StreamConfig.effective_from).asc(), col(StreamConfig.version).asc())
        ).all()
    )

    prior_idx = 0
    while prior_idx + 1 < len(priors) and priors[prior_idx + 1].effective_from <= records[0].timestamp:
        prior_idx += 1
    current_prior = priors[prior_idx]
    if current_prior.id is None:
        raise RuntimeError("Prior config missing id")

    config_idx = 0
    if configs:
        while config_idx + 1 < len(configs) and configs[config_idx + 1].effective_from <= records[0].timestamp:
            config_idx += 1
    current_config = configs[config_idx] if configs else None
    current_config_id = current_config.id if current_config else None

    mu_n, kappa_n, alpha_n, beta_n = (
        current_prior.mu0,
        current_prior.kappa0,
        current_prior.alpha0,
        current_prior.beta0,
    )
    n_obs = 0
    warn_streak = 0
    hold_streak = 0
    for record in records:
        while prior_idx + 1 < len(priors) and priors[prior_idx + 1].effective_from <= record.timestamp:
            prior_idx += 1
        record_prior = priors[prior_idx]
        if record_prior.id is None:
            raise RuntimeError("Prior config missing id")
        if record_prior.id != current_prior.id:
            current_prior = record_prior
            mu_n, kappa_n, alpha_n, beta_n = (
                current_prior.mu0,
                current_prior.kappa0,
                current_prior.alpha0,
                current_prior.beta0,
            )
            n_obs = 0
            warn_streak = 0
            hold_streak = 0

        if configs:
            while config_idx + 1 < len(configs) and configs[config_idx + 1].effective_from <= record.timestamp:
                config_idx += 1
            next_config = configs[config_idx]
            if next_config.id != current_config_id:
                warn_streak = 0
                hold_streak = 0
                current_config_id = next_config.id
            current_config = next_config

        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
            mu_n, kappa_n, alpha_n, beta_n, record.result_value
        )

        if current_config is not None:
            base_risk = _risk_from_posterior(
                mu_n=mu_n,
                kappa_n=kappa_n,
                alpha_n=alpha_n,
                beta_n=beta_n,
                config=current_config,
            )
            warn_streak, hold_streak = _update_policy_streaks(
                config=current_config,
                prev_warn_streak=warn_streak,
                prev_hold_streak=hold_streak,
                probability_outside_warning=base_risk.probability_outside_warning,
                probability_outside_action=base_risk.probability_outside_limits,
            )
        n_obs += 1

    if state:
        state.mu_n = mu_n
        state.kappa_n = kappa_n
        state.alpha_n = alpha_n
        state.beta_n = beta_n
        state.n_obs = n_obs
        state.updated_at = records[-1].timestamp
        state.prior_id = current_prior.id
        state.config_id = current_config_id
        state.warn_streak = warn_streak
        state.hold_streak = hold_streak
        session.add(state)
    else:
        state = PosteriorState(
            stream_id=stream_id,
            mu_n=mu_n,
            kappa_n=kappa_n,
            alpha_n=alpha_n,
            beta_n=beta_n,
            n_obs=n_obs,
            updated_at=records[-1].timestamp,
            prior_id=current_prior.id,
            config_id=current_config_id,
            warn_streak=warn_streak,
            hold_streak=hold_streak,
        )
        session.add(state)
    session.commit()
    return state


def infer_risk(
    session: Session,
    record_value: float,
    record_timestamp: datetime,
    stream_id: str,
    config: StreamConfig,
) -> BayesianRisk:
    prior = get_active_prior(session, stream_id, record_timestamp)
    if prior is None:
        return BayesianRisk(probability_outside_limits=0.0, risk_score=0)
    if prior.id is None:
        raise RuntimeError("Prior config missing id")

    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if not state or (state.updated_at > record_timestamp) or (state.prior_id != prior.id):
        risk = infer_risk_as_of(session, stream_id, record_timestamp, config)
        rebuild_posterior_state(session, stream_id)
        return risk

    config_id = config.id
    prev_warn_streak = state.warn_streak
    prev_hold_streak = state.hold_streak
    if config_id is not None and state.config_id != config_id:
        prev_warn_streak = 0
        prev_hold_streak = 0

    mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
        state.mu_n, state.kappa_n, state.alpha_n, state.beta_n, record_value
    )
    base_risk = _risk_from_posterior(
        mu_n=mu_n,
        kappa_n=kappa_n,
        alpha_n=alpha_n,
        beta_n=beta_n,
        config=config,
    )
    warn_streak, hold_streak = _update_policy_streaks(
        config=config,
        prev_warn_streak=prev_warn_streak,
        prev_hold_streak=prev_hold_streak,
        probability_outside_warning=base_risk.probability_outside_warning,
        probability_outside_action=base_risk.probability_outside_limits,
    )
    risk = base_risk.model_copy(update={"warn_streak": warn_streak, "hold_streak": hold_streak})

    state.mu_n = mu_n
    state.kappa_n = kappa_n
    state.alpha_n = alpha_n
    state.beta_n = beta_n
    state.n_obs += 1
    state.updated_at = record_timestamp
    state.prior_id = prior.id
    state.config_id = config_id
    state.warn_streak = warn_streak
    state.hold_streak = hold_streak
    session.add(state)
    session.commit()
    return risk
