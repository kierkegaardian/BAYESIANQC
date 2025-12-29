#!/usr/bin/env python3
import argparse
import hashlib
import secrets

from sqlmodel import Session

from app.db import get_engine, init_db
from app.db_models import ApiKey
from app.models import Role


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
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    init_db()
    with Session(get_engine()) as session:
        session.add(ApiKey(key_hash=key_hash, role=role, description=args.description))
        session.commit()

    print("API key created.")
    print(f"Role: {role.value}")
    print(f"Key: {raw_key}")


if __name__ == "__main__":
    main()
