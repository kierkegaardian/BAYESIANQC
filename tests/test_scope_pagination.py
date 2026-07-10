from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session

from app.db import get_engine
from app.db_models import AccessGrant, ApiKey, QCComment, QCEvent, QCRecordQuarantine, StreamConfig
from app.main import app
from app.models import EventType, QCCommentTargetType, QuarantineReason, Role
from app.security import api_key_lookup_hash, hash_api_key

SCOPED_KEY = "pagination-scope-key"
VISIBLE_STREAM = "hba1c-arch"
HIDDEN_STREAM = "pagination-hidden"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


def _seed_cross_scope_rows() -> None:
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as session:
        session.add(
            StreamConfig(
                stream_id=HIDDEN_STREAM,
                effective_from=now - timedelta(days=1),
                analyte="Hidden",
                method="Hidden",
                instrument="Hidden",
                qc_level="Level 1",
                control_material_lot="HIDDEN-LOT",
                units="U",
                target_value=10.0,
                sigma=1.0,
            )
        )
        key = ApiKey(
            key_hash=hash_api_key(SCOPED_KEY),
            key_lookup_hash=api_key_lookup_hash(SCOPED_KEY),
            role=Role.QC_ANALYST,
            description="pagination scope test",
        )
        session.add(key)
        session.flush()
        assert key.id is not None
        session.add(AccessGrant(api_key_id=key.id, stream_id=VISIBLE_STREAM, created_by="test"))

        for stream_id, created_at in (
            (HIDDEN_STREAM, now - timedelta(minutes=2)),
            (VISIBLE_STREAM, now - timedelta(minutes=1)),
        ):
            session.add(
                QCComment(
                    target_type=QCCommentTargetType.QC_RUN,
                    target_id=f"run-{stream_id}",
                    stream_id=stream_id,
                    body=stream_id,
                    actor="test",
                    created_at=created_at,
                )
            )

        for stream_id, created_at in (
            (VISIBLE_STREAM, now - timedelta(minutes=2)),
            (HIDDEN_STREAM, now - timedelta(minutes=1)),
        ):
            session.add(
                QCRecordQuarantine(
                    reason=QuarantineReason.MAPPING_FAILURE,
                    reason_detail="scope test",
                    stream_id=stream_id,
                    payload={},
                    context={},
                    failures=[],
                    actor="test",
                    created_at=created_at,
                )
            )
            session.add(
                QCEvent(
                    stream_id=stream_id,
                    event_type=EventType.MAINTENANCE,
                    timestamp=created_at,
                )
            )
        session.commit()


@pytest.mark.anyio
async def test_scope_filtering_happens_before_page_limit(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BAYESIANQC_ENFORCE_ACCESS_GRANTS", "1")
    _seed_cross_scope_rows()
    headers = {"X-API-Key": SCOPED_KEY}

    comments = await client.get("/qc/comments?limit=1", headers=headers)
    quarantine = await client.get("/qc/quarantine?limit=1", headers=headers)
    events = await client.get("/qc/events?limit=1", headers=headers)

    assert comments.status_code == quarantine.status_code == events.status_code == 200
    assert [row["stream_id"] for row in comments.json()] == [VISIBLE_STREAM]
    assert [row["stream_id"] for row in quarantine.json()] == [VISIBLE_STREAM]
    assert [row["stream_id"] for row in events.json()] == [VISIBLE_STREAM]
