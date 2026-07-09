#!/usr/bin/env python3
from __future__ import annotations

import os

from sqlmodel import Session, col, select

from app.db import get_engine
from app.db_models import ApiKey
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key


def main() -> None:
    raw_key = os.environ.get("BAYESIANQC_EDGE_ADMIN_API_KEY", "").strip()
    if not raw_key:
        raise SystemExit("BAYESIANQC_EDGE_ADMIN_API_KEY is required")

    description = os.environ.get("BAYESIANQC_EDGE_ADMIN_DESCRIPTION", "edge basic auth admin")
    lookup_hash = api_key_lookup_hash(raw_key)

    with Session(get_engine()) as session:
        api_key = session.exec(select(ApiKey).where(col(ApiKey.key_lookup_hash) == lookup_hash)).first()
        if api_key is None:
            api_key = ApiKey(
                key_hash=hash_api_key(raw_key),
                key_lookup_hash=lookup_hash,
                role=Role.ADMIN,
                description=description,
                active=True,
            )
        else:
            api_key.key_hash = hash_api_key(raw_key)
            api_key.key_lookup_hash = lookup_hash
            api_key.role = Role.ADMIN
            api_key.description = description
            api_key.active = True
        session.add(api_key)
        session.commit()

    print("edge admin key ready")


if __name__ == "__main__":
    main()
