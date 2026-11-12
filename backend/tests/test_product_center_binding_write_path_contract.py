"""SKU ↔ SPU **归属关系**的写入路径与取值域（2026-11-12 · 批次 D）。

背景
----
批次 B 把「归属是**一段有时效的关联**」这件事露了出来（``spu_effective_from``），
批次 C 把款 / 货的响应模型拆开了。批次 D 要做的是**让归属能被双向改动** ——
SKU 资料页里存量行的 SPU 单元格不再只读。

而要做到这一点，先得看清写入路径上真实存在的三个坑：

坑 1 · **归属没换，也在校验新款的合法性**
    ``_apply_bulk_sku_spu_binding`` 一上来就校验「这个款还能不能挂货」，
    **哪怕这次根本没有换款**。
    ⇒ 一个挂在**已淘汰款**下的 SKU，运营只想改个重量，保存时却收到
       422「SPU X 已淘汰或已删除，不能绑定新 SKU」——
       报错信息与他做的事毫无关系，而且**无从绕过**。

坑 2 · **归档口径有两个真相来源**
    换款归档写的是 ``binding_status='historical'``，
    而软删封存写的是 ``binding_status='inactive'``；
    恢复端点只认 ``'inactive'``。
    ⇒ 两个值本身合理（含义确实不同），但**取值域没有任何约束**，
       也没有任何一处把它们写在一起 ⇒ 迟早会漂移出第三、第四个值。

坑 3 · **同一天内换款被硬拒**
    ``starts_on <= binding.effective_from`` ⇒ 今天刚建的绑定今天改不了，
    运营只看到一句「effective_from must be later than…」，也不知道该怎么办。

本文件锁定：

* 三个归属状态的**唯一**定义处与三个判定条件（律 1）；
* **只有真的换款**才校验可绑定性；
* 同日换款 = 当天纠正，允许；
* ``binding_status`` 的取值域在 **ORM + 迁移**两层都有约束；
* 前端 SKU 存量行的 SPU 单元格可编辑（归属双向可达）。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services.product_spu_binding import (
    BINDING_STATUSES,
    CURRENT_BINDING_STATUS,
    HISTORICAL_BINDING_STATUS,
    INACTIVE_BINDING_STATUS,
    archived_binding_condition,
    current_binding_condition,
    render_binding_status_constraint,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = PROJECT_ROOT / "backend/domains/business/routers/product_center.py"
MIGRATION_PATH = (
    PROJECT_ROOT
    / "current_migrations/versions/20261228_bridge_spu_sku_binding_status_constraint.py"
)


# ---------------------------------------------------------------------------
# ① 真源：三个状态、三个判定条件
# ---------------------------------------------------------------------------


def test_three_binding_statuses_are_the_whole_domain():
    """归属状态**恰好三个**，且语义各不相同。"""
    assert set(BINDING_STATUSES) == {"active", "inactive", "historical"}
    assert (
        len(
            {CURRENT_BINDING_STATUS, INACTIVE_BINDING_STATUS, HISTORICAL_BINDING_STATUS}
        )
        == 3
    )


def test_current_condition_means_active_and_open_ended():
    sql = _render(current_binding_condition())

    assert "active" in sql
    assert "IS NULL" in sql.upper()
    assert "effective_to" in sql


def test_archived_condition_means_soft_delete_sealed():
    """软删封存 = **可复活** ⇒ 恢复端点找的就是它。"""
    sql = _render(archived_binding_condition())

    assert INACTIVE_BINDING_STATUS in sql
    assert HISTORICAL_BINDING_STATUS not in sql


def test_archived_condition_excludes_the_historical_status():
    """「可复活」的口径**只**含 ``inactive``，**不含** ``historical``。

    ⚠️ 换款归档是**历史证据**：复活它等于把历史改回去
       （也会把货挂回一个可能已经下线的款）。
    """
    sql = _render(archived_binding_condition())

    assert INACTIVE_BINDING_STATUS in sql
    assert HISTORICAL_BINDING_STATUS not in sql


def test_the_two_archive_semantics_are_written_by_different_paths():
    """换款归档写 ``historical``，软删封存写 ``inactive`` —— 两个值不可混用。

    ⚠️ 混用的后果不是「多一个状态」，而是**恢复端点会复活一条不该复活的关系**：
       恢复款时找的是 ``inactive``；若换款也写 ``inactive``，
       最早被捞起来的那条可能是几轮换款之前的旧关系。
    """
    source = ROUTER_PATH.read_text(encoding="utf-8")

    # 换款（批量保存通道）写 historical
    bulk = source[
        source.index("async def _apply_bulk_sku_spu_binding") : source.index(
            '@router.post("/api/skus/bulk"'
        )
    ]
    assert "HISTORICAL_BINDING_STATUS" in bulk
    assert "INACTIVE_BINDING_STATUS" not in bulk

    # 软删封存（soft_delete_spu / soft_delete_sku）写 inactive
    soft_delete = source[
        source.index("async def soft_delete_spu") : source.index(
            "async def restore_spu"
        )
    ]
    assert "INACTIVE_BINDING_STATUS" in soft_delete
    assert "HISTORICAL_BINDING_STATUS" not in soft_delete


def _render(clauses) -> str:
    from sqlalchemy.dialects import postgresql

    dialect = postgresql.dialect()
    return " ".join(
        str(clause.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
        for clause in clauses
    )


def test_rendered_constraint_covers_every_status():
    rendered = render_binding_status_constraint()

    for value in sorted(BINDING_STATUSES):
        assert "'%s'" % value in rendered, value


# ---------------------------------------------------------------------------
# ② 路由：不再手抄状态字面量
# ---------------------------------------------------------------------------


def test_router_does_not_hand_copy_the_historical_literal():
    """归档状态只从真源取。"""
    source = ROUTER_PATH.read_text(encoding="utf-8")

    assert '"historical"' not in source, "路由里仍有手抄的 historical 字面量"
    assert "'historical'" not in source


def test_router_imports_the_historical_constant():
    source = ROUTER_PATH.read_text(encoding="utf-8")

    assert "HISTORICAL_BINDING_STATUS" in source


# ---------------------------------------------------------------------------
# ③ 写入路径：只有真的换款才校验可绑定性
# ---------------------------------------------------------------------------


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _BindingDb:
    """够用的假会话：能查 SPU、查当前绑定、记录新增。"""

    def __init__(self, spu_row=None, current_binding=None):
        self.spu_row = spu_row
        self.current_binding = current_binding
        self.added = []

    async def get(self, model, key):
        if model.__name__ == "DimSpu":
            return self.spu_row
        return None

    async def execute(self, statement):
        return _RowsResult([self.current_binding] if self.current_binding else [])

    def add(self, row):
        self.added.append(row)


def _spu(spu="XH-A", biz_status="candidate", active=True):
    return SimpleNamespace(
        spu=spu,
        spu_name="Test SPU",
        biz_status=biz_status,
        active=active,
    )


def _sku():
    return SimpleNamespace(sku_id=7, sku_key="SKU-7")


def _binding(spu="XH-A", effective_from=date(2026, 3, 15)):
    return SimpleNamespace(
        id=1,
        spu=spu,
        sku_id=7,
        effective_from=effective_from,
        effective_to=None,
        binding_status=CURRENT_BINDING_STATUS,
    )


@pytest.mark.asyncio
async def test_unchanged_binding_does_not_revalidate_assignability():
    """归属**没换** ⇒ 不校验新款能不能挂货。

    否则一个挂在已淘汰款下的 SKU，运营改个重量都保存不了，
    而且报错说的是「不能绑定新 SKU」—— 与他做的事毫无关系。
    """
    from backend.domains.business.routers.product_center import (
        _apply_bulk_sku_spu_binding,
    )

    db = _BindingDb(
        spu_row=_spu("XH-A", biz_status="retired"),
        current_binding=_binding("XH-A"),
    )

    await _apply_bulk_sku_spu_binding(db, _sku(), "XH-A", None)

    assert db.added == [], "归属没换就不该写任何绑定"


@pytest.mark.asyncio
async def test_changed_binding_still_rejects_a_retired_spu():
    """**换了**款 ⇒ 仍然必须校验新款能不能挂货。"""
    from backend.domains.business.routers.product_center import (
        _apply_bulk_sku_spu_binding,
    )

    db = _BindingDb(
        spu_row=_spu("XH-B", biz_status="retired"),
        current_binding=_binding("XH-A"),
    )

    with pytest.raises(HTTPException) as exc:
        await _apply_bulk_sku_spu_binding(db, _sku(), "XH-B", None)

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_changed_binding_to_a_soft_deleted_spu_is_rejected():
    from backend.domains.business.routers.product_center import (
        _apply_bulk_sku_spu_binding,
    )

    db = _BindingDb(
        spu_row=_spu("XH-B", biz_status="retired", active=False),
        current_binding=_binding("XH-A"),
    )

    with pytest.raises(HTTPException) as exc:
        await _apply_bulk_sku_spu_binding(db, _sku(), "XH-B", None)

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_switching_spu_archives_the_old_relation_as_historical():
    """换款 = 旧关系归档（**历史**）+ 新关系生效。"""
    from backend.domains.business.routers.product_center import (
        _apply_bulk_sku_spu_binding,
    )

    db = _BindingDb(
        spu_row=_spu("XH-B"),
        current_binding=_binding("XH-A", effective_from=date(2026, 3, 15)),
    )

    await _apply_bulk_sku_spu_binding(db, _sku(), "XH-B", date(2026, 6, 1))

    assert db.current_binding.effective_to == date(2026, 6, 1)
    assert db.current_binding.binding_status == HISTORICAL_BINDING_STATUS
    assert len(db.added) == 1
    assert db.added[0].spu == "XH-B"


@pytest.mark.asyncio
async def test_same_day_switch_is_allowed():
    """今天刚建的绑定，今天改 —— 允许（当天纠正，不是改历史）。"""
    from backend.domains.business.routers.product_center import (
        _apply_bulk_sku_spu_binding,
    )

    db = _BindingDb(
        spu_row=_spu("XH-B"),
        current_binding=_binding("XH-A", effective_from=date.today()),
    )

    await _apply_bulk_sku_spu_binding(db, _sku(), "XH-B", date.today())

    assert len(db.added) == 1, "同日换款应该建出新的归属关系"


@pytest.mark.asyncio
async def test_switching_to_a_date_before_the_current_binding_is_rejected():
    """改到**过去**仍然拒绝 —— 那是在篡改历史。"""
    from backend.domains.business.routers.product_center import (
        _apply_bulk_sku_spu_binding,
    )

    db = _BindingDb(
        spu_row=_spu("XH-B"),
        current_binding=_binding("XH-A", effective_from=date(2026, 3, 15)),
    )

    with pytest.raises(HTTPException) as exc:
        await _apply_bulk_sku_spu_binding(db, _sku(), "XH-B", date(2026, 3, 1))

    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# ④ 取值域兜底：ORM + 迁移
# ---------------------------------------------------------------------------


def _orm_check_constraints() -> dict:
    from sqlalchemy import CheckConstraint

    from modules.core.db import BridgeSpuSku

    return {
        item.name: str(item.sqltext)
        for item in BridgeSpuSku.__table__.constraints
        if isinstance(item, CheckConstraint)
    }


def test_orm_declares_the_binding_status_constraint_from_the_ssot():
    constraints = _orm_check_constraints()

    assert (
        constraints.get("chk_bridge_spu_sku_binding_status")
        == render_binding_status_constraint()
    ), "ORM 的 binding_status 约束与真源不一致"


def test_migration_exists_and_chains_from_the_previous_head():
    assert MIGRATION_PATH.exists(), "缺 binding_status 取值域约束迁移"

    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert (
        'revision = "current_schema_20261228_bridge_spu_sku_binding_status_constraint"'
        in source
    )
    assert (
        'down_revision = "current_schema_20261227_dim_spu_lifecycle_constraints"'
        in source
    ), "迁移必须接在 20261227 之后"


def test_migration_renders_the_constraint_from_the_ssot():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "render_binding_status_constraint" in source, "迁移必须从真源渲染"
    assert "binding_status IN ('active'" not in source, "迁移里不得手抄状态清单"


def test_migration_renders_the_same_expression_as_orm():
    constraints = _orm_check_constraints()

    assert (
        constraints["chk_bridge_spu_sku_binding_status"]
        == render_binding_status_constraint()
    )
