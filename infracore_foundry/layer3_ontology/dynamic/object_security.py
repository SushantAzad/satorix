from typing import Any
from .property_security import property_security


class ObjectSecurityFilter:
    def filter_object(
        self,
        object_type: str,
        properties: dict[str, Any],
        actor_role: str,
    ) -> dict[str, Any]:
        return property_security.apply_masking(object_type, properties, actor_role)

    def filter_list(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
        actor_role: str,
    ) -> list[dict[str, Any]]:
        return [self.filter_object(object_type, obj, actor_role) for obj in objects]


object_security_filter = ObjectSecurityFilter()
