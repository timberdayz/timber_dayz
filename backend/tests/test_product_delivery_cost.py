"""尾程配送费（批次 3/6）守护测试。

尾程 = 仓 → 买家那段快递费，**每卖一件必付**（头程是已付库存成本，一次）。
没有它，利润虚高、最低售价底线偏低。

批次 6（2026-11-17）口径变化：承运商按**重量段**定价 ⇒ SKU 不再称重，
只报「落在哪一段」；费率表也改成「平台 × 仓 × 重量段」。

本文件锁住四件事：

1. **表**：`finance.delivery_rate_rules` 的列、当期唯一索引，以及**没有任何外键**
   （`core.dim_platforms` / `core.dim_warehouses` 会被同步 TRUNCATE CASCADE，
   建了外键会把费率规则一起删掉 —— 静默失效）。
2. **纯函数**：按段选档 / 未选段默认最轻段 / 该段没配价不算 0 / 歧义不猜。
3. **端点与前端**：费率按段可维护、测算页只读展示、SKU 页按段选。
4. **同步清单**：这张表必须进 `PRODUCT_CENTER_TABLES`（漏了云端就没有尾程费率）。
"""

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

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
from modules.core.db import DeliveryRateRule

MIGRATION_PATH = Path("current_migrations/versions/20261233_delivery_rate_rules.py")
WEIGHT_TIER_MIGRATION_PATH = Path(
    "current_migrations/versions/20261236_weight_tiers.py"
)
FRONTEND_PATH = Path("frontend/src/domains/business/views/ProductCenter.vue")
ROUTER_PATH = Path("backend/domains/business/routers/product_center.py")


