# 商品中心 SKU 定价底线（最低售价）与定价纪律规则

**状态**: 设计稿待评审
**日期**: 2026-10-20
**范围**: 商品中心（`backend/domains/business/routers/product_center.py`、`backend/schemas/product_center.py`、`backend/services/product_pricing_service.py`（新建）、`modules/core/db/schema_parts/dimensions.py`、`current_migrations/versions/`、`frontend/src/domains/business/views/ProductCenter.vue`、`frontend/src/api/productCenter.js`）。

**非范围**:
- 不修改利润测算公式 `build_platform_profit_preview` 的成本项构成（仍只含采购/物流/仓储/贴单/平台费/退货/货损/广告）
- 不修改飞书投影字段（`_enqueue_sku_projection` / `_enqueue_platform_sku_profit_projection`）
- 不做 SKU 尺寸数据（重量/体积/箱规）补齐
- 不做批量改价、不做改价审批流、不做定价回写平台
- 不修改 `finance.sku_profit_estimates` 的历史版本数据
- 不修改 `b_class` 原始层任何数据

---

## 1. 背景与动机

### 1.1 业务场景

团队成员被问「这个 SKU 最低能卖多少钱」时，系统里没有任何依据：

- 商品中心没有价格底线概念
- 前端（SKU 资料 tab、平台 SKU 利润测算 tab）完全看不到底线
- 团队只能凭经验拍价；利润测算 tab 虽会算出负利润率，但需要人工主动点「试算」才能发现

### 1.2 实测数据（本地库 `xihong_erp`，2026-10-20）

**主数据完备度**（`core` schema）：

| 字段 | 有值数 | 覆盖率 | 影响 |
|---|---|---|---|
| `dim_erp_sku` 总量 / active | 1121 / 1118 | 100% | |
| `dim_erp_sku.default_purchase_cost` | 1084 | 96.7% | 成本线可算 |
| `dim_spu.logistics_damage_rate` | 285 / 286 | 99.6% | 成本线可算 |
| `dim_spu.return_loss_rate` | 285 / 286 | 99.6% | 成本线可算 |
| `dim_erp_sku.reference_selling_price` | 2 | 0.2% | 纪律线当前几乎不生效 |
| `dim_erp_sku.turnover_class` | 3 | 0.3% | 档位规则需兜底 |
| `dim_erp_sku.unit_volume_cbm` | 3 | 0.3% | 物流仓储无法逐 SKU 精算 |
| `dim_erp_sku.weight_kg` | 0 | 0% | 同上 |
| `dim_erp_sku.units_per_carton` | 0 | 0% | 同上 |
| `bridge_spu_sku` 有效绑定 | 1121 | 100% | SPU 率可继承 |

**订单侧实际成本结构**（`b_class.fact_tiktok_orders_monthly` 2026-01~07 共 4080 行、`b_class.fact_shopee_orders_monthly` 22347 行；口径为「合计金额 / 合计收入」）：

| 成本项 | TikTok 占收入 | Shopee 占收入 |
|---|---|---|
| 采购成本 | 42.61% | 38.15% |
| 平台佣金 | 7.37% | 14.87% |
| 平台服务费 | 0% | 3.50% |
| 达人佣金 | 5.29% | — |
| 联盟商店广告佣金 | 0.77% | 1.11% |
| 实际运费 | 15.36% | 17.73% |
| 仓库操作费 | 5.91%（回冲） | 5.32% |
| 广告成本 | 14.74% | 3.62% |
| 商家折扣退款金额 | 6.70% | 2.00% |
| **净利（利润 / 收入）** | **17.81%** | **12.84%** |
| 单 SKU 平均销售利润率 | 8.31% | 6.88% |

**三条关键结论**：

1. **物流 + 广告 + 仓储合计占收入约 30%+，且无法逐 SKU 精确计算**（尺寸数据 0~3/1121）。逐项精算不可行，必须用平台级成本率参数。
2. **组合净利率 17.81% / 12.84%，但单 SKU 平均销售利润率仅 8.31% / 6.88%**。行业口径是净利率 <10% 进观察名单、<5% 已在失败（TikTok 品类基准：美妆 25–35%、服饰 15–25%、电子 10–15%）。长尾 SKU 大面积贴在盈亏线上，这是「最低售价」功能的直接价值来源。
3. **平台佣金当前配置值 2% 明显低于实测值**（TikTok 7.37%、Shopee 14.87%），利润测算算出的利润系统性偏高。

