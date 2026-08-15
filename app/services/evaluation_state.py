from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlmodel import Session, col, select

from app.db_models import AlertRecord, PriorConfig, QCRecord, StreamConfig
from app.domain import Disposition
from app.evaluation_db_models import AlertEvaluationReconciliation, QCRecordEvaluation
from app.evaluation_replay import ReplayEvaluation, ReplayResult, replay_evaluations
from app.math.evaluation_engine import EVALUATION_ENGINE_VERSION
from app.models import BayesianRisk, FrequentistSignal


@dataclass(frozen=True)
class EvaluationState:
    records: tuple[QCRecord, ...]
    configs: tuple[StreamConfig, ...]
    priors: tuple[PriorConfig, ...]
    alerts: tuple[AlertRecord, ...]
    current_evaluations: tuple[QCRecordEvaluation, ...]
    reconciliations: tuple[AlertEvaluationReconciliation, ...]


@dataclass(frozen=True)
class RecordChange:
    evaluation: ReplayEvaluation
    old_disposition: str | None
    old_rule_ids: tuple[str, ...]
    old_risk_score: int | None


@dataclass(frozen=True)
class AlertPlan:
    record_id: int
    alert: AlertRecord | None
    outcome: str


def load_evaluation_state(session: Session, stream_id: str) -> EvaluationState:
    records = tuple(
        session.exec(
            select(QCRecord)
            .where(QCRecord.stream_id == stream_id)
            .order_by(col(QCRecord.timestamp).asc(), col(QCRecord.id).asc())
        ).all()
    )
    configs = tuple(
        session.exec(
            select(StreamConfig)
            .where(StreamConfig.stream_id == stream_id)
            .order_by(col(StreamConfig.effective_from).asc(), col(StreamConfig.version).asc())
        ).all()
    )
    priors = tuple(
        session.exec(
            select(PriorConfig)
            .where(PriorConfig.stream_id == stream_id)
            .order_by(col(PriorConfig.effective_from).asc(), col(PriorConfig.version).asc())
        ).all()
    )
    alerts = tuple(
        session.exec(
            select(AlertRecord)
            .where(AlertRecord.stream_id == stream_id)
            .order_by(col(AlertRecord.created_at).asc(), col(AlertRecord.id).asc())
        ).all()
    )
    current_ids = {
        *[record.current_evaluation_id for record in records if record.current_evaluation_id],
        *[alert.source_evaluation_id for alert in alerts if alert.source_evaluation_id],
    }
    current_evaluations = tuple(
        session.exec(
            select(QCRecordEvaluation).where(col(QCRecordEvaluation.id).in_(current_ids))
        ).all()
        if current_ids
        else []
    )
    alert_ids = [alert.id for alert in alerts if alert.id is not None]
    reconciliations = tuple(
        session.exec(
            select(AlertEvaluationReconciliation)
            .where(col(AlertEvaluationReconciliation.alert_record_id).in_(alert_ids))
            .order_by(col(AlertEvaluationReconciliation.created_at).asc())
        ).all()
        if alert_ids
        else []
    )
    return EvaluationState(
        records=records,
        configs=configs,
        priors=priors,
        alerts=alerts,
        current_evaluations=current_evaluations,
        reconciliations=reconciliations,
    )


def replay_state(state: EvaluationState) -> ReplayResult:
    if state.records and not state.configs:
        raise ValueError("stream has records but no effective configurations")
    return replay_evaluations(list(state.records), list(state.configs), list(state.priors))


