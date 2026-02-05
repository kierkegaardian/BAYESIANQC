from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from sqlmodel import Session, col, select

from app.db_models import PosteriorState, PriorConfig, QCRecord, StreamConfig
from app.models import BayesianRisk
from app.storage import get_active_prior

_NORMAL_APPROX_DF_THRESHOLD = 30.0


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


def _risk_from_posterior(
    *,
    mu_n: float,
    kappa_n: float,
    alpha_n: float,
    beta_n: float,
    config: StreamConfig,
) -> BayesianRisk:
    posterior_sigma = math.sqrt(beta_n / (alpha_n - 1)) if alpha_n > 1 else None
    predictive_sigma = (
        math.sqrt(beta_n * (kappa_n + 1) / (alpha_n * kappa_n)) if (alpha_n > 0 and kappa_n > 0) else None
    )

    if predictive_sigma and predictive_sigma > 0:
        lower = config.target_value - config.action_limit_sd * config.sigma
        upper = config.target_value + config.action_limit_sd * config.sigma
        df = 2.0 * alpha_n
        if df >= _NORMAL_APPROX_DF_THRESHOLD:
            prob_inside = _normal_cdf(upper, mu_n, predictive_sigma) - _normal_cdf(lower, mu_n, predictive_sigma)
        else:
            t_upper = (upper - mu_n) / predictive_sigma
            t_lower = (lower - mu_n) / predictive_sigma
            prob_inside = _student_t_cdf(t_upper, df) - _student_t_cdf(t_lower, df)
        probability_outside_limits = max(0.0, min(1.0, 1 - prob_inside))
    else:
        probability_outside_limits = 0.0

    risk_score = int(min(100, max(0, round(probability_outside_limits * 100))))
    credible_interval = None
    if posterior_sigma and kappa_n > 0:
        stderr = posterior_sigma / math.sqrt(kappa_n)
        credible_interval = (mu_n - 1.96 * stderr, mu_n + 1.96 * stderr)

    return BayesianRisk(
        probability_outside_limits=probability_outside_limits,
        risk_score=risk_score,
        posterior_mean=mu_n,
        posterior_sigma=posterior_sigma,
        predictive_sigma=predictive_sigma,
        credible_interval=credible_interval,
    )


def update_posterior_and_infer_risk(
    *,
    mu0: float,
    kappa0: float,
    alpha0: float,
    beta0: float,
    record_value: float,
    config: StreamConfig,
) -> tuple[BayesianRisk, tuple[float, float, float, float]]:
    mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
        mu0,
        kappa0,
        alpha0,
        beta0,
        record_value,
    )
    return (
        _risk_from_posterior(
            mu_n=mu_n,
            kappa_n=kappa_n,
            alpha_n=alpha_n,
            beta_n=beta_n,
            config=config,
        ),
        (mu_n, kappa_n, alpha_n, beta_n),
    )


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

    current_prior = _active_prior(priors, records[0].timestamp)
    if current_prior is None:
        return BayesianRisk(probability_outside_limits=0.0, risk_score=0)
    if current_prior.id is None:
        raise RuntimeError("Prior config missing id")

    mu_n, kappa_n, alpha_n, beta_n = (
        current_prior.mu0,
        current_prior.kappa0,
        current_prior.alpha0,
        current_prior.beta0,
    )
    for record in records:
        record_prior = _active_prior(priors, record.timestamp)
        if record_prior is None:
            return BayesianRisk(probability_outside_limits=0.0, risk_score=0)
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
        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
            mu_n, kappa_n, alpha_n, beta_n, record.result_value
        )

    return _risk_from_posterior(
        mu_n=mu_n,
        kappa_n=kappa_n,
        alpha_n=alpha_n,
        beta_n=beta_n,
        config=config,
    )


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

    current_prior = _active_prior(priors, records[0].timestamp)
    if current_prior is None:
        if state:
            session.delete(state)
            session.commit()
        return None
    if current_prior.id is None:
        raise RuntimeError("Prior config missing id")

    mu_n, kappa_n, alpha_n, beta_n = (
        current_prior.mu0,
        current_prior.kappa0,
        current_prior.alpha0,
        current_prior.beta0,
    )
    n_obs = 0
    for record in records:
        record_prior = _active_prior(priors, record.timestamp)
        if record_prior is None:
            if state:
                session.delete(state)
                session.commit()
            return None
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
        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
            mu_n, kappa_n, alpha_n, beta_n, record.result_value
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

    mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
        state.mu_n, state.kappa_n, state.alpha_n, state.beta_n, record_value
    )
    risk = _risk_from_posterior(
        mu_n=mu_n,
        kappa_n=kappa_n,
        alpha_n=alpha_n,
        beta_n=beta_n,
        config=config,
    )

    state.mu_n = mu_n
    state.kappa_n = kappa_n
    state.alpha_n = alpha_n
    state.beta_n = beta_n
    state.n_obs += 1
    state.updated_at = record_timestamp
    state.prior_id = prior.id
    session.add(state)
    session.commit()
    return risk
