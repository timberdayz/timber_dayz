# 商品中心 SKU 定价底线（最低售价）实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在商品中心 SKU 资料页交付「当前可优惠 / 滞销可优惠 / 最低售价 / 达人佣金率」四列，并在平台 SKU 利润测算页加单层护栏，让团队成员改价时有一个可追溯、有依据的价格底线。

**Architecture:** 新增一张公司级 `finance.sku_pricing_policies` 库龄档位规则表（4 档，每档一个折扣率 + 一个目标利润率），新增一张平台级 `finance` 成本率登记（落在 `core.dim_platforms` 的两个新列），并在 `core.dim_erp_sku` 增加达人佣金率与人工覆盖最低售价两个可写列。计算逻辑全部收进新的纯函数服务 `backend/services/product_pricing_service.py`，商品中心路由只做编排。最低售价 = max(成本线, 纪律线, 人工覆盖值)，成本线由采购成本按平台成本率反解，纪律线由参考售价按当前库龄档位折扣率折算。

**Tech Stack:** PostgreSQL 15、Alembic current-schema 迁移、SQLAlchemy 2.0 async、FastAPI、Pydantic v2、pytest 8.4、Vue 3 + Element Plus、node:test。

**Spec:** `docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md`

---

## 执行前必读

### 0.1 已知既有红测试（不是本次引入，勿混淆）

`frontend/tests/productCenterUi.test.mjs` 当前**已经是红的**：

```
test("平台 SKU 利润测算保留候选接口预览并支持分页")
  assert.doesNotMatch(source, /preview:\s*null/)   ← 失败
```

根因：断言用的正则 `/preview:\s*null/` 过宽，命中了 `ProductCenter.vue:1592` 的 SPU 删除预检错误分支（`preview: null, error: e.message`）。该分支由提交 `5a264371 feat:23132`（2026-09-16）引入，早于本计划。

**处理方式（Task 10 的一步）**：把断言收窄到利润测算区域，而不是删掉 SPU 删除预检的 `preview: null`（那是有意义的错误语义）。修法：

```js
// frontend/tests/productCenterUi.test.mjs
const operatingSection = source.slice(
  source.indexOf('label="平台 SKU 利润测算"'),
  source.indexOf('label="物流仓储管理"'),
);
assert.doesNotMatch(operatingSection, /preview:\s*null/);
```

在 Task 10 修好之前，前端相关的每个 Task 的「Run test」步骤都必须**只统计本任务新增的用例**，不要把这条既有失败算到自己头上。

### 0.2 两项待业务确认的数值（Task 1 需落库，先按下列初值，可后续在定价设置抽屉改）

| 项 | 初值 | 状态 |
|---|---|---|
| 达人佣金平台兜底值 | tiktok 0.0606 / shopee 0.0111 | **待 Walter 与财务确认** |
| 平台佣金率校准 | 2% → tiktok 0.0737 / shopee 0.1487 | **待 Walter 与财务确认**（会让利润测算结果下降 5.4pp / 12.9pp） |

这两项在规则表/抽屉里都能改，确认后不需要改代码，只需改数据。

### 0.3 库龄数据当前是空的

`mart.inventory_age_current` 目前 0 行。本次交付后所有 SKU 走「日常」档兜底（`pricing_tier_source='fallback_no_age_data'`）。**库龄管道修复是独立任务，不在本计划范围。** 实现时不要依赖库龄表有数据。

### 0.4 测试命令

```powershell
# 后端
python -m pytest backend/tests/test_product_pricing_guardrails.py -q
python -m pytest backend/tests/test_sku_pricing_guardrails_contract.py -q
python -m pytest backend/tests/test_product_center_schema_contract.py -q

# 前端
node --test frontend/tests/productCenterUi.test.mjs
```

系统 Python 已装齐依赖（pytest 8.4.1 / sqlalchemy 2.0.41 / pydantic 2.11.7 / fastapi 0.116.1）；仓库 `.venv` 缺这些包，**不要用 `.venv` 跑测试**。

---

## File Structure

- Create: `current_migrations/versions/20261020_sku_pricing_guardrails.py` — 建规则表、加 4 个新列、灌初始数据、校准平台费率；`upgrade()` / `downgrade()` 均幂等。
- Create: `backend/services/product_pricing_service.py` — 纯计算：成本线 / 纪律线 / 最低售价 / 降级链 / 档位匹配。**不放 ORM 查询以外的业务判断，不 import 路由。**
- Create: `backend/tests/test_product_pricing_guardrails.py` — 计算层单测（纯函数，无需 DB）。
- Create: `backend/tests/test_sku_pricing_guardrails_contract.py` — 迁移契约测试（读迁移文件源码断言）。
- Modify: `modules/core/db/schema_parts/dimensions.py` — `DimErpSku` 加 2 列；`DimPlatform` 加 2 列。
- Modify: `modules/core/db/schema_parts/business.py` — 新增 `SkuPricingPolicy` ORM。
- Modify: `modules/core/db/schema.py` — 导入 `SkuPricingPolicy` 并加入 `__all__`。
- Modify: `backend/schemas/product_center.py` — `ProductCenterItem` + 11 字段；`SkuCreateRequest` / `SkuUpdateRequest` / `SkuBulkItem` + 2 字段；`PlatformFeeRateUpdateRequest` + 2 字段；`SkuOperatingPlatformOption` + 2 字段；新增规则表请求/响应模型。
- Modify: `backend/domains/business/routers/product_center.py` — 规则表 CRUD、平台成本率扩展、`list_skus` 计算注入、写入路径透传、利润测算护栏。
- Modify: `frontend/src/api/productCenter.js` — 新增规则表与平台成本率的 API 方法。
- Modify: `frontend/src/domains/business/views/ProductCenter.vue` — 定价设置抽屉、SKU 资料页 4 列、利润测算护栏。
- Modify: `frontend/tests/productCenterUi.test.mjs` — 新增用例 + 修 §0.1 的既有红断言。

---

## Task 1: 迁移与 ORM 骨架