@pytest.fixture(scope="module")
def isolated_engine():
    url = isolated_database_url()
    if not url:
        pytest.skip("隔离测试库地址未就绪")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def _tier(code, min_kg, max_kg, price, warehouse="MY-01", order=0):
    return DeliveryTier(
        tier_code=code,
        label=code,
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


def test_delivery_rate_rule_table_has_expected_columns():
    """批次 6：费率行只存**重量段编码**，重量上下限归全局段表管。"""
    columns = {column.name for column in inspect(DeliveryRateRule).columns}
    assert {
        "rule_id",
        "platform_code",
        "warehouse_code",
        "weight_tier_code",
        "unit_price",
        "currency",
        "effective_from",
        "effective_to",
        "status",
        "source",
        "version",
        "notes",
    } <= columns
    assert "min_weight_kg" not in columns
    assert "max_weight_kg" not in columns


def test_delivery_rate_rule_has_no_foreign_keys():
    """**刻意无外键**：父表被同步 TRUNCATE CASCADE 时会连带删掉费率规则。"""
    assert DeliveryRateRule.__table__.foreign_keys == set()


def test_delivery_rate_rule_has_current_unique_index():
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


def test_migration_creates_the_table_and_chains_from_head():
    assert MIGRATION_PATH.exists()
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision = "current_schema_20261233_delivery_rate_rules"' in source
    assert (
        'down_revision = "current_schema_20261232_inventory_contract_consumers"'
        in source
    )
    assert "op.create_table(" in source
    assert "uq_delivery_rate_rules_current" in source


def test_weight_tier_migration_swaps_kg_bounds_for_tier_code():
    """批次 6 的迁移：建段表、加段编码、删重量上下限、换唯一索引。"""
    source = WEIGHT_TIER_MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision = "current_schema_20261236_weight_tiers"' in source
    assert (
        'down_revision = "current_schema_20261235_price_adjust_baseline_warehouse"'
        in source
    )
    assert "op.create_table(" in source
    assert "dim_weight_tiers" in source
    assert "weight_tier_code" in source
    assert "weight_kg" in source


def test_delivery_rate_table_is_synced_to_cloud():
    """漏进同步清单 ⇒ 云端没有尾程费率 ⇒ 尾程费算不出来（利润虚高）。"""
    spec = importlib.util.spec_from_file_location(
        "sync_product_center_under_test",
        "scripts/sync_product_center_to_cloud.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert ("finance", "delivery_rate_rules") in set(module.PRODUCT_CENTER_TABLES)


# ---------------------------------------------------------------------------
# 2 · 纯函数
# ---------------------------------------------------------------------------


def test_tier_code_hit_uses_the_rate_table():
    tiers = [_tier("T01", 0, 0.5, 12), _tier("T02", 0.5, None, 18)]
    result = compute_delivery_cost(tiers, "T01")
    assert result.amount == Decimal("12.00")
    assert result.source == "rate_table"
    assert result.estimated is False
    assert result.missing_reasons == ()


def test_each_tier_code_selects_its_own_rate():
    tiers = [_tier("T01", 0, 0.5, 12), _tier("T02", 0.5, 1.0, 18)]
    assert compute_delivery_cost(tiers, "T01").amount == Decimal("12.00")
    assert compute_delivery_cost(tiers, "T02").amount == Decimal("18.00")


def test_tier_without_rate_is_not_treated_as_free_delivery():
    """该段没配价 ≠ 尾程免费（默认 0 会让利润虚高）。"""
    tiers = [_tier("T01", 0, 0.5, 12), _tier("T02", 0.5, None, 18)]
    result = compute_delivery_cost(tiers, "T09")
    assert result.amount is None
    assert result.missing_reasons == (MISSING_TIER_RATE,)


def test_missing_rate_is_not_treated_as_free_delivery():
    """没配费率 ≠ 尾程免费（默认 0 会让利润虚高）。"""
    result = compute_delivery_cost([], "T01")
    assert result.amount is None
    assert result.missing_reasons == (MISSING_RATE,)


def test_duplicate_tier_code_is_ambiguous_and_not_guessed():
    """同一段配了两行 ⇒ 配置错了 ⇒ 宁可算不出来，也不要算错。"""
    tiers = [_tier("T01", 0, 0.5, 12), _tier("T01", 0, 0.5, 18)]
    assert select_tier_by_code(tiers, "T01") is None
    result = compute_delivery_cost(tiers, "T01")
    assert result.amount is None
    assert result.missing_reasons == (AMBIGUOUS_TIER,)


def test_missing_tier_falls_back_to_the_lightest_tier():
    """未选段 ⇒ 默认最轻段 + 标 estimated（用户 2026-11-17 拍板）。"""
    tiers = [_tier("T01", 0, 0.5, 12), _tier("T02", 0.5, None, 18)]
    result = compute_delivery_cost(tiers, None)
    assert result.amount == Decimal("12.00")
    assert result.estimated is True
    assert result.source == "estimated"
    assert result.missing_reasons == (MISSING_WEIGHT_TIER,)
    assert result.tier_code == "T01"


def test_missing_tier_takes_the_most_expensive_warehouse():
    """未选段 ⇒ 保守估算：各仓该段价取最贵（宁高不低）。"""
    tiers = [_tier("T01", 0, 0.5, 12), _tier("T02", 0.5, None, 18)]
    fallback = [_tier("T01", 0, 0.5, 15, warehouse="SG-01")]
    result = compute_delivery_cost(tiers, None, fallback_tiers=fallback)
    assert result.amount == Decimal("15.00")
    assert result.estimated is True
    assert result.missing_reasons == (MISSING_WEIGHT_TIER,)


def test_lightest_tier_is_global_across_warehouses():
    """段定义全局一套 ⇒ 「最轻段」在各仓之间必须一致。"""
    tiers = [_tier("T02", 0.5, 1.0, 18)]
    fallback = [_tier("T01", 0, 0.5, 15, warehouse="SG-01")]
    result = compute_delivery_cost(tiers, None, fallback_tiers=fallback)
    assert result.tier_code == "T01"
    assert result.amount == Decimal("15.00")


def test_delivery_module_has_no_orm_or_db_dependency():
    """纯函数模块不许 import ORM —— 它必须在候选列表 / 试算 / 版本里复用同一份口径。"""
    source = Path("backend/services/product_delivery_cost_service.py").read_text(
        encoding="utf-8"
    )
    assert "modules.core.db" not in source
    assert "sqlalchemy" not in source
    assert "AsyncSession" not in source


# ---------------------------------------------------------------------------
# 3 · 端点与前端
# ---------------------------------------------------------------------------


def test_delivery_rate_endpoints_exist():
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert '"/api/delivery-rate-rules"' in source
    assert '"/api/delivery-rate-rules/{rule_id}"' in source


def test_weight_tier_endpoints_exist():
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert '"/api/weight-tiers"' in source
    assert '"/api/weight-tiers/{tier_code}"' in source


def test_delivery_rate_create_requires_a_real_weight_tier():
    """段必须存在：引用一个不存在的段 ⇒ 这一行永远选不中 ⇒ 费率等于没配。"""
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert "weight tier not found" in source


def test_frontend_shows_delivery_cost_as_read_only_column():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert 'label="尾程配送费"' in source
    assert "deliveryCostHint" in source


def test_sku_page_uses_weight_tier_dropdown():
    """重量段是**可选**的（没选段 ⇒ 按最轻段估算）⇒ 不再标必填。"""
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    sku_section = source[
        source.index('label="SKU 资料"') : source.index('label="平台 SKU 利润测算"')
    ]
    assert 'label="重量段"' in sku_section
    assert "row.weight_tier_code" in sku_section
    assert 'label="重量 kg"' not in sku_section
    assert "sku-required-mark" not in sku_section


# ---------------------------------------------------------------------------
# 4 · 迁移在真实 PostgreSQL 上跑一遍（幂等 + 回滚）
# ---------------------------------------------------------------------------


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_delivery_{path.stem}", path)
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
    """真跑一遍迁移的 DDL：upgrade → upgrade → downgrade → upgrade。

    ⚠️ 先把隔离库里 ``create_all`` 建出来的表删掉 ⇒ 真正执行迁移脚本的建表语句
    （否则「表已存在」会让迁移直接返回，测不到 DDL 本身）。
    """
    module = _load_module(WEIGHT_TIER_MIGRATION_PATH)
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
