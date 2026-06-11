from enum import Enum


class Role(str, Enum):
    PLATFORM_ADMINISTRATOR = "platform_administrator"
    ONTOLOGY_DESIGNER = "ontology_designer"
    DATA_STEWARD = "data_steward"
    ANALYST = "analyst"
    COMPLIANCE_HEAD = "compliance_head"
    RESTRICTED_VIEWER = "restricted_viewer"
    SYSTEM_PIPELINE = "system_pipeline"


ROLE_PERMISSIONS: dict[str, dict] = {
    Role.PLATFORM_ADMINISTRATOR: {
        "can_read_all": True,
        "can_write_all": True,
        "can_modify_schema": True,
        "can_grant_permissions": True,
        "can_execute_all_actions": True,
        "can_read_audit_log": True,
        "can_export_bulk": True,
        "can_run_queries": True,
        "can_delete_objects": True,
        "can_read_sensitive_properties": True,
    },
    Role.ONTOLOGY_DESIGNER: {
        "can_read_all": False,
        "can_write_all": False,
        "can_modify_schema": True,
        "can_grant_permissions": False,
        "can_execute_all_actions": False,
        "can_read_audit_log": False,
        "can_export_bulk": False,
        "can_run_queries": False,
        "can_delete_objects": False,
        "can_read_sensitive_properties": False,
    },
    Role.DATA_STEWARD: {
        "can_read_all": True,
        "can_write_all": True,
        "can_modify_schema": False,
        "can_grant_permissions": False,
        "can_execute_all_actions": False,
        "can_read_audit_log": False,
        "can_export_bulk": False,
        "can_run_queries": True,
        "can_delete_objects": False,
        "can_read_sensitive_properties": False,
    },
    Role.ANALYST: {
        "can_read_all": True,
        "can_write_all": False,
        "can_modify_schema": False,
        "can_grant_permissions": False,
        "can_execute_all_actions": False,
        "can_read_audit_log": False,
        "can_export_bulk": False,
        "can_run_queries": True,
        "can_delete_objects": False,
        "can_read_sensitive_properties": False,
    },
    Role.COMPLIANCE_HEAD: {
        "can_read_all": True,
        "can_write_all": False,
        "can_modify_schema": False,
        "can_grant_permissions": False,
        "can_execute_all_actions": False,
        "can_read_audit_log": False,
        "can_export_bulk": False,
        "can_run_queries": True,
        "can_delete_objects": False,
        "can_read_sensitive_properties": True,
    },
    Role.RESTRICTED_VIEWER: {
        "can_read_all": False,
        "can_write_all": False,
        "can_modify_schema": False,
        "can_grant_permissions": False,
        "can_execute_all_actions": False,
        "can_read_audit_log": False,
        "can_export_bulk": False,
        "can_run_queries": False,
        "can_delete_objects": False,
        "can_read_sensitive_properties": False,
    },
    Role.SYSTEM_PIPELINE: {
        "can_read_all": True,
        "can_write_all": True,
        "can_modify_schema": False,
        "can_grant_permissions": False,
        "can_execute_all_actions": False,
        "can_read_audit_log": False,
        "can_export_bulk": False,
        "can_run_queries": True,
        "can_delete_objects": False,
        "can_read_sensitive_properties": False,
    },
}


def get_role_permissions(role: str) -> dict:
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS[Role.RESTRICTED_VIEWER])
