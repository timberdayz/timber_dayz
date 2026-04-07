"""
审计服务测试：验证 result_status 入库
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.audit_service import AuditService


class _MockResult:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


def test_log_action_persists_result_status_in_changes_json():
    db = AsyncMock()
    added = {}

    async def _execute(_stmt):
        return _MockResult(SimpleNamespace(username="tester"))

    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()

    def _add(obj):
        added["obj"] = obj

    db.add = _add

    svc = AuditService()
    asyncio.run(
        svc.log_action(
            user_id=1,
            action="view",
            resource="me/income",
            ip_address="127.0.0.1",
            user_agent="pytest",
            resource_id="2026-03",
            details={"result_status": "linked_false"},
            db=db,
        )
    )

    log = added["obj"]
    assert "linked_false" in (log.action_description or "")
    assert log.changes_json is not None
    assert "result_status" in log.changes_json