**Files:**
- Create: `current_migrations/versions/20261020_sku_pricing_guardrails.py`
- Modify: `modules/core/db/schema_parts/dimensions.py`
- Modify: `modules/core/db/schema_parts/business.py`
- Modify: `modules/core/db/schema.py`
- Test: `backend/tests/test_sku_pricing_guardrails_contract.py`

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_sku_pricing_guardrails_contract.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_sku_pricing_guardrails_contract.py -q`

Expected: FAIL with `FileNotFoundError` — 迁移文件不存在。

- [ ] **Step 3: 写迁移**

创建 `current_migrations/versions/20261020_sku_pricing_guardrails.py`，沿用 `20260916_sku_turnover_storage_rules_cny.py` 的幂等范式（`_has_table` / `_has_column` / `_has_constraint` / `_has_index` 守卫，`safe_print` 不用 `print`）：

```python
"""Add SKU pricing guardrails: age-tier policy table, platform cost rates, SKU overrides."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "current_schema_20261020_sku_pricing_guardrails"
down_revision = "current_schema_20260921_warehouse_storage_label_fee"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        c["name"] for c in _inspector().get_columns(table, schema=schema)
    }


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        c.get("name") == name for c in _inspector().get_check_constraints(table, schema=schema)
    )


def _has_index(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        i["name"] == name for i in _inspector().get_indexes(table, schema=schema)
    )


POLICY_ROWS = [
    # min_age_days, tier_label, discount_rate, target_margin_rate, platform_basis
    (0, "日常", 0.10, 0.25, "tiktok"),
    (60, "滞销30天", 0.15, 0.22, "tiktok"),
    (90, "滞销60天", 0.20, 0.18, "tiktok"),
    (120, "滞销60天以上", 0.30, 0.10, "tiktok"),
]

PLATFORM_COST_RATES = {
    "tiktok": {
        "default_fee_rate": 0.0737,
        "default_creator_commission_rate": 0.0606,
        "other_cost_rate": 0.2727,
    },
    "shopee": {
        "default_fee_rate": 0.1487,
        "default_creator_commission_rate": 0.0111,
        "other_cost_rate": 0.4165,
    },
}


def upgrade() -> None:
    if not _has_table("sku_pricing_policies", "finance"):
        op.create_table(
            "sku_pricing_policies",
            sa.Column("policy_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("min_age_days", sa.Integer(), nullable=False),
            sa.Column("tier_label", sa.String(32), nullable=False),
            sa.Column("discount_rate", sa.Numeric(12, 8), nullable=False),
            sa.Column("target_margin_rate", sa.Numeric(12, 8), nullable=False),
            sa.Column("platform_basis", sa.String(32), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("source", sa.String(128), nullable=True),
            sa.Column("version", sa.String(64), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("min_age_days", "effective_from", name="uq_sku_pricing_policy_tier_start"),
            sa.CheckConstraint("min_age_days >= 0", name="ck_sku_pricing_policy_age_start"),
            sa.CheckConstraint("discount_rate >= 0 AND discount_rate <= 1", name="ck_sku_pricing_policy_discount_rate"),
            sa.CheckConstraint("target_margin_rate >= 0 AND target_margin_rate < 1", name="ck_sku_pricing_policy_target_margin"),
            sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_sku_pricing_policy_window"),
            sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_sku_pricing_policy_status"),
            schema="finance",
        )
    if not _has_index("sku_pricing_policies", "finance", "uq_sku_pricing_policies_current"):
        op.create_index(
            "uq_sku_pricing_policies_current",
            "sku_pricing_policies",
            ["min_age_days"],
            unique=True,
            postgresql_where=text("status = 'active' AND effective_to IS NULL"),
            schema="finance",
        )
    if not _has_index("sku_pricing_policies", "finance", "ix_sku_pricing_policy_scope"):
        op.create_index(
            "ix_sku_pricing_policy_scope",
            "sku_pricing_policies",
            ["min_age_days", "effective_from"],
            schema="finance",
        )

    if not _has_column("dim_platforms", "core", "default_creator_commission_rate"):
        op.add_column("dim_platforms", sa.Column("default_creator_commission_rate", sa.Numeric(12, 8), nullable=True), schema="core")
    if not _has_column("dim_platforms", "core", "other_cost_rate"):
        op.add_column("dim_platforms", sa.Column("other_cost_rate", sa.Numeric(12, 8), nullable=True), schema="core")
    for name in ("ck_dim_platforms_fee_rate_range", "ck_dim_platforms_creator_commission_rate_range", "ck_dim_platforms_other_cost_rate_range"):
        if not _has_constraint("dim_platforms", "core", name):
            column, expr = {
                "ck_dim_platforms_fee_rate_range": ("default_fee_rate", "default_fee_rate IS NULL OR (default_fee_rate >= 0 AND default_fee_rate <= 1)"),
                "ck_dim_platforms_creator_commission_rate_range": ("default_creator_commission_rate", "default_creator_commission_rate IS NULL OR (default_creator_commission_rate >= 0 AND default_creator_commission_rate <= 1)"),
                "ck_dim_platforms_other_cost_rate_range": ("other_cost_rate", "other_cost_rate IS NULL OR (other_cost_rate >= 0 AND other_cost_rate < 1)"),
            }[name]
            op.create_check_constraint(name, "dim_platforms", expr, schema="core")

    if not _has_column("dim_erp_sku", "core", "creator_commission_rate"):
        op.add_column("dim_erp_sku", sa.Column("creator_commission_rate", sa.Numeric(12, 8), nullable=True), schema="core")
    if not _has_column("dim_erp_sku", "core", "min_selling_price_override"):
        op.add_column("dim_erp_sku", sa.Column("min_selling_price_override", sa.Numeric(18, 2), nullable=True), schema="core")
    for name, expr in (
        ("ck_dim_erp_sku_creator_commission_rate", "creator_commission_rate IS NULL OR (creator_commission_rate >= 0 AND creator_commission_rate <= 1)"),
        ("ck_dim_erp_sku_min_selling_price_override", "min_selling_price_override IS NULL OR min_selling_price_override > 0"),
    ):
        if not _has_constraint("dim_erp_sku", "core", name):
            op.create_check_constraint(name, "dim_erp_sku", expr, schema="core")

    bind = op.get_bind()
    for min_age_days, tier_label, discount_rate, target_margin_rate, platform_basis in POLICY_ROWS:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM finance.sku_pricing_policies "
                "WHERE min_age_days = :m AND effective_from = CURRENT_DATE LIMIT 1"
            ),
            {"m": min_age_days},
        ).scalar()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO finance.sku_pricing_policies "
                    "(min_age_days, tier_label, discount_rate, target_margin_rate, platform_basis, "
                    " effective_from, status, source, version) "
                    "VALUES (:m, :l, :d, :t, :b, CURRENT_DATE, 'active', "
                    " 'industry_benchmark_2026', 'v1')"
                ),
                {
                    "m": min_age_days,
                    "l": tier_label,
                    "d": discount_rate,
                    "t": target_margin_rate,
                    "b": platform_basis,
                },
            )

    for platform_code, values in PLATFORM_COST_RATES.items():
        bind.execute(
            sa.text(
                "UPDATE core.dim_platforms SET default_fee_rate = :fee, "
                "default_creator_commission_rate = :crea, other_cost_rate = :other, "
                "fee_rate_source = 'b_class_measured_2026_01_07', fee_rate_version = 'v2' "
                "WHERE platform_code = :code AND platform_role = 'sales'"
            ),
            {"code": platform_code, "fee": values["default_fee_rate"], "crea": values["default_creator_commission_rate"], "other": values["other_cost_rate"]},
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM finance.sku_pricing_policies WHERE source = 'industry_benchmark_2026'"))
    if _has_table("sku_pricing_policies", "finance"):
        op.drop_table("sku_pricing_policies", schema="finance")
    for name in ("ck_dim_erp_sku_min_selling_price_override", "ck_dim_erp_sku_creator_commission_rate"):
        if _has_constraint("dim_erp_sku", "core", name):
            op.drop_constraint(name, "dim_erp_sku", schema="core", type_="check")
    for name in ("ck_dim_platforms_other_cost_rate_range", "ck_dim_platforms_creator_commission_rate_range", "ck_dim_platforms_fee_rate_range"):
        if _has_constraint("dim_platforms", "core", name):
            op.drop_constraint(name, "dim_platforms", schema="core", type_="check")
    for column in ("min_selling_price_override", "creator_commission_rate"):
        if _has_column("dim_erp_sku", "core", column):
            op.drop_column("dim_erp_sku", column, schema="core")
    for column in ("other_cost_rate", "default_creator_commission_rate"):
        if _has_column("dim_platforms", "core", column):
            op.drop_column("dim_platforms", column, schema="core")
```

- [ ] **Step 4: 加 ORM 列与模型**

`modules/core/db/schema_parts/dimensions.py`：

```python
# DimErpSku 内
creator_commission_rate    = Column(Numeric(12, 8), nullable=True)  # 该 SKU 达人佣金率，NULL = 用平台默认
min_selling_price_override = Column(Numeric(18, 2), nullable=True)  # 人工覆盖的最低售价

# DimPlatform 内
default_creator_commission_rate = Column(Numeric(12, 8), nullable=True)
other_cost_rate                 = Column(Numeric(12, 8), nullable=True)
```

`modules/core/db/schema_parts/business.py` 新增 `SkuPricingPolicy`（`__table_args__` 与迁移里的约束一一对应，CHECK 共 5 个、UNIQUE 1 个、INDEX 2 个）：

```python
class SkuPricingPolicy(Base):
    """公司级定价纪律规则，按 SKU 当前库龄档位配置。"""
    __tablename__ = "sku_pricing_policies"

    policy_id          = Column(Integer, primary_key=True, autoincrement=True)
    min_age_days       = Column(Integer, nullable=False)
    tier_label         = Column(String(32), nullable=False)
    discount_rate      = Column(Numeric(12, 8), nullable=False)
    target_margin_rate = Column(Numeric(12, 8), nullable=False)
    platform_basis     = Column(String(32), nullable=False)
    effective_from     = Column(Date, nullable=False)
    effective_to       = Column(Date, nullable=True)
    status             = Column(String(16), nullable=False, default="active")
    source             = Column(String(128), nullable=True)
    version            = Column(String(64), nullable=True)
    notes              = Column(Text, nullable=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at         = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("min_age_days", "effective_from", name="uq_sku_pricing_policy_tier_start"),
        CheckConstraint("min_age_days >= 0", name="ck_sku_pricing_policy_age_start"),
        CheckConstraint("discount_rate >= 0 AND discount_rate <= 1", name="ck_sku_pricing_policy_discount_rate"),
        CheckConstraint("target_margin_rate >= 0 AND target_margin_rate < 1", name="ck_sku_pricing_policy_target_margin"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_sku_pricing_policy_window"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_sku_pricing_policy_status"),
        Index("uq_sku_pricing_policies_current", "min_age_days", unique=True,
              postgresql_where=text("status = 'active' AND effective_to IS NULL")),
        Index("ix_sku_pricing_policy_scope", "min_age_days", "effective_from", schema="finance"),
        {"schema": "finance"},
    )
```

`modules/core/db/schema.py`：在 `from .schema_parts.business import (...)` 加 `SkuPricingPolicy`，并在 `__all__` 加 `"SkuPricingPolicy"`。

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_sku_pricing_guardrails_contract.py -q`

Expected: PASS.

- [ ] **Step 6: 跑迁移并验证幂等**

Run:
```powershell
python -m alembic upgrade heads
python -m alembic downgrade -1
python -m alembic upgrade heads
```

Expected: 三步均无报错。验证后查库：

```sql
SELECT count(*) FROM finance.sku_pricing_policies;              -- 4
SELECT platform_code, default_fee_rate, default_creator_commission_rate, other_cost_rate
  FROM core.dim_platforms WHERE platform_code IN ('tiktok','shopee');
-- tiktok 0.0737 / 0.0606 / 0.2727 ; shopee 0.1487 / 0.0111 / 0.4165
```

- [ ] **Step 7: 提交**

```bash
git add current_migrations/versions/20261020_sku_pricing_guardrails.py \
        modules/core/db/schema_parts/dimensions.py \
        modules/core/db/schema_parts/business.py \
        modules/core/db/schema.py \
        backend/tests/test_sku_pricing_guardrails_contract.py
git commit -m "feat:商品中心定价底线 - 迁移与 ORM 骨架"
```

---

## Task 2: 纯计算服务

**Files:**
- Create: `backend/services/product_pricing_service.py`
- Test: `backend/tests/test_product_pricing_guardrails.py`

这是整个功能的核心。**所有金额运算必须用 `Decimal`，费率不得量化。**

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_product_pricing_guardrails.py`：

```python
from decimal import Decimal

from backend.services.product_pricing_service import (
    compute_cost_floor,
    compute_discount_guard,
    compute_min_selling_price,
    select_age_tier,
)

# tiktok 基准值（实测，见 spec §2.3 / §1.2）
OTHER_COST_RATE = Decimal("0.2727")
CREATOR_COMMISSION_RATE = Decimal("0.0606")
RETURN_LOSS_RATE = Decimal("0.0467")
DAMAGE_RATE = Decimal("0.0158")


def _policy(min_age_days, label, discount_rate, target_margin_rate):
    return {
        "min_age_days": min_age_days,
        "tier_label": label,
        "discount_rate": Decimal(str(discount_rate)),
        "target_margin_rate": Decimal(str(target_margin_rate)),
    }


def test_cost_floor_matches_spec_example():
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=Decimal("0.25"),
    )
    assert floor == Decimal("28.23")


def test_cost_floor_does_not_double_count_platform_commission():
    """平台佣金率已含在 other_cost_rate 内，误加会让底线偏高 26%。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=CREATOR_COMMISSION_RATE,
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=Decimal("0.25"),
    )
    # 若误加平台佣金 0.0737，分母变 0.2805，底线会变成 35.65
    assert floor != Decimal("35.65")


def test_cost_floor_uses_sku_creator_commission_rate_when_provided():
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=OTHER_COST_RATE,
        creator_commission_rate=Decimal("0.15"),
        spu_return_loss_rate=RETURN_LOSS_RATE,
        spu_damage_rate=DAMAGE_RATE,
        target_margin_rate=Decimal("0.25"),
    )
    assert floor == Decimal("37.76")


def test_rates_are_not_quantized():
    """费率不得过 _money 量化：0.2727 -> 0.27 会让底线从 28.23 变 28.02。"""
    floor = compute_cost_floor(
        purchase_cost=Decimal("10"),
        other_cost_rate=Decimal("0.2727"),
        creator_commission_rate=Decimal("0.0606"),
        spu_return_loss_rate=Decimal("0.0467"),
        spu_damage_rate=Decimal("0.0158"),
        target_margin_rate=Decimal("0.25"),
    )
    assert floor == Decimal("28.23")


def test_self_consistency_identity():
    """目标利润率 = 实测净利率时，分母必须还原实测采购成本率 0.4261。"""
    denominator = (
        Decimal("1")
        - OTHER_COST_RATE
        - CREATOR_COMMISSION_RATE
        - RETURN_LOSS_RATE
        - DAMAGE_RATE
        - Decimal("0.1781")
    )
    assert denominator == Decimal("0.4261")


def test_discount_guard_uses_current_tier_rate():
    guard = compute_discount_guard(
        reference_selling_price=Decimal("30"),
        discount_rate=Decimal("0.15"),
    )
    assert guard == Decimal("25.50")


def test_discount_guard_is_none_without_reference_price():
    assert compute_discount_guard(reference_selling_price=None, discount_rate=Decimal("0.15")) is None


def test_select_age_tier_picks_largest_boundary_not_exceeding_age():
    policies = [
        _policy(0, "日常", 0.10, 0.25),
        _policy(60, "滞销30天", 0.15, 0.22),
        _policy(90, "滞销60天", 0.20, 0.18),
        _policy(120, "滞销60天以上", 0.30, 0.10),
    ]
    assert select_age_tier(policies, 30)["min_age_days"] == 0
    assert select_age_tier(policies, 59)["min_age_days"] == 0
    assert select_age_tier(policies, 60)["min_age_days"] == 60
    assert select_age_tier(policies, 89)["min_age_days"] == 60
    assert select_age_tier(policies, 90)["min_age_days"] == 90
    assert select_age_tier(policies, 200)["min_age_days"] == 120


def test_select_age_tier_falls_back_to_lowest_boundary_without_age():
    policies = [_policy(0, "日常", 0.10, 0.25), _policy(60, "滞销30天", 0.15, 0.22)]
    assert select_age_tier(policies, None)["min_age_days"] == 0


def test_min_selling_price_takes_the_maximum_of_three_lines():
    result = compute_min_selling_price(
        cost_floor=Decimal("28.23"),
        discount_guard=Decimal("27.00"),
        manual_override=None,
    )
    assert result["min_selling_price"] == Decimal("28.23")
    assert result["source"] == "cost_floor"


def test_min_selling_price_prefers_manual_override():
    result = compute_min_selling_price(
        cost_floor=Decimal("28.23"),
        discount_guard=Decimal("27.00"),
        manual_override=Decimal("26.00"),
    )
    assert result["min_selling_price"] == Decimal("26.00")
    assert result["source"] == "manual_override"
    assert result["is_override"] is True


