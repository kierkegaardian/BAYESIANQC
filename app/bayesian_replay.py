from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.bayesian_history import (
    active_prior,
    included_records,
    list_priors,
    list_stream_configs,
    records_after_first_prior,
)
from app.bayesian_risk import (
    available_probabilities,
    risk_from_posterior,
    unavailable_missing_prior,
    update_policy_streaks,
)
from app.db_models import StreamConfig
from app.math.nig import update_normal_inverse_gamma as _update_posterior
from app.models import BayesianRisk
from app.timeutils import as_utc


def infer_risk_as_of(
    session: Session,
    stream_id: str,
    record_timestamp: datetime,
    config: StreamConfig,
) -> BayesianRisk:
    priors = list_priors(session, stream_id)
    effective_prior = active_prior(priors, record_timestamp)
    if effective_prior is None:
        return unavailable_missing_prior()

    records = included_records(session, stream_id, through=record_timestamp)
    records = records_after_first_prior(records, priors)
    if not records:
        return risk_from_posterior(
            mu_n=effective_prior.mu0,
            kappa_n=effective_prior.kappa0,
            alpha_n=effective_prior.alpha0,
            beta_n=effective_prior.beta0,
            config=config,
        )

    configs = list_stream_configs(session, stream_id)
    first_ts = as_utc(records[0].timestamp)
    prior_idx = 0
    while (
        prior_idx + 1 < len(priors)
        and as_utc(priors[prior_idx + 1].effective_from) <= first_ts
    ):
        prior_idx += 1
    current_prior = priors[prior_idx]
    if current_prior.id is None:
        raise RuntimeError("Prior config missing id")

    config_idx = 0
    if configs:
        while (
            config_idx + 1 < len(configs)
            and as_utc(configs[config_idx + 1].effective_from) <= first_ts
        ):
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
        record_ts = as_utc(record.timestamp)
        while (
            prior_idx + 1 < len(priors)
            and as_utc(priors[prior_idx + 1].effective_from) <= record_ts
        ):
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
            while (
                config_idx + 1 < len(configs)
                and as_utc(configs[config_idx + 1].effective_from) <= record_ts
            ):
                config_idx += 1
            next_config = configs[config_idx]
            if next_config.id != current_config_id:
                warn_streak = 0
                hold_streak = 0
                current_config_id = next_config.id
            current_config = next_config

        mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
            mu_n,
            kappa_n,
            alpha_n,
            beta_n,
            record.result_value,
        )
        base_risk = risk_from_posterior(
            mu_n=mu_n,
            kappa_n=kappa_n,
            alpha_n=alpha_n,
            beta_n=beta_n,
            config=current_config,
        )
        warning_probability, action_probability = available_probabilities(base_risk)
        warn_streak, hold_streak = update_policy_streaks(
            config=current_config,
            prev_warn_streak=warn_streak,
            prev_hold_streak=hold_streak,
            probability_outside_warning=warning_probability,
            probability_outside_action=action_probability,
        )
        last_risk = base_risk.model_copy(
            update={"warn_streak": warn_streak, "hold_streak": hold_streak}
        )

    return last_risk or unavailable_missing_prior()
