from __future__ import annotations

import math
from typing import Optional

from sqlmodel import Session, select

from app.db_models import PosteriorState, QCRecord, StreamConfig
from app.models import BayesianRisk
from app.storage import get_active_prior


def _normal_cdf(x: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.5
    return 0.5 * (1 + math.erf((x - mean) / (std * math.sqrt(2))))


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


def rebuild_posterior_state(session: Session, stream_id: str) -> Optional[PosteriorState]:
    records = session.exec(
        select(QCRecord)
        .where(QCRecord.stream_id == stream_id, QCRecord.include_in_stats == True)
        .order_by(QCRecord.timestamp.asc())
    ).all()
    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if not records:
        if state:
            session.delete(state)
            session.commit()
        return None

    prior = get_active_prior(session, stream_id, records[0].timestamp)
    if prior is None:
        if state:
            session.delete(state)
            session.commit()
        return None

    mu_n, kappa_n, alpha_n, beta_n = prior.mu0, prior.kappa0, prior.alpha0, prior.beta0
    for record in records:
        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
            mu_n, kappa_n, alpha_n, beta_n, record.result_value
        )

    if state:
        state.mu_n = mu_n
        state.kappa_n = kappa_n
        state.alpha_n = alpha_n
        state.beta_n = beta_n
        state.n_obs = len(records)
        state.updated_at = records[-1].timestamp
        session.add(state)
    else:
        session.add(
            PosteriorState(
                stream_id=stream_id,
                mu_n=mu_n,
                kappa_n=kappa_n,
                alpha_n=alpha_n,
                beta_n=beta_n,
                n_obs=len(records),
                updated_at=records[-1].timestamp,
            )
        )
    session.commit()
    return state


def infer_risk(
    session: Session,
    record_value: float,
    record_timestamp,
    stream_id: str,
    config: StreamConfig,
) -> BayesianRisk:
    prior = get_active_prior(session, stream_id, record_timestamp)
    if prior is None:
        return BayesianRisk(probability_outside_limits=0.0, risk_score=0)

    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if state:
        mu0, kappa0, alpha0, beta0 = state.mu_n, state.kappa_n, state.alpha_n, state.beta_n
    else:
        mu0, kappa0, alpha0, beta0 = prior.mu0, prior.kappa0, prior.alpha0, prior.beta0

    mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
        mu0, kappa0, alpha0, beta0, record_value
    )

    posterior_sigma = math.sqrt(beta_n / (alpha_n - 1)) if alpha_n > 1 else None
    predictive_sigma = math.sqrt(beta_n * (kappa_n + 1) / (alpha_n * kappa_n)) if alpha_n > 0 else None

    if predictive_sigma and predictive_sigma > 0:
        lower = config.target_value - config.action_limit_sd * config.sigma
        upper = config.target_value + config.action_limit_sd * config.sigma
        prob_inside = _normal_cdf(upper, mu_n, predictive_sigma) - _normal_cdf(lower, mu_n, predictive_sigma)
        probability_outside_limits = max(0.0, min(1.0, 1 - prob_inside))
    else:
        probability_outside_limits = 0.0

    risk_score = int(min(100, max(0, round(probability_outside_limits * 100))))
    credible_interval = None
    if posterior_sigma and kappa_n > 0:
        stderr = posterior_sigma / math.sqrt(kappa_n)
        credible_interval = (mu_n - 1.96 * stderr, mu_n + 1.96 * stderr)

    if state:
        state.mu_n = mu_n
        state.kappa_n = kappa_n
        state.alpha_n = alpha_n
        state.beta_n = beta_n
        state.n_obs += 1
        state.updated_at = record_timestamp
        session.add(state)
    else:
        session.add(
            PosteriorState(
                stream_id=stream_id,
                mu_n=mu_n,
                kappa_n=kappa_n,
                alpha_n=alpha_n,
                beta_n=beta_n,
                n_obs=1,
                updated_at=record_timestamp,
            )
        )
    session.commit()

    return BayesianRisk(
        probability_outside_limits=probability_outside_limits,
        risk_score=risk_score,
        posterior_mean=mu_n,
        posterior_sigma=posterior_sigma,
        predictive_sigma=predictive_sigma,
        credible_interval=credible_interval,
    )
