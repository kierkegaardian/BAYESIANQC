from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from app.db_models import DEFAULT_RULE_SET, PriorConfig, QCRecord, StreamConfig
from app.domain import Disposition
from app.evaluation_models import BayesianThresholdMode, ControlLimitSource, ResolvedControlLimits
from app.math.bayesian_nig import BayesianPolicy, PosteriorParameters
from app.math.control_limits import resolve_control_limits, threshold_mode
from app.math.evaluation_engine import EvaluationPointInput, EvaluationPointOutput, evaluate_point
from app.models import BayesianRisk, FrequentistSignal
from app.timeutils import as_utc


@dataclass(frozen=True)
class ReplayEvaluation:
    record_id: int
    timestamp: datetime
    signals: tuple[FrequentistSignal, ...]
    risk: BayesianRisk | None
    disposition: Disposition
    config: StreamConfig
    prior: PriorConfig | None
    limits: ResolvedControlLimits
    threshold_mode: BayesianThresholdMode


@dataclass(frozen=True)
class ReplayResult:
    evaluations: tuple[ReplayEvaluation, ...]
    posterior: PosteriorParameters | None
    posterior_prior_id: int | None
    posterior_config_id: int | None
    posterior_n_obs: int
    warn_streak: int
    hold_streak: int
    updated_at: datetime | None


VersionT = TypeVar("VersionT", StreamConfig, PriorConfig)


def _active_version(versions: list[VersionT], at_time: datetime) -> VersionT | None:
    active: VersionT | None = None
    at_utc = as_utc(at_time)
    for version in versions:
        if as_utc(version.effective_from) <= at_utc:
            active = version
        else:
            break
    return active


def _limits_by_config(
    configs: list[StreamConfig],
) -> dict[int, ResolvedControlLimits]:
    resolved: dict[int, ResolvedControlLimits] = {}
    for config in configs:
        if config.id is None:
            raise RuntimeError("Stream config missing id")
        source = ControlLimitSource(config.control_limit_source)
        if source == ControlLimitSource.FIXED_BASELINE:
            if config.baseline_start is None or config.baseline_end is None:
                raise ValueError("fixed_baseline configuration is missing its date range")
            if as_utc(config.baseline_end) > as_utc(config.effective_from):
                raise ValueError("fixed_baseline baseline_end must not exceed effective_from")
        resolved[config.id] = resolve_control_limits(
            source=source,
            configured_target=config.target_value,
            configured_sigma=config.sigma,
            warning_limit_sd=config.warning_limit_sd,
            action_limit_sd=config.action_limit_sd,
            baseline_start=config.baseline_start,
            baseline_end=config.baseline_end,
            baseline_centerline=config.baseline_centerline,
            baseline_sigma=config.baseline_sigma,
            baseline_count=config.baseline_count,
        )
    return resolved


def _policy(config: StreamConfig) -> BayesianPolicy:
    return BayesianPolicy(
        risk_threshold_warn=config.risk_threshold_warn,
        risk_threshold_hold=config.risk_threshold_hold,
        warn_probability_threshold=config.bayes_warn_prob_threshold,
        warn_consecutive=config.bayes_warn_consecutive or 1,
        hold_probability_threshold=config.bayes_hold_prob_threshold,
        hold_consecutive=config.bayes_hold_consecutive or 1,
    )


def _prior_parameters(prior: PriorConfig) -> PosteriorParameters:
    return PosteriorParameters(
        mu=prior.mu0,
        kappa=prior.kappa0,
        alpha=prior.alpha0,
        beta=prior.beta0,
    )


def replay_evaluations(
    records: list[QCRecord],
    configs: list[StreamConfig],
    priors: list[PriorConfig],
) -> ReplayResult:
    ordered_records = sorted(records, key=lambda record: (as_utc(record.timestamp), record.id or 0))
    ordered_configs = sorted(configs, key=lambda config: (as_utc(config.effective_from), config.version))
    ordered_priors = sorted(priors, key=lambda prior: (as_utc(prior.effective_from), prior.version))
    limits_by_config = _limits_by_config(ordered_configs)

    recent_values: deque[float] = deque(maxlen=9)
    pending_values: list[float] = []
    pending_timestamp: datetime | None = None
    current_prior_id: int | None = None
    current_config_id: int | None = None
    posterior: PosteriorParameters | None = None
    posterior_n_obs = 0
    warn_streak = 0
    hold_streak = 0
    updated_at: datetime | None = None
    evaluations: list[ReplayEvaluation] = []

    for record in ordered_records:
        if record.id is None:
            raise RuntimeError("QC record missing id")
        if pending_timestamp is None:
            pending_timestamp = record.timestamp
        elif as_utc(record.timestamp) != as_utc(pending_timestamp):
            recent_values.extend(pending_values)
            pending_values.clear()
            pending_timestamp = record.timestamp

        config = _active_version(ordered_configs, record.timestamp)
        if config is None or config.id is None:
            raise ValueError(f"no stream configuration is effective for record {record.id}")
        prior = _active_version(ordered_priors, record.timestamp)
        prior_id = prior.id if prior is not None else None
        if prior is not None and prior_id is None:
            raise RuntimeError("Prior config missing id")

        if prior_id != current_prior_id:
            posterior = _prior_parameters(prior) if prior is not None else None
            posterior_n_obs = 0
            warn_streak = 0
            hold_streak = 0
            current_prior_id = prior_id
        if config.id != current_config_id:
            warn_streak = 0
            hold_streak = 0
            current_config_id = config.id

        rule_ids = tuple(str(rule) for rule in (config.rule_set or DEFAULT_RULE_SET).get("rules", []))
        result: EvaluationPointOutput = evaluate_point(
            EvaluationPointInput(
                value=record.result_value,
                include_in_stats=record.include_in_stats,
                recent_values=tuple(recent_values),
                rule_ids=rule_ids,
                limits=limits_by_config[config.id],
                posterior=posterior,
                policy=_policy(config),
                warn_streak=warn_streak,
                hold_streak=hold_streak,
            )
        )
        posterior = result.posterior
        warn_streak = result.warn_streak
        hold_streak = result.hold_streak
        if record.include_in_stats:
            pending_values.append(record.result_value)
            updated_at = record.timestamp
            if prior is not None:
                posterior_n_obs += 1
        evaluations.append(
            ReplayEvaluation(
                record_id=record.id,
                timestamp=record.timestamp,
                signals=result.signals,
                risk=result.risk,
                disposition=result.disposition,
                config=config,
                prior=prior,
                limits=limits_by_config[config.id],
                threshold_mode=threshold_mode(
                    config.bayes_warn_prob_threshold,
                    config.bayes_hold_prob_threshold,
                ),
            )
        )

    return ReplayResult(
        evaluations=tuple(evaluations),
        posterior=posterior,
        posterior_prior_id=current_prior_id,
        posterior_config_id=current_config_id,
        posterior_n_obs=posterior_n_obs,
        warn_streak=warn_streak,
        hold_streak=hold_streak,
        updated_at=updated_at,
    )
