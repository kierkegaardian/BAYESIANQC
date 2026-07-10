from __future__ import annotations

from typing import Optional

from app.db_models import Capa, Investigation
from app.models import CapaOut, InvestigationOut


def investigation_out(
    investigation: Investigation,
    alert_id: Optional[str] = None,
) -> InvestigationOut:
    if investigation.id is None:
        raise RuntimeError("Investigation missing id")
    return InvestigationOut(
        id=investigation.id,
        stream_id=investigation.stream_id,
        status=investigation.status,
        problem_statement=investigation.problem_statement,
        suspected_cause=investigation.suspected_cause,
        containment=investigation.containment,
        data_reviewed=investigation.data_reviewed,
        outcome=investigation.outcome,
        decision=investigation.decision,
        created_at=investigation.created_at,
        updated_at=investigation.updated_at,
        created_by=investigation.created_by,
        alert_id=alert_id,
    )


def capa_out(
    capa: Capa,
    alert_id: Optional[str] = None,
    investigation_id: Optional[int] = None,
) -> CapaOut:
    if capa.id is None:
        raise RuntimeError("CAPA missing id")
    return CapaOut(
        id=capa.id,
        stream_id=capa.stream_id,
        status=capa.status,
        root_cause_category=capa.root_cause_category,
        corrective_actions=capa.corrective_actions,
        preventive_actions=capa.preventive_actions,
        owners=capa.owners,
        due_at=capa.due_at,
        verification_plan=capa.verification_plan,
        effectiveness_criteria=capa.effectiveness_criteria,
        created_at=capa.created_at,
        updated_at=capa.updated_at,
        created_by=capa.created_by,
        alert_id=alert_id,
        investigation_id=investigation_id,
    )
