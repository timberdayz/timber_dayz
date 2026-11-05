"""rebuild_views.py 必须**立刻**自愈「被普通视图的 DROP ... CASCADE 连带删掉」的物化视图。

背景（本地实跑 + 生产 pg_depend 闭包都已确认）：
``sql/semantic/analytics_atomic.sql`` 开头是
``DROP VIEW IF EXISTS semantic.fact_analytics_atomic CASCADE``，
而 ``semantic.fact_analytics_atomic_mv`` **正是它的下游** ⇒ 重建这个普通视图
会把那个物化视图**连带删掉**。

而 ``mart.shop_day_kpi`` 的定义**要读那个物化视图** ⇒ 如果等到全部重建完
才自愈，``mart.shop_day_kpi`` 这一步就会直接失败：
``relation "semantic.fact_analytics_atomic_mv" does not exist``
（本地实跑确实失败过一次）。

所以自愈必须**当场**做：每重建一个目标就检查一次，有被连带删掉的立刻建回来。
"""

from __future__ import annotations

from typing import Any

import pytest


class _FakeNested:
    async def __aenter__(self) -> "_FakeNested":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    def begin_nested(self) -> _FakeNested:
        return _FakeNested()


class _FakeSessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


CASCADE_VICTIM = "semantic.fact_analytics_atomic_mv"
CASCADE_SOURCE = "semantic.fact_analytics_atomic"


def _patch_rebuild_views(
    monkeypatch,
    *,
    existing_plain_views: list[str],
    materialized_views: set[str],
    executed: list[str],
    drop_on_target: str | None = None,
) -> None:
    from scripts import rebuild_views

    async def _fake_view_targets(db: Any) -> list[str]:
        return list(existing_plain_views) + sorted(materialized_views)

    async def _fake_plain_view_targets(db: Any) -> list[str]:
        return list(existing_plain_views)

    async def _fake_materialized_view_targets(db: Any) -> list[str]:
        return sorted(materialized_views)

    async def _fake_ordered_view_targets(db: Any, wanted: list[str]) -> list[str]:
        return list(wanted)

    async def _fake_execute_sql_target(db: Any, target: str, **kwargs: Any) -> str:
        executed.append(target)
        if drop_on_target is not None and target == drop_on_target:
            # 模拟 DROP VIEW ... CASCADE 把下游物化视图连带删掉
            materialized_views.discard(CASCADE_VICTIM)
        if target == CASCADE_VICTIM:
            # 模拟资产文件建回来
            materialized_views.add(CASCADE_VICTIM)
        return "run_test"

    monkeypatch.setattr(
        rebuild_views, "AsyncSessionLocal", lambda: _FakeSessionContext(_FakeSession())
    )
    monkeypatch.setattr(rebuild_views, "_view_targets", _fake_view_targets)
    monkeypatch.setattr(rebuild_views, "_plain_view_targets", _fake_plain_view_targets)
    monkeypatch.setattr(
        rebuild_views, "_materialized_view_targets", _fake_materialized_view_targets
    )
    monkeypatch.setattr(
        rebuild_views, "_ordered_view_targets", _fake_ordered_view_targets
    )
    monkeypatch.setattr(rebuild_views, "execute_sql_target", _fake_execute_sql_target)


@pytest.mark.asyncio
async def test_rebuild_heals_cascade_deleted_materialized_view_immediately(
    monkeypatch, capsys
):
    """被 CASCADE 连带删掉的物化视图必须**当场**建回来（不能等到最后）。

    等到全部重建完再自愈就来不及了：后面的目标（比如 ``mart.shop_day_kpi``）
    要读那个物化视图，它不在就直接失败。
    """
    from scripts import rebuild_views

    executed: list[str] = []
    _patch_rebuild_views(
        monkeypatch,
        existing_plain_views=[CASCADE_SOURCE, "mart.shop_day_kpi"],
        materialized_views={CASCADE_VICTIM},
        executed=executed,
        drop_on_target=CASCADE_SOURCE,
    )

    rc = await rebuild_views.rebuild([], all_plain_views=True)

    assert rc == 0, "自愈成功时不该报错"
    assert CASCADE_VICTIM in executed, "被连带删掉的物化视图必须被重建回来"
    # 自愈必须发生在**下一个目标之前** —— 否则依赖它的目标会失败
    assert executed.index(CASCADE_VICTIM) < executed.index(
        "mart.shop_day_kpi"
    ), executed

    output = capsys.readouterr().out
    assert "RECREATED_MATERIALIZED_VIEWS:" in output
    assert CASCADE_VICTIM in output.split("RECREATED_MATERIALIZED_VIEWS:")[1]


@pytest.mark.asyncio
async def test_rebuild_fails_when_cascade_deleted_view_cannot_be_recreated(
    monkeypatch, capsys
):
    """建不回来就必须**失败** —— 不能留半坏的库上线。"""
    from scripts import rebuild_views

    executed: list[str] = []
    _patch_rebuild_views(
        monkeypatch,
        existing_plain_views=[CASCADE_SOURCE],
        materialized_views={CASCADE_VICTIM},
        executed=executed,
        drop_on_target=CASCADE_SOURCE,
    )

    async def _fake_execute_sql_target(db: Any, target: str, **kwargs: Any) -> str:
        executed.append(target)
        if target == CASCADE_SOURCE:
            raise RuntimeError("模拟重建失败")
        return "run_test"

    from scripts import rebuild_views as module

    monkeypatch.setattr(module, "execute_sql_target", _fake_execute_sql_target)

    rc = await module.rebuild([], all_plain_views=True)

    assert rc == 1, "重建失败必须返回非零退出码"
    output = capsys.readouterr().out
    assert "❌" in output


@pytest.mark.asyncio
async def test_rebuild_reports_rebuilt_targets(monkeypatch, capsys):
    """机器可读输出：部署脚本靠它复核「重建出来的视图确实存在」。"""
    from scripts import rebuild_views

    executed: list[str] = []
    _patch_rebuild_views(
        monkeypatch,
        existing_plain_views=["mart.shop_day_kpi"],
        materialized_views=set(),
        executed=executed,
    )

    rc = await rebuild_views.rebuild([], all_plain_views=True)

    assert rc == 0
    output = capsys.readouterr().out
    assert "REBUILT_TARGETS: mart.shop_day_kpi" in output
