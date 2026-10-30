"""Central RBAC policy: roles map to explicit permissions."""
from enum import Enum
from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User, UserRole


class Permission(str, Enum):
    REPOSITORY_READ = "repository:read"
    REPOSITORY_WRITE = "repository:write"
    TASK_READ = "task:read"
    TASK_WRITE = "task:write"
    AGENT_READ = "agent:read"
    AGENT_RUN = "agent:run"
    TOOL_READ = "tool:read"
    TOOL_INVOKE = "tool:invoke"
    USER_READ = "user:read"
    USER_MANAGE = "user:manage"
    SANDBOX_EXECUTE = "sandbox:execute"
    # --- Task lifecycle (RAD workflow) -------------------------------------
    TASK_CREATE = "task:create"
    MR_CREATE = "mr:create"
    MR_APPROVE = "mr:approve"
    MR_REJECT = "mr:reject"
    PLAN_APPROVE = "plan:approve"
    PLAN_REJECT = "plan:reject"
    DEPLOY_EXECUTE = "deploy:execute"

# The human review gates. These permissions belong to the ARCHITECT role *only*;
# ADMIN deliberately does not hold them (separation of duties), so they are
# subtracted from the "everything" set below.
REVIEW_PERMISSIONS = frozenset({
    Permission.MR_APPROVE, Permission.MR_REJECT,
    Permission.PLAN_APPROVE, Permission.PLAN_REJECT,
})

_AUTHOR_PERMISSIONS = frozenset({
    Permission.TASK_CREATE, Permission.MR_CREATE, Permission.DEPLOY_EXECUTE,
})

ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: frozenset(Permission) - REVIEW_PERMISSIONS,
    UserRole.DEVELOPER: _AUTHOR_PERMISSIONS | frozenset({
        Permission.REPOSITORY_READ, Permission.REPOSITORY_WRITE,
        Permission.TASK_READ, Permission.TASK_WRITE,
        Permission.AGENT_READ, Permission.AGENT_RUN,
        Permission.TOOL_READ, Permission.TOOL_INVOKE,
        Permission.SANDBOX_EXECUTE,
    }),
    UserRole.ARCHITECT: REVIEW_PERMISSIONS | frozenset({
        Permission.REPOSITORY_READ, Permission.TASK_READ,
        Permission.AGENT_READ, Permission.TOOL_READ,
    }),
    UserRole.VIEWER: frozenset({
        Permission.REPOSITORY_READ, Permission.TASK_READ,
        Permission.AGENT_READ, Permission.TOOL_READ,
    }),
}


def permissions_for_role(role: UserRole) -> list[str]:
    """Sorted permission strings for a role (exposed via /api/auth/me so the UI never duplicates the matrix)."""
    return sorted(p.value for p in ROLE_PERMISSIONS.get(role, frozenset()))


def has_permission(user: User, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(user.role, frozenset())


def require_permission(permission: Permission):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission.value}")
        return user
    return dependency


def require_role(*roles: UserRole):
    allowed = set(roles)
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return dependency
