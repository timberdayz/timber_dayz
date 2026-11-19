"""重量段化（批次 6，2026-11-17）守护测试。

业务概念
--------
承运商按**重量段**定价（Shopee SG / TikTok SG 价目表都是「≤1kg / ≤5kg / ≤10kg …
一档价」），所以：

* **SKU 不用称重**，只选「落在哪一段」；
* **承运商调价**只改费率表的那一行（平台 × 仓 × 重量段），不用动 SKU；
* **重量段定义全局一套**（``core.dim_weight_tiers``），所有平台共用同一把尺子。

三条口径
--------
1. **段定义全局一套** —— 段表在 ``core.dim_weight_tiers``，SKU 与尾程费率都只存
   ``weight_tier_code`` 引用它。
2. **老的精确重量 ``weight_kg`` 直接删** —— 「填 0.8kg」这套口径是承运商**按件**定价
   时代的产物；按段定价后它只会让人偷偷按重量算，和费率表对不上。
3. **SKU 未选段 ⇒ 默认最轻段**（用户 2026-11-17 拍板）—— 尾程按最轻段估算 +
   标 ``estimated`` + 原因码 ``missing_weight_tier``。
   ⚠️ 最轻段通常是最便宜的一档 ⇒ 这是**偏乐观**口径，所以必须醒目标记，
   界面要提示「重货务必选段」。

本文件锁住五件事：

1. **表**：``core.dim_weight_tiers``（无外键）+ SKU / 费率表改挂 ``weight_tier_code``
2. **纯函数**：按段选档 / 未选段默认最轻段 / 该段没配价 ≠ 免费 / 歧义不猜
3. **契约**：SKU 与费率都按段，旧 ``weight_kg`` 字段彻底消失
4. **端点**：重量段可读可维护
5. **前端**：SKU 资料页重量段下拉 + 尾程费率页按段录入 + 缺失原因文案
"""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from backend.schemas.product_center import (
    DeliveryRateRuleCreateRequest,
    DeliveryRateRuleUpdateRequest,
    SkuCreateRequest,
    SkuItem,
    SkuUpdateRequest,
    WeightTierCreateRequest,
    WeightTierUpdateRequest,
)
from backend.services.product_delivery_cost_service import (
    AMBIGUOUS_TIER,
    MISSING_RATE,
    MISSING_TIER_RATE,
    MISSING_WEIGHT_TIER,
    DeliveryTier,
    compute_delivery_cost,
    select_tier_by_code,
)
from backend.utils.project_env import isolated_database_url
from modules.core.db import DeliveryRateRule, DimErpSku, DimWeightTier

MIGRATION_PATH = Path("current_migrations/versions/20261236_weight_tiers.py")
FRONTEND_PATH = Path("frontend/src/domains/business/views/ProductCenter.vue")
FRONTEND_API_PATH = Path("frontend/src/api/productCenter.js")
ROUTER_PATH = Path("backend/domains/business/routers/product_center.py")


@pytest.fixture(scope="module")
def isolated_engine():
    url = isolated_database_url()
    if not url:
        pytest.skip("隔离测试库地址未就绪")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def _tier(code, min_kg, max_kg, price, warehouse="MY-01", label=None, order=0):
    return DeliveryTier(
        tier_code=code,
        label=label or code,
        min_weight_kg=Decimal(str(min_kg)),
        max_weight_kg=Decimal(str(max_kg)) if max_kg is not None else None,
        unit_price=Decimal(str(price)),
        currency="CNY",
        warehouse_code=warehouse,
        sort_order=order,
    )


# ---------------------------------------------------------------------------
# 1 · 表
# ---------------------------------------------------------------------------


def test_weight_tier_table_has_expected_columns():
    columns = {column.name for column in inspect(DimWeightTier).columns}
    assert {
        "tier_code",
        "label",
        "min_kg",
        "max_kg",
        "sort_order",
        "status",
    } <= columns


def test_weight_tier_has_no_foreign_keys():
    """**刻意无外键**：``core.dim_weight_tiers`` 会被同步 TRUNCATE CASCADE，
    建了外键会把引用它的 SKU / 费率规则一起删掉 —— 静默失效。"""
    assert DimWeightTier.__table__.foreign_keys == set()


