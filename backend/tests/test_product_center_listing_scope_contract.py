"""商品中心列表端点的「包含范围」参数契约（2026-11-12）。

背景
----
``include_inactive`` 这一个参数名，在三个端点上含义各不相同：

* ``GET /api/spus``                   —— ``active IS TRUE``（SPU 用布尔软删标记）
* ``GET /api/product-categories``     —— ``status=='active' AND is_selectable``
  （**两件不同的业务事实**被挤进了同一个开关）
* ``GET /api/warehouse-storage-rules`` —— ``status == 'active'``

⇒ 同一个参数名、三种规则；
⇒ 品类那边还让调用方无法「只要停用的、但不要不可选的」。

前端还有**第三处**真相：``ProductCenter.vue`` 里硬编码的
``legacyUnselectableCodes``（``PET_DAILY``）—— 而数据库里
``PET_DAILY.is_selectable`` 本来就是 ``false``（实测：全表唯一一条
``is_selectable=false``）⇒ 同一件事两处定义，**改库不会改前端**。

本文件锁定三件事：

1. 每个端点的范围参数名要说清它控制什么；
2. 品类端点的「停用」与「不可选」**分属两个参数**；
3. 「不可选」只以数据库 ``is_selectable`` 为准，前端不再硬编码清单。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from backend.domains.business.routers.product_center import (
    list_product_categories,
    list_spus,
    list_warehouse_storage_rules,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_CENTER_VIEW = (
    PROJECT_ROOT / "frontend/src/domains/business/views/ProductCenter.vue"
)


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._rows[0] if self._rows else 0


class _CapturingDb:
    """记录执行的语句，回一批空行。"""

    def __init__(self):
        self.executed = []

    async def execute(self, statement):
        self.executed.append(statement)
        return _ScalarResult([])


def _where_sql(statement) -> str:
    whereclause = statement.whereclause
    if whereclause is None:
        return ""
    return str(whereclause.compile(compile_kwargs={"literal_binds": True}))


# ---------------------------------------------------------------------------
# ① SPU：范围参数要说清是「软删」
# ---------------------------------------------------------------------------


def test_spu_listing_uses_include_soft_deleted_not_include_inactive():
    """SPU 的软删是**布尔标记**，参数名必须说清它控制的是「已删除的款」。

    ⚠️ 之前叫 ``include_inactive`` —— 与「停用」同名却含义不同，
    是三个端点里最容易踩的那个。
    """
    params = inspect.signature(list_spus).parameters

    assert "include_soft_deleted" in params
    assert (
        "include_inactive" not in params
    ), "SPU 端点不该再用 include_inactive（与「停用」同名不同义）"


@pytest.mark.asyncio
async def test_spu_listing_soft_deleted_flag_controls_active_filter():
    db = _CapturingDb()
    await list_spus(
        db=db,
        keyword=None,
        biz_status=None,
        include_soft_deleted=False,
        page=1,
        page_size=20,
    )
    assert "active IS true" in _where_sql(db.executed[1])

    db_all = _CapturingDb()
    await list_spus(
        db=db_all,
        keyword=None,
        biz_status=None,
        include_soft_deleted=True,
        page=1,
        page_size=20,
    )
    assert _where_sql(db_all.executed[1]) == "", "含软删时不该再按 active 过滤"


# ---------------------------------------------------------------------------
# ② 品类：停用与不可选分属两个参数
# ---------------------------------------------------------------------------


def test_category_listing_separates_inactive_from_unselectable():
    """品类端点必须提供两个独立参数，调用方才能只要其中一样。"""
    params = inspect.signature(list_product_categories).parameters

    assert "include_inactive" in params, "停用与否仍由 include_inactive 控制"
    assert "include_unselectable" in params, "不可选与否必须有自己的参数"


@pytest.mark.asyncio
async def test_category_include_unselectable_controls_only_the_selectable_flag():
    """``include_unselectable`` 只管 ``is_selectable``，不碰 ``status``。"""
    db = _CapturingDb()
    await list_product_categories(
        db=db,
        level=None,
        parent_category_code=None,
        include_inactive=True,
        include_unselectable=False,
    )
    where = _where_sql(db.executed[0])
    assert "is_selectable" in where
    assert "status" not in where


@pytest.mark.asyncio
async def test_category_include_inactive_controls_only_the_status_flag():
    """``include_inactive`` 只管 ``status``，不碰 ``is_selectable``。"""
    db = _CapturingDb()
    await list_product_categories(
        db=db,
        level=None,
        parent_category_code=None,
        include_inactive=False,
        include_unselectable=True,
    )
    where = _where_sql(db.executed[0])
    assert "status" in where
    assert "is_selectable" not in where


@pytest.mark.asyncio
async def test_category_default_scope_filters_both_like_before():
    """默认口径与改动前一致：停用的与不可选的都过滤掉。"""
    db = _CapturingDb()
    await list_product_categories(
        db=db,
        level=None,
        parent_category_code=None,
        include_inactive=False,
        include_unselectable=False,
    )
    where = _where_sql(db.executed[0])
    assert "status" in where
    assert "is_selectable" in where


# ---------------------------------------------------------------------------
# ③ 仓储规则：语义本就明确，保留
# ---------------------------------------------------------------------------


def test_storage_rule_listing_keeps_include_inactive():
    """仓储规则的 ``include_inactive`` 本就表示「停用的规则」⇒ 语义明确，保留。"""
    params = inspect.signature(list_warehouse_storage_rules).parameters

    assert "include_inactive" in params


# ---------------------------------------------------------------------------
# ④ 前端：「不可选」只以数据库为准
# ---------------------------------------------------------------------------


def test_frontend_does_not_hardcode_unselectable_category_codes():
    """前端不得再硬编码不可选品类清单。

    ⚠️ 数据库里 ``PET_DAILY.is_selectable`` 本来就是 ``false``
    （全表唯一一条）⇒ 前端那份硬编码清单是**重复定义**：
    改库不会改前端，两边迟早漂移。

    ⚠️ 断言针对**硬编码集合**本身，而不是某个字符串是否出现 ——
    注释里提到这个编码是正常的（说明为什么删掉了它）。
    """
    source = PRODUCT_CENTER_VIEW.read_text(encoding="utf-8")

    assert "legacyUnselectableCodes" not in source, "前端仍硬编码不可选品类清单"
    hard_coded_set = re.search(r"new Set\(\s*\[[^\]]*[\"'][A-Z][A-Z0-9_]*[\"']", source)
    assert hard_coded_set is None, f"前端仍硬编码品类编码集合: {hard_coded_set}"


def test_frontend_category_option_disabled_still_uses_backend_is_selectable():
    """不可选仍要置灰 —— 但判据只能是后端下发的 ``is_selectable``。"""
    source = PRODUCT_CENTER_VIEW.read_text(encoding="utf-8")

    assert "!cat.is_selectable" in source
