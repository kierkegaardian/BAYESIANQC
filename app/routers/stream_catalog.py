from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, col, select

from app.db import get_session
from app.db_models import StreamConfig
from app.models import Permission, StreamCatalogOut
from app.rbac import UserContext, require_permission
from app.services.access_scopes import effective_scope, stream_scope_predicate

router = APIRouter(tags=["streams"])


@router.get("/stream-catalog", response_model=list[StreamCatalogOut])
def list_stream_catalog(
    user: UserContext = Depends(require_permission(Permission.READ)),
    session: Session = Depends(get_session),
) -> list[StreamCatalogOut]:
    """Return only current display fields; scheduled/governed details stay private."""
    scope = effective_scope(session, user)
    configs = session.exec(
        select(StreamConfig)
        .where(
            stream_scope_predicate(scope),
            StreamConfig.effective_from <= datetime.now(timezone.utc),
        )
        .order_by(
            col(StreamConfig.stream_id),
            col(StreamConfig.effective_from).desc(),
            col(StreamConfig.version).desc(),
        )
    ).all()
    latest: dict[str, StreamConfig] = {}
    for config in configs:
        latest.setdefault(config.stream_id, config)
    return [StreamCatalogOut.model_validate(config.model_dump()) for config in latest.values()]
