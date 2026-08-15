from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Session, select

from app.db_models import AlertRecord, PosteriorState
from app.domain import Disposition
from app.evaluation_db_models import (
    AlertEvaluationReconciliation,
    EvaluationRun,
    QCRecordEvaluation,
)
from app.evaluation_models import (
    AlertReconciliationOutcome,
    EvaluationReprocessApplyOut,
    EvaluationTrigger,
)
from app.evaluation_replay import ReplayEvaluation, ReplayResult
from app.math.evaluation_engine import (
    BAYESIAN_METHOD,
    EVALUATION_ENGINE_VERSION,
    FREQUENTIST_METHOD,
    RISK_SEMANTICS,
)
from app.models import BayesianRisk
from app.services.evaluation_state import EvaluationState, alert_plan, changed_records


@dataclass(frozen=True)
class PersistedEvaluationRun:
    response: EvaluationReprocessApplyOut
    created_alerts_by_record: dict[int, AlertRecord]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _severity(disposition: Disposition) -> str:
    if disposition in {Disposition.REJECT, Disposition.HOLD_FOR_REVIEW}:
        return "action"
    return "warn"


def _snapshot(run_id: str, evaluation: ReplayEvaluation) -> QCRecordEvaluation:
    config = evaluation.config
    if config.id is None:
        raise RuntimeError("Stream config missing id")
    prior = evaluation.prior
    risk_json = evaluation.risk.model_dump(mode="json") if evaluation.risk is not None else None
    limits = evaluation.limits
    return QCRecordEvaluation(
        run_id=run_id,
        qc_record_id=evaluation.record_id,
        engine_version=EVALUATION_ENGINE_VERSION,
        frequentist_method=FREQUENTIST_METHOD,
        bayesian_method=BAYESIAN_METHOD,
        risk_semantics=RISK_SEMANTICS,
        stream_config_id=config.id,
        stream_config_version=config.version,
        prior_config_id=prior.id if prior is not None else None,
        prior_config_version=prior.version if prior is not None else None,
        threshold_mode=evaluation.threshold_mode,
        control_limit_source=limits.source,
        applied_centerline=limits.centerline,
        applied_sigma=limits.sigma,
        warning_limit_sd=limits.warning_limit_sd,
        action_limit_sd=limits.action_limit_sd,
        warning_lower=limits.warning_lower,
        warning_upper=limits.warning_upper,
        action_lower=limits.action_lower,
        action_upper=limits.action_upper,
        baseline_start=limits.baseline_start,
        baseline_end=limits.baseline_end,
        baseline_count=limits.baseline_count,
        signals=[signal.model_dump(mode="json") for signal in evaluation.signals],
        bayesian_risk=risk_json,
        disposition=evaluation.disposition.value,
    )


def _sync_posterior_state(session: Session, stream_id: str, replay: ReplayResult) -> None:
    state = session.exec(select(PosteriorState).where(PosteriorState.stream_id == stream_id)).first()
    if replay.posterior is None or replay.updated_at is None or replay.posterior_prior_id is None:
        if state is not None:
            session.delete(state)
        return
    values = {
        "mu_n": replay.posterior.mu,
        "kappa_n": replay.posterior.kappa,
        "alpha_n": replay.posterior.alpha,
        "beta_n": replay.posterior.beta,
        "n_obs": replay.posterior_n_obs,
        "updated_at": replay.updated_at,
        "prior_id": replay.posterior_prior_id,
        "config_id": replay.posterior_config_id,
        "warn_streak": replay.warn_streak,
        "hold_streak": replay.hold_streak,
    }
    if state is None:
        session.add(PosteriorState(stream_id=stream_id, **values))
        return
    for field, value in values.items():
        setattr(state, field, value)
    session.add(state)


def _new_alert(evaluation: ReplayEvaluation, evaluation_id: int) -> AlertRecord:
    risk = evaluation.risk or BayesianRisk(probability_outside_limits=0.0, risk_score=0)
    return AlertRecord(
        alert_id=str(uuid4()),
        stream_id=evaluation.config.stream_id,
        qc_record_id=evaluation.record_id,
        severity=_severity(evaluation.disposition),
        disposition=evaluation.disposition.value,
        signals=[signal.model_dump(mode="json") for signal in evaluation.signals],
        bayesian_risk=risk.model_dump(mode="json"),
        source_evaluation_id=evaluation_id,
    )


