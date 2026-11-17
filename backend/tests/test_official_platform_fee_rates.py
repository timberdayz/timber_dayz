"""平台费率按官方牌价校准（迁移 20261238）的守护测试。

背景
----
``core.dim_platforms`` 的费率原来是 2026-01-07 的实测残差（TikTok 7.37% / Shopee 14.87%），
而官方在这之后两次调价 ⇒ 底线偏低 ⇒ 定价偏低 ⇒ 亏本。本迁移把**平台佣金率**
按官方牌价校准，并把 Shopee SG 尾程切到官方 3PF 标准。

这一批钉死四件事：

1. **佣金按官方牌价**：Shopee 三方仓 16%（含税，2026-01-01 起）、TikTok 非 BXP
   8.175%（含 GST，2026-04-01 起）。
2. **尾程按官方 3PF 标准**，且口径是「商家包邮时承担总额 = 买家那份 + 卖家那份」
   —— 买家付 1.99 时那 1.99 不是卖家的成本，包邮后卖家要一个人扛两份。
3. **残差桶与尾程占收入比不动**：前者要用新实测数据重算，后者要与费率表同源，
   两者的前置条件这轮都不具备 ⇒ 保持原值，不在本迁移里"顺手改"。
4. **幂等**：既有行更新、没有则插入（生产上尾程费率 0 行，本地有 5 行）。
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261238_official_platform_fee_rates.py"
)


def _load_migration():
    """按文件路径加载（迁移文件名以数字开头，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location(
        "current_migration_20261238_official_platform_fee_rates", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


def test_migration_is_on_the_current_chain():
    """必须接在批次 6 的迁移后面，否则生产升级链会断。"""
    assert migration.revision == "current_schema_20261238_official_platform_fee_rates"
    assert migration.down_revision == "current_schema_20261237_free_shipping_flag"


def test_platform_commission_follows_official_rate_cards():
    """平台佣金按官方牌价：Shopee 三方仓 16% / TikTok 非 BXP 8.175%。"""
    updates = migration.PLATFORM_FEE_UPDATES
    assert updates["shopee"]["default_fee_rate"] == 0.16
    assert updates["tiktok"]["default_fee_rate"] == 0.08175
    # 生效日期必须写官方调价日，不能沿用旧实测的日期。
    assert str(updates["shopee"]["fee_rate_effective_from"]) == "2026-01-01"
    assert str(updates["tiktok"]["fee_rate_effective_from"]) == "2026-04-01"
    # 来源标记要说清「佣金是官方的、残差桶还是实测的」——混成一个来源会误导人。
    assert "official" in updates["shopee"]["fee_rate_source"]
    assert "b_class_measured" in updates["shopee"]["fee_rate_source"]
    assert "official" in updates["tiktok"]["fee_rate_source"]


def test_delivery_tiers_follow_official_3pf_card():
    """Shopee SG 尾程 = 官方 3PF 标准（2025-03-18 起），总额口径。"""
    tiers = migration.SHOPEE_SG_3PF_TIERS
    assert [item[0] for item in tiers] == ["T01", "T02", "T03", "T04", "T05"]
    for tier_code, buyer_sgd, seller_sgd, total_sgd in tiers:
        # 总额 = 买家那份 + 卖家那份（包邮后商家一个人扛两份）。
        assert buyer_sgd + seller_sgd == round(total_sgd, 2), tier_code
    # 官方 3PF 卡：买家 1.99 + 卖家 2.03/2.87/3.38/5.42/10.00。
    assert [item[2] for item in tiers] == [2.03, 2.87, 3.38, 5.42, 10.00]
    assert [item[3] for item in tiers] == [4.02, 4.86, 5.37, 7.41, 11.99]
    # 折算成人民币等值（汇率沿用 5.2077，不引入新汇率变量）。
    assert [migration._round_cny(item[3]) for item in tiers] == [
        20.93,
        25.31,
        27.97,
        38.59,
        62.44,
    ]


def test_migration_does_not_touch_residual_bucket_or_delivery_ratio():
    """残差桶与尾程占收入比**不动** —— 这轮没有重算它们的依据。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    update_section = source.split("def upgrade")[1].split("def downgrade")[0]
    for column in (
        "other_cost_rate",
        "delivery_cost_rate",
        "default_creator_commission_rate",
    ):
        assert column not in update_section, f"迁移不该改 {column}"


def test_tail_rate_upsert_is_idempotent():
    """生产上尾程费率 0 行、本地有 5 行 ⇒ 迁移必须"有则改、无则插"。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert migration.RULE_SCHEMA == "finance"
    assert migration.RULE_TABLE == "delivery_rate_rules"
    assert "SELECT rule_id FROM {RULE_SCHEMA}.{RULE_TABLE}" in source
    assert "UPDATE {RULE_SCHEMA}.{RULE_TABLE} SET" in source
    assert "INSERT INTO {RULE_SCHEMA}.{RULE_TABLE}" in source
    # 唯一键是 (platform_code, warehouse_code, weight_tier_code) 的当期有效行。
    assert "weight_tier_code = :tier" in source
    assert "status = 'active'" in source


def test_downgrade_restores_previous_values():
    """downgrade 必须能把佣金与尾程还原回迁移前的值。"""
    assert migration.PLATFORM_FEE_ROLLBACK["shopee"]["default_fee_rate"] == 0.1487
    assert migration.PLATFORM_FEE_ROLLBACK["tiktok"]["default_fee_rate"] == 0.0737
    assert migration.LEGACY_SHOPEE_SG_TOTALS["T01"] == 4.29
    assert migration.LEGACY_SHOPEE_SG_TOTALS["T05"] == 13.19
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "def downgrade" in source
    assert "b_class_measured_2026_01_07" in source


def test_downgrade_restores_effective_from_too():
    """降级要把**生效日期**也还原 —— 否则费率回到 1 月实测口径、日期却留在官方调价日。

    这是一个真实的数据错位：``fee_rate_effective_from`` 是产品中心保存费率时写下的
    生效日，迁移覆盖了它；降级若只还原费率不还原日期 ⇒ 一行"7.37%、2026-04-01 起"
    的自相矛盾数据（TikTok 官方调价日是 4 月，旧实测是 1 月 7 日）。
    """
    rollback = migration.PLATFORM_FEE_ROLLBACK
    # 旧口径是 2026-01-07 的实测残差 ⇒ 生效日期必须回到那一天。
    assert str(rollback["shopee"]["fee_rate_effective_from"]) == "2026-01-07"
    assert str(rollback["tiktok"]["fee_rate_effective_from"]) == "2026-01-07"
    # downgrade 段的 SQL 必须真的写了这一列（不是只在字典里躺着）。
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade_section = source.split("def downgrade")[1]
    assert "fee_rate_effective_from = :eff" in downgrade_section