def test_sku_uses_weight_tier_instead_of_weight_kg():
    columns = {column.name for column in inspect(DimErpSku).columns}
    assert "weight_tier_code" in columns
    assert "weight_kg" not in columns


def test_delivery_rate_rule_uses_weight_tier_instead_of_kg_bounds():
    columns = {column.name for column in inspect(DeliveryRateRule).columns}
    assert "weight_tier_code" in columns
    assert "min_weight_kg" not in columns
    assert "max_weight_kg" not in columns


def test_delivery_rate_rule_current_unique_index_is_by_tier_code():
    indexes = {
        index.name: index for index in DeliveryRateRule.__table__.indexes if index.name
    }
    current = indexes.get("uq_delivery_rate_rules_current")
    assert current is not None, "缺少当期唯一索引"
    assert current.unique is True
    assert set(column.name for column in current.columns) == {
        "platform_code",
        "warehouse_code",
        "weight_tier_code",
    }
    where = str(current.dialect_options["postgresql"]["where"])
    assert "status = 'active'" in where
    assert "effective_to IS NULL" in where


def test_weight_tier_table_is_synced_to_cloud():
    """漏进同步清单 ⇒ 云端没有重量段定义 ⇒ 下拉框空 ⇒ SKU 选不了段。"""
    spec = importlib.util.spec_from_file_location(
        "sync_product_center_under_test",
        "scripts/sync_product_center_to_cloud.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert ("core", "dim_weight_tiers") in set(module.PRODUCT_CENTER_TABLES)
    # ⚠️ 插入顺序必须**先段表后 SKU**：SKU 挂着 weight_tier_code 引用段表。
    tables = list(module.PRODUCT_CENTER_TABLES)
    assert tables.index(("core", "dim_weight_tiers")) < tables.index(
        ("core", "dim_erp_sku")
    )


def test_migration_creates_weight_tiers_and_swaps_columns():
    assert MIGRATION_PATH.exists()
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision = "current_schema_20261236_weight_tiers"' in source
    assert (
        'down_revision = "current_schema_20261235_price_adjust_baseline_warehouse"'
        in source
    )
    assert "op.create_table(" in source
    assert "dim_weight_tiers" in source
    # 删掉老列 + 换唯一索引
    assert "weight_kg" in source
    assert "weight_tier_code" in source
    assert "uq_delivery_rate_rules_current" in source


# ---------------------------------------------------------------------------
# 2 · 纯函数
# ---------------------------------------------------------------------------


def test_tier_code_hit_uses_the_rate_table():
    tiers = [_tier("T01", 0, 1, 12), _tier("T02", 1, 5, 18)]
    result = compute_delivery_cost(tiers, "T01")
    assert result.amount == Decimal("12.00")
    assert result.source == "rate_table"
    assert result.estimated is False
    assert result.missing_reasons == ()
    assert result.tier_code == "T01"


def test_each_tier_code_selects_its_own_rate():
    tiers = [_tier("T01", 0, 1, 12), _tier("T02", 1, 5, 18), _tier("T03", 5, 10, 30)]
    assert compute_delivery_cost(tiers, "T02").amount == Decimal("18.00")
    assert compute_delivery_cost(tiers, "T03").amount == Decimal("30.00")


def test_tier_without_rate_is_not_treated_as_free_delivery():
    """该段没配价 ≠ 尾程免费（默认 0 会让利润虚高）。"""
    tiers = [_tier("T01", 0, 1, 12), _tier("T02", 1, 5, 18)]
    result = compute_delivery_cost(tiers, "T09")
    assert result.amount is None
    assert result.missing_reasons == (MISSING_TIER_RATE,)


def test_no_rate_rows_at_all_is_missing_rate():
    result = compute_delivery_cost([], "T01")
    assert result.amount is None
    assert result.missing_reasons == (MISSING_RATE,)


def test_duplicate_tier_code_is_ambiguous_and_not_guessed():
    """同一段配了两行 ⇒ 配置错了 ⇒ 宁可算不出来，也不要算错。"""
    tiers = [_tier("T01", 0, 1, 12), _tier("T01", 0, 1, 18)]
    assert select_tier_by_code(tiers, "T01") is None
    result = compute_delivery_cost(tiers, "T01")
    assert result.amount is None
    assert result.missing_reasons == (AMBIGUOUS_TIER,)


def test_missing_tier_falls_back_to_the_lightest_tier():
    """未选段 ⇒ 默认最轻段 + 标 estimated（用户 2026-11-17 拍板）。"""
    tiers = [_tier("T01", 0, 1, 12), _tier("T02", 1, 5, 18)]
    result = compute_delivery_cost(tiers, None)
    assert result.amount == Decimal("12.00")
    assert result.estimated is True
    assert result.source == "estimated"
    assert result.missing_reasons == (MISSING_WEIGHT_TIER,)
    assert result.tier_code == "T01"


def test_missing_tier_takes_the_most_expensive_warehouse():
    """未选段 ⇒ 保守估算：各仓该段价取最贵（宁高不低）。"""
    tiers = [_tier("T01", 0, 1, 12), _tier("T02", 1, 5, 18)]
    fallback = [_tier("T01", 0, 1, 15, warehouse="SG-01")]
    result = compute_delivery_cost(tiers, None, fallback_tiers=fallback)
    assert result.amount == Decimal("15.00")
    assert result.estimated is True
    assert result.missing_reasons == (MISSING_WEIGHT_TIER,)


def test_lightest_tier_is_global_across_warehouses():
    """段定义全局一套 ⇒ 「最轻段」在各仓之间必须一致，不能各仓各挑各的。"""
    tiers = [_tier("T02", 1, 5, 18)]
    fallback = [_tier("T01", 0, 1, 15, warehouse="SG-01")]
    result = compute_delivery_cost(tiers, None, fallback_tiers=fallback)
    assert result.tier_code == "T01"
    assert result.amount == Decimal("15.00")
    assert result.estimated is True


def test_delivery_module_has_no_orm_or_db_dependency():
    """纯函数模块不许 import ORM —— 它必须在候选列表 / 试算 / 版本里复用同一份口径。"""
    source = Path("backend/services/product_delivery_cost_service.py").read_text(
        encoding="utf-8"
    )
    assert "modules.core.db" not in source
    assert "sqlalchemy" not in source
    assert "AsyncSession" not in source


# ---------------------------------------------------------------------------
# 3 · 契约
# ---------------------------------------------------------------------------


def test_sku_item_exposes_weight_tier_not_weight_kg():
    fields = SkuItem.model_fields
    assert "weight_tier_code" in fields
    assert "weight_kg" not in fields


def test_sku_write_requests_take_weight_tier_code():
    for model in (SkuCreateRequest, SkuUpdateRequest):
        assert "weight_tier_code" in model.model_fields
        assert "weight_kg" not in model.model_fields


def test_delivery_rate_create_requires_weight_tier_code():
    with pytest.raises(Exception):
        DeliveryRateRuleCreateRequest(
            platform_code="shopee",
            warehouse_code="SG-01",
            unit_price=22.34,
            currency="CNY",
            effective_from="2026-01-01",
        )
    row = DeliveryRateRuleCreateRequest(
        platform_code="shopee",
        warehouse_code="SG-01",
        weight_tier_code="T01",
        unit_price=22.34,
        currency="CNY",
        effective_from="2026-01-01",
    )
    assert row.weight_tier_code == "T01"


def test_delivery_rate_update_rejects_weight_tier_overwrite():
    """重量段是这一行的身份：改了等于换了一档费率 ⇒ 只能新开一行。"""
    with pytest.raises(Exception):
        DeliveryRateRuleUpdateRequest(weight_tier_code="T02")


def test_weight_tier_contract_models_exist():
    create = WeightTierCreateRequest(
        tier_code="T07",
        label="30 kg 以上",
        min_kg=30,
        max_kg=None,
        sort_order=6,
    )
    assert create.tier_code == "T07"
    update = WeightTierUpdateRequest(label="30kg 以上")
    assert update.label == "30kg 以上"


# ---------------------------------------------------------------------------
# 4 · 端点
# ---------------------------------------------------------------------------


def test_weight_tier_endpoints_exist():
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert '"/api/weight-tiers"' in source
    assert '"/api/weight-tiers/{tier_code}"' in source


def test_delivery_rate_rules_are_keyed_by_tier_code():
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert "weight_tier_code" in source
    assert "DeliveryRateRule.weight_tier_code" in source


# ---------------------------------------------------------------------------
# 5 · 前端
# ---------------------------------------------------------------------------


def test_sku_page_uses_weight_tier_dropdown():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    sku_section = source[
        source.index('label="SKU 资料"') : source.index('label="平台 SKU 利润测算"')
    ]
    assert 'label="重量段"' in sku_section
    assert "row.weight_tier_code" in sku_section
    # 老的「精确重量」输入框整体退役
    assert 'label="重量 kg"' not in sku_section
    assert "row.weight_kg" not in sku_section


def test_delivery_rate_page_is_driven_by_weight_tier():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    # ⚠️ 批次 9 术语统一：「物流批次」改叫「头程批次」
    #    （物流 = 头程 + 尾程两段，混叫会让运营以为这是同一笔钱的两种叫法）。
    section = source[
        source.index('label="尾程费率"') : source.index('label="头程批次"')
    ]
    assert 'label="重量段"' in section
    assert "row.weight_tier_code" in section
    # 重量上下限手工填 ⇒ 迟早填出重叠段 ⇒ 改为一律从段表里选
    assert 'label="重量下限 kg"' not in source
    assert 'label="重量上限 kg"' not in source


def test_frontend_api_has_weight_tier_endpoints():
    source = FRONTEND_API_PATH.read_text(encoding="utf-8")
    assert "listWeightTiers" in source
    assert "createWeightTier" in source
    assert "updateWeightTier" in source


def test_frontend_reports_missing_weight_tier():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "missing_weight_tier" in source
    assert "missing_delivery_rate_for_tier" in source
    assert "missing_weight" not in source.replace("missing_weight_tier", "")


def test_frontend_no_longer_sends_weight_kg():
    """SKU 保存载荷里不许再有 ``weight_kg`` —— 段才是唯一口径。

    ⚠️ 只查 ``weight_kg:`` 的**独立字段**：物流账单行里的
    ``actual_total_weight_kg`` 是承运商实重，与 SKU 重量段是两回事。
    """
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "weight_kg: null" not in source
    assert "row.weight_kg" not in source
    assert "sku.weight_kg" not in source


# ---------------------------------------------------------------------------
# 6 · 迁移在真实 PostgreSQL 上跑一遍（幂等 + 回滚）
# ---------------------------------------------------------------------------


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_weight_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(engine, module, func_name: str) -> None:
    def _do(connection):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(module, func_name)()

    with engine.begin() as connection:
        _do(connection)


def test_weight_tier_migration_is_repeatable_and_rollback_cleanly(isolated_engine):
    module = _load_module(MIGRATION_PATH)
    with isolated_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS core.dim_weight_tiers"))

    _run_migration(isolated_engine, module, "upgrade")
    inspector = inspect(isolated_engine)
    assert inspector.has_table("dim_weight_tiers", schema="core")
    columns = {
        column["name"]
        for column in inspector.get_columns("dim_weight_tiers", schema="core")
    }
    assert {"tier_code", "label", "min_kg", "max_kg", "sort_order", "status"} <= columns
    # 段表里必须已经种好全局那几档，否则下拉框是空的。
    with isolated_engine.begin() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM core.dim_weight_tiers")
        ).scalar()
    assert count and count >= 5

    # 幂等：重复执行不报错
    _run_migration(isolated_engine, module, "upgrade")

    # 回滚能干净撤掉
    _run_migration(isolated_engine, module, "downgrade")
    inspector = inspect(isolated_engine)
    assert not inspector.has_table("dim_weight_tiers", schema="core")

    # 复原（后面的用例可能还要这张表）
    _run_migration(isolated_engine, module, "upgrade")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
