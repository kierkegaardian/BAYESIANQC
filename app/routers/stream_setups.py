from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlmodel import Session

from app.db import get_session
from app.models import Permission
from app.rbac import UserContext, require_permission
from app.services.stream_setup_workbook import parse_workbook, workbook_template_bytes
from app.services.stream_setups import apply_stream_setups, preview_stream_setups
from app.stream_setup_models import StreamSetupApplyOut, StreamSetupBatchIn, StreamSetupPreviewOut

router = APIRouter(prefix="/stream-setups", tags=["stream-setups"])


@router.post("/preview", response_model=StreamSetupPreviewOut)
def preview_datastream_setup(
    payload: StreamSetupBatchIn,
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> StreamSetupPreviewOut:
    return preview_stream_setups(session, payload, user)


@router.post("/apply", response_model=StreamSetupApplyOut)
def apply_datastream_setup(
    payload: StreamSetupBatchIn,
    user: UserContext = Depends(require_permission(Permission.EDIT_CONFIG)),
    session: Session = Depends(get_session),
) -> StreamSetupApplyOut:
    return apply_stream_setups(session, payload, user)


@router.get("/template.xlsx")
def download_datastream_template(
    user: UserContext = Depends(require_permission(Permission.READ)),
) -> Response:
    del user
    return Response(
        content=workbook_template_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="bayesianqc-datastream-template.xlsx"'},
    )


@router.post("/import/preview", response_model=StreamSetupPreviewOut)
async def preview_datastream_import(
    file: UploadFile = File(...),
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> StreamSetupPreviewOut:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload must be an .xlsx workbook")
    batch, invalid_rows = parse_workbook(await file.read())
    preview = preview_stream_setups(session, batch, user)
    rows = invalid_rows + preview.rows
    return StreamSetupPreviewOut(
        valid=sum(1 for row in rows if row.valid),
        invalid=sum(1 for row in rows if not row.valid),
        rows=rows,
    )
