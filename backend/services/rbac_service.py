from __future__ import annotations

import json
from typing import Any, Iterable

from modules.core.logger import get_logger

from backend.services.permission_service import get_permission_service

logger = get_logger(__name__)

ROLE_NAME_TO_CODE = {
    "管理员": "admin",
    "系统管理员": "admin",
    "admin": "admin",
    "主管": "manager",
    "经理": "manager",
    "manager": "manager",
    "操作员": "operator",
    "运营人员": "operator",
    "operator": "operator",
    "财务": "finance",
    "finance": "finance",
    "游客": "tourist",
    "tourist": "tourist",
    "投资人": "investor",
    "investor": "investor",
}


def normalize_role_code(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return ROLE_NAME_TO_CODE.get(text, ROLE_NAME_TO_CODE.get(text.lower(), text.lower()))


def parse_permission_ids(raw_permissions: Any) -> list[str]:
    if raw_permissions in (None, ""):
        return []
    if isinstance(raw_permissions, list):
        return [str(item).strip() for item in raw_permissions if str(item).strip()]
    if isinstance(raw_permissions, str):
        try:
            parsed = json.loads(raw_permissions)
        except json.JSONDecodeError:
            parsed = [raw_permissions]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        if parsed:
            return [str(parsed).strip()]
    return [str(raw_permissions).strip()]


def extract_role_codes(roles: Iterable[Any] | None) -> list[str]:
    codes: list[str] = []
    for role in roles or []:
        role_code = getattr(role, "role_code", None)
        role_name = getattr(role, "role_name", None)
        normalized = normalize_role_code(role_code or role_name)
        if normalized and normalized not in codes:
            codes.append(normalized)
    return codes


class RBACService:
    def __init__(self) -> None:
        self._permission_service = get_permission_service()

    def get_permission_catalog(self) -> list[dict[str, Any]]:
        return self._permission_service.get_all_permissions()

    def get_permission_ids(self) -> set[str]:
        return {item["id"] for item in self.get_permission_catalog()}

    def is_admin(self, user: Any) -> bool:
        if getattr(user, "is_superuser", False):
            return True
        return "admin" in extract_role_codes(getattr(user, "roles", []))

    def get_user_role_codes(self, user: Any) -> list[str]:
        return extract_role_codes(getattr(user, "roles", []))

    def resolve_permissions_from_roles(self, roles: Iterable[Any] | None) -> list[str]:
        role_list = list(roles or [])
        if "admin" in extract_role_codes(role_list):
            return ["*"]

        granted: list[str] = []
        known_permission_ids = self.get_permission_ids()
        for role in role_list:
            for permission_id in parse_permission_ids(getattr(role, "permissions", [])):
                normalized = str(permission_id).strip()
                if normalized == "*":
                    return ["*"]
                if normalized and normalized in known_permission_ids and normalized not in granted:
                    granted.append(normalized)
        return granted

    def build_auth_payload(self, user: Any) -> dict[str, Any]:
        return {
            "roles": self.get_user_role_codes(user),
            "permissions": self.resolve_permissions_from_roles(getattr(user, "roles", [])),
            "is_admin": self.is_admin(user),
        }

    def serialize_role(self, role: Any) -> dict[str, Any]:
        return {
            "id": role.role_id,
            "name": getattr(role, "role_name", ""),
            "role_code": normalize_role_code(getattr(role, "role_code", "")),
            "role_name": getattr(role, "role_name", ""),
            "description": getattr(role, "description", None),
            "permissions": parse_permission_ids(getattr(role, "permissions", [])),
            "is_active": bool(getattr(role, "is_active", True)),
            "is_system": bool(getattr(role, "is_system", False)),
            "created_at": getattr(role, "created_at", None),
        }


_rbac_service = RBACService()


def get_rbac_service() -> RBACService:
    return _rbac_service
