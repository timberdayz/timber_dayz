# -*- coding: utf-8 -*-
"""函数型目标的存在性核对 —— v7.13.5 部署失败的真实原因。

事故
----
``semantic.shop_identity_resolver`` 这个刷新目标建的是**函数**
``semantic.resolve_shop_identity``。函数不在 ``pg_class``，也不在
``information_schema`` 的表与视图清单里。

而资产盘点只查关系型对象 ⇒ 这个目标**永远**被判成 missing
⇒ 积压资产组被判 drift ⇒ **部署 bootstrap 失败、应用被回滚**，
而实际上那个函数好好地躺在库里。

这是「存在性核对」和「对象盘点」两处都要修的原因：
- 盘点（``_collect_existing_assets``）不查 ``pg_proc`` ⇒ 看不见函数；
- 核对（``_build_module_report`` / ``_target_exists``）用**逻辑目标名**去比，
  库里躺着的是**真实对象名** ⇒ 名字对不上。

守护
----
1. 资产盘点必须查 ``pg_proc``（函数）。
2. 逻辑目标名 ↔ 真实对象名是**双向**的：真实名存在 ⇒ 逻辑名也算存在。
3. 依赖展开确实会把函数型目标带进核心清单（这正是误报的触发路径），
   所以第 1、2 条不是「理论上的隐患」，而是每次部署都会踩。
"""

from __future__ import annotations

import pytest


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """按 SQL 内容分派结果，模拟资产盘点。"""

    def __init__(self, *, schemas=(), objects=(), functions=()):
        self._schemas = list(schemas)
        self._objects = list(objects)
        self._functions = list(functions)
        self.statements: list[str] = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "information_schema.schemata" in sql:
            return _FakeRowsResult([(name,) for name in self._schemas])
        # 盘点对象用的是**一条** UNION 语句（表 + 视图 + 物化视图 + 函数）
        if "information_schema.tables" in sql or "pg_matviews" in sql:
            return _FakeRowsResult(
                [(schema, name) for schema, name in self._objects]
                + [(schema, name) for schema, name in self._functions]
            )
        raise AssertionError(f"unexpected SQL: {sql}")


@pytest.mark.asyncio
async def test_asset_inventory_counts_functions_as_existing_objects():
    """资产盘点必须把**函数**也算成已存在对象。"""
    from backend.services.data_pipeline.dashboard_bootstrap import (
        _collect_existing_assets,
    )

    session = _FakeSession(
        schemas=["semantic"],
        objects=[("semantic", "fact_orders_atomic")],
        functions=[("semantic", "resolve_shop_identity")],
    )

    _, existing_objects = await _collect_existing_assets(session)

    assert "semantic.resolve_shop_identity" in existing_objects
    assert "semantic.fact_orders_atomic" in existing_objects
    # 盘点必须真的查了 pg_proc，否则函数永远进不来
    assert any("pg_proc" in sql for sql in session.statements)


@pytest.mark.asyncio
async def test_logical_target_counts_as_present_when_its_real_object_exists():
    """真实对象存在 ⇒ 逻辑目标也算存在。

    逻辑目标名（``semantic.shop_identity_resolver``）只是刷新流程里的代号，
    库里躺着的是真实名（``semantic.resolve_shop_identity``）
    ⇒ 比对前必须把名字对上，否则活着的目标被判 missing。
    """
    from backend.services.data_pipeline.dashboard_bootstrap import (
        _collect_existing_assets,
    )

    session = _FakeSession(
        schemas=["semantic"],
        objects=[],
        functions=[("semantic", "resolve_shop_identity")],
    )

    _, existing_objects = await _collect_existing_assets(session)

    assert "semantic.resolve_shop_identity" in existing_objects
    assert "semantic.shop_identity_resolver" in existing_objects


def test_function_target_really_reaches_the_core_plan():
    """函数型目标确实会被依赖展开带进核心清单 —— 误报的触发路径。

    若哪天依赖图变了、这个目标不再进核心清单，本条会失败并提醒同步更新
    下面的漂移用例（那时误报已经不会发生，但守护也应同步）。
    """
    from backend.services.data_pipeline.dashboard_bootstrap import _module_core_plan

    plan = _module_core_plan("inventory_backlog")

    assert "semantic.shop_identity_resolver" in plan


def test_function_target_present_does_not_mark_module_as_drift():
    """函数型目标存在时，模块不得被判 drift（否则部署被拦）。"""
    from backend.services.data_pipeline import dashboard_bootstrap

    core_plan = dashboard_bootstrap._module_core_plan("inventory_backlog")
    existing_objects = set(core_plan) - {"semantic.shop_identity_resolver"}
    existing_objects.add("semantic.resolve_shop_identity")

    report = dashboard_bootstrap._build_module_report(
        module_name="inventory_backlog",
        module_state={
            "status": "ready",
            "asset_fingerprint_applied": (
                dashboard_bootstrap._compute_targets_fingerprint(core_plan)
            ),
            "details_json": {},
        },
        existing_objects=existing_objects,
        active_refresh_run=None,
    )

    assert report["core_missing_objects"] == []
    assert report["status"] == "ready"
    assert report["ready"] is True


def test_missing_function_target_is_still_reported_as_drift():
    """函数真不在了 ⇒ 仍然要报 drift（别把检查改成永远通过）。"""
    from backend.services.data_pipeline import dashboard_bootstrap

    core_plan = dashboard_bootstrap._module_core_plan("inventory_backlog")
    existing_objects = set(core_plan) - {"semantic.shop_identity_resolver"}

    report = dashboard_bootstrap._build_module_report(
        module_name="inventory_backlog",
        module_state={
            "status": "ready",
            "asset_fingerprint_applied": (
                dashboard_bootstrap._compute_targets_fingerprint(core_plan)
            ),
            "details_json": {},
        },
        existing_objects=existing_objects,
        active_refresh_run=None,
    )

    assert "semantic.shop_identity_resolver" in report["core_missing_objects"]
    assert report["status"] == "drift"
    assert report["ready"] is False


@pytest.mark.asyncio
async def test_target_exists_helper_sees_functions_and_logical_names():
    """``_target_exists`` 必须既能认函数，又能认逻辑目标名。"""
    from backend.services.data_pipeline.refresh_validation import _target_exists

    class _ScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Session:
        def __init__(self, value):
            self._value = value

        async def execute(self, statement, params=None):
            sql = str(statement)
            if "pg_proc" in sql:
                assert "pg_class" in sql, "关系与函数都要查"
                # 逻辑目标名必须先解析成真实对象名再查
                assert params["object_name"] == "semantic.resolve_shop_identity"
                return _ScalarResult(self._value)
            raise AssertionError(f"unexpected SQL: {sql}")

    assert await _target_exists(_Session(True), "semantic.shop_identity_resolver")
    assert not await _target_exists(_Session(False), "semantic.shop_identity_resolver")