def test_min_selling_price_reports_unavailable_when_no_line():
    result = compute_min_selling_price(cost_floor=None, discount_guard=None, manual_override=None)
    assert result["min_selling_price"] is None
    assert result["source"] == "unavailable"
    assert result["missing_reasons"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.product_pricing_service'`.

- [ ] **Step 3: 写实现**

创建 `backend/services/product_pricing_service.py`：

```python
```python
"""商品中心 SKU 定价底线的纯计算逻辑。

设计约束（来自 docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md）：
- 所有金额用 Decimal；费率只做 Decimal(str(x)) 转换，**不得量化**
- 平台佣金率已包含在 other_cost_rate 内，不得单独进入分母
- 达人佣金率优先用 SKU 值，NULL 时由调用方传入平台默认值
- 档位由当前库龄决定；库龄缺失回落 min_age_days 最小的一行

本模块**不持有任何平台参数**——费率由调用方从 dim_platforms 读出后传入，
避免平台口径变化时服务里的常量悄悄过期。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

MONEY_QUANTUM = Decimal("0.01")


def _decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    """最终金额量化到分。费率不要用这个函数。"""
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def compute_cost_floor(
    *,
    purchase_cost,
    other_cost_rate,
    creator_commission_rate,
    spu_return_loss_rate,
    spu_damage_rate,
    target_margin_rate,
) -> Optional[Decimal]:
    """采购成本反解出的保价底线；分母非正时返回 None。"""
    cost = _decimal(purchase_cost)
    if cost is None:
        return None
    denominator = (
        Decimal("1")
        - (_decimal(other_cost_rate) or Decimal("0"))
        - (_decimal(creator_commission_rate) or Decimal("0"))
        - (_decimal(spu_return_loss_rate) or Decimal("0"))
        - (_decimal(spu_damage_rate) or Decimal("0"))
        - (_decimal(target_margin_rate) or Decimal("0"))
    )
    if denominator <= 0:
        return None
    return _money(cost / denominator)


def compute_discount_guard(*, reference_selling_price, discount_rate) -> Optional[Decimal]:
    """参考售价按当前档折扣率折算的纪律线。"""
    price = _decimal(reference_selling_price)
    if price is None:
        return None
    rate = _decimal(discount_rate) or Decimal("0")
    return _money(price * (Decimal("1") - rate))


def select_age_tier(policies: Iterable[dict], age_days: Optional[int]) -> Optional[dict]:
    """按库龄命中档位；库龄缺失时回落 min_age_days 最小的一行。"""
    rows = [p for p in policies if p is not None]
    if not rows:
        return None
    if age_days is None:
        return min(rows, key=lambda p: p["min_age_days"])
    eligible = [p for p in rows if p["min_age_days"] <= age_days]
    if not eligible:
        return min(rows, key=lambda p: p["min_age_days"])
    return max(eligible, key=lambda p: p["min_age_days"])


def compute_min_selling_price(
    *,
    cost_floor: Optional[Decimal],
    discount_guard: Optional[Decimal],
    manual_override: Optional[Decimal],
) -> dict:
    """取三条线里的最大值，并给出来源标记。"""
    override = _decimal(manual_override)
    if override is not None:
        return {
            "min_selling_price": _money(override),
            "source": "manual_override",
            "is_override": True,
            "missing_reasons": [],
        }
    candidates = [(cost_floor, "cost_floor"), (discount_guard, "discount_guard")]
    available = [(value, source) for value, source in candidates if value is not None]
    if not available:
        return {
            "min_selling_price": None,
            "source": "unavailable",
            "is_override": False,
            "missing_reasons": ["no_pricing_input"],
        }
    value, source = max(available, key=lambda item: item[0])
    return {
        "min_selling_price": _money(value),
        "source": source,
        "is_override": False,
        "missing_reasons": [],
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py -q`

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add backend/services/product_pricing_service.py backend/tests/test_product_pricing_guardrails.py
git commit -m "feat:定价底线纯计算服务"
```

---

## Task 3: Pydantic 契约

**Files:**
- Modify: `backend/schemas/product_center.py`
- Modify: `backend/tests/test_product_center_schema_contract.py`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_product_center_schema_contract.py` 追加：

```python
def test_product_center_item_exposes_pricing_fields_as_optional():
    from backend.schemas.product_center import ProductCenterItem

    fields = ProductCenterItem.model_fields
    for name in (
        "creator_commission_rate",
        "current_discount_rate",
        "clearance_max_discount_rate",
        "min_selling_price",
        "min_selling_price_source",
        "min_selling_price_is_override",
        "min_selling_price_override",
        "min_selling_price_missing_reasons",
        "pricing_tier_label",
        "pricing_age_days",
        "pricing_tier_source",
    ):
        assert name in fields, name
        assert fields[name].is_required() is False, name


def test_sku_write_models_accept_pricing_overrides():
    from backend.schemas.product_center import SkuBulkItem, SkuCreateRequest, SkuUpdateRequest

    for model in (SkuUpdateRequest, SkuBulkItem, SkuCreateRequest):
        assert "creator_commission_rate" in model.model_fields
        assert "min_selling_price_override" in model.model_fields


def test_pricing_policy_request_models_expose_single_discount_rate():
    from backend.schemas.product_center import (
        SkuPricingPolicyCreateRequest,
        SkuPricingPolicyUpdateRequest,
    )

    for model in (SkuPricingPolicyCreateRequest, SkuPricingPolicyUpdateRequest):
        assert "discount_rate" in model.model_fields
        assert "standard_discount_rate" not in model.model_fields
        assert "clearance_discount_rate" not in model.model_fields
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_product_center_schema_contract.py -q`

Expected: FAIL with `ImportError` / `AssertionError` — 新字段与模型不存在。

- [ ] **Step 3: 改 schema**

`backend/schemas/product_center.py`：

```python
# ProductCenterItem 内追加（全部 Optional，带默认值）
creator_commission_rate: Optional[float] = None
current_discount_rate: Optional[float] = None
clearance_max_discount_rate: Optional[float] = None
min_selling_price: Optional[float] = None
min_selling_price_source: Optional[str] = None
min_selling_price_is_override: Optional[bool] = None
min_selling_price_override: Optional[float] = None
min_selling_price_missing_reasons: list[str] = Field(default_factory=list)
pricing_tier_label: Optional[str] = None
pricing_age_days: Optional[int] = None
pricing_tier_source: Optional[str] = None
```

```python
# SkuCreateRequest / SkuUpdateRequest / SkuBulkItem 内追加
creator_commission_rate: Optional[float] = Field(default=None, ge=0, le=1)
min_selling_price_override: Optional[float] = Field(default=None, gt=0)
```

```python
# PlatformFeeRateUpdateRequest 内追加
default_creator_commission_rate: Optional[float] = Field(default=None, ge=0, le=1)
other_cost_rate: Optional[float] = Field(default=None, ge=0, lt=1)
```

```python
# SkuOperatingPlatformOption 内追加
default_creator_commission_rate: Optional[float] = None
other_cost_rate: Optional[float] = None
```

新增规则表模型：

```python
class SkuPricingPolicyBase(BaseModel):
    tier_label: str = Field(min_length=1, max_length=32)
    discount_rate: float = Field(ge=0, le=1)
    target_margin_rate: float = Field(ge=0, lt=1)
    platform_basis: str = Field(min_length=1, max_length=32)
    effective_from: date
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None


class SkuPricingPolicyCreateRequest(SkuPricingPolicyBase):
    min_age_days: int = Field(ge=0)


class SkuPricingPolicyUpdateRequest(SkuPricingPolicyBase):
    min_age_days: int = Field(ge=0)


class SkuPricingPolicyResponse(SkuPricingPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    policy_id: int
    min_age_days: int
    effective_to: Optional[date] = None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_product_center_schema_contract.py -q`

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add backend/schemas/product_center.py backend/tests/test_product_center_schema_contract.py
git commit -m "feat:定价底线 Pydantic 契约"
```

---

## Task 4: 规则表与平台成本率 API

**Files:**
- Modify: `backend/domains/business/routers/product_center.py`
- Test: `backend/tests/test_product_pricing_guardrails.py`（追加 API 用例）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_product_pricing_guardrails.py` 追加（用仓库既有的 `AsyncSession` 测试夹具；**若该夹具不存在，改为纯源码断言**，参照 `backend/tests/test_product_center_p1_final.py` 的 `source.index()` 风格）：

```python
def test_router_exposes_pricing_policy_routes():
    from pathlib import Path

    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    assert '@router.get("/api/sku-pricing-policies")' in source
    assert '@router.get("/api/sku-pricing-policies/current")' in source
    assert '@router.post("/api/sku-pricing-policies")' in source
    assert '@router.put("/api/sku-pricing-policies/{min_age_days}")' in source
    assert "_require_platform_fee_editor" in source
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py -q`

Expected: FAIL — 路由不存在。

- [ ] **Step 3: 实现规则表 API**

`backend/domains/business/routers/product_center.py` 顶部新增导入（**当前文件没有 `Decimal`，必须加**）：

```python
from decimal import Decimal
```

并在 `from modules.core.db import (...)` 那一组里加入 `SkuPricingPolicy`；同时新增：

```python
from backend.services.product_pricing_service import (
    compute_cost_floor,
    compute_discount_guard,
    compute_min_selling_price,
    select_age_tier,
)
```

新增「当前行」唯一谓词与共享 helper（**两处必须复用，禁止各写一份**）：

```python
def _policy_current_predicate():
    return (
        SkuPricingPolicy.status == "active",
        SkuPricingPolicy.effective_to.is_(None),
        SkuPricingPolicy.effective_from <= date.today(),
    )


async def _current_policies(db: AsyncSession) -> list[SkuPricingPolicy]:
    result = await db.execute(
        select(SkuPricingPolicy).where(*_policy_current_predicate())
    )
    return list(result.scalars().all())
```

四个端点：

```python
@router.get("/api/sku-pricing-policies", response_model=list[SkuPricingPolicyResponse])
async def list_sku_pricing_policies(db: AsyncSession = Depends(get_async_db)):
    rows = (await db.execute(
        select(SkuPricingPolicy).order_by(SkuPricingPolicy.min_age_days, SkuPricingPolicy.effective_from)
    )).scalars().all()
    return [SkuPricingPolicyResponse.model_validate(row) for row in rows]


@router.get("/api/sku-pricing-policies/current", response_model=list[SkuPricingPolicyResponse])
async def list_current_sku_pricing_policies(db: AsyncSession = Depends(get_async_db)):
    rows = await _current_policies(db)
    return [SkuPricingPolicyResponse.model_validate(row) for row in rows]


@router.post("/api/sku-pricing-policies", response_model=SkuPricingPolicyResponse, status_code=201)
async def create_sku_pricing_policy(
    body: SkuPricingPolicyCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
    existing = (await db.execute(
        select(SkuPricingPolicy).where(
            SkuPricingPolicy.min_age_days == body.min_age_days,
            *_policy_current_predicate(),
        )
    )).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="a current policy already exists for this age tier")
    row = SkuPricingPolicy(**body.model_dump())
    db.add(row)
    await db.flush()
    await _write_product_center_audit(
        db, _user, action_type="create", resource_type="sku_pricing_policy",
        resource_id=str(row.policy_id), changes=body.model_dump(mode="json"),
    )
    await db.commit()
    await db.refresh(row)
    return SkuPricingPolicyResponse.model_validate(row)


@router.put("/api/sku-pricing-policies/{min_age_days}", response_model=SkuPricingPolicyResponse)
async def update_sku_pricing_policy(
    min_age_days: int,
    body: SkuPricingPolicyUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    _user=Depends(_require_platform_fee_editor),
):
    if body.min_age_days != min_age_days:
        raise HTTPException(status_code=422, detail="min_age_days in path and body must match")
    current = (await db.execute(
        select(SkuPricingPolicy).where(
            SkuPricingPolicy.min_age_days == min_age_days,
            *_policy_current_predicate(),
        ).with_for_update()
    )).scalars().first()

    if current is None:
        # 无当前行：等价 POST
        row = SkuPricingPolicy(**body.model_dump())
        db.add(row)
        action = "create"
    elif body.effective_from == current.effective_from:
        # 同日：原地 UPDATE（避免撞 UNIQUE(min_age_days, effective_from)）
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(current, key, value)
        row = current
        action = "update"
    elif body.effective_from > current.effective_from:
        # 跨期：关旧行 + 建新行（min_age_days 不同则不撞 UNIQUE）
        current.effective_to = body.effective_from
        current.status = "inactive"
        row = SkuPricingPolicy(**body.model_dump())
        db.add(row)
        action = "version"
    else:
        raise HTTPException(status_code=422, detail="effective_from cannot be earlier than the current policy")

    await db.flush()
    await _write_product_center_audit(
        db, _user, action_type=action, resource_type="sku_pricing_policy",
        resource_id=str(row.policy_id), changes=body.model_dump(mode="json"),
    )
    await db.commit()
    await db.refresh(row)
    return SkuPricingPolicyResponse.model_validate(row)
```

**并发保护**：捕获 `IntegrityError` → `await db.rollback()` → `HTTPException(409)`，与 `bulk_save_skus` 的既有模式一致。

- [ ] **Step 4: 扩展平台成本率端点**

`update_platform_fee_rate`（`product_center.py:1983`）改为「未传则保持原值」：

```python
values = body.model_dump(exclude_unset=True)
for key, value in values.items():
    setattr(row, key, value)
```

并把 `default_creator_commission_rate` / `other_cost_rate` 加进 `PlatformFeeRateUpdateRequest`（Task 3 已加）。响应体补回这两项。

`list_sku_operating_dimensions` 的 platforms 显式 dict（`product_center.py:2250-2252`）补两个新字段：

```python
"platforms": [{
    "platform_code": row.platform_code,
    "name": row.name,
    "default_fee_rate": row.default_fee_rate,
    "default_creator_commission_rate": row.default_creator_commission_rate,
    "other_cost_rate": row.other_cost_rate,
    "fee_rate_effective_from": row.fee_rate_effective_from,
    "fee_rate_source": row.fee_rate_source,
    "fee_rate_version": row.fee_rate_version,
} for row in platforms],
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py backend/tests/test_product_center_schema_contract.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add backend/domains/business/routers/product_center.py backend/tests/test_product_pricing_guardrails.py
git commit -m "feat:定价纪律规则表 API 与平台成本率扩展"
```

---

## Task 5: SKU 读写集成

**Files:**
- Modify: `backend/domains/business/routers/product_center.py`
- Test: `backend/tests/test_product_pricing_guardrails.py`

- [ ] **Step 1: 写失败测试**

追加源码断言 + 计算注入断言：

```python
def test_list_skus_injects_pricing_payload():
    from pathlib import Path

    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    for name in (
        "current_discount_rate",
        "clearance_max_discount_rate",
        "min_selling_price",
        "min_selling_price_source",
        "min_selling_price_override",
        "pricing_tier_label",
        "pricing_age_days",
        "pricing_tier_source",
    ):
        assert name in source, name
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py -q`

Expected: FAIL — 字段未注入。

- [ ] **Step 3: 实现库龄读取与最低售价计算**

在 `product_center.py` 新增两个辅助函数（`Decimal` 已在 Task 4 Step 3 导入；`DimErpSku` / `DimSpu` / `DimPlatform` / `BridgeSpuSku` 该文件已 import）：

```python
async def _load_age_days_by_sku(db: AsyncSession, sku_ids: list[int]) -> dict[int, int]:
    """按 product_sku -> dim_erp_sku.sku_key 关联取当前库龄。

    mart.inventory_age_current.sku_id 是 varchar 的平台侧 id，与 dim_erp_sku.sku_id(integer)
    不是一回事，必须走 product_sku -> sku_key。
    """
    if not sku_ids:
        return {}
    rows = (await db.execute(
        select(DimErpSku.sku_id, DimErpSku.sku_key)
        .where(DimErpSku.sku_id.in_(sku_ids))
    )).all()
    key_to_sku = {row.sku_key: row.sku_id for row in rows}
    if not key_to_sku:
        return {}
    age_rows = (await db.execute(
        text(
            "SELECT product_sku, MIN(age_days) AS age_days "
            "FROM mart.inventory_age_current "
            "WHERE product_sku = ANY(:keys) "
            "GROUP BY product_sku"
        ),
        {"keys": list(key_to_sku)},
    )).all()
    return {key_to_sku[row.product_sku]: row.age_days for row in age_rows if row.product_sku in key_to_sku}


async def _pricing_context(db: AsyncSession, sku_ids: list[int]) -> dict:
    """一次性把规则表、平台成本率、库龄读出来，供批量计算。"""
    policies = await _current_policies(db)
    policy_rows = [
        {
            "min_age_days": p.min_age_days,
            "tier_label": p.tier_label,
            "discount_rate": Decimal(str(p.discount_rate)),
            "target_margin_rate": Decimal(str(p.target_margin_rate)),
            "platform_basis": p.platform_basis,
        }
        for p in policies
    ]
    basis = policy_rows[0]["platform_basis"] if policy_rows else "tiktok"
    platform = await db.get(DimPlatform, basis)
    age_map = await _load_age_days_by_sku(db, sku_ids)
    return {
        "policies": policy_rows,
        "platform": platform,
        "age_days": age_map,
    }


def _compute_pricing_for_sku(
    *,
    context: dict,
    sku_row,
    linked_spu,
) -> dict:
    """给定 SKU 与其 SPU 率，算出该 SKU 的定价字段。list_skus 与利润测算护栏共用。"""
    policies = context["policies"]
    platform = context["platform"]
    age_days = context["age_days"].get(sku_row.sku_id)

    policy = select_age_tier(policies, age_days)
    deepest = max(policies, key=lambda p: p["min_age_days"]) if policies else None
    tier_source = "age_data" if age_days is not None else "fallback_no_age_data"

    missing_reasons: list[str] = []
    cost_floor = None
    discount_guard = None

    if policy is None:
        missing_reasons.append("missing_pricing_policy")
    else:
        creator_rate = sku_row.creator_commission_rate
        if creator_rate is None and platform is not None:
            creator_rate = platform.default_creator_commission_rate
        other_rate = platform.other_cost_rate if platform is not None else None
        if other_rate is None:
            missing_reasons.append("missing_platform_cost_rate")
        if creator_rate is None:
            missing_reasons.append("missing_creator_commission_rate")
        if other_rate is not None and creator_rate is not None:
            cost_floor = compute_cost_floor(
                purchase_cost=sku_row.default_purchase_cost,
                other_cost_rate=other_rate,
                creator_commission_rate=creator_rate,
                spu_return_loss_rate=linked_spu.return_loss_rate if linked_spu else None,
                spu_damage_rate=linked_spu.logistics_damage_rate if linked_spu else None,
                target_margin_rate=policy["target_margin_rate"],
            )
            if cost_floor is None:
                missing_reasons.append("non_positive_cost_denominator")
        if linked_spu is None:
            missing_reasons.append("missing_spu_binding")
        discount_guard = compute_discount_guard(
            reference_selling_price=sku_row.reference_selling_price,
            discount_rate=policy["discount_rate"],
        )

    pricing = compute_min_selling_price(
        cost_floor=cost_floor,
        discount_guard=discount_guard,
        manual_override=sku_row.min_selling_price_override,
    )
    all_reasons = list(dict.fromkeys(pricing["missing_reasons"] + missing_reasons))

    return {
        "creator_commission_rate": sku_row.creator_commission_rate,
        "current_discount_rate": float(policy["discount_rate"]) if policy else None,
        "clearance_max_discount_rate": float(deepest["discount_rate"]) if deepest else None,
        "min_selling_price": (
            float(pricing["min_selling_price"]) if pricing["min_selling_price"] is not None else None
        ),
        "min_selling_price_source": pricing["source"],
        "min_selling_price_is_override": pricing["is_override"],
        "min_selling_price_override": (
            float(sku_row.min_selling_price_override)
            if sku_row.min_selling_price_override is not None
            else None
        ),
        "min_selling_price_missing_reasons": all_reasons,
        "pricing_tier_label": policy["tier_label"] if policy else None,
        "pricing_age_days": age_days,
        "pricing_tier_source": tier_source,
    }


async def _compute_sku_min_selling_price(db: AsyncSession, sku_id: int) -> Optional[Decimal]:
    """单 SKU 的最低售价，供利润测算保存拦截复用。"""
    sku_row = await db.get(DimErpSku, sku_id)
    if sku_row is None:
        return None
    binding = (await db.execute(
        select(BridgeSpuSku).where(
            BridgeSpuSku.sku_id == sku_id,
            BridgeSpuSku.binding_status == "active",
            BridgeSpuSku.effective_to.is_(None),
        )
    )).scalars().first()
    linked_spu = await db.get(DimSpu, binding.spu) if binding else None
    context = await _pricing_context(db, [sku_id])
    payload = _compute_pricing_for_sku(context=context, sku_row=sku_row, linked_spu=linked_spu)
    value = payload["min_selling_price"]
    return Decimal(str(value)) if value is not None else None
```

> `_pricing_context` 里的 `basis` 取自当前生效规则行；`policy_rows` 需要带 `platform_basis` 字段，上面构造 dict 时补上 `"platform_basis": p.platform_basis`。

在 `list_skus` 里，`items` 循环前取一次 context，循环内注入：

```python
context = await _pricing_context(db, [row.sku_id for row in rows])
```

循环内（`payload.update({...})` 里追加）：

```python
pricing_payload = _compute_pricing_for_sku(
    context=context,
    sku_row=row,
    linked_spu=linked_spu,
)
payload.update(pricing_payload)
```

> `ProductCenterItem.model_validate(row)` 会从 ORM 行自动取到 `creator_commission_rate` / `min_selling_price_override`（这两个是真实列），其余 9 个字段靠上面的 `payload.update()` 注入。

- [ ] **Step 4: 打通写入路径**

`update_sku` / `bulk_save_skus` / `create_sku` 现有实现已用 `model_dump(exclude_unset=True)` + `setattr`，新增的 2 个字段自动生效，**无需改动**。但 `SkuBulkItem` 的 `sku_key` 必填、`update_sku` 传 `null` 即清空覆盖值——**确认这两点后**在 `backend/tests/test_product_pricing_guardrails.py` 加一条断言：

```python
def test_sku_update_accepts_null_to_clear_override():
    from backend.schemas.product_center import SkuUpdateRequest

    model = SkuUpdateRequest(min_selling_price_override=None)
    assert "min_selling_price_override" in model.model_dump(exclude_unset=True)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add backend/domains/business/routers/product_center.py backend/tests/test_product_pricing_guardrails.py
git commit -m "feat:SKU 列表注入定价底线字段"
```

---

## Task 6: 利润测算护栏

**Files:**
- Modify: `backend/domains/business/routers/product_center.py`
- Test: `backend/tests/test_product_pricing_guardrails.py`

- [ ] **Step 1: 写失败测试**

```python
def test_profit_candidates_and_estimate_guardrail_wired():
    from pathlib import Path

    source = Path("backend/domains/business/routers/product_center.py").read_text(encoding="utf-8")
    assert "below_min_selling_price" in source
    assert "min_selling_price_below" in source
    assert "clearance_max_discount_rate" in source
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py -q`

Expected: FAIL — 护栏未接线。

- [ ] **Step 3: 实现候选行注入**

`list_platform_sku_profit_candidates`（`product_center.py:2260`）里，**复用 Task 5 的 `_compute_pricing_for_sku`**：

```python
# 循环前
context = await _pricing_context(db, [row.sku_id for row in sku_rows])
```

```python
# 循环内
pricing_payload = _compute_pricing_for_sku(
    context=context,
    sku_row=row,
    linked_spu=assigned,
)
expected_selling_price = profile.expected_selling_price if profile else None
floor = pricing_payload["min_selling_price"]
pricing_payload["min_selling_price_below"] = bool(
    floor is not None
    and expected_selling_price is not None
    and Decimal(str(expected_selling_price)) < Decimal(str(floor))
)
items.append({**pricing_payload, ...})
```

> 候选接口一次最多 100 行，**用同一个 `_pricing_context` 批量取**，不要逐行 await。
> `assigned` 是该行绑定的 SPU（`spu_by_code.get(assigned_spu)`），没有绑定时传 `None`。

- [ ] **Step 4: 实现保存拦截**

`save_platform_sku_profit_estimates`（`product_center.py:2479`）在 `missing_fields` 校验之后、落库之前插入：

```python
floor = await _compute_sku_min_selling_price(db, values["sku_id"])
if floor is not None and values.get("expected_selling_price") is not None:
    if Decimal(str(values["expected_selling_price"])) < floor:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "below_min_selling_price",
                "min_selling_price": float(floor),
                "expected_selling_price": values["expected_selling_price"],
                "message": f"预计售价低于最低售价 {floor}",
            },
        )
```

`_compute_sku_min_selling_price(db, sku_id)` 是把 Task 5 的单 SKU 计算抽出来的薄封装（供这里复用，避免重复实现）。

> **草稿不拦截**：`save_platform_sku_profit_draft` 不加这段。

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest backend/tests/test_product_pricing_guardrails.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add backend/domains/business/routers/product_center.py backend/tests/test_product_pricing_guardrails.py
git commit -m "feat:利润测算最低售价护栏"
```

---

## Task 7: 前端 API 层与定价设置抽屉

**Files:**
- Modify: `frontend/src/api/productCenter.js`
- Modify: `frontend/src/domains/business/views/ProductCenter.vue`
- Test: `frontend/tests/productCenterUi.test.mjs`

- [ ] **Step 1: 写失败测试**

在 `frontend/tests/productCenterUi.test.mjs` 追加：

```js
test("商品中心提供定价纪律规则表 API", () => {
  assert.match(api, /sku-pricing-policies/);
  assert.match(api, /listSkuPricingPolicies/);
  assert.match(api, /updateSkuPricingPolicy/);
});

test("商品中心把平台费率抽屉升级为定价设置", () => {
  assert.match(source, /定价设置/);
  assert.match(source, /库龄档位规则/);
  assert.match(source, /当前可优惠/);
  assert.match(source, /清货极限/);
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Expected: 新增两条 FAIL（既有那条 `preview:\s*null` 的失败与本任务无关，见 §0.1）。

- [ ] **Step 3: 加 API 方法**

`frontend/src/api/productCenter.js`：

```js
  listSkuPricingPolicies(params = {}) {
    return api._get("/sku-pricing-policies", { params });
  },
  listCurrentSkuPricingPolicies() {
    return api._get("/sku-pricing-policies/current");
  },
  updateSkuPricingPolicy(minAgeDays, payload) {
    return api._put(`/sku-pricing-policies/${minAgeDays}`, payload);
  },
```

> `api._put` 已存在（`frontend/src/api/index.js` 导出，`productCenter.js` 里 `saveLogisticsBatchLines` 已在用），直接调用即可。

- [ ] **Step 4: 升级抽屉**

`ProductCenter.vue`：

1. 现有 `platformFeeDrawer` 改名 `pricingDrawer`，`title="定价设置"`，`size="720px"`，内含两个 `el-tab-pane`：
   - `平台成本率`：现有字段 + `默认达人佣金率`（`default_creator_commission_rate`）+ `平台其他成本率`（`other_cost_rate`）+ 只读「成本率合计」
   - `库龄档位规则`：4 行可编辑表格，列为 `库龄起点(min_age_days)` / `档位名(tier_label)` / `折扣率(discount_rate)` / `目标利润率(target_margin_rate)`
2. 利润测算 tab 的「平台费率管理」按钮改文案为「定价设置」，`@click` 打开抽屉时默认选中「平台成本率」子页
3. SKU 资料 tab 工具栏新增「定价设置」按钮，打开时默认选中「库龄档位规则」子页
4. 百分比输入统一走既有的 `toPercent` / `fromPercent`（`ProductCenter.vue:1866-1869`）

> ⚠️ **「默认达人佣金率」在 SKU 资料页的「达人佣金率」列被清空时，必须提交 `null` 而不是 `0`**。既有 `fromPercent(value, fallback = 0)` 默认会把空值转成 0 落库，导致成本线按 0% 佣金算、底线被压低 14.6%。该列要用 `fromPercent($event, null)`。

- [ ] **Step 5: 跑测试确认通过**

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Expected: 本任务新增的两条 PASS；`preview:\s*null` 那条仍 FAIL（Task 10 修）。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/productCenter.js frontend/src/domains/business/views/ProductCenter.vue frontend/tests/productCenterUi.test.mjs
git commit -m "feat:商品中心定价设置抽屉与规则表 API"
```

---

## Task 8: 前端 SKU 资料页四列

**Files:**
- Modify: `frontend/src/domains/business/views/ProductCenter.vue`
- Test: `frontend/tests/productCenterUi.test.mjs`

- [ ] **Step 1: 写失败测试**

```js
test("SKU 资料页展示定价底线四列", () => {
  assert.match(source, /当前可优惠/);
  assert.match(source, /滞销可优惠/);
  assert.match(source, /最低售价/);
  assert.match(source, /达人佣金率/);
  assert.match(source, /row\.current_discount_rate/);
  assert.match(source, /row\.clearance_max_discount_rate/);
  assert.match(source, /row\.min_selling_price_override/);
  assert.match(source, /row\.creator_commission_rate/);
});

test("SKU 保存剔除只读计算字段但保留可写字段", () => {
  const section = source.slice(
    source.indexOf("const payloadSku"),
    source.indexOf("const validateSpu"),
  );
  assert.match(section, /delete payload\.current_discount_rate/);
  assert.match(section, /delete payload\.min_selling_price/);
  assert.doesNotMatch(section, /delete payload\.min_selling_price_override/);
  assert.doesNotMatch(section, /delete payload\.creator_commission_rate/);
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Expected: 新增两条 FAIL。

- [ ] **Step 3: 加四列**

`ProductCenter.vue` 的 SKU 资料 tab，插在「参考售价」列之后：

```vue
<el-table-column label="当前可优惠" width="110">
  <template #default="{ row }">
    <el-tag size="small" type="info">{{ percent(row.current_discount_rate) }}</el-tag>
  </template>
</el-table-column>
<el-table-column label="滞销可优惠" width="110">
  <template #default="{ row }">
    <el-tag size="small" type="warning">{{ percent(row.clearance_max_discount_rate) }}</el-tag>
  </template>
</el-table-column>
<el-table-column label="最低售价" width="190">
  <template #default="{ row }">
    <div class="rate-cell">
      <span class="readonly-cell">{{ money(row.min_selling_price) }}</span>
      <el-input-number
        v-model="row.min_selling_price_override"
        :min="0.01"
        :precision="2"
        :controls="false"
        size="small"
        placeholder="自动"
        @change="markDirty('sku', row)" />
    </div>
  </template>
</el-table-column>
<el-table-column label="达人佣金率" width="115">
  <template #default="{ row }">
    <el-input-number
      :model-value="toPercent(row.creator_commission_rate)"
      :min="0"
      :max="100"
      :step="0.1"
      :precision="2"
      :controls="false"
      size="small"
      @update:model-value="row.creator_commission_rate = fromPercent($event, null); markDirty('sku', row)" />
  </template>
</el-table-column>
```

> `percent` / `money` helper 若不存在，用既有的百分比与金额格式化函数替换。

- [ ] **Step 4: 剔除只读字段**

`payloadSku`（`ProductCenter.vue:1341`）改为：

```js
const payloadSku = (row) => {
  const { __new, ...payload } = row;
  payload.purchase_cost_currency = "CNY";
  payload.selling_price_currency = "CNY";
  // 只读计算字段：后端算出来的，不回传
  delete payload.current_discount_rate;
  delete payload.clearance_max_discount_rate;
  delete payload.min_selling_price;
  delete payload.min_selling_price_source;
  delete payload.min_selling_price_is_override;
  delete payload.min_selling_price_missing_reasons;
  delete payload.pricing_tier_label;
  delete payload.pricing_age_days;
  delete payload.pricing_tier_source;
  return payload;
};
```

- [ ] **Step 5: `blankSku` 补字段**

`ProductCenter.vue:925` 的 `blankSku()` 追加：

```js
  creator_commission_rate: null,
  min_selling_price_override: null,
```

- [ ] **Step 6: 跑测试确认通过**

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Expected: 本任务新增的两条 PASS。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/domains/business/views/ProductCenter.vue frontend/tests/productCenterUi.test.mjs
git commit -m "feat:SKU 资料页定价底线四列"
```

---

## Task 9: 前端利润测算护栏

**Files:**
- Modify: `frontend/src/domains/business/views/ProductCenter.vue`
- Test: `frontend/tests/productCenterUi.test.mjs`

- [ ] **Step 1: 写失败测试**

```js
test("利润测算页展示最低售价并拦截低于底线的预计售价", () => {
  assert.match(source, /row\.min_selling_price/);
  assert.match(source, /row\.current_discount_rate/);
  assert.match(source, /row\.clearance_max_discount_rate/);
  assert.match(source, /低于最低售价/);
  assert.match(source, /below_min_selling_price/);
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Expected: 新增一条 FAIL。

- [ ] **Step 3: 加三列与拦截**

「预计售价」列右侧加：

```vue
<el-table-column label="最低售价" width="110">
  <template #default="{ row }">
    <span class="readonly-cell">{{ money(row.min_selling_price) }}</span>
  </template>
</el-table-column>
```

「竞品价格」列右侧加：

```vue
<el-table-column label="当前可优惠" width="110">
  <template #default="{ row }">
    <el-tag size="small" type="info">{{ percent(row.current_discount_rate) }}</el-tag>
  </template>
</el-table-column>
<el-table-column label="清货极限" width="100">
  <template #default="{ row }">
    <el-tag size="small" type="warning">{{ percent(row.clearance_max_discount_rate) }}</el-tag>
  </template>
</el-table-column>
```

「预计售价」输入框加标红与提示：

```vue
<el-input-number
  v-model="row.expected_selling_price"
  :class="{ 'price-below-floor': isBelowFloor(row) }"
  ... />
```

```js
const isBelowFloor = (row) =>
  row.min_selling_price != null &&
  row.expected_selling_price != null &&
  Number(row.expected_selling_price) < Number(row.min_selling_price);
```

「保存利润版本」按钮禁用：

```vue
<el-button
  link
  :disabled="isBelowFloor(row)"
  @click="saveOperatingEstimate(row)">
  保存利润版本
</el-button>
```

`saveOperatingEstimate` 的 catch 分支扩展示新 422：

```js
const detail = error?.response?.data?.detail || error?.detail;
if (detail?.code === "below_min_selling_price") {
  ElMessage.error(
    `预计售价低于最低售价 ${money(detail.min_selling_price)}（当前 ${money(detail.expected_selling_price)}）`,
  );
  return;
}
const missing = detail?.missing_fields;
```

- [ ] **Step 4: 跑测试确认通过**

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Expected: 本任务新增的一条 PASS。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/domains/business/views/ProductCenter.vue frontend/tests/productCenterUi.test.mjs
git commit -m "feat:利润测算最低售价护栏前端"
```

---

## Task 10: 全量验证与既有红测试修复

**Files:**
- Modify: `frontend/tests/productCenterUi.test.mjs`
- Test: 全部

- [ ] **Step 1: 修 §0.1 的既有红断言**

`frontend/tests/productCenterUi.test.mjs` 里，把

```js
assert.doesNotMatch(source, /preview:\s*null/);
```

改为作用域收窄的写法：

```js
const operatingSection = source.slice(
  source.indexOf('label="平台 SKU 利润测算"'),
  source.indexOf('label="物流仓储管理"'),
);
assert.doesNotMatch(operatingSection, /preview:\s*null/);
```

- [ ] **Step 2: 跑全部后端相关测试**

Run:
```powershell
python -m pytest backend/tests/test_product_pricing_guardrails.py backend/tests/test_sku_pricing_guardrails_contract.py backend/tests/test_product_center_schema_contract.py backend/tests/test_turnover_storage_contract.py backend/tests/test_product_center_service.py backend/tests/test_product_center_p1_final.py -q
```

Expected: 全部 PASS（既有测试不得回归）。

- [ ] **Step 3: 跑全部前端测试**

Run: `node --test frontend/tests/productCenterUi.test.mjs`

Expected: 全部 PASS。

- [ ] **Step 4: 端到端手工验证**

启动后端与前端（见 `docs/guides/DEVELOPMENT_WORKFLOW.md`），在商品中心页验证：

1. SKU 资料 tab 出现 4 列；`166851422928` 显示 当前可优惠 10%、滞销可优惠 30%、最低售价 28.23、达人佣金率空
2. 把该 SKU 的达人佣金率填 15% 并保存 → 最低售价变为 37.76
3. 把该 SKU 的最低售价覆盖值填 20.00 并保存 → 生效值 20.00，来源标记显示「人工设定」
4. 点「重置为自动值」→ 回到 37.76
5. 定价设置抽屉两个子 Tab 可切换；档位规则改「日常」档折扣率 10% → 12% 保存后，SKU 资料页「当前可优惠」变 12%
6. 利润测算 tab 输入低于最低售价的预计售价 → 输入框标红、保存按钮禁用
7. 恢复上述手工改动（清空达人佣金率与覆盖值、档位恢复 10%）

- [ ] **Step 5: 提交**

```bash
git add frontend/tests/productCenterUi.test.mjs
git commit -m "test:收窄商品中心预览断言作用域,修复既有失败"
```

---

## 收尾

- [ ] **Step 1: 记录库龄管道依赖**

在 spec 的「已知限制」第 5 条追加一行实施后确认的信息：本次上线后 `pricing_tier_source='fallback_no_age_data'` 的 SKU 数（应为 1118），以及库龄管道修通后无需改代码的验证点。

- [ ] **Step 2: 提交**

```bash
git add docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md
git commit -m "docs:记录定价底线交付后的库龄兜底实况"
```

- [ ] **Step 3: 汇总交付**

向 Walter 报告：完成的 10 个任务、验证命令与结果、两项待业务确认数值（达人佣金兜底值、平台佣金校准）的当前状态，以及**库龄管道修复仍未开始**这一事实。

---

## 附：给后续任务（不属本计划）的移交说明

库龄管道修复（独立 spec / 独立计划）需要处理：

1. `b_class.fact_*_inventory_snapshot` 三张表 0 行 —— 采集层 2026-09 重写为 V2 canonical（`modules/platforms/miaoshou/components/inventory_export.py` + `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["inventory"]`）后，同步层未同步（该次 spec 非范围明确写了「不改同步层、不改 SQL 三层」）
2. `stage_inventory` 只在 `backend/domains/data_platform/routers/field_mapping_ingest.py:869` 被调用；`backend/services/data_ingestion_service.py` import 了却从不调用
3. `core.staging_inventory` 的 80280 行是 2025-11-17~22 的一次性历史导入（`scripts/migrate_miaoshou_to_inventory_domain.py` 的数据域改名迁移产物），不是持续采集
4. 管道修通后必须补的验收断言：**tiktok / shopee 的库存行必须带 `商品SKU`**，否则 `mart.inventory_age_current.product_sku` 为 NULL，该平台库龄对商品中心的 join 永远匹配不上
5. 库龄匹配率基线：`mart.inventory_age_current.product_sku` → `core.dim_erp_sku.sku_key` 实测 1080/1094（98.72%），无一对多
