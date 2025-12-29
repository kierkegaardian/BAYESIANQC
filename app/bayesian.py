from __future__ import annotations

import math

from sqlmodel import Session, select

from app.db_models import PosteriorState, StreamConfig
from app.models import BayesianRisk
from app.storage import get_active_prior


def _normal_cdf(x: float, mean: float, std: float) -> float:
    if std <= 0:
        return 0.5
    return 0.5 * (1 + math.erf((x - mean) / (std * math.sqrt(2))))


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

    kappa_n = kappa0 + 1
    mu_n = (kappa0 * mu0 + record_value) / kappa_n
    alpha_n = alpha0 + 0.5
    beta_n = beta0 + 0.5 * kappa0 * ((record_value - mu0) ** 2) / kappa_n

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
