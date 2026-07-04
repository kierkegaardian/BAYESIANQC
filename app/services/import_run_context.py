from __future__ import annotations

from enum import Enum
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.import_db_models import ImportBatch, ImportRow, ParserProfile
from app.import_models import ImportRowStatus


class ImportRunContextPolicy(str, Enum):
    REQUIRED = "required"
    ALLOW_PROVISIONAL = "allow_provisional"


RUN_CONTEXT_REQUIRED_WARNING = "run/backlog association is required"


def profile_run_context_policy(profile: ParserProfile | None) -> ImportRunContextPolicy:
    if profile is None:
        return ImportRunContextPolicy.REQUIRED
    value = profile.config.get("run_context_policy")
    if value == ImportRunContextPolicy.ALLOW_PROVISIONAL.value:
        return ImportRunContextPolicy.ALLOW_PROVISIONAL
    return ImportRunContextPolicy.REQUIRED


def profile_allows_provisional_run(profile: ParserProfile | None) -> bool:
    return profile_run_context_policy(profile) == ImportRunContextPolicy.ALLOW_PROVISIONAL


def fields_have_run_context(fields: dict[str, Any]) -> bool:
    run_id = fields.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return True
    return isinstance(fields.get("qc_backlog_item_id"), int)


def missing_required_run_context(profile: ParserProfile | None, fields: dict[str, Any]) -> bool:
    return not profile_allows_provisional_run(profile) and not fields_have_run_context(fields)


def run_context_warning(profile: ParserProfile | None, fields: dict[str, Any]) -> str | None:
    if missing_required_run_context(profile, fields):
        return RUN_CONTEXT_REQUIRED_WARNING
    return None


def enforce_run_context(profile: ParserProfile | None, fields: dict[str, Any]) -> None:
    warning = run_context_warning(profile, fields)
    if warning:
        raise HTTPException(status_code=422, detail=warning)


def profile_for_batch(session: Session, batch: ImportBatch) -> ParserProfile | None:
    if batch.parser_profile_id is None:
        return None
    return session.get(ParserProfile, batch.parser_profile_id)


def batch_for_row(session: Session, row: ImportRow) -> ImportBatch:
    batch = session.exec(select(ImportBatch).where(ImportBatch.id == row.batch_id)).first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return batch


def mark_row_needs_run_context(row: ImportRow) -> None:
    if RUN_CONTEXT_REQUIRED_WARNING not in row.warnings:
        row.warnings = [*row.warnings, RUN_CONTEXT_REQUIRED_WARNING]
    row.status = ImportRowStatus.NEEDS_REVIEW
