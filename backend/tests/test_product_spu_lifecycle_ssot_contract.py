"""SPU 生命周期 **SSOT 守卫**（律 1「真源只能有一个，而且必须写在纸上」）。

背景（2026-11-12）
------------------
「这个 SPU 还活着吗 / 还能不能挂新 SKU」这**一个**业务事实，被两个字段分别编码：

* ``dim_spu.active``（布尔）—— 是否被软删；
* ``dim_spu.biz_status``（candidate/testing/promoted/retired）—— 业务成熟度。

而两者的写入约定**不一致**：

* 软删 / 恢复端点**捆绑**写两个字段
  （``product_center.py`` 的 ``soft_delete_spu`` / ``batch_soft_delete_spus`` /
  ``restore_spu``）；
* ``/api/spus/bulk`` 与 ``PATCH /api/spus/{spu}`` 的请求体里 ``active`` 与
  ``biz_status`` **各自独立可写** ⇒ 能造出 ``active=false +
  biz_status='candidate'`` 这种自相矛盾的行；
* ``dim_spu`` 上当时**没有任何 CHECK 约束** ⇒ 不变量只靠「大家记得一起写」维持；
* 前端 ``payloadSpu`` 整行回写 ⇒ 每次保存都把 ``active`` 原样提交一次。

⇒ 「这个 SPU 还能不能挂新 SKU」在系统里**没有唯一答案**。

建模决策（2026-11-12，Walter 拍板）
----------------------------------
**建模 A**：``active=false`` 必然是 ``retired``；但 ``retired`` 可以不删
（逻辑淘汰 —— 业务上不再经营，历史仍要留）。

⇒ 不变量：``active=false ⟹ biz_status='retired'``
⇒ 「可绑定」= ``biz_status`` 不是 ``retired`` ⇒ **单一条件**即可判定
   （依赖上面的不变量：已删的款必然是 retired，自动被排除）。

⇒ 本守卫测试断言：真源是唯一定义处，**ORM 约束 / 路由判定 / 迁移全部从它派生**。
   任何一处手抄 ⇒ 本文件必须红。
"""

from __future__ import annotations

from pathlib import Path

