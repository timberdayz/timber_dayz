"""SKU 定价底线：迁移与 ORM 契约测试。

读迁移文件源码断言（迁移不会在测试库里跑，所以只能读源码），
外加 ORM 层的列 / 约束 / 索引断言——ORM 断言能提前抓住 import 期崩溃
（例如 Index 误传 schema= 关键字）。
"""

from pathlib import Path

MIGRATION = Path("current_migrations/versions/20261020_sku_pricing_guardrails.py")


def test_migration_declares_pricing_policy_table_and_columns():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "current_schema_20261020_sku_pricing_guardrails"' in source
    assert 'down_revision = "current_schema_20260921_warehouse_storage_label_fee"' in source
    assert "sku_pricing_policies" in source
    assert "min_age_days" in source
    assert "tier_label" in source
    assert "discount_rate" in source
    assert "target_margin_rate" in source
    assert "default_creator_commission_rate" in source
    assert "other_cost_rate" in source
    assert "creator_commission_rate" in source
    assert "min_selling_price_override" in source
    assert "def downgrade" in source
    # 旧的双折扣率模型不得复活
    assert "standard_discount_rate" not in source
    assert "clearance_discount_rate" not in source


def test_migration_seeds_four_age_tiers():
    source = MIGRATION.read_text(encoding="utf-8")
    for label in ("日常", "滞销30天", "滞销60天", "滞销60天以上"):
        assert label in source
    for rate in ("0.10", "0.15", "0.20", "0.30"):
        assert rate in source


def test_migration_calibrates_platform_fee_rates():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "0.0737" in source   # tiktok 平台佣金率
    assert "0.1487" in source   # shopee 平台佣金率
    assert "0.2727" in source   # tiktok 平台其他成本率
    assert "0.4165" in source   # shopee 平台其他成本率
    assert "0.0606" in source   # tiktok 默认达人佣金率
    assert "0.0111" in source   # shopee 默认达人佣金率


def test_migration_is_idempotent_guarded():
    """迁移必须自带存在性守卫，可重复执行。"""
    source = MIGRATION.read_text(encoding="utf-8")
    for guard in ("_has_table", "_has_column", "_has_constraint", "_has_index"):
        assert f"def {guard}" in source, guard


def test_orm_exposes_pricing_columns_and_policy_table():
    from modules.core.db import DimErpSku, DimPlatform, SkuPricingPolicy

    sku_columns = {c.name for c in DimErpSku.__table__.columns}
    assert {"creator_commission_rate", "min_selling_price_override"} <= sku_columns

    platform_columns = {c.name for c in DimPlatform.__table__.columns}
    assert {"default_creator_commission_rate", "other_cost_rate"} <= platform_columns

    policy_columns = {c.name for c in SkuPricingPolicy.__table__.columns}
    assert {
        "policy_id", "min_age_days", "tier_label", "discount_rate",
        "target_margin_rate", "platform_basis", "effective_from", "effective_to",
        "status", "source", "version", "notes",
    } <= policy_columns

    constraint_names = {c.name for c in SkuPricingPolicy.__table__.constraints}
    assert {
        "uq_sku_pricing_policy_tier_start",
        "ck_sku_pricing_policy_age_start",
        "ck_sku_pricing_policy_discount_rate",
        "ck_sku_pricing_policy_target_margin",
        "ck_sku_pricing_policy_window",
        "ck_sku_pricing_policy_status",
    } <= constraint_names

    index_names = {i.name for i in SkuPricingPolicy.__table__.indexes}
    assert {
        "uq_sku_pricing_policies_current",
        "ix_sku_pricing_policy_scope",
    } <= index_names

    # Index 不接受 schema= 关键字，索引 schema 由表继承
    assert SkuPricingPolicy.__table__.schema == "finance"
    for index in SkuPricingPolicy.__table__.indexes:
        assert index.table.schema == "finance"


def test_orm_policy_model_is_exported_from_schema_module():
    """ORM SSOT 是 modules/core/db/schema.py：新模型必须从这里导出。"""
    import modules.core.db.schema as schema_module

    assert "SkuPricingPolicy" in schema_module.__all__
    assert hasattr(schema_module, "SkuPricingPolicy")
