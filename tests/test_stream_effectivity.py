from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session

from app.db import get_engine
from app.db_models import PriorConfig, StreamConfig
from app.main import app
from app.storage import get_active_prior, get_active_stream_config

ADMIN = {"X-API-Key": "local-dev-key"}


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        yield api


def _future_stream(stream_id: str, effective_from: datetime) -> StreamConfig:
    return StreamConfig(
        stream_id=stream_id,
        version=1,
        effective_from=effective_from,
        analyte="Future analyte",
        method="Future method",
        instrument="Future instrument",
        qc_level="Level 1",
        control_material_lot="FUTURE-1",
        units="%",
        target_value=10.0,
        sigma=1.0,
    )


@pytest.mark.anyio
async def test_future_only_configs_are_not_active_or_listed_by_default(client: httpx.AsyncClient) -> None:
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=2)
    with Session(get_engine()) as session:
        session.add(_future_stream("future-only", future))
        session.add(
            PriorConfig(
                stream_id="future-only",
                version=1,
                effective_from=future,
                mu0=10.0,
                kappa0=1.0,
                alpha0=2.0,
                beta0=1.0,
            )
        )
        session.commit()
        assert get_active_stream_config(session, "future-only", now) is None
        assert get_active_prior(session, "future-only", now) is None

    active = await client.get("/streams", headers=ADMIN)
    scheduled = await client.get("/streams?include_scheduled=true", headers=ADMIN)
    assert active.status_code == scheduled.status_code == 200
    assert "future-only" not in {row["stream_id"] for row in active.json()}
    assert "future-only" in {row["stream_id"] for row in scheduled.json()}
