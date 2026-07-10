from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, JsonValue

from app.domain import Disposition
from app.model_enums import AlertStatus, CapaStatus, InvestigationStatus
from app.statistical_models import BayesianRisk, FrequentistSignal


class AlertOut(BaseModel):
    id: str
    stream_id: str
    created_at: datetime
    qc_record_id: Optional[int] = None
    qc_record_timestamp: Optional[datetime] = None
    signals: List[FrequentistSignal]
    bayesian_risk: BayesianRisk
    disposition: Disposition
    acknowledged: bool = False
    status: Optional[AlertStatus] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None


class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    acknowledged_by: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None
    reason: Optional[str] = None


class InvestigationBase(BaseModel):
    problem_statement: str
    suspected_cause: Optional[str] = None
    containment: Optional[str] = None
    data_reviewed: Optional[str] = None
    outcome: Optional[str] = None
    decision: Optional[str] = None
    alert_id: Optional[str] = None


class InvestigationIn(InvestigationBase):
    status: Optional[InvestigationStatus] = None
    reason: Optional[str] = None


class InvestigationOut(InvestigationBase):
    id: int
    stream_id: Optional[str] = None
    status: InvestigationStatus
    created_at: datetime
    updated_at: datetime
    created_by: str


class CapaBase(BaseModel):
    root_cause_category: Optional[str] = None
    corrective_actions: Optional[List[dict[str, JsonValue]]] = None
    preventive_actions: Optional[List[dict[str, JsonValue]]] = None
    owners: Optional[List[str]] = None
    due_at: Optional[datetime] = None
    verification_plan: Optional[str] = None
    effectiveness_criteria: Optional[dict[str, JsonValue]] = None
    alert_id: Optional[str] = None
    investigation_id: Optional[int] = None


class CapaIn(CapaBase):
    status: Optional[CapaStatus] = None
    reason: Optional[str] = None


class CapaOut(CapaBase):
    id: int
    stream_id: Optional[str] = None
    status: CapaStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
