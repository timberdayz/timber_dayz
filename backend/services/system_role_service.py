from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import DimRole


DEFAULT_SYSTEM_ROLES = {
    "admin": {
        "role_name": "管理员",
        "description": "系统管理员，拥有全部权限",
        "permissions": ["*"],
        "data_scope": "all",
    },
    "manager": {
        "role_name": "主管",
        "description": "业务主管，拥有经营与财务查看权限",
        "permissions": [
            "business-overview",
            "financial-management",
            "expense-management",
            "finance-reports",
            "employee-management",
            "my-income",
            "personal-settings",
        ],
        "data_scope": "all",
    },
    "operator": {
        "role_name": "操作员",
        "description": "运营执行角色",
        "permissions": [
            "business-overview",
            "sales-analysis",
            "store-management",
            "employee-management",
            "my-income",
            "personal-settings",
        ],
        "data_scope": "shop",
    },
    "finance": {
        "role_name": "财务",
        "description": "财务角色",
        "permissions": [
            "business-overview",
            "financial-management",
            "expense-management",
            "finance-reports",
            "finance-reports-detail",
            "personal-settings",
        ],
        "data_scope": "all",
    },
    "tourist": {
        "role_name": "游客",
        "description": "只读访客角色",
        "permissions": ["business-overview", "performance:read"],
        "data_scope": "self",
    },
    "investor": {
        "role_name": "投资人",
        "description": "投资人角色，只允许查看个人投资收益相关信息",
        "permissions": [
            "business-overview",
            "personal-settings",
            "user-guide",
            "video-tutorials",
            "faq",
            "my-follow-investment-income",
        ],
        "data_scope": "self",
    },
}


async def ensure_system_roles(db: AsyncSession) -> list[str]:
    result = await db.execute(select(DimRole))
    existing_roles = [
        role for role in result.scalars().all() if getattr(role, "role_code", None)
    ]
    existing_by_code = {role.role_code: role for role in existing_roles}

    touched_codes: list[str] = []
    for role_code, spec in DEFAULT_SYSTEM_ROLES.items():
        existing_role = existing_by_code.get(role_code)
        if existing_role is None:
            db.add(
                DimRole(
                    role_name=spec["role_name"],
                    role_code=role_code,
                    description=spec["description"],
                    permissions=json.dumps(spec["permissions"], ensure_ascii=False),
                    data_scope=spec["data_scope"],
                    is_active=True,
                    is_system=True,
                )
            )
            touched_codes.append(role_code)
            continue

        current_permissions = getattr(existing_role, "permissions", None) or ""
        needs_permission_repair = current_permissions in ("", "[]", "null", "None", None)
        if needs_permission_repair:
            existing_role.permissions = json.dumps(spec["permissions"], ensure_ascii=False)
            if not getattr(existing_role, "role_name", None):
                existing_role.role_name = spec["role_name"]
            if not getattr(existing_role, "description", None):
                existing_role.description = spec["description"]
            if not getattr(existing_role, "data_scope", None):
                existing_role.data_scope = spec["data_scope"]
            existing_role.is_system = True
            touched_codes.append(role_code)

    if touched_codes:
        await db.commit()

    return touched_codes