def state_fingerprint(state: EvaluationState) -> str:
    payload = {
        "engine": EVALUATION_ENGINE_VERSION,
        "records": [record.model_dump(mode="json") for record in state.records],
        "configs": [config.model_dump(mode="json") for config in state.configs],
        "priors": [prior.model_dump(mode="json") for prior in state.priors],
        "alerts": [alert.model_dump(mode="json") for alert in state.alerts],
        "current_evaluations": [
            evaluation.model_dump(mode="json") for evaluation in state.current_evaluations
        ],
        "reconciliations": [
            reconciliation.model_dump(mode="json") for reconciliation in state.reconciliations
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def changed_records(state: EvaluationState, replay: ReplayResult) -> tuple[RecordChange, ...]:
    records_by_id = {record.id: record for record in state.records}
    changes: list[RecordChange] = []
    for evaluation in replay.evaluations:
        record = records_by_id[evaluation.record_id]
        new_signals = [signal.model_dump(mode="json") for signal in evaluation.signals]
        new_risk = evaluation.risk.model_dump(mode="json") if evaluation.risk is not None else None
        if (
            record.signals == new_signals
            and record.bayesian_risk == new_risk
            and record.disposition == evaluation.disposition.value
            and record.current_evaluation_id is not None
        ):
            continue
        old_signals = [FrequentistSignal.model_validate(signal) for signal in (record.signals or [])]
        old_risk = (
            BayesianRisk.model_validate(record.bayesian_risk)
            if record.bayesian_risk is not None
            else None
        )
        changes.append(
            RecordChange(
                evaluation=evaluation,
                old_disposition=record.disposition,
                old_rule_ids=tuple(signal.rule for signal in old_signals),
                old_risk_score=old_risk.risk_score if old_risk is not None else None,
            )
        )
    return tuple(changes)


def _bayesian_tier(risk: BayesianRisk | None, warn_required: int, hold_required: int) -> str:
    if risk is None:
        return "none"
    if risk.hold_streak >= hold_required:
        return "hold"
    if risk.warn_streak >= warn_required:
        return "warn"
    return "none"


def _semantic_signature(
    *,
    disposition: str,
    severity: str,
    signals: list[dict] | tuple[FrequentistSignal, ...],
    risk: BayesianRisk | None,
    warn_required: int,
    hold_required: int,
) -> tuple:
    parsed_signals = [
        signal if isinstance(signal, FrequentistSignal) else FrequentistSignal.model_validate(signal)
        for signal in signals
    ]
    rule_signature = tuple(sorted((signal.rule, signal.rule_variant) for signal in parsed_signals))
    return (
        disposition,
        severity,
        rule_signature,
        _bayesian_tier(risk, warn_required, hold_required),
    )


def alert_plan(
    state: EvaluationState,
    replay: ReplayResult,
    record_ids: set[int] | None = None,
) -> tuple[AlertPlan, ...]:
    latest_reconciliation: dict[int, AlertEvaluationReconciliation] = {}
    for reconciliation in state.reconciliations:
        latest_reconciliation[reconciliation.alert_record_id] = reconciliation
    active_by_record: dict[int, list[AlertRecord]] = {}
    for alert in state.alerts:
        if alert.id is None or alert.qc_record_id is None:
            continue
        last = latest_reconciliation.get(alert.id)
        if last is not None and last.outcome == "superseded":
            continue
        active_by_record.setdefault(alert.qc_record_id, []).append(alert)

    plans: list[AlertPlan] = []
    evaluations_by_id = {
        evaluation.id: evaluation
        for evaluation in state.current_evaluations
        if evaluation.id is not None
    }
    configs_by_id = {config.id: config for config in state.configs if config.id is not None}
    for evaluation in replay.evaluations:
        if record_ids is not None and evaluation.record_id not in record_ids:
            continue
        existing_alerts = active_by_record.get(evaluation.record_id, [])
        accepting = evaluation.disposition == Disposition.ACCEPT
        new_severity = (
            "action"
            if evaluation.disposition in {Disposition.REJECT, Disposition.HOLD_FOR_REVIEW}
            else "warn"
        )
        if not existing_alerts:
            if not accepting:
                plans.append(AlertPlan(evaluation.record_id, None, "create"))
            continue
        new_signature = _semantic_signature(
            disposition=evaluation.disposition.value,
            severity=new_severity,
            signals=evaluation.signals,
            risk=evaluation.risk,
            warn_required=evaluation.config.bayes_warn_consecutive or 1,
            hold_required=evaluation.config.bayes_hold_consecutive or 1,
        )
        confirmed = False
        for existing in existing_alerts:
            old_risk = BayesianRisk.model_validate(existing.bayesian_risk)
            source_evaluation = (
                evaluations_by_id.get(existing.source_evaluation_id)
                if existing.source_evaluation_id is not None
                else None
            )
            source_config = (
                configs_by_id.get(source_evaluation.stream_config_id)
                if source_evaluation is not None
                else evaluation.config
            ) or evaluation.config
            old_signature = _semantic_signature(
                disposition=existing.disposition,
                severity=existing.severity,
                signals=existing.signals,
                risk=old_risk,
                warn_required=source_config.bayes_warn_consecutive or 1,
                hold_required=source_config.bayes_hold_consecutive or 1,
            )
            outcome = "confirm" if old_signature == new_signature else "supersede"
            plans.append(AlertPlan(evaluation.record_id, existing, outcome))
            confirmed = confirmed or outcome == "confirm"
        if not accepting and not confirmed:
            plans.append(AlertPlan(evaluation.record_id, None, "create"))
    return tuple(plans)
