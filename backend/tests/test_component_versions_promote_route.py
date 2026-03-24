from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.routers.component_versions import promote_to_stable
from modules.core.db import ComponentVersion


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_promote_to_stable_route_works_with_async_session():
    target = ComponentVersion(
        id=88,
        component_name="miaoshou/login",
        version="1.0.1",
        file_path="modules/platforms/miaoshou/components/login_v1_0_1.py",
        is_stable=False,
        is_active=True,
        is_testing=True,
        updated_at=datetime.now(timezone.utc),
    )
    old_stable = ComponentVersion(
        id=77,
        component_name="miaoshou/login",
        version="1.0.0",
        file_path="modules/platforms/miaoshou/components/login.py",
        is_stable=True,
        is_active=True,
        is_testing=False,
        updated_at=datetime.now(timezone.utc),
    )

    async def _execute(stmt, *args, **kwargs):
        sql = str(stmt)
        if "WHERE component_versions.id =" in sql:
            return _ScalarResult(target)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [old_stable]))

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    response = await promote_to_stable(version_id=88, db=db)

    assert response["success"] is True
    assert target.is_stable is True
    assert target.is_testing is False
    assert old_stable.is_stable is False
    assert db.commit.await_count == 1
