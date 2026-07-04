#!/usr/bin/env python3
import argparse
import secrets

from sqlmodel import Session

from app.db import get_engine, init_db
from app.db_models import AccessGrant, ApiKey
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a BayesianQC API key.")
    parser.add_argument("--role", default="qc_analyst", help="Role for the key (default: qc_analyst)")
    parser.add_argument("--description", default="generated key", help="Description for the key")
    parser.add_argument("--key", help="Provide a specific key value (otherwise generated)")
    parser.add_argument("--grant-site", action="append", default=[], help="Grant access to a site")
    parser.add_argument("--grant-bench", action="append", default=[], help="Grant access to a lab bench")
    parser.add_argument("--grant-stream", action="append", default=[], help="Grant access to a stream id")
    parser.add_argument("--grant-group", action="append", default=[], help="Grant access to an assignment group")
    parser.add_argument("--grant-reason", default="api key creation", help="Reason stored on grant rows")
    args = parser.parse_args()

    try:
        role = Role(args.role)
    except ValueError as exc:
        raise SystemExit(f"Invalid role: {args.role}") from exc

    raw_key = args.key or secrets.token_urlsafe(24)
    key_hash = hash_api_key(raw_key)
    lookup_hash = api_key_lookup_hash(raw_key)

    init_db()
    with Session(get_engine()) as session:
        api_key = ApiKey(key_hash=key_hash, key_lookup_hash=lookup_hash, role=role, description=args.description)
        session.add(api_key)
        session.flush()
        if api_key.id is None:
            raise RuntimeError("API key id missing after insert")
        for site in args.grant_site:
            session.add(AccessGrant(api_key_id=api_key.id, site=site, created_by="create_api_key", reason=args.grant_reason))
        for bench in args.grant_bench:
            session.add(
                AccessGrant(api_key_id=api_key.id, lab_bench=bench, created_by="create_api_key", reason=args.grant_reason)
            )
        for stream in args.grant_stream:
            session.add(
                AccessGrant(api_key_id=api_key.id, stream_id=stream, created_by="create_api_key", reason=args.grant_reason)
            )
        for group in args.grant_group:
            session.add(
                AccessGrant(
                    api_key_id=api_key.id,
                    assignment_group=group,
                    created_by="create_api_key",
                    reason=args.grant_reason,
                )
            )
        session.commit()

    print("API key created.")
    print(f"Role: {role.value}")
    print(f"Grants: {len(args.grant_site) + len(args.grant_bench) + len(args.grant_stream) + len(args.grant_group)}")
    print(f"Key: {raw_key}")


if __name__ == "__main__":
    main()
