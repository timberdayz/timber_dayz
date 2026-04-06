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

    assert investor["role_name"] == "投资人"
    assert "business-overview" in investor["permissions"]
    assert "personal-settings" in investor["permissions"]


@pytest.mark.asyncio
async def test_ensure_system_roles_inserts_missing_investor_role():
    existing_roles = [
        SimpleNamespace(role_code="admin"),
        SimpleNamespace(role_code="manager"),
        SimpleNamespace(role_code="operator"),
        SimpleNamespace(role_code="finance"),
        SimpleNamespace(role_code="tourist"),
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
    assert inserted_role.role_name == "投资人"
    assert fake_db.commit.await_count == 1
