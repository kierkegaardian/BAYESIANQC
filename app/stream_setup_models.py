from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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
    site_id: Optional[int] = None
    lab_area_id: Optional[int] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    instrument_id: Optional[int] = None
    instrument_name: str
    instrument_manufacturer: Optional[str] = None
    instrument_model: Optional[str] = None
    method_id: Optional[int] = None
    method_name: str
    method_technique: Optional[str] = None
    analyte_id: Optional[int] = None
    parameter_name: str
    units: str
    control_material_id: Optional[int] = None
    material_name: str
    material_manufacturer: Optional[str] = None
    matrix: Optional[str] = None
    qc_level: str
    control_material_lot: str
    target_value: float
    sigma: float
    warning_limit_sd: float = 2.0
    action_limit_sd: float = 3.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    risk_threshold_warn: int = 50
    risk_threshold_hold: int = 80
    bayes_warn_prob_threshold: Optional[float] = 0.25
    bayes_warn_consecutive: Optional[int] = 1
    bayes_hold_prob_threshold: Optional[float] = 0.8
    bayes_hold_consecutive: Optional[int] = 2
    effective_from: Optional[datetime] = None
    config_reason: Optional[str] = None
    prior_mu0: Optional[float] = None
    prior_kappa0: float = 1.0
    prior_alpha0: float = 2.0
    prior_beta0: Optional[float] = None
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