def persist_replay(
    session: Session,
    *,
    stream_id: str,
    state: EvaluationState,
    replay: ReplayResult,
    trigger: EvaluationTrigger,
    actor: str,
    reason: str,
    input_fingerprint: str,
    record_ids: set[int] | None = None,
) -> PersistedEvaluationRun:
    selected = [
        evaluation
        for evaluation in replay.evaluations
        if record_ids is None or evaluation.record_id in record_ids
    ]
    run_id = str(uuid4())
    changes = [
        change
        for change in changed_records(state, replay)
        if record_ids is None or change.evaluation.record_id in record_ids
    ]
    plans = alert_plan(state, replay, record_ids)
    run = EvaluationRun(
        run_id=run_id,
        stream_id=stream_id,
        trigger=trigger,
        engine_version=EVALUATION_ENGINE_VERSION,
        frequentist_method=FREQUENTIST_METHOD,
        bayesian_method=BAYESIAN_METHOD,
        risk_semantics=RISK_SEMANTICS,
        actor=actor,
        reason=reason,
        input_fingerprint=input_fingerprint,
        record_count=len(selected),
        changed_record_count=len(changes),
    )
    session.add(run)
    session.flush()

    records_by_id = {record.id: record for record in state.records}
    snapshots_by_record: dict[int, QCRecordEvaluation] = {}
    evaluations_by_record = {evaluation.record_id: evaluation for evaluation in selected}
    for evaluation in selected:
        snapshot = _snapshot(run_id, evaluation)
        session.add(snapshot)
        session.flush()
        if snapshot.id is None:
            raise RuntimeError("Evaluation snapshot missing id")
        record = records_by_id[evaluation.record_id]
        record.current_evaluation_id = snapshot.id
        record.signals = snapshot.signals
        record.bayesian_risk = snapshot.bayesian_risk
        record.disposition = snapshot.disposition
        session.add(record)
        snapshots_by_record[evaluation.record_id] = snapshot

    created_alerts: dict[int, AlertRecord] = {}
    create_records = {plan.record_id for plan in plans if plan.outcome == "create"}
    for record_id in create_records:
        snapshot = snapshots_by_record[record_id]
        if snapshot.id is None:
            raise RuntimeError("Evaluation snapshot missing id")
        alert = _new_alert(evaluations_by_record[record_id], snapshot.id)
        session.add(alert)
        session.flush()
        created_alerts[record_id] = alert

    confirmed = 0
    superseded = 0
    for plan in plans:
        if plan.alert is None:
            continue
        if plan.alert.id is None:
            raise RuntimeError("Alert record missing id")
        current = snapshots_by_record[plan.record_id]
        if current.id is None:
            raise RuntimeError("Evaluation snapshot missing id")
        outcome = (
            AlertReconciliationOutcome.CONFIRMED
            if plan.outcome == "confirm"
            else AlertReconciliationOutcome.SUPERSEDED
        )
        replacement = created_alerts.get(plan.record_id) if outcome == AlertReconciliationOutcome.SUPERSEDED else None
        session.add(
            AlertEvaluationReconciliation(
                run_id=run_id,
                alert_record_id=plan.alert.id,
                previous_evaluation_id=plan.alert.source_evaluation_id,
                current_evaluation_id=current.id,
                outcome=outcome,
                replacement_alert_record_id=replacement.id if replacement is not None else None,
                actor=actor,
                reason=reason,
            )
        )
        if outcome == AlertReconciliationOutcome.CONFIRMED:
            confirmed += 1
        else:
            superseded += 1

    _sync_posterior_state(session, stream_id, replay)
    run.completed_at = _utcnow()
    run.alerts_confirmed = confirmed
    run.alerts_superseded = superseded
    run.alerts_created = len(created_alerts)
    session.add(run)
    session.flush()
    return PersistedEvaluationRun(
        response=EvaluationReprocessApplyOut(
            run_id=run_id,
            stream_id=stream_id,
            engine_version=EVALUATION_ENGINE_VERSION,
            records_evaluated=len(selected),
            records_changed=len(changes),
            alerts_confirmed=confirmed,
            alerts_superseded=superseded,
            alerts_created=len(created_alerts),
        ),
        created_alerts_by_record=created_alerts,
    )