### 1.3 达人佣金粒度（设计输入）

达人佣金在 TikTok Shop 是**按商品设置佣金区间、按达人链接单独谈**，不是平台统一费率。实测验证（TikTok 月表，按产品聚合）：

| 产品 ID | 订单数 | 收入 | 达人佣金率 | 平台佣金率 |
|---|---|---|---|---|
| 1730795978936518642 | 172 | 12,739 | -6.96% | 固定 |
| 1731239874443642866 | 833 | 26,481 | -6.31% | 固定 |
| 1731242880818710514 | 511 | 33,080 | -6.20% | 固定 |
| 1731820246736996338 | 136 | 8,681 | -6.09% | 固定 |
| 1731263303349405682 | 7 | 801 | -13.01% | 固定 |
| 1730807590838700018 | 1 | 132 | -15.01% | 固定 |
| 1730795977695791090 | 2 | 44 | -33.80% | 固定 |

订单级分布：0–5% 占 53%，5–10% 占 34%，10–15% 占 12%，15–20% 占 0.8%。
对比：平台佣金在订单级 100% 落在同一固定档位。

**结论**：平台佣金是平台级固定值 → 落 `dim_platforms`；达人佣金是商品级变量 → 落 `dim_erp_sku`（可空，NULL 表示使用平台默认值）。

---

## 2. 决策

| 决策项 | 结论 |
|---|---|
| 最低售价定义 | `max(成本线, 纪律线, 人工覆盖值)` |
| 成本线 | 采购成本 ÷ (1 − 平台其他成本率 − SPU退货损失率 − SPU货损率 − 达人佣金率 − 目标毛利率) |
| 纪律线 | 参考售价 × (1 − 滞销可优惠率) |
| 折扣率归属 | 公司级规则表 `finance.sku_pricing_policies`，按周转档位 |
| 档位缺失 | 规则表增加 `unclassified` 兜底档，不动存量数据 |
| 目标毛利率 | 规则表每档独立 |
| 人工覆盖 | `core.dim_erp_sku.min_selling_price_override` 存人工值；自动值**实时计算，不落库** |
| 平台佣金校准 | 本次一并校准 `dim_platforms.default_fee_rate` 为实测值；底线口径与利润测算口径合并 |
| 护栏 | 利润测算 tab 显示最低售价 + 填价标红 + 保存利润版本后端 422 |
| 参数录入入口 | 升级现有「平台费率管理」抽屉为「定价设置」抽屉（两个子 Tab），不新增独立入口 |

### 2.1 行业基准（规则表初始值的依据）

| 项 | 区间 | 来源 |
|---|---|---|
| 拉新/常规促销折扣 | 10%–25% | racklify《How To Structure TikTok Shop Product Discounts For Seasonal Campaigns》 |
| 锚定定价（略低于竞品） | 低 5%–10% | 大数跨境《TikTok市场定价策略与运营指南》 |
| 库存清仓折扣 | 30%–60% | racklify 同上 |
| 清仓最佳折扣区间 | 原价 30%–50% | 大数跨境《美国速卖通清仓运营指南》 |
| 分阶段清仓 | 90–180 天降 20%–25%；181–365 天降 35%–50% | 大数跨境《美国电商库存定价策略与成本控制指南》 |
| 清仓毛利底线 | 实际毛利率 ≥ 15% | 大数跨境《美国速卖通清仓运营指南》 |
| 净利率观察线 / 失败线 | < 10% / < 5% | margn.shop《unprofitable tiktok shop products》 |
| 品类净利率基准 | 美妆 25–35%、服饰 15–25%、电子 10–15% | margn.shop 同上 |

### 2.2 规则表初始值

`finance.sku_pricing_policies` 初始 4 行（`effective_from` = 迁移执行日）：

