from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.system_role_service import DEFAULT_SYSTEM_ROLES, ensure_system_roles


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_default_system_roles_include_investor():
    investor = DEFAULT_SYSTEM_ROLES["investor"]

    assert "business-overview" in investor["permissions"]
    assert "my-follow-investment-income" in investor["permissions"]
    assert "personal-settings" not in investor["permissions"]


@pytest.mark.asyncio
async def test_default_system_roles_do_not_keep_retired_frontend_page_permissions():
    manager_permissions = set(DEFAULT_SYSTEM_ROLES["manager"]["permissions"])
    operator_permissions = set(DEFAULT_SYSTEM_ROLES["operator"]["permissions"])
    finance_permissions = set(DEFAULT_SYSTEM_ROLES["finance"]["permissions"])

    for retired_permission in {
        "sales-analysis",
        "sales-detail",
        "customer-management",
        "store-management",
        "purchase-orders",
        "grn-management",
        "vendor-management",
        "invoice-management",
        "sales-reports",
        "inventory-reports",
        "vendor-reports",
        "finance-reports-detail",
        "sales-dashboard-v3",
    }:
        assert retired_permission not in manager_permissions
        assert retired_permission not in operator_permissions
        assert retired_permission not in finance_permissions


@pytest.mark.asyncio
async def test_ensure_system_roles_inserts_missing_investor_role():
    existing_roles = [
        SimpleNamespace(role_code="admin", permissions='["*"]'),
        SimpleNamespace(role_code="manager", permissions='["business-overview"]'),
        SimpleNamespace(role_code="operator", permissions='["business-overview"]'),
        SimpleNamespace(role_code="finance", permissions='["business-overview"]'),
        SimpleNamespace(role_code="tourist", permissions='["business-overview"]'),
    ]

    added = []

    fake_db = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(existing_roles)),
        add=added.append,
        commit=AsyncMock(),
    )

    created = await ensure_system_roles(fake_db)

    assert created == ["investor"]
    assert len(added) == 1
    inserted_role = added[0]
    assert inserted_role.role_code == "investor"
    assert fake_db.commit.await_count == 1


@pytest.mark.asyncio
async def test_ensure_system_roles_repairs_empty_permissions_for_existing_roles():
    existing_roles = [
        SimpleNamespace(
            role_code="operator",
            role_name="操作员",
            description="",
            permissions="[]",
            data_scope="",
            is_system=False,
        ),
        SimpleNamespace(
            role_code="admin",
            role_name="管理员",
            description="",
            permissions="[]",
            data_scope="",
            is_system=False,
        ),
    ]

    fake_db = SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(existing_roles)),
        add=lambda *_args, **_kwargs: None,
        commit=AsyncMock(),
    )

    touched = await ensure_system_roles(fake_db)

    assert "operator" in touched
    assert "admin" in touched
    assert existing_roles[0].permissions != "[]"
    assert existing_roles[1].permissions != "[]"
    assert existing_roles[0].is_system is True
    assert existing_roles[1].is_system is True
    assert fake_db.commit.await_count == 1
