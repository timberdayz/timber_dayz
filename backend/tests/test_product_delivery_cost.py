"""尾程配送费（批次 3，2026-11-16）守护测试。

尾程 = 仓 → 买家那段快递费，**每卖一件必付**（头程是已付库存成本，一次）。
没有它，利润虚高、最低售价底线偏低。

本文件锁住四件事：

1. **表**：`finance.delivery_rate_rules` 的列、当期唯一索引，以及**没有任何外键**
   （`core.dim_platforms` / `core.dim_warehouses` 会被同步 TRUNCATE CASCADE，
   建了外键会把费率规则一起删掉 —— 静默失效）。
2. **纯函数**：选档 / 降级 / 歧义不猜 / 没配费率不算 0。
3. **端点与前端**：费率可维护、测算页只读展示、重量必填且表头不再标蓝。
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
    MISSING_WEIGHT,
    WEIGHT_ABOVE_TOP_TIER,
    DeliveryTier,
    compute_delivery_cost,
    select_delivery_tier,
)
from backend.utils.project_env import isolated_database_url
from modules.core.db import DeliveryRateRule

MIGRATION_PATH = Path("current_migrations/versions/20261233_delivery_rate_rules.py")
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


def _tier(min_kg, max_kg, price, warehouse="MY-01"):
    return DeliveryTier(
        min_weight_kg=Decimal(str(min_kg)),
        max_weight_kg=Decimal(str(max_kg)) if max_kg is not None else None,
        unit_price=Decimal(str(price)),
        currency="CNY",
        warehouse_code=warehouse,
    )


# ---------------------------------------------------------------------------
# 1 · 表
# ---------------------------------------------------------------------------


def test_delivery_rate_rule_table_has_expected_columns():
    columns = {column.name for column in inspect(DeliveryRateRule).columns}
    assert {
        "rule_id",
        "platform_code",
        "warehouse_code",
        "min_weight_kg",
        "max_weight_kg",
        "unit_price",
        "currency",
        "effective_from",
        "effective_to",
        "status",
        "source",
        "version",
        "notes",
    } <= columns


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
        "min_weight_kg",
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


def test_delivery_rate_table_is_synced_to_cloud():
    """漏进同步清单 ⇒ 云端没有尾程费率 ⇒ 尾程费算不出来（利润虚高）。"""
    import importlib.util

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


def test_weight_inside_tier_uses_the_rate_table():
    tiers = [_tier(0, 0.5, 12), _tier(0.5, None, 18)]
    result = compute_delivery_cost(tiers, Decimal("0.2"))
    assert result.amount == Decimal("12.00")
    assert result.source == "rate_table"
    assert result.estimated is False
    assert result.missing_reasons == ()


def test_tier_boundaries_belong_to_the_next_tier():
    """重量段是**左闭右开** ``[min, max)``：相邻两档不重叠，边界归下一档。"""
    tiers = [_tier(0, 0.5, 12), _tier(0.5, None, 18)]
    assert compute_delivery_cost(tiers, Decimal("0.4")).amount == Decimal("12.00")
    assert compute_delivery_cost(tiers, Decimal("0.5")).amount == Decimal("18.00")
    assert compute_delivery_cost(tiers, Decimal("0.6")).amount == Decimal("18.00")


def test_overlapping_tiers_are_ambiguous_and_not_guessed():
    """两档同时命中 = 配置错了 ⇒ 宁可算不出来，也不要算错。"""
    tiers = [_tier(0, 1.0, 12), _tier(0.5, None, 18)]
    assert select_delivery_tier(tiers, Decimal("0.7")) is None
    result = compute_delivery_cost(tiers, Decimal("0.7"))
    assert result.amount is None
    assert result.missing_reasons == (AMBIGUOUS_TIER,)


def test_missing_rate_is_not_treated_as_free_delivery():
    """没配费率 ≠ 尾程免费（默认 0 会让利润虚高）。"""
    result = compute_delivery_cost([], Decimal("0.2"))
    assert result.amount is None
    assert result.missing_reasons == (MISSING_RATE,)


def test_missing_weight_falls_back_to_the_most_expensive_warehouse():
    """缺重量 ⇒ 保守估算（该仓最轻档 vs 最贵仓的最轻档，取更贵的）+ 标 estimated。"""
    tiers = [_tier(0, 0.5, 12), _tier(0.5, None, 18)]
    fallback = [_tier(0, 0.5, 15, warehouse="SG-01")]
    result = compute_delivery_cost(tiers, None, fallback_tiers=fallback)
    assert result.amount == Decimal("15.00")
    assert result.estimated is True
    assert result.source == "estimated"
    assert result.missing_reasons == (MISSING_WEIGHT,)


def test_missing_weight_uses_local_tier_when_no_other_warehouse():
    tiers = [_tier(0, 0.5, 12), _tier(0.5, None, 18)]
    result = compute_delivery_cost(tiers, None)
    assert result.amount == Decimal("12.00")
    assert result.estimated is True
    assert result.missing_reasons == (MISSING_WEIGHT,)


def test_weight_above_all_tiers_falls_back_to_the_top_tier():
    tiers = [_tier(0, 0.5, 12), _tier(0.5, 1.0, 18)]
    result = compute_delivery_cost(tiers, Decimal("3"))
    assert result.amount == Decimal("18.00")
    assert result.estimated is True
    assert result.missing_reasons == (WEIGHT_ABOVE_TOP_TIER,)


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


def test_delivery_rate_create_rejects_overlapping_weight_tiers():
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert "_delivery_rate_weight_overlaps" in source
    assert "overlaps an active rule" in source


def test_frontend_shows_delivery_cost_as_read_only_column():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert 'label="尾程配送费"' in source
    assert "deliveryCostHint" in source


def test_weight_column_is_black_and_marked_required():
    """重量是必填项 ⇒ 表头不能是蓝色（蓝色 = 「这列可以不填」）。"""
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert (
        'const skuOptionalColumnLabels = ["规格", "箱规（件/箱）", "基准售价来源"]'
        in source
    )
    assert "sku-required-mark" in source
    assert "重量 kg 是必填项" in source


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


def test_delivery_rate_migration_is_repeatable_and_rollback_cleanly(isolated_engine):
    """真跑一遍迁移的 DDL：upgrade → upgrade → downgrade → upgrade。

    ⚠️ 先把隔离库里 ``create_all`` 建出来的表删掉 ⇒ 真正执行迁移脚本的建表语句
    （否则「表已存在」会让迁移直接返回，测不到 DDL 本身）。
    """
    module = _load_module(MIGRATION_PATH)
    with isolated_engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS finance.delivery_rate_rules"))

    _run_migration(isolated_engine, module, "upgrade")
    inspector = inspect(isolated_engine)
    assert inspector.has_table("delivery_rate_rules", schema="finance")
    columns = {
        column["name"]
        for column in inspector.get_columns("delivery_rate_rules", schema="finance")
    }
    assert {
        "platform_code",
        "warehouse_code",
        "min_weight_kg",
        "max_weight_kg",
        "unit_price",
        "currency",
        "effective_from",
        "effective_to",
        "status",
    } <= columns
    indexes = {
        index["name"]
        for index in inspector.get_indexes("delivery_rate_rules", schema="finance")
    }
    assert "uq_delivery_rate_rules_current" in indexes

    # 幂等：重复执行不报错
    _run_migration(isolated_engine, module, "upgrade")

    # 回滚能干净撤掉
    _run_migration(isolated_engine, module, "downgrade")
    inspector = inspect(isolated_engine)
    assert not inspector.has_table("delivery_rate_rules", schema="finance")

    # 复原（后面的用例可能还要这张表）
    _run_migration(isolated_engine, module, "upgrade")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
