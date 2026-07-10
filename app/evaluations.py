from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Optional, Sequence

from sqlmodel import Session, col, select

from app.bayesian import update_posterior_and_infer_risk
from app.db_models import PosteriorState, PriorConfig, QCRecord, StreamConfig
from app.domain import Disposition, SignalSeverity
from app.frequentist import evaluate_rules_for_values
from app.models import BayesianRisk, BayesianRiskStatus, BayesianRiskUnavailableReason, Role
from app.services.alert_reconciliation import reconcile_stream_alerts
from app.stats import sample_mean_sd
from app.timeutils import as_utc


def _baseline_target_sigma(records: Sequence[QCRecord], config: StreamConfig) -> tuple[float, float]:
    if config.baseline_start and config.baseline_end:
        baseline_start = as_utc(config.baseline_start)
        baseline_end = as_utc(config.baseline_end)
        values = [
            r.result_value
            for r in records
            if r.include_in_stats
            and as_utc(r.timestamp) >= baseline_start
            and as_utc(r.timestamp) <= baseline_end
        ]
        if len(values) >= 2:
            return sample_mean_sd(values)
    return config.target_value, config.sigma


def reprocess_stream_evaluations(
    session: Session,
    stream_id: str,
    *,
    commit: bool = True,
    actor: str = "system:reprocess",
    actor_role: Optional[Role] = None,
    api_key_id: Optional[int] = None,
) -> None:
    """
    Recompute and persist per-record evaluations for a stream.

    This is intentionally "batchy" and should be called when historical changes
    can invalidate cached evaluations: out-of-order ingestion, record exclusion,
    or config/prior changes.
    """

    records = session.exec(
        select(QCRecord)
        .where(QCRecord.stream_id == stream_id)
        .order_by(col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
    ).all()
    if not records:
        state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
        if state:
            session.delete(state)
        reconcile_stream_alerts(
            session,
            stream_id,
            actor=actor,
            actor_role=actor_role,
            api_key_id=api_key_id,
        )
        if commit:
            session.commit()
        else:
            session.flush()
        return

    configs = session.exec(
        select(StreamConfig)
        .where(StreamConfig.stream_id == stream_id)
        .order_by(col(StreamConfig.effective_from).asc(), col(StreamConfig.version).asc())
    ).all()
    priors = session.exec(
        select(PriorConfig)
        .where(PriorConfig.stream_id == stream_id)
        .order_by(col(PriorConfig.effective_from).asc(), col(PriorConfig.version).asc())
    ).all()

    if not configs:
        for record in records:
            record.signals = None
            record.bayesian_risk = None
            record.disposition = None
            session.add(record)
        state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
        if state:
            session.delete(state)
        reconcile_stream_alerts(
            session,
            stream_id,
            actor=actor,
            actor_role=actor_role,
            api_key_id=api_key_id,
        )
        if commit:
            session.commit()
        else:
            session.flush()
        return

    baseline_by_config_id: dict[int, tuple[float, float]] = {}
    for cfg in configs:
        if cfg.id is None:
            continue
        baseline_by_config_id[cfg.id] = _baseline_target_sigma(records, cfg)

    config_idx = 0
    recent_included_values: deque[float] = deque(maxlen=9)
    pending_included_values: list[float] = []
    pending_timestamp: Optional[datetime] = None
    rule_config_id: Optional[int] = None

    # Bayesian chain (only advanced on include_in_stats records).
    started_bayes = False
    prior_idx = 0
    current_prior: Optional[PriorConfig] = None
    mu_n = kappa_n = alpha_n = beta_n = 0.0
    n_obs = 0
    warn_streak = 0
    hold_streak = 0
    current_config_id: Optional[int] = None
    last_included_timestamp: Optional[datetime] = None

    for record in records:
        record_ts = as_utc(record.timestamp)
        if pending_timestamp is None:
            pending_timestamp = record.timestamp
        elif record.timestamp != pending_timestamp:
            for value in pending_included_values:
                recent_included_values.append(value)
            pending_included_values.clear()
            pending_timestamp = record.timestamp

        if record_ts < as_utc(configs[0].effective_from):
            record.signals = None
            record.bayesian_risk = None
            record.disposition = None
            session.add(record)
            continue

        while config_idx + 1 < len(configs) and as_utc(configs[config_idx + 1].effective_from) <= record_ts:
            config_idx += 1
        config_at_time = configs[config_idx]

        if rule_config_id != config_at_time.id:
            recent_included_values.clear()
            pending_included_values.clear()
            rule_config_id = config_at_time.id

        target, sigma = (
            baseline_by_config_id.get(config_at_time.id, (config_at_time.target_value, config_at_time.sigma))
            if config_at_time.id is not None
            else (config_at_time.target_value, config_at_time.sigma)
        )

        if sigma <= 0:
            raise ValueError("sigma must be > 0 to evaluate frequentist rules")
        signals = evaluate_rules_for_values(
            record_value=record.result_value,
            target=target,
            sigma=sigma,
            recent_values=tuple(recent_included_values),
            config=config_at_time,
        )

        risk: Optional[BayesianRisk]
        if not record.include_in_stats:
            risk = None
        elif not priors or record_ts < as_utc(priors[0].effective_from):
            risk = BayesianRisk(
                status=BayesianRiskStatus.UNAVAILABLE,
                unavailable_reason=BayesianRiskUnavailableReason.MISSING_EFFECTIVE_PRIOR,
            )
        else:
            if not started_bayes:
                while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= record_ts:
                    prior_idx += 1
                current_prior = priors[prior_idx]
                if current_prior.id is None:
                    raise RuntimeError("Prior config missing id")
                mu_n, kappa_n, alpha_n, beta_n = (
                    current_prior.mu0,
                    current_prior.kappa0,
                    current_prior.alpha0,
                    current_prior.beta0,
                )
                n_obs = 0
                warn_streak = 0
                hold_streak = 0
                current_config_id = config_at_time.id
                started_bayes = True
            else:
                while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= record_ts:
                    prior_idx += 1
                record_prior = priors[prior_idx]
                if record_prior.id is None:
                    raise RuntimeError("Prior config missing id")
                if current_prior is None or record_prior.id != current_prior.id:
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

                if config_at_time.id is not None and current_config_id != config_at_time.id:
                    warn_streak = 0
                    hold_streak = 0
                    current_config_id = config_at_time.id

            risk, (mu_n, kappa_n, alpha_n, beta_n) = update_posterior_and_infer_risk(
                mu0=mu_n,
                kappa0=kappa_n,
                alpha0=alpha_n,
                beta0=beta_n,
                record_value=record.result_value,
                config=config_at_time,
                warn_streak=warn_streak,
                hold_streak=hold_streak,
            )
            warn_streak = risk.warn_streak
            hold_streak = risk.hold_streak
            n_obs += 1
            last_included_timestamp = record_ts

        disposition = Disposition(
            Disposition.REJECT.value
            if any(s.severity == SignalSeverity.ACTION for s in signals)
            else (
                Disposition.HOLD_FOR_REVIEW.value
                if (
                    risk
                    and (
                        risk.status == BayesianRiskStatus.UNAVAILABLE
                        or risk.hold_streak >= (config_at_time.bayes_hold_consecutive or 1)
                    )
                )
                else (
                    Disposition.MONITOR.value
                    if (signals or (risk and risk.warn_streak >= (config_at_time.bayes_warn_consecutive or 1)))
                    else Disposition.ACCEPT.value
                )
            )
        )

        record.signals = [s.model_dump(mode="json") for s in signals]
        record.bayesian_risk = risk.model_dump(mode="json") if risk is not None else None
        record.disposition = disposition.value
        session.add(record)

        if record.include_in_stats:
            pending_included_values.append(record.result_value)

    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if not priors or not started_bayes or current_prior is None or last_included_timestamp is None:
        if state:
            session.delete(state)
        reconcile_stream_alerts(
            session,
            stream_id,
            actor=actor,
            actor_role=actor_role,
            api_key_id=api_key_id,
        )
        if commit:
            session.commit()
        else:
            session.flush()
        return

    if state:
        state.mu_n = mu_n
        state.kappa_n = kappa_n
        state.alpha_n = alpha_n
        state.beta_n = beta_n
        state.n_obs = n_obs
        state.updated_at = last_included_timestamp
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
            updated_at=last_included_timestamp,
            prior_id=current_prior.id,
            config_id=current_config_id,
            warn_streak=warn_streak,
            hold_streak=hold_streak,
        )
        session.add(state)
    reconcile_stream_alerts(
        session,
        stream_id,
        actor=actor,
        actor_role=actor_role,
        api_key_id=api_key_id,
    )
    if commit:
        session.commit()
    else:
        session.flush()