from backend.services.product_spu_lifecycle import (
    SPU_ASSIGNABLE_STATUSES,
    SPU_BIZ_STATUSES,
    SPU_BIZ_STATUS_RETIRED,
    render_spu_assignable_constraint,
    render_spu_biz_status_constraint,
    render_spu_lifecycle_constraint,
    spu_assignable_condition,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIMENSIONS_SCHEMA = PROJECT_ROOT / "modules/core/db/schema_parts/dimensions.py"
PRODUCT_CENTER_ROUTER = (
    PROJECT_ROOT / "backend/domains/business/routers/product_center.py"
)
MIGRATION_PATH = (
    PROJECT_ROOT
    / "current_migrations/versions/20261227_dim_spu_lifecycle_constraints.py"
)


# ---------------------------------------------------------------------------
# ① 真源自身
# ---------------------------------------------------------------------------


def test_biz_status_set_covers_the_four_business_states():
    assert set(SPU_BIZ_STATUSES) == {
        "candidate",
        "testing",
        "promoted",
        "retired",
    }


def test_retired_is_the_only_non_assignable_state():
    """可绑定状态集合 = 全集去掉 ``retired`` —— 这是「可绑定」的唯一口径。"""
    assert set(SPU_ASSIGNABLE_STATUSES) == set(SPU_BIZ_STATUSES) - {SPU_BIZ_STATUS_RETIRED}


def test_assignable_states_are_a_subset_of_all_states():
    assert set(SPU_ASSIGNABLE_STATUSES) <= set(SPU_BIZ_STATUSES)


def test_rendered_biz_status_constraint_contains_every_state():
    rendered = render_spu_biz_status_constraint()

    missing = [
        value for value in sorted(SPU_BIZ_STATUSES) if "'%s'" % value not in rendered
    ]
    assert not missing, f"渲染的 biz_status 约束漏掉状态: {missing}"


def test_rendered_lifecycle_constraint_encodes_the_modelling_a_invariant():
    """建模 A 的不变量：``active=false`` 必须是 ``retired``。

    渲染出来必须是「active 为真就放行，为假就必须 retired」。
    """
    rendered = render_spu_lifecycle_constraint()

    assert "active" in rendered
    assert SPU_BIZ_STATUS_RETIRED in rendered
    # 「active OR biz_status='retired'」—— active 为真时不约束，为假时强制 retired
    assert rendered.count("OR") == 1, f"不变量表达式形态不对: {rendered}"


def test_renderers_are_deterministic():
    """同一份真源必须永远渲染出同一串 SQL ⇒ 迁移可按字符串比对。"""
    assert render_spu_biz_status_constraint() == render_spu_biz_status_constraint()
    assert render_spu_lifecycle_constraint() == render_spu_lifecycle_constraint()
    assert render_spu_assignable_constraint() == render_spu_assignable_constraint()


def test_assignable_constraint_excludes_retired_and_keeps_the_rest():
    rendered = render_spu_assignable_constraint()

    assert SPU_BIZ_STATUS_RETIRED not in rendered
    for value in sorted(SPU_ASSIGNABLE_STATUSES):
        assert "'%s'" % value in rendered, f"可绑定约束漏掉状态: {value}"


def test_assignable_condition_is_one_shared_sqlalchemy_expression():
    """查询与校验必须引用**同一个**条件对象 ⇒ 不可能各写一份而漂移。"""
    first = spu_assignable_condition()
    second = spu_assignable_condition()

    assert str(first) == str(second)

    # ⚠️ 必须用 literal_binds 渲染，否则 `IN (...)` 的值在 str() 里是
    #    POSTCOMPILE 占位符，看不到实际状态。
    rendered = str(
        first.compile(compile_kwargs={"literal_binds": True}),
    )
    assert SPU_BIZ_STATUS_RETIRED not in rendered
    for value in sorted(SPU_ASSIGNABLE_STATUSES):
        assert value in rendered


# ---------------------------------------------------------------------------
# ② ORM 派生点
# ---------------------------------------------------------------------------


def _orm_check_constraints() -> dict:
    """取出 DimSpu 上的 CHECK 约束 {名字: 表达式}。

    ⚠️ ``DimSpu.__table__.constraints`` 里还有 UniqueConstraint / Index，
    它们没有 ``sqltext`` ⇒ 必须按类型过滤。
    """
    from sqlalchemy import CheckConstraint

    from modules.core.db.schema_parts.dimensions import DimSpu

    return {
        item.name: str(item.sqltext)
        for item in DimSpu.__table__.constraints
        if isinstance(item, CheckConstraint)
    }


def test_orm_declares_both_spu_constraints_rendered_from_ssot():
    """ORM 的两个 CHECK 约束必须**由真源渲染**，不能手抄。"""
    constraints = _orm_check_constraints()

    assert (
        constraints.get("chk_dim_spu_biz_status") == render_spu_biz_status_constraint()
    ), "ORM 的 biz_status 约束与真源不一致"
    assert (
        constraints.get("chk_dim_spu_lifecycle") == render_spu_lifecycle_constraint()
    ), "ORM 的生命周期不变量约束与真源不一致"


def test_orm_schema_source_calls_the_ssot_renderers():
    source = DIMENSIONS_SCHEMA.read_text(encoding="utf-8")

    assert (
        "render_spu_biz_status_constraint()" in source
    ), "ORM 必须调用真源的 biz_status 渲染函数"
    assert (
        "render_spu_lifecycle_constraint()" in source
    ), "ORM 必须调用真源的��命周期不变量渲染函数"
    # 手抄的 biz_status 清单必须消失
    assert "biz_status IN ('candidate'" not in source, "ORM 里仍存在手抄的状态清单"


# ---------------------------------------------------------------------------
# ③ 路由派生点
# ---------------------------------------------------------------------------


def test_router_derives_assignable_rule_from_ssot():
    """路由必须从真源取「可绑定」判定，不能自己手写条件。"""
    source = PRODUCT_CENTER_ROUTER.read_text(encoding="utf-8")

    assert (
        "from backend.services.product_spu_lifecycle import" in source
    ), "product_center 路由必须从真源导入 SPU 生命周期判定"
    assert (
        "spu_assignable_condition()" in source
    ), "product_center 路由必须调用真源的可绑定条件"


def test_router_does_not_hand_copy_the_retired_literal():
    """路由里不得再手抄 ``biz_status != 'retired'`` 这类条件。"""
    source = PRODUCT_CENTER_ROUTER.read_text(encoding="utf-8")

    assert "biz_status != \"retired\"" not in source
    assert "biz_status != 'retired'" not in source


# ---------------------------------------------------------------------------
# ④ 写入路径收敛（active 只能由删除/恢复写）
# ---------------------------------------------------------------------------


def test_bulk_and_update_requests_cannot_write_active():
    """``active`` 只由软删 / 恢复端点写 —— 批量保存与单行更新都不得写它。

    否则运营在表格里改个名称就能顺手把 SPU 删掉，或者造出
    ``active=false + biz_status='candidate'`` 这种自相矛盾的行。
    """
    from backend.schemas.product_center import SpuBulkItem, SpuUpdateRequest

    assert "active" not in SpuBulkItem.model_fields
    assert "active" not in SpuUpdateRequest.model_fields


def test_bulk_request_ignores_a_smuggled_active_field():
    """前端整行回写会带上 ``active`` ⇒ 必须被**忽略**而不是写进库。"""
    from backend.schemas.product_center import SpuBulkItem

    item = SpuBulkItem(spu="XH-1", spu_name="x", active=False)
    dumped = item.model_dump(exclude_unset=True)

    assert "active" not in dumped, "active 不得从请求体透传到写入载荷"


# ---------------------------------------------------------------------------
# ⑤ 迁移
# ---------------------------------------------------------------------------


def test_migration_exists_and_chains_from_previous_head():
    assert MIGRATION_PATH.exists(), "缺 dim_spu 生命周期约束迁移"

    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert (
        'revision = "current_schema_20261227_dim_spu_lifecycle_constraints"' in source
    )
    assert (
        'down_revision = "current_schema_20261226_task_center_status_constraint"'
        in source
    ), "迁移必须接在 20261226 之后"


def test_migration_renders_constraints_from_ssot_not_hardcoded():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "render_spu_biz_status_constraint" in source, "迁移必须从真源渲染"
    assert "render_spu_lifecycle_constraint" in source, "迁移必须从真源渲染"
    assert "biz_status IN ('candidate'" not in source, "迁移里不得手抄状态清单"


def test_migration_renders_the_same_expressions_as_orm():
    """迁移渲染出的表达式必须与 ORM 用的**完全一致** ⇒ 两边不会漂移。"""
    constraints = _orm_check_constraints()

    assert (
        constraints["chk_dim_spu_biz_status"] == render_spu_biz_status_constraint()
    )
    assert constraints["chk_dim_spu_lifecycle"] == render_spu_lifecycle_constraint()
