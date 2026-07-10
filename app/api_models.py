from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.domain import Disposition
from app.models import AlertOut, BayesianRisk, FrequentistSignal, IngestionResult, QCEventOut, QuarantineResult


class CsvRowError(BaseModel):
    row: int
    error: str


class CsvIngestResult(BaseModel):
    accepted: int = Field(ge=0)
    quarantined: int = Field(default=0, ge=0)
    errors: list[CsvRowError]
    results: list[IngestionResult | QuarantineResult]


class AlertSummary(BaseModel):
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    acknowledged: int = Field(ge=0)
    closed: int = Field(default=0, ge=0)


class InvestigationSummary(BaseModel):
    total: int = Field(ge=0)
    open: int = Field(ge=0)


class CapaSummary(BaseModel):
    total: int = Field(ge=0)
    open: int = Field(ge=0)


class ReportSummaryOut(BaseModel):
    alerts: AlertSummary
    investigations: InvestigationSummary
    capas: CapaSummary


class LotSegmentOut(BaseModel):
    control_material_lot: str
    start: datetime
    end: datetime
    count: int = Field(ge=0)


class QCRecordChartOut(BaseModel):
    id: int
    timestamp: datetime
    result_value: float
    control_material_lot: str
    include_in_stats: bool
    resolved_reason: Optional[str] = None
    resolved_at: Optional[datetime] = None
    signals: Optional[list[FrequentistSignal]] = None
    bayesian_risk: Optional[BayesianRisk] = None
    disposition: Optional[Disposition] = None


class StreamChartOut(BaseModel):
    records: list[QCRecordChartOut]
    events: list[QCEventOut]
    alerts: list[AlertOut]
    lot_segments: list[LotSegmentOut]
