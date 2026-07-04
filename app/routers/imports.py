from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlmodel import Session

from app.db import get_session
from app.import_models import (
    CollectorTransferEventIn,
    CollectorTransferEventOut,
    ImportBatchDetailOut,
    ImportBatchOut,
    ImportBatchStatus,
    ImportCreateOut,
    ImportRowOut,
    ImportRowUpdate,
    ParserProfileIn,
    ParserProfileOut,
    ParserProfileStatus,
    ParserProfileUpdate,
)
from app.models import Permission
from app.rbac import UserContext, require_permission
from app.services.import_apply import apply_ready_rows
from app.services.import_outputs import batch_detail, get_batch, list_batches, row_out
from app.services.import_profiles import create_profile, list_profiles, update_profile
from app.services.imports import create_collector_event, create_import, update_row

router = APIRouter(tags=["qc-imports"])


@router.get("/qc/import-profiles", response_model=list[ParserProfileOut])
def list_import_profiles(
    status: Optional[ParserProfileStatus] = None,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[ParserProfileOut]:
    del user
    return list_profiles(session, status)


@router.post("/qc/import-profiles", response_model=ParserProfileOut)
def create_import_profile(
    payload: ParserProfileIn,
    user: UserContext = Depends(require_permission(Permission.MANAGE_IMPORTS)),
    session: Session = Depends(get_session),
) -> ParserProfileOut:
    return create_profile(session, payload, user)


@router.patch("/qc/import-profiles/{profile_id}", response_model=ParserProfileOut)
def patch_import_profile(
    profile_id: int,
    payload: ParserProfileUpdate,
    user: UserContext = Depends(require_permission(Permission.MANAGE_IMPORTS)),
    session: Session = Depends(get_session),
) -> ParserProfileOut:
    return update_profile(session, profile_id, payload, user)


@router.post("/qc/imports", response_model=ImportCreateOut)
def upload_import(
    file: UploadFile = File(...),
    source_id: Optional[str] = Form(default=None),
    source_path: Optional[str] = Form(default=None),
    profile_id: Optional[int] = Form(default=None),
    auto_apply: bool = Form(default=False),
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> ImportCreateOut:
    filename = file.filename or "upload.bin"
    data = file.file.read()
    batch = create_import(
        session,
        filename=filename,
        data=data,
        source_id=source_id,
        source_path=source_path,
        profile_id=profile_id,
        auto_apply=auto_apply,
        user=user,
    )
    return ImportCreateOut(batch=batch_detail(session, batch), collector_action=batch.collector_action)


@router.get("/qc/imports", response_model=list[ImportBatchOut])
def list_import_batches(
    status: Optional[ImportBatchStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[ImportBatchOut]:
    del user
    return list_batches(session, status, limit)


@router.get("/qc/imports/{batch_id}", response_model=ImportBatchDetailOut)
def get_import_batch(
    batch_id: int,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> ImportBatchDetailOut:
    del user
    return batch_detail(session, get_batch(session, batch_id))


@router.post("/qc/imports/{batch_id}/apply", response_model=ImportBatchDetailOut)
def apply_import_batch(
    batch_id: int,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> ImportBatchDetailOut:
    batch = apply_ready_rows(session, get_batch(session, batch_id), user)
    return batch_detail(session, batch)


@router.patch("/qc/imports/rows/{row_id}", response_model=ImportRowOut)
def patch_import_row(
    row_id: int,
    payload: ImportRowUpdate,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> ImportRowOut:
    return row_out(update_row(session, row_id, payload, user))


@router.post("/qc/collector/transfers/{transfer_id}/events", response_model=CollectorTransferEventOut)
def post_collector_transfer_event(
    transfer_id: str,
    payload: CollectorTransferEventIn,
    user: UserContext = Depends(require_permission(Permission.INGEST_QC)),
    session: Session = Depends(get_session),
) -> CollectorTransferEventOut:
    return create_collector_event(session, transfer_id, payload, user)