| turnover_class | 常规最大折扣率 | 滞销最大折扣率 | 目标毛利率 | 成本基准平台 | 依据 |
|---|---|---|---|---|---|
| `fast` (30 天) | 10% | 20% | 20% | tiktok | 常规取拉新促销 10–25% 下沿；30 天压货对应行业 90–180 天档 20–25% |
| `normal` (60 天) | 10% | 30% | 18% | tiktok | 清仓 30–50% 下沿；目标毛利贴近实测净利率 17.81% |
| `slow` (90 天) | 15% | 40% | 15% | tiktok | 慢销品本就让利；15% 正是行业清仓毛利底线 |
| `unclassified` | 10% | 30% | 18% | tiktok | 兜底取 normal 档 |

目标毛利率阶梯跨越实测净利率 17.81%：快销品要求比现状更好（20%），普通品维持现状（18%），慢销品允许降到行业清仓底线（15%）。

### 2.3 平台成本率初始值

`core.dim_platforms`：

| platform_code | `default_fee_rate`（平台佣金率） | `default_creator_commission_rate` | `other_cost_rate` |
|---|---|---|---|
| tiktok | 0.0737 | 0.0606 | 0.2727 |
| shopee | 0.1487 | 0.0111 | 0.4165 |

`other_cost_rate` 定义（平台级，除采购成本、平台佣金、达人佣金、SPU 退货/货损之外的全部成本占收入比）：

```
other_cost_rate = 1 − 实测采购成本率 − 实测净利率 − 平均 SPU 退货损失率 − 平均 SPU 货损率 − 默认达人佣金率

tiktok: 1 − 0.4261 − 0.1781 − 0.0467 − 0.0158 − 0.0606 = 0.2727
shopee:  1 − 0.3815 − 0.1284 − 0.0467 − 0.0158 − 0.0111 = 0.4165
```

用恒等式反推而非逐项加总，因为逐项加总会漏项（Shopee 分项加总 42.65% vs 反推 49.01%，差 6.36 个百分点无法归因）。

`amazon` 无实测数据，`default_fee_rate` 保持 NULL，三项成本率均不设置 → 不参与底线计算（见 §4.4 降级链）。

---

## 3. 数据模型

### 3.1 `core.dim_platforms` — 新增 2 列 + 校准 1 列

```python
default_creator_commission_rate = Column(Numeric(12, 8), nullable=True)  # 默认达人/联盟佣金率
other_cost_rate                 = Column(Numeric(12, 8), nullable=True)  # 平台其他成本率
```

`default_fee_rate` 语义**收窄为「平台佣金率」**并校准为实测值。`fee_rate_effective_from` / `fee_rate_source` / `fee_rate_version` 复用为这三项成本率共同的生效日期 / 来源 / 版本标记，不新增列。

约束：
```sql
CHECK (default_fee_rate IS NULL OR (default_fee_rate >= 0 AND default_fee_rate <= 1))
CHECK (default_creator_commission_rate IS NULL OR (default_creator_commission_rate >= 0 AND default_creator_commission_rate <= 1))
CHECK (other_cost_rate IS NULL OR (other_cost_rate >= 0 AND other_cost_rate < 1))
```

### 3.2 `core.dim_erp_sku` — 新增 2 列

```python
creator_commission_rate    = Column(Numeric(12, 8), nullable=True)  # 该 SKU 达人佣金率，NULL = 用平台默认
min_selling_price_override = Column(Numeric(18, 2), nullable=True)  # 人工覆盖的最低售价
```

约束：
```sql
CHECK (creator_commission_rate IS NULL OR (creator_commission_rate >= 0 AND creator_commission_rate <= 1))
CHECK (min_selling_price_override IS NULL OR min_selling_price_override > 0)
```

### 3.3 新表 `finance.sku_pricing_policies`

