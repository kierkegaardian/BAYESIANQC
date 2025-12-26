from __future__ import annotations

from typing import Dict, List

from fastapi import Depends, HTTPException, status

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
    def __init__(self, role: Role):
        self.role = role

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, [])


def get_current_user(role: Role = Role.QC_ANALYST) -> UserContext:
    return UserContext(role=role)


def require_permission(permission: Permission):
    def dependency(user: UserContext = Depends(get_current_user)) -> UserContext:
        if not user.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency
