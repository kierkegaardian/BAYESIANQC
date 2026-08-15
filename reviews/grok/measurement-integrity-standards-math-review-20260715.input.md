REVIEW CONTEXT
Repository: BAYESIANQC, branch codex/measurement-integrity, uncommitted correctness slice.
Product currently evaluates single-result laboratory QC streams with Westgard-like frequentist rules plus a Normal-Inverse-Gamma Bayesian posterior predictive risk layer.
The review must distinguish implemented behavior from roadmap-only standards features.

CURRENT OFFICIAL CATALOG FACTS AND PRIMARY URLS
ASTM D6299-26 is the current ASTM practice for applying statistical quality assurance and control charting techniques to evaluate analytical measurement system performance: ongoing stability, precision, and bias; continuous numerical results; stable systems; Gaussian adequacy assumptions. https://store.astm.org/d6299-26.html
ISO 7870-2:2023 is the current Shewhart control-chart standard. https://www.iso.org/standard/78859.html
ISO 7870-6:2024 is the current EWMA control-chart standard and supersedes the withdrawn 2016 edition. https://www.iso.org/standard/83852.html
ISO 7870-8:2017 covers control charts for short runs and small mixed batches, including sample-size-one variables charts. https://www.iso.org/standard/67410.html
ISO 7870-9:2020 covers control charts for stationary processes. https://www.iso.org/standard/69641.html
ISO 7870-4:2021 covers CUSUM charts. https://www.iso.org/standard/74101.html
ISO/IEC 17025:2017 remains current after 2023 confirmation and covers laboratory competence, impartiality, and consistent operation. https://www.iso.org/standard/66912.html
ASTM training material identifies ILCP outputs, site precision R-prime, accepted reference value, and control charts as D6299 concerns. https://store.astm.org/astm-tpt-141.html
Full licensed standard text is not in this packet. Do not invent clause numbers, normative requirements, or proprietary formulas. Mark anything needing licensed-copy verification.

ACCEPTANCE EVIDENCE
The slice passed Ruff, Pyright, 143 backend tests, four Vitest workflow tests, frontend typecheck/build, nine Postgres migration/rehearsal tests, an API image import smoke, and browser smoke. Existing evaluations are not reprocessed.


===== FILE: app/math/student_t.py =====
from __future__ import annotations

import math

from scipy.special import stdtr, stdtrit


def _finite(name: str, value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _degrees_of_freedom(value: float) -> float:
    degrees_of_freedom = _finite("degrees_of_freedom", value)
    if degrees_of_freedom <= 0:
        raise ValueError("degrees_of_freedom must be > 0")
    return degrees_of_freedom


def student_t_cdf(t_value: float, degrees_of_freedom: float) -> float:
    """Return the Student-t cumulative probability for a finite value and df."""

    t = _finite("t_value", t_value)
    df = _degrees_of_freedom(degrees_of_freedom)
    return float(stdtr(df, t))


def student_t_ppf(probability: float, degrees_of_freedom: float) -> float:
    """Return the Student-t quantile for a probability strictly between zero and one."""

    p = _finite("probability", probability)
    if not 0.0 < p < 1.0:
        raise ValueError("probability must be between 0 and 1")
    df = _degrees_of_freedom(degrees_of_freedom)
    return float(stdtrit(df, p))


def student_t_interval_quantile(degrees_of_freedom: float, level: float = 0.95) -> float:
    interval_level = _finite("level", level)
    if not 0.0 < interval_level < 1.0:
        raise ValueError("level must be between 0 and 1")
    probability = (1.0 + interval_level) / 2.0
    return student_t_ppf(probability, degrees_of_freedom)


def student_t_probability_outside_bounds(
    *,
    mean: float,
    scale: float,
    degrees_of_freedom: float,
    lower: float,
    upper: float,
) -> float:
    """Return two-sided probability outside bounds without subtracting from one."""

    center = _finite("mean", mean)
    spread = _finite("scale", scale)
    if spread <= 0:
        raise ValueError("scale must be > 0")
    df = _degrees_of_freedom(degrees_of_freedom)
    lower_bound = _finite("lower", lower)
    upper_bound = _finite("upper", upper)
    if lower_bound > upper_bound:
        raise ValueError("lower must be <= upper")

    lower_t = (lower_bound - center) / spread
    upper_t = (upper_bound - center) / spread
    lower_tail = float(stdtr(df, lower_t))
    upper_tail = float(stdtr(df, -upper_t))
    return max(0.0, min(1.0, lower_tail + upper_tail))

===== FILE: app/math/prior.py =====
from __future__ import annotations

import math


def prior_beta_from_sigma(alpha0: float, sigma: float) -> float:
    """Return the NIG beta that gives the requested prior variance."""

    if not math.isfinite(alpha0) or alpha0 <= 1:
        raise ValueError("alpha0 must be finite and > 1")
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma must be finite and > 0")
    return (alpha0 - 1.0) * sigma**2

===== FILE: app/bayesian.py =====
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from sqlmodel import Session, col, select

from app.db_models import PosteriorState, PriorConfig, QCRecord, StreamConfig
from app.math.student_t import student_t_interval_quantile, student_t_probability_outside_bounds
from app.models import BayesianRisk
from app.storage import get_active_prior
from app.timeutils import as_utc

_DEFAULT_INTERVAL_LEVEL = 0.95


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


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

        probability_outside_warning = student_t_probability_outside_bounds(
            mean=mu_n,
            scale=predictive_sigma,
            degrees_of_freedom=df,
            lower=warn_lower,
            upper=warn_upper,
        )
        probability_outside_action = student_t_probability_outside_bounds(
            mean=mu_n,
            scale=predictive_sigma,
            degrees_of_freedom=df,
            lower=action_lower,
            upper=action_upper,
        )

    risk_score = int(min(100, max(0, round(probability_outside_action * 100))))

    q = student_t_interval_quantile(df, _DEFAULT_INTERVAL_LEVEL)

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
    at_time_utc = as_utc(at_time)
    for prior in priors:
        if as_utc(prior.effective_from) <= at_time_utc:
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
    first_ts = as_utc(records[0].timestamp)
    while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= first_ts:
        prior_idx += 1
    current_prior = priors[prior_idx]
    if current_prior.id is None:
        raise RuntimeError("Prior config missing id")

    config_idx = 0
    if configs:
        while config_idx + 1 < len(configs) and as_utc(configs[config_idx + 1].effective_from) <= first_ts:
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
        while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= record_ts:
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
            while config_idx + 1 < len(configs) and as_utc(configs[config_idx + 1].effective_from) <= record_ts:
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


def rebuild_posterior_state(session: Session, stream_id: str, *, commit: bool = True) -> Optional[PosteriorState]:
    records = session.exec(
        select(QCRecord)
        .where(QCRecord.stream_id == stream_id, QCRecord.include_in_stats == True)
        .order_by(col(QCRecord.timestamp).asc())
    ).all()
    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if not records:
        if state:
            session.delete(state)
            if commit:
                session.commit()
            else:
                session.flush()
        return None

    priors = _list_priors(session, stream_id)
    if not priors:
        if state:
            session.delete(state)
            if commit:
                session.commit()
            else:
                session.flush()
        return None

    configs = list(
        session.exec(
            select(StreamConfig)
            .where(StreamConfig.stream_id == stream_id)
            .order_by(col(StreamConfig.effective_from).asc(), col(StreamConfig.version).asc())
        ).all()
    )

    prior_idx = 0
    first_ts = as_utc(records[0].timestamp)
    while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= first_ts:
        prior_idx += 1
    current_prior = priors[prior_idx]
    if current_prior.id is None:
        raise RuntimeError("Prior config missing id")

    config_idx = 0
    if configs:
        while config_idx + 1 < len(configs) and as_utc(configs[config_idx + 1].effective_from) <= first_ts:
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
        while prior_idx + 1 < len(priors) and as_utc(priors[prior_idx + 1].effective_from) <= record_ts:
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
            while config_idx + 1 < len(configs) and as_utc(configs[config_idx + 1].effective_from) <= record_ts:
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
    if prior is None:
        return BayesianRisk(probability_outside_limits=0.0, risk_score=0)
    if prior.id is None:
        raise RuntimeError("Prior config missing id")

    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if not state or (as_utc(state.updated_at) > as_utc(record_timestamp)) or (state.prior_id != prior.id):
        risk = infer_risk_as_of(session, stream_id, record_timestamp, config)
        rebuild_posterior_state(session, stream_id, commit=commit)
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
    if commit:
        session.commit()
    else:
        session.flush()
    return risk

===== FILE: app/frequentist.py =====
from __future__ import annotations

from datetime import datetime
from typing import List, Sequence

from sqlmodel import Session

from app.db_models import DEFAULT_RULE_SET, StreamConfig
from app.domain import SignalSeverity
from app.models import FrequentistSignal
from app.storage import baseline_stats, get_recent_records


def evaluate_rules_for_values(
    *,
    record_value: float,
    target: float,
    sigma: float,
    recent_values: Sequence[float],
    config: StreamConfig,
) -> List[FrequentistSignal]:
    z_score = (record_value - target) / sigma
    signals: List[FrequentistSignal] = []
    rules = (config.rule_set or DEFAULT_RULE_SET).get("rules", [])

    def _signal(rule: str, severity: SignalSeverity, evidence: str) -> None:
        signals.append(FrequentistSignal(rule=rule, severity=severity, evidence=evidence))

    warn_limit = config.warning_limit_sd
    action_limit = config.action_limit_sd

    if "1-3s" in rules and abs(z_score) >= action_limit:
        _signal("1-3s", SignalSeverity.ACTION, f"|z|={abs(z_score):.2f} exceeds action limit")

    recent_z = [((v - target) / sigma, v) for v in recent_values]

    if "2-2s" in rules and abs(z_score) >= warn_limit and recent_z:
        prev_z = recent_z[-1][0]
        if (z_score >= warn_limit and prev_z >= warn_limit) or (z_score <= -warn_limit and prev_z <= -warn_limit):
            direction = "high" if z_score > 0 else "low"
            _signal(
                "2-2s",
                SignalSeverity.WARN,
                f"Consecutive warning-level deviations in same direction ({direction})",
            )

    if "R-4s" in rules and recent_z:
        prev_z = recent_z[-1][0]
        if (z_score >= warn_limit and prev_z <= -warn_limit) or (z_score <= -warn_limit and prev_z >= warn_limit):
            _signal(
                "R-4s",
                SignalSeverity.ACTION,
                "Consecutive results exceed 4 SD range in opposite directions",
            )

    if "4-1s" in rules:
        last_four = recent_z[-3:] + [(z_score, record_value)]
        if len(last_four) == 4:
            if all(z >= 1 for z, _ in last_four) or all(z <= -1 for z, _ in last_four):
                _signal("4-1s", SignalSeverity.WARN, "Four consecutive results exceed 1 SD on the same side")

    if "10x" in rules:
        last_ten = recent_z[-9:] + [(z_score, record_value)]
        if len(last_ten) == 10:
            if all(z > 0 for z, _ in last_ten) or all(z < 0 for z, _ in last_ten):
                _signal("10x", SignalSeverity.WARN, "Ten consecutive results on the same side of the mean")

    return signals


def evaluate_rules(
    session: Session,
    record_value: float,
    record_timestamp: datetime,
    stream_id: str,
    config: StreamConfig,
) -> List[FrequentistSignal]:
    target, sigma = baseline_stats(session, config, record_timestamp)
    recent = get_recent_records(session, stream_id, record_timestamp, limit=9)
    return evaluate_rules_for_values(
        record_value=record_value,
        target=target,
        sigma=sigma,
        recent_values=[r.result_value for r in recent],
        config=config,
    )

===== FILE: app/stats.py =====
from __future__ import annotations

import math
from collections.abc import Sequence


def sample_mean_sd(values: Sequence[float]) -> tuple[float, float]:
    """
    Compute sample mean and sample standard deviation (ddof=1).

    Raises ValueError when fewer than two values are provided.
    """
    if len(values) < 2:
        raise ValueError("Need at least two values to compute sample SD")
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


===== FILE: app/evaluations.py =====
from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Optional, Sequence

from sqlmodel import Session, col, select

from app.bayesian import update_posterior_and_infer_risk
from app.db_models import PosteriorState, PriorConfig, QCRecord, StreamConfig
from app.domain import Disposition, SignalSeverity
from app.frequentist import evaluate_rules_for_values
from app.models import BayesianRisk
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


def reprocess_stream_evaluations(session: Session, stream_id: str, *, commit: bool = True) -> None:
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

        while config_idx + 1 < len(configs) and as_utc(configs[config_idx + 1].effective_from) <= record_ts:
            config_idx += 1
        config_at_time = configs[config_idx]

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
        elif not priors:
            risk = BayesianRisk(probability_outside_limits=0.0, risk_score=0)
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
                if (risk and risk.hold_streak >= (config_at_time.bayes_hold_consecutive or 1))
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
    if commit:
        session.commit()
    else:
        session.flush()

===== FILE: tests/test_statistical_math.py =====
from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.math.prior import prior_beta_from_sigma
from app.math.student_t import (
    student_t_cdf,
    student_t_interval_quantile,
    student_t_ppf,
    student_t_probability_outside_bounds,
)
from app.models import PriorConfigIn, QCRecordIn, StreamConfigIn

# Independently recorded R pt/qt reference values.
REFERENCE_VALUES = [
    (4.0, 0.8130495168499705, -7.173182219782321, 2.776445105197799),
    (10.0, 0.8295534338489701, -4.143700494046623, 2.2281388519649385),
    (30.0, 0.8373456922869849, -3.3851848668182165, 2.0422724563012373),
    (100.0, 0.8401379221079384, -3.173739493738782, 1.9839715184496334),
]


def _stream_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": "finite-stream",
        "analyte": "Sulfur",
        "method": "ASTM D7039",
        "instrument": "Sindie",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "units": "ppm",
        "target_value": 10.0,
        "sigma": 0.5,
        "warning_limit_sd": 2.0,
        "action_limit_sd": 3.0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(("df", "cdf_at_one", "q001", "q975"), REFERENCE_VALUES)
def test_student_t_matches_reference_values(df: float, cdf_at_one: float, q001: float, q975: float) -> None:
    assert student_t_cdf(1.0, df) == pytest.approx(cdf_at_one, abs=1e-10)
    assert student_t_cdf(-1.0, df) == pytest.approx(1.0 - cdf_at_one, abs=1e-10)
    assert student_t_ppf(0.001, df) == pytest.approx(q001, abs=1e-8)
    assert student_t_ppf(0.975, df) == pytest.approx(q975, abs=1e-8)
    assert student_t_interval_quantile(df) == pytest.approx(q975, abs=1e-8)


@pytest.mark.parametrize("df", [4.0, 10.0, 30.0, 100.0])
@pytest.mark.parametrize("probability", [1e-6, 0.001, 0.025, 0.5, 0.975, 0.999, 1.0 - 1e-6])
def test_student_t_cdf_ppf_round_trip(df: float, probability: float) -> None:
    quantile = student_t_ppf(probability, df)
    assert student_t_cdf(quantile, df) == pytest.approx(probability, abs=1e-10)


@pytest.mark.parametrize("scale", [0.25, 1.0, 10.0])
def test_df_30_three_scale_tail_is_student_t(scale: float) -> None:
    outside = student_t_probability_outside_bounds(
        mean=0.0,
        scale=scale,
        degrees_of_freedom=30.0,
        lower=-3.0 * scale,
        upper=3.0 * scale,
    )
    assert outside == pytest.approx(0.005389964065651934, abs=1e-10)


def test_student_t_has_no_df_30_cutover_discontinuity() -> None:
    below = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=29.999999, lower=-3.0, upper=3.0
    )
    at_cutover = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=30.0, lower=-3.0, upper=3.0
    )
    above = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=30.000001, lower=-3.0, upper=3.0
    )
    assert abs(below - at_cutover) < 1e-9
    assert abs(above - at_cutover) < 1e-9


@pytest.mark.parametrize("df", [4.0, 10.0, 30.0, 100.0])
def test_warning_probability_is_not_below_action_probability(df: float) -> None:
    warning = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=df, lower=-2.0, upper=2.0
    )
    action = student_t_probability_outside_bounds(
        mean=0.0, scale=1.0, degrees_of_freedom=df, lower=-3.0, upper=3.0
    )
    assert warning >= action


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_value": math.nan},
        {"sigma": math.inf},
        {"warning_limit_sd": -math.inf},
        {"action_limit_sd": math.nan},
        {"bayes_warn_prob_threshold": math.inf},
        {"bayes_hold_prob_threshold": math.nan},
        {"min_value": 5.0, "max_value": 4.0},
    ],
)
def test_stream_config_rejects_invalid_statistical_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StreamConfigIn.model_validate(_stream_payload(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"sigma": 0.0},
        {"sigma": -0.5},
        {"warning_limit_sd": 0.0},
        {"action_limit_sd": -3.0},
        {"warning_limit_sd": 3.0, "action_limit_sd": 2.0},
    ],
)
def test_stream_config_rejects_nonpositive_or_reversed_scales(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StreamConfigIn.model_validate(_stream_payload(**overrides))


@pytest.mark.parametrize(
    "conversion",
    [math.inf, {"factor": math.nan}, {"offset": math.inf}, {"factor": 1.0, "unexpected": 2.0}],
)
def test_stream_config_rejects_invalid_unit_conversions(conversion: object) -> None:
    with pytest.raises(ValidationError):
        StreamConfigIn.model_validate(_stream_payload(unit_conversions={"mg/L": conversion}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"mu0": math.nan},
        {"kappa0": math.inf},
        {"alpha0": -math.inf},
        {"beta0": math.nan},
    ],
)
def test_prior_rejects_nonfinite_parameters(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {"stream_id": "finite-stream", "mu0": 10.0, "kappa0": 1.0, "alpha0": 2.0}
    payload.update(overrides)
    with pytest.raises(ValidationError):
        PriorConfigIn.model_validate(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"kappa0": 0.0},
        {"kappa0": -1.0},
        {"alpha0": 1.0},
        {"alpha0": 0.0},
        {"beta0": 0.0},
        {"beta0": -1.0},
    ],
)
def test_prior_rejects_invalid_scale_parameters(overrides: dict[str, object]) -> None:
    payload: dict[str, object] = {"stream_id": "finite-stream", "mu0": 10.0, "kappa0": 1.0, "alpha0": 2.0}
    payload.update(overrides)
    with pytest.raises(ValidationError):
        PriorConfigIn.model_validate(payload)


def test_prior_beta_may_be_omitted_and_has_variance_preserving_default() -> None:
    prior = PriorConfigIn(stream_id="finite-stream", mu0=10.0, kappa0=1.0, alpha0=5.0)
    assert prior.beta0 is None
    assert prior_beta_from_sigma(prior.alpha0, 0.5) == pytest.approx(1.0)


def test_qc_result_must_be_finite() -> None:
    with pytest.raises(ValidationError):
        QCRecordIn(
            stream_id="finite-stream",
            result_value=math.nan,
            timestamp=datetime(2026, 7, 15, tzinfo=timezone.utc),
            analyte="Sulfur",
            qc_level="L1",
            instrument_id="Sindie",
            method_id="ASTM D7039",
            control_material_lot="LOT-1",
            units="ppm",
        )

===== FILE: tests/test_measurement_integrity_api.py =====
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.main import app

