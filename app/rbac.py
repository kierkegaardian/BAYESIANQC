from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.db import get_session
from app.db_models import ApiKey
from app.models import Permission, Role
from app.security import api_key_hash_needs_migration, api_key_lookup_hash, hash_api_key, legacy_sha256_hash, verify_api_key


ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.QC_ANALYST: [Permission.READ, Permission.INGEST_QC],
    Role.SUPERVISOR: [Permission.READ, Permission.INGEST_QC, Permission.APPROVE],
    Role.QA_MANAGER: [Permission.READ, Permission.INGEST_QC, Permission.APPROVE, Permission.OVERRIDE],
    Role.ADMIN: [
        Permission.READ,
        Permission.INGEST_QC,
        Permission.APPROVE,
        Permission.OVERRIDE,
        Permission.EDIT_CONFIG,
    ],
    Role.AUDITOR: [Permission.READ],
    Role.DATA_STEWARD: [Permission.READ, Permission.EDIT_CONFIG],
}


class UserContext:
    def __init__(self, role: Role, api_key_id: Optional[int] = None):
        self.role = role
        self.api_key_id = api_key_id

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, [])

    @property
    def permissions(self) -> list[Permission]:
        return ROLE_PERMISSIONS.get(self.role, [])

    @property
    def actor(self) -> str:
        key_id = self.api_key_id if self.api_key_id is not None else "unknown"
        return f"{self.role.value}:key-{key_id}"


def get_current_user(
    api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    session: Session = Depends(get_session),
) -> UserContext:
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    lookup_hash = api_key_lookup_hash(api_key)
    legacy_hash = legacy_sha256_hash(api_key)
    record = session.exec(
        select(ApiKey).where(
            col(ApiKey.active) == True,
            or_(col(ApiKey.key_lookup_hash) == lookup_hash, col(ApiKey.key_hash) == legacy_hash),
        )
    ).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    if not verify_api_key(api_key, record.key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    if api_key_hash_needs_migration(record.key_hash):
        record.key_hash = hash_api_key(api_key)
        record.key_lookup_hash = lookup_hash
        session.add(record)
        session.commit()
    elif record.key_lookup_hash != lookup_hash:
        record.key_lookup_hash = lookup_hash
        session.add(record)
        session.commit()
    return UserContext(role=record.role, api_key_id=record.id)


def require_permission(permission: Permission):
    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency
