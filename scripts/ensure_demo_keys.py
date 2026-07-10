#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlmodel import Session, col, delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_engine
from app.db_models import AccessGrant, ApiKey, StreamConfig
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key


def _required_secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def _ensure_key(session: Session, raw_key: str, role: Role, description: str) -> ApiKey:
    lookup_hash = api_key_lookup_hash(raw_key)
    api_key = session.exec(select(ApiKey).where(col(ApiKey.key_lookup_hash) == lookup_hash)).first()
    if api_key is None:
        api_key = ApiKey(
            key_hash=hash_api_key(raw_key),
            key_lookup_hash=lookup_hash,
            role=role,
            description=description,
            active=True,
        )
    else:
        api_key.key_hash = hash_api_key(raw_key)
        api_key.role = role
        api_key.description = description
        api_key.active = True
    session.add(api_key)
    session.flush()
    if api_key.id is None:
        raise RuntimeError("demo API key id was not assigned")
    return api_key


def _replace_grants(session: Session, api_key: ApiKey, stream_ids: list[str] | None) -> int:
    if api_key.id is None:
        raise RuntimeError("demo API key id is missing")
    session.execute(delete(AccessGrant).where(col(AccessGrant.api_key_id) == api_key.id))
    if stream_ids is None:
        session.add(
            AccessGrant(
                api_key_id=api_key.id,
                created_by="demo-bootstrap",
                reason="isolated synthetic demo bootstrap",
            )
        )
        return 1
    for stream_id in stream_ids:
        session.add(
            AccessGrant(
                api_key_id=api_key.id,
                stream_id=stream_id,
                created_by="demo-bootstrap",
                reason="synthetic stakeholder stream",
            )
        )
    return len(stream_ids)


def main() -> None:
    bootstrap_secret = _required_secret("BAYESIANQC_BOOTSTRAP_API_KEY")
    stakeholder_secret = _required_secret("BAYESIANQC_EDGE_API_KEY")

    with Session(get_engine()) as session:
        bootstrap = _ensure_key(session, bootstrap_secret, Role.ADMIN, "synthetic demo fixture bootstrap")
        stakeholder = _ensure_key(session, stakeholder_secret, Role.STAKEHOLDER, "Josh stakeholder edge identity")
        _replace_grants(session, bootstrap, None)
        stream_ids = sorted(
            set(
                session.exec(
                    select(StreamConfig.stream_id).where(col(StreamConfig.stream_id).like("demo-%"))
                ).all()
            )
        )
        stakeholder_grants = _replace_grants(session, stakeholder, stream_ids)
        session.commit()

    print(f"demo keys ready; stakeholder_stream_grants={stakeholder_grants}")


if __name__ == "__main__":
    main()