AUTH_HEADERS = {"X-API-Key": "local-dev-key"}
JSON_HEADERS = {**AUTH_HEADERS, "Content-Type": "application/json"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def _stream_payload(stream_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": stream_id,
        "analyte": "Sulfur",
        "method": "ASTM D7039",
        "instrument": "Sindie",
        "site": "Refinery",
        "lab_bench": "Bench A",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "units": "ppm",
        "target_value": 10.0,
        "sigma": 0.5,
        "warning_limit_sd": 2.0,
        "action_limit_sd": 3.0,
    }
    payload.update(overrides)
    return payload


def _setup_payload(stream_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "stream_id": stream_id,
        "site": "Refinery",
        "lab_bench": "Bench A",
        "instrument_name": "Sindie",
        "method_name": "ASTM D7039",
        "parameter_name": "Sulfur",
        "units": "ppm",
        "material_name": "Sulfur QC",
        "qc_level": "L1",
        "control_material_lot": "LOT-1",
        "target_value": 10.0,
        "sigma": 0.5,
        "warning_limit_sd": 2.0,
        "action_limit_sd": 3.0,
        "prior_mu0": 10.0,
        "prior_kappa0": 1.0,
        "prior_alpha0": 5.0,
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_direct_prior_derives_omitted_beta_from_effective_stream_config(client: httpx.AsyncClient) -> None:
    effective_from = datetime.now(timezone.utc) - timedelta(minutes=1)
    stream = await client.post(
        "/streams",
        json=_stream_payload("derived-prior", effective_from=effective_from.isoformat()),
        headers=AUTH_HEADERS,
    )
    assert stream.status_code == 200, stream.text

    prior = await client.post(
        "/streams/derived-prior/priors",
        json={
            "stream_id": "ignored-path-wins",
            "mu0": 10.0,
            "kappa0": 1.0,
            "alpha0": 5.0,
            "effective_from": effective_from.isoformat(),
        },
        headers=AUTH_HEADERS,
    )
    assert prior.status_code == 200, prior.text
    assert prior.json()["beta0"] == pytest.approx(1.0)


@pytest.mark.anyio
async def test_omitted_beta_requires_an_effective_config_but_explicit_beta_is_preserved(
    client: httpx.AsyncClient,
) -> None:
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=1)
    stream = await client.post(
        "/streams",
        json=_stream_payload("future-config", effective_from=future.isoformat()),
        headers=AUTH_HEADERS,
    )
    assert stream.status_code == 200, stream.text

    omitted = await client.post(
        "/streams/future-config/priors",
        json={"stream_id": "future-config", "mu0": 10.0, "kappa0": 1.0, "alpha0": 2.0, "effective_from": now.isoformat()},
        headers=AUTH_HEADERS,
    )
    assert omitted.status_code == 422
    assert "beta0 is required" in omitted.json()["detail"]

    explicit = await client.post(
        "/streams/future-config/priors",
        json={
            "stream_id": "future-config",
            "mu0": 10.0,
            "kappa0": 1.0,
            "alpha0": 2.0,
            "beta0": 0.75,
            "effective_from": now.isoformat(),
        },
        headers=AUTH_HEADERS,
    )
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()["beta0"] == pytest.approx(0.75)


@pytest.mark.anyio
async def test_stream_setup_apply_derives_omitted_beta(client: httpx.AsyncClient) -> None:
    payload = {"rows": [_setup_payload("setup-derived-prior")]}
    preview = await client.post("/stream-setups/preview", json=payload, headers=AUTH_HEADERS)
    assert preview.status_code == 200, preview.text
    assert preview.json()["invalid"] == 0

    applied = await client.post("/stream-setups/apply", json=payload, headers=AUTH_HEADERS)
    assert applied.status_code == 200, applied.text
    assert applied.json()["rows"][0]["prior"]["beta0"] == pytest.approx(1.0)

    explicit_payload = {"rows": [_setup_payload("setup-explicit-prior", prior_beta0=0.75)]}
    explicit_preview = await client.post("/stream-setups/preview", json=explicit_payload, headers=AUTH_HEADERS)
    assert explicit_preview.status_code == 200, explicit_preview.text
    explicit_applied = await client.post("/stream-setups/apply", json=explicit_payload, headers=AUTH_HEADERS)
    assert explicit_applied.status_code == 200, explicit_applied.text
    assert explicit_applied.json()["rows"][0]["prior"]["beta0"] == pytest.approx(0.75)


@pytest.mark.anyio
async def test_statistical_configuration_failures_return_422(client: httpx.AsyncClient) -> None:
    for stream_id, overrides in [
        ("nan-target", {"target_value": float("nan")}),
        ("positive-infinity-sigma", {"sigma": float("inf")}),
        ("negative-infinity-limit", {"warning_limit_sd": float("-inf")}),
        ("zero-sigma", {"sigma": 0.0}),
        ("negative-sigma", {"sigma": -0.5}),
    ]:
        response = await client.post(
            "/streams",
            content=json.dumps(_stream_payload(stream_id, **overrides)),
            headers=JSON_HEADERS,
        )
        assert response.status_code == 422, response.text

    bounds_response = await client.post(
        "/streams",
        json=_stream_payload("reversed-bounds", min_value=12.0, max_value=11.0),
        headers=AUTH_HEADERS,
    )
    assert bounds_response.status_code == 422

    conversion_response = await client.post(
        "/streams",
        json=_stream_payload(
            "bad-conversion",
            unit_conversions={"mg/L": {"factor": 1.0, "unexpected": 2.0}},
        ),
        headers=AUTH_HEADERS,
    )
    assert conversion_response.status_code == 422


@pytest.mark.anyio
async def test_stream_setup_preview_and_apply_reject_invalid_statistics(client: httpx.AsyncClient) -> None:
    invalid_setups = [
        _setup_payload("setup-nan", target_value=float("nan")),
        _setup_payload("setup-infinity", sigma=float("inf")),
        _setup_payload("setup-zero-scale", sigma=0.0),
        _setup_payload("setup-negative-kappa", prior_kappa0=-1.0),
        _setup_payload("setup-reversed-bounds", min_value=12.0, max_value=11.0),
    ]
    for index, setup in enumerate(invalid_setups):
        body = json.dumps({"rows": [setup]})
        for endpoint in ("preview", "apply"):
            response = await client.post(
                f"/stream-setups/{endpoint}",
                content=body,
                headers=JSON_HEADERS,
            )
            assert response.status_code == 422, f"case {index} {endpoint}: {response.text}"


@pytest.mark.anyio
async def test_valid_unit_conversion_shape_round_trips(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/streams",
        json=_stream_payload(
            "typed-conversion",
            unit_conversions={"mg/L": {"factor": 2.0, "offset": 1.0}, "ug/mL": 0.5},
        ),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["unit_conversions"] == {"mg/L": {"factor": 2.0, "offset": 1.0}, "ug/mL": 0.5}

===== CONFIG MODELS: app/models.py lines 330-590 =====
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    completed_qc_record_id: Optional[int] = None
    last_quarantine_id: Optional[int] = None


class QCCommentIn(BaseModel):
    target_type: QCCommentTargetType
    target_id: str
    body: str
    stream_id: Optional[str] = None

    @field_validator("target_id", "body")
    @classmethod
    def text_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        return stripped


class QCCommentOut(BaseModel):
    id: int
    target_type: QCCommentTargetType
    target_id: str
    stream_id: Optional[str] = None
    qc_record_id: Optional[int] = None
    alert_id: Optional[str] = None
    run_id: Optional[str] = None
    body: str
    actor: str
    actor_role: Optional[Role] = None
    api_key_id: Optional[int] = None
    created_at: datetime


class UnitConversionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor: FiniteFloat = 1.0
    offset: FiniteFloat = 0.0


UnitConversionValue = FiniteFloat | UnitConversionSpec


class StreamConfigBase(BaseModel):
    stream_id: str
    analyte: str
    method: str
    instrument: str
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    matrix: Optional[str] = None
    qc_level: str
    control_material_lot: str
    control_material_id: Optional[int] = None
    units: str
    target_value: FiniteFloat
    sigma: FiniteFloat
    action_limit_sd: FiniteFloat = 3.0
    warning_limit_sd: FiniteFloat = 2.0
    min_value: Optional[FiniteFloat] = None
    max_value: Optional[FiniteFloat] = None
    allowed_units: Optional[List[str]] = None
    unit_conversions: Optional[dict[str, UnitConversionValue]] = None
    baseline_start: Optional[datetime] = None
    baseline_end: Optional[datetime] = None
    risk_threshold_warn: int = 50
    risk_threshold_hold: int = 80
    bayes_warn_prob_threshold: Optional[FiniteFloat] = None
    bayes_warn_consecutive: Optional[int] = None
    bayes_hold_prob_threshold: Optional[FiniteFloat] = None
    bayes_hold_consecutive: Optional[int] = None
    rule_set: Optional[dict[str, JsonValue]] = None

    @field_validator("sigma")
    @classmethod
    def sigma_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("sigma must be > 0")
        return v

    @field_validator("warning_limit_sd", "action_limit_sd")
    @classmethod
    def limits_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("limit SD values must be > 0")
        return v

    @model_validator(mode="after")
    def validate_limits_and_thresholds(self) -> "StreamConfigBase":
        if self.action_limit_sd < self.warning_limit_sd:
            raise ValueError("action_limit_sd must be >= warning_limit_sd")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value must be <= max_value")
        if not (0 <= self.risk_threshold_warn <= 100):
            raise ValueError("risk_threshold_warn must be between 0 and 100")
        if not (0 <= self.risk_threshold_hold <= 100):
            raise ValueError("risk_threshold_hold must be between 0 and 100")
        if self.risk_threshold_hold < self.risk_threshold_warn:
            raise ValueError("risk_threshold_hold must be >= risk_threshold_warn")
        if self.bayes_warn_prob_threshold is not None and not (0 <= self.bayes_warn_prob_threshold <= 1):
            raise ValueError("bayes_warn_prob_threshold must be between 0 and 1")
        if self.bayes_hold_prob_threshold is not None and not (0 <= self.bayes_hold_prob_threshold <= 1):
            raise ValueError("bayes_hold_prob_threshold must be between 0 and 1")
        if self.bayes_warn_consecutive is not None and self.bayes_warn_consecutive <= 0:
            raise ValueError("bayes_warn_consecutive must be > 0")
        if self.bayes_hold_consecutive is not None and self.bayes_hold_consecutive <= 0:
            raise ValueError("bayes_hold_consecutive must be > 0")
        if self.baseline_start and self.baseline_end and self.baseline_end < self.baseline_start:
            raise ValueError("baseline_end must be >= baseline_start")
        return self


class StreamConfigIn(StreamConfigBase):
    effective_from: Optional[datetime] = None


class StreamConfigOut(StreamConfigBase):
    version: int
    created_at: datetime
    created_by: str
    effective_from: datetime


class InstrumentIn(BaseModel):
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: bool = True


class InstrumentOut(InstrumentIn):
    id: int
    created_at: datetime
    created_by: str


class InstrumentUpdate(BaseModel):
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: Optional[bool] = None


class MethodIn(BaseModel):
    name: str
    instrument_id: int
    technique: Optional[str] = None
    active: bool = True


class MethodOut(MethodIn):
    id: int
    created_at: datetime
    created_by: str


class MethodUpdate(BaseModel):
    name: Optional[str] = None
    instrument_id: Optional[int] = None
    technique: Optional[str] = None
    active: Optional[bool] = None


class AnalyteIn(BaseModel):
    name: str
    method_id: int
    units: Optional[str] = None
    active: bool = True


class AnalyteOut(AnalyteIn):
    id: int
    created_at: datetime
    created_by: str


class AnalyteUpdate(BaseModel):
    name: Optional[str] = None
    method_id: Optional[int] = None
    units: Optional[str] = None
    active: Optional[bool] = None


class PriorConfigBase(BaseModel):
    stream_id: str
    mu0: FiniteFloat
    kappa0: FiniteFloat
    alpha0: FiniteFloat

    @field_validator("kappa0")
    @classmethod
    def kappa0_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("kappa0 must be > 0")
        return v

    @field_validator("alpha0")
    @classmethod
    def alpha0_must_be_gt_one(cls, v: float) -> float:
        if v <= 1:
            raise ValueError("alpha0 must be > 1")
        return v

class PriorConfigIn(PriorConfigBase):
    beta0: Optional[FiniteFloat] = None
    effective_from: Optional[datetime] = None

    @field_validator("beta0")
    @classmethod
    def beta0_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("beta0 must be > 0")
        return v


class PriorConfigOut(PriorConfigBase):
    beta0: FiniteFloat
    version: int
    created_at: datetime
    created_by: str
    effective_from: datetime

    @field_validator("beta0")
    @classmethod
    def output_beta0_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("beta0 must be > 0")
        return v


class QCEventIn(BaseModel):
    event_type: EventType
    timestamp: datetime
    stream_id: Optional[str] = None
    instrument_id: Optional[str] = None
    analyte: Optional[str] = None
    method_id: Optional[str] = None
    metadata: Optional[dict[str, JsonValue]] = None


class QCEventOut(QCEventIn):
    id: int
    created_at: datetime
    created_by: str


class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None
    reason: Optional[str] = None



===== STREAM SETUP MODELS =====
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, FiniteFloat, field_validator, model_validator

from app.models import PriorConfigOut, StreamConfigOut


class ControlMaterialIn(BaseModel):
    name: str
    lot: str
    qc_level: str
    matrix: Optional[str] = None
    manufacturer: Optional[str] = None
    active: bool = True

    @field_validator("name", "lot", "qc_level")
    @classmethod
    def text_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        return stripped


class ControlMaterialOut(ControlMaterialIn):
    id: int
    created_at: datetime
    created_by: str


class KioskPanelIn(BaseModel):
    stream_id: str
    title: str
    display_order: Optional[int] = None
    start: Optional[str] = None
    end: Optional[str] = None
    window_label: Optional[str] = None
    mode: Literal["results", "risk", "both"] = "both"
    active: bool = True

    @field_validator("stream_id", "title")
    @classmethod
    def panel_text_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        return stripped


class KioskPanelOut(KioskPanelIn):
    id: int
    kiosk_id: int
    display_order: int = 0
    created_at: datetime
    created_by: str


class KioskLayoutIn(BaseModel):
    slug: str
    label: str
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: bool = True

    @field_validator("slug")
    @classmethod
    def slug_required(cls, value: str) -> str:
        stripped = value.strip().lower()
        if not stripped:
            raise ValueError("slug is required")
        return stripped

    @field_validator("label")
    @classmethod
    def label_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("label is required")
        return stripped


class KioskLayoutOut(KioskLayoutIn):
    id: int
    created_at: datetime
    created_by: str
    panels: list[KioskPanelOut] = Field(default_factory=list)


class StreamSetupKioskAssignment(BaseModel):
    kiosk_slug: Optional[str] = None
    kiosk_label: Optional[str] = None
    panel_title: Optional[str] = None
    panel_start: Optional[str] = None
    panel_end: Optional[str] = None
    panel_window_label: Optional[str] = None
    mode: Literal["results", "risk", "both"] = "both"

    @model_validator(mode="after")
    def validate_kiosk_label(self) -> "StreamSetupKioskAssignment":
        if self.kiosk_slug and not self.kiosk_label:
            self.kiosk_label = self.kiosk_slug.replace("-", " ").title()
        return self


class StreamSetupIn(BaseModel):
    stream_id: str
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    instrument_name: str
    instrument_manufacturer: Optional[str] = None
    instrument_model: Optional[str] = None
    method_name: str
    method_technique: Optional[str] = None
    parameter_name: str
    units: str
    material_name: str
    material_manufacturer: Optional[str] = None
    matrix: Optional[str] = None
    qc_level: str
    control_material_lot: str
    target_value: FiniteFloat
    sigma: FiniteFloat
    warning_limit_sd: FiniteFloat = 2.0
    action_limit_sd: FiniteFloat = 3.0
    min_value: Optional[FiniteFloat] = None
    max_value: Optional[FiniteFloat] = None
    risk_threshold_warn: int = 50
    risk_threshold_hold: int = 80
    bayes_warn_prob_threshold: Optional[FiniteFloat] = 0.25
    bayes_warn_consecutive: Optional[int] = 1
    bayes_hold_prob_threshold: Optional[FiniteFloat] = 0.8
    bayes_hold_consecutive: Optional[int] = 2
    effective_from: Optional[datetime] = None
    config_reason: Optional[str] = None
    prior_mu0: Optional[FiniteFloat] = None
    prior_kappa0: FiniteFloat = 1.0
    prior_alpha0: FiniteFloat = 2.0
    prior_beta0: Optional[FiniteFloat] = None
    prior_effective_from: Optional[datetime] = None
    kiosk: Optional[StreamSetupKioskAssignment] = None

    @field_validator(
        "stream_id",
        "instrument_name",
        "method_name",
        "parameter_name",
        "units",
        "material_name",
        "qc_level",
        "control_material_lot",
    )
    @classmethod
    def setup_text_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        return stripped

    @field_validator("sigma", "warning_limit_sd", "action_limit_sd", "prior_kappa0", "prior_beta0")
    @classmethod
    def positive_numbers(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value <= 0:
            raise ValueError("value must be > 0")
        return value

    @field_validator("prior_alpha0")
    @classmethod
    def alpha_gt_one(cls, value: float) -> float:
        if value <= 1:
            raise ValueError("prior_alpha0 must be > 1")
        return value

    @model_validator(mode="after")
    def statistical_bounds_are_ordered(self) -> "StreamSetupIn":
        if self.action_limit_sd < self.warning_limit_sd:
            raise ValueError("action_limit_sd must be >= warning_limit_sd")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError("min_value must be <= max_value")
        return self


class StreamSetupBatchIn(BaseModel):
    rows: list[StreamSetupIn]


class StreamSetupAction(BaseModel):
    entity: str
    action: Literal["create", "reuse", "version", "append"]
    detail: str


class StreamSetupPreviewRow(BaseModel):
    row: int
    stream_id: str
    valid: bool
    errors: list[str] = Field(default_factory=list)
    actions: list[StreamSetupAction] = Field(default_factory=list)
    canonical: Optional[StreamSetupIn] = None


class StreamSetupPreviewOut(BaseModel):
    valid: int
    invalid: int
    rows: list[StreamSetupPreviewRow]


class StreamSetupApplyRow(BaseModel):
    row: int
    stream_id: str
    stream: StreamConfigOut
    prior: PriorConfigOut
    control_material: ControlMaterialOut
    kiosk: Optional[KioskLayoutOut] = None
    actions: list[StreamSetupAction]


class StreamSetupApplyOut(BaseModel):
    applied: int
    rows: list[StreamSetupApplyRow]

===== STORAGE BASELINE/CONFIG REFERENCES =====
app/db_models.py-107-    qc_level: str = Field(index=True)
app/db_models.py-108-    matrix: Optional[str] = None
app/db_models.py-109-    manufacturer: Optional[str] = None
app/db_models.py-110-    active: bool = True
app/db_models.py-111-    created_at: datetime = Field(default_factory=utcnow)
app/db_models.py-112-    created_by: str = Field(default="system")
app/db_models.py-113-
app/db_models.py-114-
app/db_models.py:115:class StreamConfig(SQLModel, table=True):
app/db_models.py-116-    __table_args__ = (UniqueConstraint("stream_id", "version", name="uq_streamconfig_stream_version"),)
app/db_models.py-117-
app/db_models.py-118-    id: Optional[int] = Field(default=None, primary_key=True)
app/db_models.py-119-    stream_id: str = Field(index=True)
app/db_models.py-120-    version: int = Field(default=1, index=True)
app/db_models.py-121-    effective_from: datetime = Field(default_factory=utcnow, index=True)
app/db_models.py-122-    created_at: datetime = Field(default_factory=utcnow)
app/db_models.py-123-    created_by: str = Field(default="system")
--
app/db_models.py-145-    risk_threshold_hold: int = 80
app/db_models.py-146-    bayes_warn_prob_threshold: Optional[float] = None
app/db_models.py-147-    bayes_warn_consecutive: Optional[int] = None
app/db_models.py-148-    bayes_hold_prob_threshold: Optional[float] = None
app/db_models.py-149-    bayes_hold_consecutive: Optional[int] = None
app/db_models.py-150-    rule_set: dict[str, Any] = Field(default_factory=lambda: DEFAULT_RULE_SET.copy(), sa_column=Column(JSON))
app/db_models.py-151-
app/db_models.py-152-
app/db_models.py:153:class PriorConfig(SQLModel, table=True):
app/db_models.py-154-    __table_args__ = (UniqueConstraint("stream_id", "version", name="uq_priorconfig_stream_version"),)
app/db_models.py-155-
app/db_models.py-156-    id: Optional[int] = Field(default=None, primary_key=True)
app/db_models.py-157-    stream_id: str = Field(index=True)
app/db_models.py-158-    version: int = Field(default=1, index=True)
app/db_models.py-159-    effective_from: datetime = Field(default_factory=utcnow, index=True)
app/db_models.py-160-    created_at: datetime = Field(default_factory=utcnow)
app/db_models.py-161-    created_by: str = Field(default="system")
--
app/storage.py-15-    Capa,
app/storage.py-16-    CapaLink,
app/storage.py-17-    DEFAULT_RULE_SET,
app/storage.py-18-    IngestionReceipt,
app/storage.py-19-    Instrument,
app/storage.py-20-    Investigation,
app/storage.py-21-    InvestigationAlertLink,
app/storage.py-22-    Method,
app/storage.py:23:    PriorConfig,
app/storage.py-24-    QCEvent,
app/storage.py-25-    QCRecord,
app/storage.py:26:    StreamConfig,
app/storage.py-27-)
app/storage.py-28-from app.models import (
app/storage.py-29-    DuplicateStatus,
app/storage.py:30:    PriorConfigIn,
app/storage.py-31-    Role,
app/storage.py:32:    StreamConfigIn,
app/storage.py-33-    UnitConversionSpec,
app/storage.py-34-)
app/storage.py-35-from app.security import api_key_hash_needs_migration, api_key_lookup_hash, hash_api_key, legacy_sha256_hash, verify_api_key
app/storage.py-36-from app.stats import sample_mean_sd
app/storage.py-37-
app/storage.py-38-
app/storage.py-39-def utcnow() -> datetime:
app/storage.py-40-    return datetime.now(timezone.utc)
--
app/storage.py-92-            method_id=method_id,
app/storage.py-93-            units="%",
app/storage.py-94-            created_by="seed",
app/storage.py-95-        )
app/storage.py-96-        session.add(analyte)
app/storage.py-97-        session.commit()
app/storage.py-98-        session.refresh(analyte)
app/storage.py-99-
app/storage.py:100:    stream_exists = session.exec(select(StreamConfig).where(StreamConfig.stream_id == "hba1c-arch")).first()
app/storage.py-101-    if not stream_exists:
app/storage.py:102:        stream = StreamConfig(
app/storage.py-103-            stream_id="hba1c-arch",
app/storage.py-104-            analyte="HbA1c",
app/storage.py-105-            method="HPLC",
app/storage.py-106-            instrument="Architect",
app/storage.py-107-            site="Main Lab",
app/storage.py-108-            matrix=None,
app/storage.py-109-            qc_level="Level 1",
app/storage.py-110-            control_material_lot="LOT-001",
--
app/storage.py-119-            bayes_warn_consecutive=1,
app/storage.py-120-            bayes_hold_prob_threshold=0.8,
app/storage.py-121-            bayes_hold_consecutive=2,
app/storage.py-122-            created_by="seed",
app/storage.py-123-        )
app/storage.py-124-        session.add(stream)
app/storage.py-125-        session.commit()
app/storage.py-126-
app/storage.py:127:    prior_exists = session.exec(select(PriorConfig).where(PriorConfig.stream_id == "hba1c-arch")).first()
app/storage.py-128-    if not prior_exists:
app/storage.py:129:        prior = PriorConfig(
app/storage.py-130-            stream_id="hba1c-arch",
app/storage.py-131-            mu0=5.2,
app/storage.py-132-            kappa0=1.0,
app/storage.py-133-            alpha0=2.0,
app/storage.py-134-            beta0=0.25**2,
app/storage.py-135-            created_by="seed",
app/storage.py-136-        )
app/storage.py-137-        session.add(prior)
--
app/storage.py-170-                    description="local dev key",
app/storage.py-171-                )
app/storage.py-172-            )
app/storage.py-173-            session.commit()
app/storage.py-174-
app/storage.py-175-
app/storage.py-176-def create_stream_config(
app/storage.py-177-    session: Session,
app/storage.py:178:    payload: StreamConfigIn,
app/storage.py-179-    created_by: str,
app/storage.py-180-    *,
app/storage.py-181-    commit: bool = True,
app/storage.py:182:) -> StreamConfig:
app/storage.py-183-    current_version = session.exec(
app/storage.py:184:        select(StreamConfig.version)
app/storage.py:185:        .where(StreamConfig.stream_id == payload.stream_id)
app/storage.py:186:        .order_by(col(StreamConfig.version).desc())
app/storage.py-187-    ).first()
app/storage.py-188-    next_version = (current_version or 0) + 1
app/storage.py:189:    config = StreamConfig(
app/storage.py-190-        stream_id=payload.stream_id,
app/storage.py-191-        analyte=payload.analyte,
app/storage.py-192-        method=payload.method,
app/storage.py-193-        instrument=payload.instrument,
app/storage.py-194-        site=payload.site,
app/storage.py-195-        lab_bench=payload.lab_bench,
app/storage.py-196-        matrix=payload.matrix,
app/storage.py-197-        qc_level=payload.qc_level,
--
app/storage.py-234-    if commit:
app/storage.py-235-        session.commit()
app/storage.py-236-    else:
app/storage.py-237-        session.flush()
app/storage.py-238-    session.refresh(config)
app/storage.py-239-    return config
app/storage.py-240-
app/storage.py-241-
app/storage.py:242:def get_active_stream_config(session: Session, stream_id: str, at_time: datetime) -> Optional[StreamConfig]:
app/storage.py-243-    config = session.exec(
app/storage.py:244:        select(StreamConfig)
app/storage.py:245:        .where(StreamConfig.stream_id == stream_id, StreamConfig.effective_from <= at_time)
app/storage.py:246:        .order_by(col(StreamConfig.effective_from).desc(), col(StreamConfig.version).desc())
app/storage.py-247-    ).first()
app/storage.py-248-    if config:
app/storage.py-249-        return config
app/storage.py-250-    return session.exec(
app/storage.py:251:        select(StreamConfig)
app/storage.py:252:        .where(StreamConfig.stream_id == stream_id)
app/storage.py:253:        .order_by(col(StreamConfig.effective_from).asc(), col(StreamConfig.version).asc())
app/storage.py-254-    ).first()
app/storage.py-255-
app/storage.py-256-
app/storage.py:257:def list_stream_configs(session: Session, stream_id: str) -> list[StreamConfig]:
app/storage.py-258-    return list(
app/storage.py-259-        session.exec(
app/storage.py:260:            select(StreamConfig)
app/storage.py:261:            .where(StreamConfig.stream_id == stream_id)
app/storage.py:262:            .order_by(col(StreamConfig.version).desc())
app/storage.py-263-        ).all()
app/storage.py-264-    )
app/storage.py-265-
app/storage.py-266-
app/storage.py-267-def create_prior_config(
app/storage.py-268-    session: Session,
app/storage.py-269-    stream_id: str,
app/storage.py:270:    payload: PriorConfigIn,
app/storage.py-271-    created_by: str,
app/storage.py-272-    *,
app/storage.py-273-    commit: bool = True,
app/storage.py:274:) -> PriorConfig:
app/storage.py-275-    if payload.beta0 is None:
app/storage.py-276-        raise ValueError("beta0 must be resolved before creating a prior config")
app/storage.py-277-    current_version = session.exec(
app/storage.py:278:        select(PriorConfig.version)
app/storage.py:279:        .where(PriorConfig.stream_id == stream_id)
app/storage.py:280:        .order_by(col(PriorConfig.version).desc())
app/storage.py-281-    ).first()
app/storage.py-282-    next_version = (current_version or 0) + 1
app/storage.py:283:    config = PriorConfig(
app/storage.py-284-        stream_id=stream_id,
app/storage.py-285-        mu0=payload.mu0,
app/storage.py-286-        kappa0=payload.kappa0,
app/storage.py-287-        alpha0=payload.alpha0,
app/storage.py-288-        beta0=payload.beta0,
app/storage.py-289-        effective_from=payload.effective_from or utcnow(),
app/storage.py-290-        version=next_version,
app/storage.py-291-        created_by=created_by,
--
app/storage.py-294-    if commit:
app/storage.py-295-        session.commit()
app/storage.py-296-    else:
app/storage.py-297-        session.flush()
app/storage.py-298-    session.refresh(config)
app/storage.py-299-    return config
app/storage.py-300-
app/storage.py-301-
app/storage.py:302:def get_active_prior(session: Session, stream_id: str, at_time: datetime) -> Optional[PriorConfig]:
app/storage.py-303-    prior = session.exec(
app/storage.py:304:        select(PriorConfig)
app/storage.py:305:        .where(PriorConfig.stream_id == stream_id, PriorConfig.effective_from <= at_time)
app/storage.py:306:        .order_by(col(PriorConfig.effective_from).desc(), col(PriorConfig.version).desc())
app/storage.py-307-    ).first()
app/storage.py-308-    if prior:
app/storage.py-309-        return prior
app/storage.py-310-    return session.exec(
app/storage.py:311:        select(PriorConfig)
app/storage.py:312:        .where(PriorConfig.stream_id == stream_id)
app/storage.py:313:        .order_by(col(PriorConfig.effective_from).asc(), col(PriorConfig.version).asc())
app/storage.py-314-    ).first()
app/storage.py-315-
app/storage.py-316-
app/storage.py:317:def baseline_stats(session: Session, config: StreamConfig, at_time: datetime) -> Tuple[float, float]:
app/storage.py-318-    if config.baseline_start and config.baseline_end:
app/storage.py-319-        rows = session.exec(
app/storage.py-320-            select(QCRecord)
app/storage.py-321-            .where(
app/storage.py-322-                QCRecord.stream_id == config.stream_id,
app/storage.py-323-                QCRecord.include_in_stats == True,
app/storage.py-324-                QCRecord.timestamp >= config.baseline_start,
app/storage.py-325-                QCRecord.timestamp <= config.baseline_end,

===== INGESTION/BAYESIAN TEST INDEX =====
103:async def test_ingestion_quarantines_missing_stream(client: httpx.AsyncClient):
115:async def test_units_mismatch_quarantined_without_qc_record(client: httpx.AsyncClient):
133:async def test_future_timestamp_quarantined(client: httpx.AsyncClient):
146:async def test_out_of_bounds_value_quarantined(client: httpx.AsyncClient):
173:async def test_quarantine_queue_can_be_reviewed(client: httpx.AsyncClient):
208:async def test_action_signal_and_alert_created(client: httpx.AsyncClient):
252:async def test_comments_can_be_added_to_accepted_record_and_run(client: httpx.AsyncClient):
306:async def test_signal_alert_comments_link_to_alert_and_record(client: httpx.AsyncClient):
336:async def test_minimal_qc_payload_accepts_documented_optional_fields(client: httpx.AsyncClient):
351:async def test_manual_batch_multi_level_records_use_qc_records_endpoint(client: httpx.AsyncClient):
415:async def test_read_roles_can_read_without_mutating(client: httpx.AsyncClient):
462:async def test_invalid_api_key_does_not_scan_pbkdf2_keys(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch):
474:async def test_legacy_api_key_migrates_without_active_key_scan(client: httpx.AsyncClient):
496:async def test_audit_entries_include_actor_role_and_key(client: httpx.AsyncClient):
512:async def test_resolution_reason_required_for_statistical_inclusion_changes(client: httpx.AsyncClient):
546:async def test_alert_update_requires_reason_and_uses_backend_actor(client: httpx.AsyncClient):
573:async def test_concurrent_same_stream_ingestion_matches_posterior_history(client: httpx.AsyncClient):
608:async def test_bayesian_risk_includes_intervals_and_policy_state(client: httpx.AsyncClient):
623:async def test_bayesian_hold_requires_persistence(client: httpx.AsyncClient):
672:async def test_duplicate_detection(client: httpx.AsyncClient):
684:async def test_manual_entry_audited(client: httpx.AsyncClient):
697:async def test_bayesian_state_rebuilds_on_out_of_order_ingestion(client: httpx.AsyncClient):
740:async def test_bayesian_state_resets_on_prior_change(client: httpx.AsyncClient):

===== STANDARDS ROADMAP EXCERPT =====
Visualize credible intervals for the posterior mean and predictive intervals for future observations. These bands should be visually distinct from control limits.

### F2.7 Proficiency Testing and Measurement Uncertainty

Ingest proficiency-testing events, z-scores, assigned values, uncertainty, and bias evidence. Link method uncertainty budgets to stream configuration and Bayesian priors.

Feature scope:
- Treat proficiency testing and interlaboratory crosscheck data as a separate evidence workflow from routine QC charting.
- Store round/program metadata, provider, sample identifiers, assigned or accepted reference value, uncertainty, peer-group context, and received/reported timestamps.
- Compute and preserve z-score or equivalent performance metrics when the lab SOP defines the formula and acceptance criteria.
- Link PT/ILCP failures to alerts, investigations, CAPA, affected-method review, and auditor export packets.
- Do not treat PT/ILCP samples as ordinary posterior-updating QC points unless a lab-owned policy explicitly says to do so.

### F2.8 CAPA Effectiveness Automation

Let CAPAs define statistical effectiveness criteria and have the system propose pass/fail when post-CAPA data meets or misses the criteria.

## Execution Planning TODO: Advanced SQC Waves

Use these roadmap handles when generating execution plans in future chats. Each wave should produce its own plan before implementation; avoid bundling all advanced statistics into one slice.

Before any implementation wave, create a fit-for-purpose research note for the target method. The note should compare qcc-style feature coverage, open statistical references, lab SOP needs, and BAYESIANQC workflow constraints. Use qcc as a feature taxonomy and behavior reference only; do not copy, port, or translate GPL-licensed code into this project.

### qcc-Informed Gap Research Backlog

TODO: Determine which qcc-supported SPC features are worth implementing in BAYESIANQC, and in what form, before treating them as product commitments.

Research needed:
- Full Shewhart family fit: decide which of `xbar`, `R`, `S`, one-at-time, `p`, `np`, `c`, `u`, and `g` charts map to likely lab workflows.
- One-at-time / I-MR fit: determine whether moving-range sigma estimation should become the default for individual analytical-result streams or remain an optional baseline method.
- Attribute and count workflows: define the data model for defect, nonconforming-unit, nonconformity, and non-event counts before implementing `p`, `np`, `c`, `u`, or `g` charts.
- Phase I / Phase II semantics: decide how baseline/training data, monitoring data, exclusions, and new data should be represented in a validated lab workflow.
- Rule-set alignment: compare current Westgard-style rules with Western Electric-style rule variants and decide which built-in schemes and severity defaults should be offered.
- EWMA / CUSUM fit: determine parameters, warm-up, reset, and disposition semantics that make sense for lab QC rather than generic manufacturing SPC.
- OC curves, ARL, and process capability: decide whether these are analyst planning tools, validation-pack outputs, or routine dashboard features.
- Multivariate SPC: identify real use cases before adding Hotelling T2-style charts, covariance modeling, or ellipse views.
- Pareto and cause-effect tools: decide whether these belong in investigation/CAPA analytics rather than the core QC chart module.
- Overdispersion checks: determine whether binomial/Poisson diagnostics are needed for attribute/count QC streams.
- Overlay and comparison strategy: decide when overlaying charts is valid, when normalized overlays are required, and when aligned small multiples are safer.
- Context stratification analytics: determine which operator, actor, group, shift, site, bench, instrument, method, lot, and entry-source comparisons support process improvement without becoming naive blame metrics.
- Extension model: decide whether BAYESIANQC should expose custom chart/rule plugins or keep methods as reviewed, versioned first-party modules.

### W1 SQC Configuration Foundation

TODO: Build the versioned configuration layer that later chart families can share.

Plan must cover:
- Versioned chart family, rule set, baseline method, control-limit source, severity policy, affected-interval policy, and SOP reference.
- Effective-date behavior, retroactive reprocessing rules, and audit rationale.
- Fixtures that prove historical reconstruction uses the then-effective config.

### W2 Routine Shewhart Expansion

TODO: Expand beyond the current individual Levey-Jennings/Shewhart chart without overfitting to demo data.

Plan must cover:
- I-MR first for individual analytical results, including moving range calculation and optional MR chart view.
- X-bar/R/S only after subgroup data has a real data model and import path.
- Attribute charts (`p`, `np`, `c`, `u`) only when a defect/count workflow exists.
- Process capability only after baseline selection, distribution assumptions, and spec limits are explicit.

### W3 EWMA and CUSUM

TODO: Implement EWMA and CUSUM as configurable small-shift detectors.

Plan must cover:
- EWMA lambda, warm-up behavior, dynamic limits, reset policy, and chart overlay.
- CUSUM target, reference value, decision interval, one-sided/two-sided handling, reset policy, and chart overlay.
- Signal generation, disposition integration, audit evidence, and validation fixtures.

### W4 D6299-Style Precision and Bias Support

TODO: Add standards-aware evidence support for precision, bias, and site-performance workflows without embedding licensed standards text.

Plan must cover:
- Lab-owned SOP binding for precision/bias checks, accepted reference values, site precision, and bias acceptance criteria.
- Robust baseline and outlier handling, uncertainty inputs, and reportable evidence packets.
- Clear separation between "supports following D6299-style workflows" and "certifies compliance."

### W5 PT / ILCP Module

TODO: Build a dedicated proficiency-testing and interlaboratory crosscheck workflow.

Plan must cover:
- PT/ILCP round metadata, assigned or accepted values, uncertainty, peer-group summaries, z-scores or local performance metrics, and report packets.
- Links to alerts, investigations, CAPA, method review, and affected-result evaluation.
- Guardrails that keep PT/ILCP evidence distinct from routine QC posterior updates unless policy-approved.

### W6 Validation and Export Layer

TODO: Make advanced SQC outputs defensible for audit and future standards mapping.

Plan must cover:
- Backtesting with known fixtures for each chart/rule family.
- Reproducible export packets for chart state, rule firings, Bayesian risk, PT/ILCP evidence, investigations, and CAPA links.
- A release-note gap statement that says which methods are supported, partially supported, or not supported.

### W7 Chart Comparison and Context Analytics

TODO: Add comparison tools that help labs find process causes without overclaiming from raw counts.

Plan must cover:
- Overlay rules for same-stream, same-units, normalized z-score, QC-level, cross-instrument, and cross-method views.
- Operator/user/group analytics for signal, reject, quarantine, exclusion, retest, comment, investigation, and CAPA rates.
- Denominator, minimum-sample, and stratification controls by site, bench, instrument, method, analyte, QC level, lot, shift, and entry source.
- UI language that frames findings as training/process-review signals, not individual blame.

### W8 Enterprise Scope and Access Control

TODO: Add enterprise access scoping so users and service accounts only see or enter data for authorized sites, benches, instruments, and streams.


===== SRS QC EXCERPT =====
- **REQ-DATA-11**: Validate units and apply controlled unit conversions where configured (with audit trail).
- **REQ-DATA-12**: Detect impossible/illogical values (configurable bounds) and route to an exception queue.
- **REQ-DATA-13**: Detect duplicates (same stream + timestamp/run ID + value) with configurable handling.
- **REQ-DATA-14**: Store original raw ingested payloads for traceability and link to normalized records.

## 5. Master Data and Configuration (REQ-CONFIG)
- **REQ-CONFIG-01**: Maintain master data for instruments, analytes, methods, QC materials/levels, target values, allowable total error (TEa)/clinical relevance thresholds (optional), sites, operators (optional), and lots.
- **REQ-CONFIG-02**: Support per-stream configuration for chart type(s), rule set(s), control limit approach, baseline period selection, and Bayesian model selection.
- **REQ-CONFIG-03**: Version-control configuration objects (chart definitions, rule sets, priors) and prevent silent edits; changes are time-stamped and attributable.
- **REQ-CONFIG-04**: Support effective-date activation of new configurations so changes do not retroactively alter historical interpretations unless explicitly reprocessed with an auditable reason.

## 6. Frequentist Control Charts and Rules (REQ-FREQ)
### 6.1 Chart Generation
- **REQ-FREQ-01**: Generate Levey–Jennings/Shewhart charts with centerline and control limits for each QC stream.
- **REQ-FREQ-02**: Support warning limits and action limits (e.g., ±2 SD, ±3 SD) as configurable.
- **REQ-FREQ-03**: Support CUSUM and EWMA charts as optional chart types per stream.
- **REQ-FREQ-04**: Support rolling-window and fixed-baseline options for mean/SD estimation, configurable per stream.
- **REQ-FREQ-05**: Allow QC points to be marked as excluded from statistical calculations while remaining visible on charts with clear visual distinction and audit trail.

### 6.2 Limit Calculation and Baseline Management
- **REQ-FREQ-10**: Support baseline selection by date range, by run count, and by “stable period” criteria.
- **REQ-FREQ-11**: Compute mean and SD using at least classical (mean/SD) and robust (median/MAD or trimmed) methods, configurable.
- **REQ-FREQ-12**: Support rules for when to re-baseline (e.g., after CAPA closure, after lot change, after calibration change), configurable.
- **REQ-FREQ-13**: Preserve historical baselines and show which baseline applied to each plotted point.

### 6.3 Rule Evaluation (Signals)
- **REQ-FREQ-20**: Evaluate rule sets per incoming QC point and generate signals (violations) with rule ID and evidence.
- **REQ-FREQ-21**: Support common multirule schemes (e.g., 1-3s, 2-2s, R-4s, 4-1s, 10x) and allow custom rule definitions.
- **REQ-FREQ-22**: Support rule evaluation across multiple QC levels for the same analyte/instrument if configured.
- **REQ-FREQ-23**: Classify signals by severity (info/warn/action) based on rule type and local policy.

## 7. Bayesian Modeling Layer (REQ-BAYES)
### 7.1 Model Catalog (Minimum Viable Set)
- **REQ-BAYES-01**: Support Bayesian in-control mean/variance model for each QC stream (posterior for μ and σ).
- **REQ-BAYES-02**: Support Bayesian drift model (time-varying mean) for early detection of gradual shifts.
- **REQ-BAYES-03**: Support Bayesian lot-effect model (control-material lot and/or reagent lot) with partial pooling.
- **REQ-BAYES-04**: Support Bayesian multi-instrument hierarchical model (optional) to borrow strength across instruments for the same method/analyte.
- **REQ-BAYES-05**: Support an outlier/contamination component (e.g., mixture likelihood) or robust likelihood option for occasional gross errors.

### 7.2 Priors and Governance
- **REQ-BAYES-10**: Allow priors to be defined per stream and/or inherited from a template (per method/analyte).
- **REQ-BAYES-11**: Provide default priors suitable for startup/low-data conditions and allow explicit override with justification.
- **REQ-BAYES-12**: Version priors and record author, rationale, effective date, and approval status.

### 7.3 Inference and Outputs
- **REQ-BAYES-20**: Update posterior summaries upon new QC data ingestion (at least daily; optionally near-real-time).
- **REQ-BAYES-21**: Output for each point/time: posterior mean, credible interval for μ, posterior for σ, and posterior predictive distribution.
- **REQ-BAYES-22**: Compute exceedance probabilities at minimum:
  - P(|μ − target| > bias_threshold)
  - P(next_result outside frequentist action limits)
  - P(drift_rate > configured_delta) when drift model enabled
- **REQ-BAYES-23**: Surface a normalized Bayesian Risk Score (0–100) per stream and timestamp derived from configured probabilities.

### 7.4 Model Diagnostics
- **REQ-BAYES-30**: Provide basic model-fit diagnostics (posterior predictive checks summary, residual flags) suitable for QA review.
- **REQ-BAYES-31**: Detect model failure conditions (non-convergence/degenerate updates) and fall back to frequentist-only scoring with explicit warning and audit log.

## 8. Hybrid Decision Engine (REQ-HYB)
- **REQ-HYB-01**: Support hybrid policies combining frequentist signals and Bayesian risk metrics into dispositions.
- **REQ-HYB-02**: Provide policy templates, including:
  - Frequentist action rule OR Bayesian high-risk triggers escalation.
  - Frequentist marginal violation AND Bayesian low-risk ⇒ confirmatory QC required before CAPA.
  - No frequentist violation BUT Bayesian drift probability > threshold for N consecutive points ⇒ emerging drift investigation.
- **REQ-HYB-03**: Allow per-stream thresholds for Bayesian triggers (e.g., 0.8/0.9/0.95) and persistence requirements (N points).
- **REQ-HYB-04**: Support confirmatory testing workflows (repeat QC, second QC level, recalibration check) as defined actions triggered by hybrid policies.
- **REQ-HYB-05**: Generate a single, auditable disposition for each QC point/run (e.g., Accept, Accept-with-monitoring, Hold-for-review, Reject/Out-of-control).

## 9. Alerting, Routing, and Escalation (REQ-ALERT)
- **REQ-ALERT-01**: Create alert objects from frequentist signals, Bayesian risk triggers, or hybrid dispositions.
- **REQ-ALERT-02**: Support routing rules by site, instrument group, analyte criticality, and on-call schedule (configurable).
- **REQ-ALERT-03**: Support notifications via email and/or messaging integration (configurable), with throttling to prevent alert storms.
- **REQ-ALERT-04**: Support acknowledgment, assignment, due dates, and escalation if SLA is breached.

## 10. Investigation Workflow (REQ-INV)
- **REQ-INV-01**: Allow conversion of an alert into an Investigation record.
- **REQ-INV-02**: Capture problem statement, affected streams/runs, suspected causes, immediate containment, data reviewed, attachments, and decision outcome.
- **REQ-INV-03**: Link investigations to relevant events (calibration/maintenance/lot change) and display them on the chart timeline.
- **REQ-INV-04**: Support investigation outcomes: No issue found, Operator error, Instrument issue, Reagent/lot issue, Method issue, Environmental, Other (configurable taxonomy).

## 11. CAPA Module (REQ-CAPA)
### 11.1 CAPA Lifecycle

===== CURRENT CHANGE SUMMARY =====
 app/api_models.py                       |   4 +-
 app/bayesian.py                         | 158 +----------
 app/main.py                             |  19 ++
 app/models.py                           |  85 +++---
 app/services/stream_setups.py           |   7 +-
 app/storage.py                          |  16 +-
 app/stream_setup_models.py              |  34 ++-
 frontend/package-lock.json              | 488 ++++++++++++++++++++++++++++++++
 frontend/package.json                   |   4 +-
 frontend/src/api/schema.ts              |  19 +-
 frontend/src/pages/DatastreamSetup.vue  |   2 +-
 frontend/src/pages/Ingestion.vue        |   7 +-
 frontend/src/pages/ingestionWorkflow.ts |  13 +-
 pyproject.toml                          |   2 +
 requirements.txt                        |   2 +
 uv.lock                                 | 472 +++++++++++++++++++++++++++++-
 16 files changed, 1111 insertions(+), 221 deletions(-)
