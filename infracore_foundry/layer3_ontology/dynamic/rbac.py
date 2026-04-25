from .roles import get_role_permissions
from fastapi import HTTPException, status


class RBACMiddleware:
    def check_permission(self, actor_role: str, permission: str) -> bool:
        perms = get_role_permissions(actor_role)
        return perms.get(permission, False)

    def require_permission(self, actor_role: str, permission: str) -> None:
        if not self.check_permission(actor_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} requires higher role than {actor_role}",
            )

    def can_read(self, actor_role: str) -> bool:
        return self.check_permission(actor_role, "can_read_all") or actor_role in ("analyst", "data_steward", "compliance_head", "platform_administrator", "system")

    def can_write(self, actor_role: str) -> bool:
        return self.check_permission(actor_role, "can_write_all")

    def can_modify_schema(self, actor_role: str) -> bool:
        return self.check_permission(actor_role, "can_modify_schema")


rbac = RBACMiddleware()
