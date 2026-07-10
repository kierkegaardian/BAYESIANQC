from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.bayesian_history import (
    included_records,
    list_priors,
    list_stream_configs,
    records_after_first_prior,
)
from app.bayesian_replay import infer_risk_as_of
from app.bayesian_risk import (
    available_probabilities,
    risk_from_posterior,
    unavailable_missing_prior,
    update_policy_streaks,
)
from app.db_models import PosteriorState, StreamConfig
from app.math.nig import update_normal_inverse_gamma as _update_posterior
from app.models import BayesianRisk
from app.storage import get_active_prior
from app.timeutils import as_utc


def _discard_state(
    session: Session,
    state: Optional[PosteriorState],
    *,
    commit: bool,
) -> None:
    if state is None:
        return
    session.delete(state)
    if commit:
        session.commit()
    else:
        session.flush()


def rebuild_posterior_state(
    session: Session,
    stream_id: str,
    *,
    commit: bool = True,
) -> Optional[PosteriorState]:
    records = included_records(session, stream_id)
    state = session.exec(
        select(PosteriorState).where(PosteriorState.stream_id == stream_id)
    ).first()
    if not records:
        _discard_state(session, state, commit=commit)
        return None

    priors = list_priors(session, stream_id)
    records = records_after_first_prior(records, priors)
    if not records:
        _discard_state(session, state, commit=commit)
        return None

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
            n_obs = 0
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
        if current_config is not None:
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
        n_obs += 1

    if state is None:
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
    else:
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
    if commit:
        session.commit()
    else:
        session.flush()
    return state


def infer_risk(
    session: Session,
    record_value: float,
    record_timestamp: datetime,
    stream_id: str,
    config: StreamConfig,
    *,
    commit: bool = True,
) -> BayesianRisk:
    prior = get_active_prior(session, stream_id, record_timestamp)
    if prior is None or as_utc(prior.effective_from) > as_utc(record_timestamp):
        return unavailable_missing_prior()
    if prior.id is None:
        raise RuntimeError("Prior config missing id")

    state = session.exec(
        select(PosteriorState).where(PosteriorState.stream_id == stream_id)
    ).first()
    if (
        state is None
        or as_utc(state.updated_at) > as_utc(record_timestamp)
        or state.prior_id != prior.id
    ):
        risk = infer_risk_as_of(session, stream_id, record_timestamp, config)
        rebuild_posterior_state(session, stream_id, commit=commit)
        return risk

    prev_warn_streak = state.warn_streak
    prev_hold_streak = state.hold_streak
    if config.id is not None and state.config_id != config.id:
        prev_warn_streak = 0
        prev_hold_streak = 0

    mu_n, kappa_n, alpha_n, beta_n = _update_posterior(
        state.mu_n,
        state.kappa_n,
        state.alpha_n,
        state.beta_n,
        record_value,
    )
    base_risk = risk_from_posterior(
        mu_n=mu_n,
        kappa_n=kappa_n,
        alpha_n=alpha_n,
        beta_n=beta_n,
        config=config,
    )
    warning_probability, action_probability = available_probabilities(base_risk)
    warn_streak, hold_streak = update_policy_streaks(
        config=config,
        prev_warn_streak=prev_warn_streak,
        prev_hold_streak=prev_hold_streak,
        probability_outside_warning=warning_probability,
        probability_outside_action=action_probability,
    )
    risk = base_risk.model_copy(
        update={"warn_streak": warn_streak, "hold_streak": hold_streak}
    )

    state.mu_n = mu_n
    state.kappa_n = kappa_n
    state.alpha_n = alpha_n
    state.beta_n = beta_n
    state.n_obs += 1
    state.updated_at = record_timestamp
    state.prior_id = prior.id
    state.config_id = config.id
    state.warn_streak = warn_streak
    state.hold_streak = hold_streak
    session.add(state)
    if commit:
        session.commit()
    else:
        session.flush()
    return risk