```python
class SkuPricingPolicy(Base):
    """公司级定价纪律规则，按 SKU 周转档位配置。"""
    __tablename__ = "sku_pricing_policies"

    policy_id                 = Column(Integer, primary_key=True, autoincrement=True)
    turnover_class            = Column(String(16), nullable=False)          # fast|normal|slow|unclassified
    standard_discount_rate    = Column(Numeric(12, 8), nullable=False)      # 常规最大折扣率
    clearance_discount_rate   = Column(Numeric(12, 8), nullable=False)      # 滞销最大折扣率
    target_margin_rate        = Column(Numeric(12, 8), nullable=False)      # 目标净利率
    platform_basis            = Column(String(32), nullable=False)          # 成本基准平台
    effective_from            = Column(Date, nullable=False)
    effective_to              = Column(Date, nullable=True)
    policy_source             = Column(String(128), nullable=True)
    created_at                = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at                = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("turnover_class", "effective_from", name="uq_sku_pricing_policy_tier_start"),
        CheckConstraint("turnover_class IN ('fast','normal','slow','unclassified')", name="ck_sku_pricing_policy_tier"),
        CheckConstraint("standard_discount_rate >= 0 AND standard_discount_rate <= 1", name="ck_sku_pricing_policy_standard_discount"),
        CheckConstraint("clearance_discount_rate >= standard_discount_rate", name="ck_sku_pricing_policy_clearance_ge_standard"),
        CheckConstraint("target_margin_rate >= 0 AND target_margin_rate < 1", name="ck_sku_pricing_policy_target_margin"),
        Index("ix_sku_pricing_policy_scope", "turnover_class", "effective_from", schema="finance"),
        {"schema": "finance"},
    )
```

规则变更需要真实版本历史（改一次影响 1118 个 SKU 的底价），因此用 `effective_from` / `effective_to` 软关闭历史行。

---

## 4. 计算模型

### 4.1 公式

```
成本线 = 采购成本 C ÷ (1 − 平台其他成本率 − SPU退货损失率 − SPU货损率 − 达人佣金率 − 目标毛利率)

纪律线 = 参考售价 × (1 − 滞销可优惠率)

最低售价 = max(成本线, 纪律线, min_selling_price_override)
```

其中：
- 平台其他成本率 = 规则表 `platform_basis` 对应平台的 `dim_platforms.other_cost_rate`
- SPU 退货损失率 / 货损率 = 该 SKU 有效绑定 SPU 的 `dim_spu.return_loss_rate` / `logistics_damage_rate`
- 达人佣金率 = `dim_erp_sku.creator_commission_rate`，NULL 时取平台的 `default_creator_commission_rate`
- 目标毛利率 = 规则表对应档位的 `target_margin_rate`
- 滞销可优惠率 = 规则表对应档位的 `clearance_discount_rate`

### 4.2 自洽性验证

当「目标毛利率 = 实测净利率」且「各 SKU 率 = 实测均值」时：

```
分母 = 1 − 0.2727 − 0.0467 − 0.0158 − 0.0606 − 0.1781 = 0.4261 = 实测采购成本率
⟹ 最低售价 = C ÷ 0.4261 = 当前平均售价
```

模型天然自校准：调高目标毛利率 → 底线线性抬高；调低 → 放宽折扣空间。

### 4.3 计算示例

**`166851422928`**（采购成本 10，参考售价 30，fast 档，SPU 率 4.67% / 1.58%）：
```
成本线 = 10 ÷ (1 − 0.2727 − 0.0467 − 0.0158 − 0.0606 − 0.20) = 28.12
纪律线 = 30 × (1 − 0.20) = 24.00
最低售价 = 28.12   来源：cost_floor
```

**`SKU-0001`**（采购成本 100，参考售价 500，normal 档）：
```
成本线 = 100 ÷ (1 − 0.2727 − 0.0467 − 0.0158 − 0.0606 − 0.18) = 236.26
纪律线 = 500 × (1 − 0.30) = 350.00
最低售价 = 350.00   来源：discount_guard
```

### 4.4 降级链与来源标记

`min_selling_price_source` 取值：

| 值 | 含义 | 触发条件 |
|---|---|---|
| `manual_override` | 人工覆盖 | `min_selling_price_override` 非空 |
| `discount_guard` | 纪律线（参考售价 × 折扣） | 参考售价非空且纪律线 > 成本线 |
| `cost_floor` | 成本线 | 成本线可算且 ≥ 纪律线 |
| `unavailable` | 无法计算 | 采购成本缺失，或缺 SPU 绑定/率，或平台成本率未配置 |

**降级链（逐级尝试）**：

1. 人工覆盖值非空 → 直接返回
2. 成本线可算？需要：采购成本、SPU 有效绑定且两率齐全、平台 `other_cost_rate` 已配置、目标毛利率与达人佣金率可解析
3. 纪律线可算？需要：参考售价非空
4. 取二者较大值；仅一条可算时取该条
5. 都不可算 → `unavailable`，同时返回 `min_selling_price_missing_reasons` 清单（对齐既有 `reference_cost_missing_reasons` 风格）

**边界**：
- 分母 `1 − 各项率 ≤ 0` → 不计算成本线，降级到纪律线，并在 `missing_reasons` 记 `non_positive_cost_denominator`
- 全部率之和 ≥ 1 → 视为配置错误，返回 `unavailable`

### 4.5 金额精度

复用 `backend/services/product_profit_service.py` 的 `_money`（`Decimal` + `ROUND_HALF_UP` + `MONEY_QUANTUM = 0.01`）。禁止用 float 做成本线计算。

---

## 5. API 变更

### 5.1 规则表（档位级）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/sku-pricing-policies` | 登录 | 返回全部规则行（含历史），按 `turnover_class, effective_from` 排序 |
| GET | `/api/sku-pricing-policies/current` | 登录 | 返回当前生效的 4 行（`effective_to IS NULL`） |
| POST | `/api/sku-pricing-policies` | `_require_platform_fee_editor` | 新建规则行；若同档位已有生效行则拒绝（409），要求先关闭 |
| PUT | `/api/sku-pricing-policies/{turnover_class}` | `_require_platform_fee_editor` | 版本化更新：关闭当前行（写 `effective_to`）并新建一行 |

`PUT` 采用「关旧行 + 建新行」而非原地 UPDATE，保证历史可追溯。新行的 `effective_from` 必须 ≥ 旧行的 `effective_from`。

### 5.2 平台成本率

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/platforms/{platform_code}/cost-rates` | 登录 | 返回 `default_fee_rate` / `default_creator_commission_rate` / `other_cost_rate` / 生效日期 / 来源 / 版本 |
| PATCH | `/api/platforms/{platform_code}/cost-rates` | `_require_platform_fee_editor` | 更新三项成本率 + 生效日期 / 来源 / 版本，写审计 |

`PATCH` 只允许 `platform_role = 'sales'` 的平台（沿用既有 `update_platform_fee_rate` 的 409 规则）。

### 5.3 SKU 读接口

`GET /api/skus` 响应 `ProductCenterItem` 新增 5 个字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `standard_discount_rate` | `float \| None` | 规则表该档位的常规最大折扣率 |
| `clearance_discount_rate` | `float \| None` | 规则表该档位的滞销最大折扣率 |
| `min_selling_price` | `float \| None` | 生效的最低售价 |
| `min_selling_price_source` | `str` | `manual_override` / `discount_guard` / `cost_floor` / `unavailable` |
| `min_selling_price_is_override` | `bool` | 是否人工覆盖 |
| `min_selling_price_missing_reasons` | `list[str]` | 无法计算时的原因清单 |
| `pricing_tier` | `str` | 实际命中的档位（含 `unclassified`） |
| `pricing_tier_is_fallback` | `bool` | 是否走了兜底档 |

`GET /api/sku-operating-dimensions` 的 `platforms` 项新增 `default_creator_commission_rate`、`other_cost_rate`（供前端展示成本率合计）。

### 5.4 SKU 写接口

- `PATCH /api/skus/{sku_id}`：`SkuUpdateRequest` 新增 `creator_commission_rate`（`Optional[float]`，0≤x≤1）与 `min_selling_price_override`（`Optional[float]`，>0）。**必须用 `exclude_unset=True` 语义**，`null` 表示清除覆盖值（既有 `update_sku` 已是 `model_dump(exclude_unset=True)`，传 `null` 即可清空）。
- `POST /api/skus/bulk`：`SkuBulkItem` 同步新增两个字段，语义同上。
- `POST /api/skus`：`SkuCreateRequest` 同步新增两个字段。

### 5.5 利润测算护栏

`GET /api/platform-sku-profit/candidates` 每行新增：

| 字段 | 说明 |
|---|---|
| `min_selling_price` | 该 SKU 的全局最低售价（SKU 资料页同一个数） |
| `min_selling_price_source` | 来源标记 |
| `min_selling_price_below` | `expected_selling_price < min_selling_price` 时为 `True` |

`POST /api/platform-sku-profit/estimates` 增加拦截：

```json
HTTP 422
{
  "detail": {
    "code": "below_min_selling_price",
    "min_selling_price": 28.12,
    "expected_selling_price": 25.00,
    "message": "预计售价低于最低售价 28.12"
  }
}
```

判定条件：`expected_selling_price` 非空 且 `min_selling_price` 非空 且 `expected_selling_price < min_selling_price`。

**`POST /api/platform-sku-profit/drafts` 不拦截**——草稿是探索性保存，允许记录"我试过这个价"。

---

## 6. 前端变更

### 6.1 「定价设置」抽屉（升级现有 `platformFeeDrawer`）

现有「平台费率管理」抽屉（`ProductCenter.vue:561-576`，入口 `ProductCenter.vue:323`）升级为**「定价设置」抽屉**，宽度 720px，含两个子 Tab。

**子 Tab 1「平台成本率」** — 沿用现有字段骨架（平台 / 生效日期 / 来源 / 版本），成本率字段扩为 3 项：

```
┌─ 定价设置 · TikTok ───────────────────────────────┐
│ [info] 平台成本率用于最低售价底线计算，仅管理员、  │
│        主管和财务可维护。                           │
├────────────────────────────────────────────────────┤
│ 平台   TikTok                                     │
│  平台佣金率          [ 7.37 ] %                    │
│  默认达人佣金率      [ 6.06 ] %                    │
│  平台其他成本率      [ 27.27 ] %                   │
│  ──────────────────────────────────────            │
│  成本率合计          40.70 %   (自动算，只读)       │
│                                                    │
│ 生效日期   [2026-09-01]                            │
│ 来源       [b_class 实测 2026-01~07]                │
│ 版本       [v1]                                    │
└────────────────────────────────────────────────────┘
```

「成本率合计」= 平台佣金率 + 默认达人佣金率 + 平台其他成本率，仅作展示参考；**实际底线计算还要叠加 SPU 退货/货损率与目标毛利率**（提示文案需说明，避免误解为最终底线）。

**子 Tab 2「档位折扣规则」** — 4 行可编辑表格：

```
┌────────────┬──────────┬──────────┬──────────┬──────────┐
│ 周转档位    │ 常规可优惠│ 滞销可优惠│ 目标毛利率│ 成本基准平台│
├────────────┼──────────┼──────────┼──────────┼──────────┤
│ 快销(30天)  │  10%     │   20%    │   20%    │ tiktok   │
│ 普通(60天)  │  10%     │   30%    │   18%    │ tiktok   │
│ 慢销(90天)  │  15%     │   40%    │   15%    │ tiktok   │
│ 未分类      │  10%     │   30%    │   18%    │ tiktok   │
└────────────┴──────────┴──────────┴──────────┴──────────┘
```

编辑任一格 → 保存时提交 `PUT /api/sku-pricing-policies/{turnover_class}`（版本化更新）。

### 6.2 入口

| 位置 | 按钮 | 默认打开 | 条件 |
|---|---|---|---|
| 平台 SKU 利润测算 tab（现有按钮改名） | 定价设置 | 平台成本率 | `canManagePlatformFee`（admin/manager/finance） |
| SKU 资料 tab（新增按钮） | 定价设置 | 档位折扣规则 | `canManagePlatformFee` |

不新增独立页面或独立抽屉，保证「平台成本参数只有一个录入入口」。

### 6.3 SKU 资料 tab 新增 3 列

位置：紧跟「参考售价」列之后（团队改价时最常看的相邻列）。

| 列 | 渲染 | 可编辑 |
|---|---|---|
| 常规可优惠 | 只读 tag + 档位标签（`快销(30天)` / `未分类`） | 否 |
| 滞销可优惠 | 只读 tag | 否 |
| 最低售价 | `el-input-number`（`:min="0"` `:precision="2"` `:controls="false"`）+ 来源标记 tooltip + 「重置为自动值」按钮 | 是 |

- 来源标记 tooltip 文案：
  - `manual_override` → 「人工设定」
  - `discount_guard` → 「参考售价 × (1 − 滞销可优惠率)」
  - `cost_floor` → 「成本 + 目标毛利反解」
  - `unavailable` → 展示缺失原因（`min_selling_price_missing_reasons`）
- 未命中档位时（`pricing_tier_is_fallback === true`）在档位标签上加「兜底」提示
- 编辑最低售价 → 写入 `min_selling_price_override`，走既有 `dirtyRows` + `/api/skus/bulk` 批量保存链路
- 「重置为自动值」→ 把 `min_selling_price_override` 置 `null`，恢复自动计算

### 6.4 利润测算 tab 护栏

- 「预计售价」列右侧新增「最低售价」只读列
- `expected_selling_price < min_selling_price` 时：
  - 预计售价输入框标红
  - 行内提示「低于最低售价 {min_selling_price}」
  - 「保存利润版本」按钮禁用 + tooltip 说明原因
- 后端 422 返回时，前端展示 `detail.min_selling_price` 与差额

---

## 7. 权限

| 操作 | 依赖 | 允许角色 |
|---|---|---|
| 读规则表 / 平台成本率 | `get_current_user` | 全部登录用户 |
| 读最低售价（三列） | `get_current_user` | 全部登录用户 |
| 写规则表 | `_require_platform_fee_editor` | admin / manager / finance |
| 写平台成本率 | `_require_platform_fee_editor` | admin / manager / finance |
| 写 `min_selling_price_override` | `_require_editor` | admin / manager / finance / operator |
| 写 `creator_commission_rate` | `_require_editor` | admin / manager / finance / operator |

人工覆盖最低售价放开到 `operator`（一线运营在改价场景下需要调整底线）；规则与平台成本率属于财务口径，收紧到 admin/manager/finance。

---

## 8. 测试

### 8.1 后端

新建 `backend/tests/test_product_pricing_guardrails.py`：

| 用例 | 断言 |
|---|---|
| 成本线公式 | 给定固定输入，返回精确 Decimal 值（到分） |
| 自洽性 | 目标毛利率 = 实测净利率、各项率 = 实测均值时，底线 = C ÷ 采购成本率 |
| 分母 ≤ 0 | 不抛异常，降级到纪律线，`missing_reasons` 含 `non_positive_cost_denominator` |
| 纪律线 | 参考售价 × (1 − clearance_discount_rate) |
| 取大 | 成本线与纪律线取大，人工覆盖优先级最高 |
| 降级链 | 采购成本缺失 / SPU 未绑定 / 平台成本率未配置 → `unavailable` + 原因清单 |
| 兜底档 | `turnover_class` 为 NULL 的 SKU 命中 `unclassified` 规则，`pricing_tier_is_fallback = True` |
| 达人佣金回退 | SKU 未设 `creator_commission_rate` 时取平台默认；设了则用 SKU 值 |
| 规则表约束 | `clearance < standard` / `target_margin ≥ 1` / 非法 turnover_class 均被拒 |
| 版本化更新 | `PUT` 后旧行 `effective_to` 被写，新行生效，历史行未被删 |
| 护栏拦截 | 预计售价 < 最低售价 → 422 `below_min_selling_price`；≥ 则通过 |
| 草稿不拦截 | `POST /drafts` 在低于最低售价时仍返回 201 |
| 写接口审计 | 规则表 / 平台成本率 / SKU 覆盖值的写操作均产生 `FactAuditLog` |

### 8.2 契约测试

在 `backend/tests/test_product_center_schema_contract.py` 追加：
- `ProductCenterItem` 含 8 个新字段
- `SkuUpdateRequest` / `SkuBulkItem` / `SkuCreateRequest` 含 2 个新字段
- `DimErpSku` 含 `creator_commission_rate` / `min_selling_price_override`
- `DimPlatform` 含 `default_creator_commission_rate` / `other_cost_rate`
- `SkuPricingPolicy` 表存在且约束齐全

### 8.3 迁移契约

在 `backend/tests/test_turnover_storage_contract.py` 同级新增迁移断言：
- 迁移文件包含 `sku_pricing_policies` 建表语句
- 迁移文件包含 `dim_platforms` 两列新增
- 迁移文件包含 `dim_erp_sku` 两列新增
- 迁移文件包含 4 条规则初始数据与 2 条平台成本率初始数据

### 8.4 前端

在 `frontend/tests/productCenterUi.test.mjs` 追加：
- SKU 资料 tab 渲染 3 个新列
- 最低售价列的来源标记 tooltip 文案
- 利润测算 tab 低于最低售价时输入框标红、保存按钮禁用
- 定价设置抽屉两个子 Tab 可切换，字段绑定正确

---

## 9. 迁移

文件：`current_migrations/versions/20261020_sku_pricing_guardrails.py`

沿用 `20260916_sku_turnover_storage_rules_cny.py` 的幂等范式（`_has_table` / `_has_column` / `_has_constraint` / `_has_index` 守卫）。

```python
revision = "current_schema_20261020_sku_pricing_guardrails"
down_revision = "current_schema_20260921_warehouse_storage_label_fee"
```

内容：
1. 建 `finance.sku_pricing_policies` 表（含 5 个 CHECK、1 个 UNIQUE、1 个 INDEX）
2. `core.dim_platforms` 加 `default_creator_commission_rate` / `other_cost_rate` 两列 + 3 个 CHECK
3. `core.dim_erp_sku` 加 `creator_commission_rate` / `min_selling_price_override` 两列 + 2 个 CHECK
4. 插入 4 条 `finance.sku_pricing_policies` 初始规则（`effective_from` = 执行日，`policy_source = 'industry_benchmark_2026'`）
5. 更新 `core.dim_platforms` 初始成本率（当前两行均为 `default_fee_rate=0.02, fee_rate_source='manual', fee_rate_version='v1'`）：
   - tiktok：`default_fee_rate = 0.0737`、`default_creator_commission_rate = 0.0606`、`other_cost_rate = 0.2727`、`fee_rate_source = 'b_class_measured_2026_01_07'`、`fee_rate_version = 'v2'`
   - shopee：`default_fee_rate = 0.1487`、`default_creator_commission_rate = 0.0111`、`other_cost_rate = 0.4165`、同上

   `fee_rate_effective_from` **保留原值**（tiktok `2026-09-01`、shopee `2026-09-15`）——本次是纠正错误取值而非新增未来费率，回溯生效日期才能让历史区间的测算也用正确费率。

`dim_platforms.default_fee_rate` 的校准值**必须用 SQL UPDATE 显式写入**，不能依赖 ORM 默认值。

`amazon`（role=sales）与 `miaoshou`（role=source）、`验证码测试账号`（role=test）三行不配置成本率；`amazon` 的 SKU 底线因此只能走纪律线或 `unavailable`。

---

## 10. 已知限制

1. **成本线不含逐 SKU 精算的物流与仓储**。`weight_kg` 0/1121、`unit_volume_cbm` 3/1121 有值，改用平台级 `other_cost_rate`。尺寸数据补齐后可升级为逐 SKU 精算，届时 `other_cost_rate` 退化为兜底值。**这意味着当前底线对大件/重货 SKU 偏低。**
2. **成本线不含广告费的独立建模**。广告成本已包含在 `other_cost_rate` 内（TikTok 14.74%），但利润测算里的广告费率是「广告前利润的分配比例」口径，两者不可直接互换。
3. **达人佣金用平台均值，除非 SKU 单独设置**。实测波动 3.7%–33.8%，平台均值对高佣金商品偏低。
4. **参考售价 0.2% 填充率**，纪律线当前几乎不生效，绝大多数 SKU 走成本线。参考售价补齐后纪律线自动叠加，无需改代码。
5. **周转档位 0.3% 填充率**，1118 个 SKU 走 `unclassified` 兜底档。档位补齐后底线会自动重算。
6. **`other_cost_rate` 是黑盒数字**。它是恒等式反推值，财务无法从 UI 看出构成；子 Tab 1 应展示「成本率合计」并注明推导方式。
7. **校准 `default_fee_rate` 会改变利润测算结果**（TikTok 利润下降约 5.4 个百分点，Shopee 约 12.9 个百分点）。历史 `finance.sku_profit_estimates` 版本不被改写，但新旧测算不可直接比较，需在 UI 上标注 `fee_rate_version`。
8. **`amazon` 未配置成本率**，不参与底线计算，其 SKU 的最低售价只会走纪律线或 `unavailable`。
