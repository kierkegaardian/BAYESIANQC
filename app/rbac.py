from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from app.db import get_session
from app.db_models import ApiKey
from app.models import Permission, Role


ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.QC_ANALYST: [Permission.INGEST_QC],
    Role.SUPERVISOR: [Permission.INGEST_QC, Permission.APPROVE],
    Role.QA_MANAGER: [Permission.INGEST_QC, Permission.APPROVE, Permission.OVERRIDE],
    Role.ADMIN: [Permission.INGEST_QC, Permission.APPROVE, Permission.OVERRIDE, Permission.EDIT_CONFIG],
    Role.AUDITOR: [],
    Role.DATA_STEWARD: [Permission.EDIT_CONFIG],
}


class UserContext:
    def __init__(self, role: Role, api_key_id: Optional[int] = None):
        self.role = role
        self.api_key_id = api_key_id

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, [])


def get_current_user(
    api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    session: Session = Depends(get_session),
) -> UserContext:
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    record = session.exec(select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active == True)).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return UserContext(role=record.role, api_key_id=record.id)


def require_permission(permission: Permission):
    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency
