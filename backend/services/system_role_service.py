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
    existing_codes = {
        role.role_code
        for role in result.scalars().all()
        if getattr(role, "role_code", None)
    }

    created_codes: list[str] = []
    for role_code, spec in DEFAULT_SYSTEM_ROLES.items():
        if role_code in existing_codes:
            continue

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
        created_codes.append(role_code)

    if created_codes:
        await db.commit()

    return created_codes
