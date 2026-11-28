"""费用 ``remark`` 的系统所有权 + 软删行不得被普通保存静默复活。

背景（2026-11-28）
------------------
* ``a_class.operating_costs.remark`` 一度**一列两义**：既是用户填的「备注」，
  又是占位行清理迁移写下的**批次标记**（``[占位行清理 2026-11-28]``）。
  实测 233 行里 113 行有 remark，**全部**是批次标记，人工写的 **0 条**。
  ⇒ 用户侧「备注」字段退役，``remark`` 收窄为**系统所有**的列。
* 原 UPSERT 的 ``remark = EXCLUDED.remark`` 会用客户端的空值**抹掉批次标记**，
  批次溯源就断了。
* 同一个 UPSERT 的 ``ON CONFLICT DO UPDATE`` **不重置** ``deleted_at``
  ⇒ 对已软删行写入会「**保存成功但行不可见**」，数据静默丢失；
  而且这条路径绕过了「恢复」的二次确认，能把占位行偷偷放回成本口径。

这两条都必须由契约守住，否则「备注退役」会把标记变成可被随手抹掉的软数据。
"""

import json
import re
from pathlib import Path

import pytest

ROUTER_PATH = Path("backend/domains/business/routers/expense_management.py")
SOURCE = ROUTER_PATH.read_text(encoding="utf-8")


def _slice(start_marker: str, end_marker: str) -> str:
    start = SOURCE.index(start_marker)
    end = SOURCE.index(end_marker, start)
    return SOURCE[start:end]


def _upsert_sql() -> str:
    """截取 ``create_or_update_expense`` 里那段 UPSERT SQL。"""
    start = SOURCE.index("INSERT INTO a_class.operating_costs")
    end = SOURCE.index("RETURNING", start)
    return SOURCE[start:end]


# ---------------------------------------------------------------------------
# 静态契约
# ---------------------------------------------------------------------------


def test_upsert_conflict_branch_never_overwrites_remark():
    """冲突更新分支不得改写 remark —— 它是系统所有的列。"""
    upsert = _upsert_sql()
    assert "remark = EXCLUDED.remark" not in upsert, (
        "remark 承载占位行清理的批次标记，冲突更新不得用 EXCLUDED 覆盖它"
    )


def test_upsert_insert_uses_empty_string_not_null_for_remark():
    """新行写 remark 时用空串，保持与迁移的 ``COALESCE(remark,'')=''`` 判定一致。"""
    upsert = _upsert_sql()
    assert "COALESCE(:note, '')" in upsert, (
        "新行 remark 必须落成空串（NULL 会让迁移的占位行判定失准）"
    )


def test_update_route_does_not_write_remark():
    """PUT 路由同样不得改写系统所有的 remark。"""
    update_block = _slice("async def update_expense(", "@router.delete")
    assert "remark = :note" not in update_block, (
        "更新路由不得用客户端的 note 覆盖系统标记"
    )


def test_post_detects_soft_deleted_conflict_row():
    """保存前必须探测同键软删行，并给出明确报错。"""
    post_block = _slice("async def create_or_update_expense(", "@router.put")
    assert "deleted_at IS NOT NULL" in post_block, (
        "保存前必须探测同 (platform_code, shop_id, year_month) 的软删行"
    )
    assert "该费用记录已被删除" in post_block, "命中软删行必须给出可读的报错文案"


def test_upsert_does_not_resurrect_soft_deleted_rows():
    """复活只能走恢复路由（带二次确认），普通保存不得自行复活。"""
    upsert = _upsert_sql()
    assert "deleted_at = NULL" not in upsert, (
        "UPSERT 不得自行复活软删行 —— 复活只走 /restore（前端有二次确认）"
    )


def test_restore_route_still_clears_the_batch_marker():
    """批次标记的清除仍然由恢复路由负责（否则标记会永远留在行上）。"""
    restore_block = SOURCE[SOURCE.index("async def restore_expense(") :]
    assert "remark" in restore_block, "恢复路由必须处理 remark（清批次标记）"
    assert re.search(r"remark\s*=\s*CASE", restore_block), (
        "恢复路由必须按批次标记前缀清空 remark"
    )


# ---------------------------------------------------------------------------
# 运行时契约：命中软删行必须 400
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return [self._row] if self._row is not None else []

    def scalars(self):
        return self

    def all(self):
        return [] if self._row is None else [self._row]


class _DB:
    """按 SQL 关键字分派的假会话。"""

    def __init__(self, soft_deleted: bool):
        self.soft_deleted = soft_deleted
        self.executed = []
        self.committed = False

    async def execute(self, query, params=None):
        sql = str(query)
        self.executed.append((sql, params))
        # ⚠️ 顺序要紧：UPSERT 的 RETURNING 子句里就有 ``is_locked as locked``，
        #    先判 is_locked 会把写入语句误判成锁检查。
        if "RETURNING" in sql:
            return _Result(
                _Row(
                    id=1,
                    shop_id=params["shop_id"],
                    platform_code=params["platform_code"],
                    year_month=params["year_month"],
                    rent=0.0,
                    marketing_fee=0.0,
                    utilities=0.0,
                    ai_token_cost=0.0,
                    labor_cost=0.0,
                    other_costs=0.0,
                    total_cost=0.0,
                    note="",
                    attachments=[],
                    locked=False,
                    created_at=None,
                    updated_at=None,
                )
            )
        if "is_locked" in sql:
            return _Result(_Row(locked=False))
        if "deleted_at IS NOT NULL" in sql:
            return _Result(
                _Row(deleted_at="2026-11-28 03:00:00") if self.soft_deleted else None
            )
        return _Result(None)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


def _user():
    from types import SimpleNamespace

    return SimpleNamespace(
        user_id=1,
        username="tester",
        is_superuser=False,
        roles=[SimpleNamespace(role_code="finance", role_name="finance")],
    )


def _request():
    from backend.schemas.expense import ExpenseCreateRequest

    return ExpenseCreateRequest(
        platform_code="shopee",
        shop_id="1292370001",
        year_month="2026-11",
        rent=10.0,
    )


@pytest.mark.asyncio
async def test_post_rejects_soft_deleted_row_with_400():
    """同键行已软删 ⇒ 400 + 明确指引，而不是「保存成功但看不见」。"""
    from backend.domains.business.routers import expense_management as module

    db = _DB(soft_deleted=True)
    result = await module.create_or_update_expense(
        request=_request(), db=db, current_user=_user()
    )

    assert getattr(result, "status_code", None) == 400, "命中软删行必须返回 400"
    body = json.loads(result.body.decode("utf-8"))
    message = json.dumps(body, ensure_ascii=False)
    assert "该费用记录已被删除" in message
    assert db.committed is False, "被拒绝的保存不得落库"


@pytest.mark.asyncio
async def test_post_allows_live_row():
    """没有软删行时，正常保存照常成功（不得被新守卫误伤）。"""
    from backend.domains.business.routers import expense_management as module

    db = _DB(soft_deleted=False)
    result = await module.create_or_update_expense(
        request=_request(), db=db, current_user=_user()
    )

    assert isinstance(result, dict), "正常保存必须返回普通字典（不是错误响应）"
    assert result["success"] is True
    assert db.committed is True
