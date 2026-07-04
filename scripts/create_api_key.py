#!/usr/bin/env python3
import argparse
import secrets

from sqlmodel import Session

from app.db import get_engine, init_db
from app.db_models import ApiKey
from app.models import Role
from app.security import api_key_lookup_hash, hash_api_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a BayesianQC API key.")
    parser.add_argument("--role", default="qc_analyst", help="Role for the key (default: qc_analyst)")
    parser.add_argument("--description", default="generated key", help="Description for the key")
    parser.add_argument("--key", help="Provide a specific key value (otherwise generated)")
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
        session.add(ApiKey(key_hash=key_hash, key_lookup_hash=lookup_hash, role=role, description=args.description))
        session.commit()

    print("API key created.")
    print(f"Role: {role.value}")
    print(f"Key: {raw_key}")


if __name__ == "__main__":
    main()
