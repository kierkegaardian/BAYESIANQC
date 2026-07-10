from app.models import Permission, Role
from app.rbac import ROLE_PERMISSIONS


def test_supervisor_retains_all_granular_workflow_permissions() -> None:
    permissions = set(ROLE_PERMISSIONS[Role.SUPERVISOR])

    assert {
        Permission.COMMENT_QC,
        Permission.RESOLVE_QC,
        Permission.MANAGE_ALERTS,
        Permission.MANAGE_INVESTIGATIONS,
        Permission.MANAGE_CAPAS,
    } <= permissions
