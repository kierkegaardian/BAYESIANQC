from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Optional

from pydantic import BaseModel, field_validator


class EnterpriseSiteIn(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def site_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped

    @field_validator("code", "description")
    @classmethod
    def optional_text_stripped(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EnterpriseSiteOut(EnterpriseSiteIn):
    id: int
    created_at: datetime
    created_by: str


class EnterpriseSiteUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def update_site_name_required(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class LabAreaIn(BaseModel):
    site_id: int
    name: str
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def area_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped

    @field_validator("description")
    @classmethod
    def area_description_stripped(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class LabAreaOut(LabAreaIn):
    id: int
    site_name: str
    created_at: datetime
    created_by: str


class LabAreaUpdate(BaseModel):
    site_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def update_area_name_required(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class InstrumentIn(BaseModel):
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site_id: Optional[int] = None
    lab_area_id: Optional[int] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def instrument_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class InstrumentOut(InstrumentIn):
    id: int
    created_at: datetime
    created_by: str


class InstrumentUpdate(BaseModel):
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    site_id: Optional[int] = None
    lab_area_id: Optional[int] = None
    site: Optional[str] = None
    lab_bench: Optional[str] = None
    active: Optional[bool] = None


class MethodIn(BaseModel):
    name: str
    instrument_id: int
    technique: Optional[str] = None
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def method_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped


class MethodOut(MethodIn):
    id: int
    created_at: datetime
    created_by: str


class MethodUpdate(BaseModel):
    name: Optional[str] = None
    instrument_id: Optional[int] = None
    technique: Optional[str] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class AnalyteIn(BaseModel):
    name: str
    method_id: int
    units: Optional[str] = None
    result_resolution: Optional[float] = None
    description: Optional[str] = None
    active: bool = True

    @field_validator("name")
    @classmethod
    def analyte_name_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name is required")
        return stripped

    @field_validator("result_resolution")
    @classmethod
    def result_resolution_positive(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError("result_resolution must be > 0")
        return value


class AnalyteOut(AnalyteIn):
    id: int
    created_at: datetime
    created_by: str


class AnalyteUpdate(BaseModel):
    name: Optional[str] = None
    method_id: Optional[int] = None
    units: Optional[str] = None
    result_resolution: Optional[float] = None
    description: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("result_resolution")
    @classmethod
    def update_result_resolution_positive(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and (not isfinite(value) or value <= 0):
            raise ValueError("result_resolution must be > 0")
        return value


class TestCreateIn(BaseModel):
    instrument_id: int
    name: str
    technique: Optional[str] = None
    description: Optional[str] = None
    analyte_name: str
    analyte_units: str
    analyte_result_resolution: float
    analyte_description: Optional[str] = None
    active: bool = True

    @field_validator("name", "analyte_name", "analyte_units")
    @classmethod
    def test_text_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value is required")
        return stripped

    @field_validator("analyte_result_resolution")
    @classmethod
    def test_resolution_positive(cls, value: float) -> float:
        if not isfinite(value) or value <= 0:
            raise ValueError("analyte_result_resolution must be > 0")
        return value


class TestCreateOut(BaseModel):
    method: MethodOut
    analyte: AnalyteOut
