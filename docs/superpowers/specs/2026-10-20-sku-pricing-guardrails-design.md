# 商品中心 SKU 定价底线（最低售价）与定价纪律规则

**状态**: 设计稿待评审
**日期**: 2026-10-20
**范围**: 商品中心（`backend/domains/business/routers/product_center.py`、`backend/schemas/product_center.py`、`backend/services/product_pricing_service.py`（新建）、`modules/core/db/schema_parts/dimensions.py`、`modules/core/db/schema_parts/business.py`、`modules/core/db/schema.py`、`current_migrations/versions/`、`frontend/src/domains/business/views/ProductCenter.vue`、`frontend/src/api/productCenter.js`）。

**非范围**:
- 不修改利润测算公式 `build_platform_profit_preview` 的成本项构成（仍只含采购/物流/仓储/贴单/平台费/退货/货损/广告）
- 不修改飞书投影字段（`_enqueue_sku_projection` / `_enqueue_platform_sku_profit_projection`）
- 不做 SKU 尺寸数据（重量/体积/箱规）补齐
- 不做批量改价、不做改价审批流、不做定价回写平台
- 不修改 `finance.sku_profit_estimates` 的历史版本数据
- 不修改 `b_class` 原始层任何数据
- **不修复库存库龄数据管道**（采集→同步→落盘→semantic→mart→api 整条链路当前为空，是独立任务）。本 spec **只读取** `mart.inventory_age_current`，读不到时回落「日常」档
- **不做达人佣金自动回填**，**不建**「平台商品ID → ERP SKU」映射表——达人佣金率在商品中心手工填写
- **不修改 `dim_erp_sku.turnover_class` 的现有用途**（继续只用于参考仓储天数）
- 不新增 `semantic` / `mart` / `api` schema 的对象

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
| `dim_erp_sku.turnover_class` | 3 | 0.3% | **与定价无关**，仅用于参考仓储天数 |
| `dim_erp_sku.unit_volume_cbm` | 3 | 0.3% | 物流仓储无法逐 SKU 精算 |
| `dim_erp_sku.weight_kg` | 0 | 0% | 同上 |
| `dim_erp_sku.units_per_carton` | 0 | 0% | 同上 |
| `bridge_spu_sku` 有效绑定 | 1118（总 1121，其中 3 条 `effective_to` 非空或非 active） | 100% / 99.7% | SPU 率可继承；3 个 SKU 走 `missing_spu_binding` |

**库存库龄数据现状**（档位匹配的数据源）：

| 表 | 行数 | 说明 |
|---|---|---|
| `mart.inventory_age_current` | **0** | 库龄当前表，**定价档位的数据源** |
| `semantic.fact_inventory_snapshot` | **0** | 语义层，UNION 自 3 张 `b_class.fact_*_inventory_snapshot`（也全 0 行） |
| `mart.inventory_snapshot_history` / `_latest` / `_change` / `_company_daily` | **0** | 快照四表 |
| `mart.inventory_age_history` | **0** | 库龄历史表 |
| `core.staging_inventory` | **80280** | 原始暂存层，2025-11-17~22 一次性导入（`scripts/migrate_miaoshou_to_inventory_domain.py` 的数据域改名迁移产物） |

库龄的**计算逻辑与分档函数都已存在**（`backend/services/data_pipeline/inventory_age_refresh_service.py`：`:142` `bucket_age_days()` 分 0-30/31-60/61-90/91-180/180+，`:37` `compute_age_transition()` 处理补货归零 / 卖空重现归零 / 持续累加），前端库龄页 `frontend/src/domains/business/views/inventory/InventoryAging.vue` 也已存在（分档下拉用同样的 5 个 bucket 值，并已有「只看高库龄 ≥61 天」筛选）。

**断点**：采集层 2026-09 重写为 V2 canonical（`modules/platforms/miaoshou/components/inventory_export.py` + `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["inventory"]`），但该次 spec 的非范围明确写了「不改同步层、不改 SQL 三层」——`stage_inventory` 只在 `backend/domains/data_platform/routers/field_mapping_ingest.py:869` 一条路径被调用，`backend/services/data_ingestion_service.py` import 了却从不调用，因此采集产物落不到 `b_class.fact_*_inventory_snapshot`。

**对本 spec 的影响**：库龄档位读不到数据 → 全部回落「日常」档（§4.4）。库龄管道修复是**独立任务**，不在本 spec 范围。

**订单侧实际成本结构**（`b_class.fact_tiktok_orders_monthly` 2026-01~07 共 4080 行、`b_class.fact_shopee_orders_monthly` 22347 行；口径为「合计金额 / 合计收入」）：

**收入基数口径（必须写明，否则无法复算）**：

| 平台 | 收入基数列 | 合计 | 说明 |
|---|---|---|---|
| TikTok | `总收入` | 261,932 | 订单表自带的总收入列 |
| Shopee | `买家支付` | 1,360,218 | shopee 表**没有** `总收入` 列，用 `买家支付` 作基数（`实付金额` 为空；`订单原始金额` 1,475,909 是含退款前的原价，不能当分母） |

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
4. **上表的分项列不可直接加总**。TikTok 按成本口径相加 98.75%（仓库操作费按回冲则 86.93%），与其 17.81% 净利率隐含的 82.19% 成本率相差 4.74~16.56pp；Shopee 全部非采购成本项相加 48.15% vs 反推 49.01%，差 0.86pp。两处差额都说明分项不可直接写进计算，平台成本率一律用恒等式反推（§2.3）。

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
| 档位维度 | **库龄阶梯**：按 SKU 当前库龄落在哪一档取对应规则。`turnover_class`（快销/普通/慢销）**不参与定价**，它只用于参考仓储天数 |
| 底线口径 | **公司统一口径**：所有 SKU 的底线都用「成本基准平台」这一个平台的费率计算（`platform_basis`，统一为 `tiktok`）。底线**不是**按该 SKU 实际售卖平台逐个算的 |
| 成本线 | 采购成本 ÷ (1 − 平台其他成本率 − SPU退货损失率 − SPU货损率 − 达人佣金率 − 目标利润率) |
| 纪律线 | 参考售价 × (1 − **当前库龄档位的 `discount_rate`**) |
| 折扣率归属 | 公司级规则表 `finance.sku_pricing_policies`，按库龄档位 |
| 达人佣金率 | **SKU 级字段**（`core.dim_erp_sku.creator_commission_rate`），在商品中心填写与计算使用。**不做自动回填、不建平台商品映射表**。SKU 未设置时取平台的 `default_creator_commission_rate` 兜底 |
| 库龄缺失 | 回落到第 1 档（日常，目标利润率最高 → 底线最保守），并标记 `pricing_tier_source='fallback_no_age_data'` |
| 人工覆盖 | `core.dim_erp_sku.min_selling_price_override` 存人工值；自动值**实时计算，不落库** |
| 平台佣金校准 | 本次一并校准 `dim_platforms.default_fee_rate` 为实测值。**校准的是「平台佣金率」这一个字段，它只服务利润测算**；底线计算用的是 `other_cost_rate` + `default_creator_commission_rate`，平台佣金已包含在 `other_cost_rate` 内，不重复扣减 |
| 护栏 | 利润测算 tab 显示最低售价 + **单层拦截**（低于最低售价 = 标红 + 禁用保存 + 后端 422）。纪律线已是最低售价的组成部分，不需要额外的黄色软提示 |
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

### 2.2 规则表初始值（库龄阶梯，4 档）

`finance.sku_pricing_policies` 初始 4 行（`effective_from` = 迁移执行日）：

| 库龄起点(天) | 档位名 | 折扣率 | 目标利润率 | 依据 |
|---|---|---|---|---|
| 0 | 日常 | 10% | 25% | 新品要求高毛利；折扣率取拉新促销 10–25% 的下沿 |
| 60 | 滞销30天 | 15% | 22% | 滞销阈值 60 天（≈对齐现有库龄页「只看高库龄 ≥61 天」）；折扣率取拉新促销区间上沿附近，清仓 30–50% 的起步 |
| 90 | 滞销60天 | 20% | 18% | 目标利润率贴近实测净利率 17.81%；折扣率对应行业清仓 30–50% 区间下沿 |
| 120 | 滞销60天以上 | 30% | 10% | 最深档，吸收所有 ≥120 天；折扣率对应行业清仓 30–50% 区间中位；目标利润率 10% 低于行业 15% 清仓底线是刻意为之（120 天未动的货再保 15% 毛利不现实） |

**每档只有一个折扣率**——折扣力度**完全由库龄档位触发**，没有「同档位两个额度」的概念。

**SKU 资料页的两列怎么从这 4 档取值**：

| 列 | 取值 | 含义 |
|---|---|---|
| **常规可优惠** | **当前库龄命中的档位的折扣率** | 「这个品**现在**最多能打几折」——随库龄变化 |
| **滞销可优惠** | **最深档（120 天档）的折扣率 = 30%** | 「**清货极限**」——公司统一红线，所有 SKU 一样 |

两列**不重复**：一列随库龄变化，一列是不变的红线。规则表里最深的折扣率同时就是「滞销可优惠」列的取值来源，不需要额外的参数。

> **边界情形**：库龄 ≥120 天的 SKU 两列同为 30%（当前档就是最深档）。这不是 bug——此时「现在能给多少」和「清货极限」本来就重合。UI 上这两列会显示相同值，属预期。

**库龄阶梯的语义**：
- 档位由**当前库龄**（`mart.inventory_age_current.age_days`）落在哪个区间决定，与 SKU 的快销/普通/慢销属性**无关**
- 库龄越久，折扣上限与目标利润率同步放宽——这就是「越滞销越该让利清货」
- 底线也随之下沉（§4.3 有四档的对照表）

**「滞销阈值」不是一个独立参数**，它内含在档位边界里（第 1 档 0–59 天为未滞销，第 2 档起为滞销）。要改阈值就是改第 2 档的 `min_age_days`。

**最深的 120 天档吸收所有 ≥120 天的库存，不再单设「150 天以上」档**。该档取合并前最深档的率（折扣 30% / 目标利润率 10%），理由：既然 120 天以上一律归入最深档，就该给最深的权限——否则「压了 200 天的货反而只能给 25% 折、清不掉」，合并反而会**丢失清货能力**。合并后规则不丢任何已有能力。

**术语约定**：本 spec 中的「目标利润率」= **净利口径**（利润 ÷ 净收入），与仓库既有 `SkuProfitEstimate.estimated_margin_rate` / `build_platform_profit_preview` 的 `margin_rate` 同义（`product_profit_service.py:122` `estimated_margin_rate = profit / revenue`）。**不是**中文严格意义上的「毛利率」（毛利 ÷ 收入）。实现与 UI 文案统一用「利润率」，不混用「毛利率」。

### 2.3 平台成本率初始值

`core.dim_platforms`：

| platform_code | `default_fee_rate`（平台佣金率） | `default_creator_commission_rate` | `other_cost_rate` | 参与底线计算？ |
|---|---|---|---|---|
| tiktok | 0.0737 | 0.0606 | 0.2727 | **是**（当前 `platform_basis`） |
| shopee | 0.1487 | 0.0111 | 0.4165 | 否（仅供利润测算与将来切换基准平台） |
| amazon | NULL | NULL | NULL | 否（`platform_role='sales'` 但未配置费率） |

**口径说明**：
- `default_creator_commission_rate` = 「达人佣金 + 联盟商店广告佣金」合计。tiktok 0.0606 = 达人佣金 5.29% + 联盟广告佣金 0.77%；shopee 0.0111 = 联盟佣金 1.11%（shopee 无达人佣金列）
- `other_cost_rate` 定义（平台级，除采购成本、达人佣金、SPU 退货/货损之外的全部成本占收入比，**平台佣金率已包含在内**）：

```
other_cost_rate = 1 − 实测采购成本率 − 实测净利率 − 平均 SPU 退货损失率 − 平均 SPU 货损率 − 默认达人佣金率

tiktok: 1 − 0.4261 − 0.1781 − 0.0467 − 0.0158 − 0.0606 = 0.2727
shopee:  1 − 0.3815 − 0.1284 − 0.0467 − 0.0158 − 0.0111 = 0.4165
```

用恒等式反推而非逐项加总。**分项列不可直接加总**——两边都有无法归因的残差，且仓库操作费的符号约定不明（TikTok 侧 `仓库操作费` 在源数据里是回冲，按成本加总得 98.75%、按回冲算得 86.93%，而净利率隐含的总成本率是 82.19%，差 4.74~16.56pp；Shopee 侧全部非采购成本项加总 48.15% vs 反推 49.01%，差 0.86pp）。分项仅用于说明成本结构，不可写进计算。

**⚠️ `default_fee_rate`（平台佣金率）不单独进入成本线分母**——它**已经包含在 `other_cost_rate` 桶内**（反推式从净利率倒推，净利率早已扣掉平台佣金）。若再减一次就是重复计算，会让底线偏高 26%（例 1：分母 0.3542 → 0.2805，底线 28.23 → 35.65）。

**默认底线基数（平台侧，SKU 未单独设置达人佣金率时）= 平台其他成本率 + 默认达人佣金率**：
```
默认底线基数 = 0.2727(其他成本) + 0.0606(达人默认) = 0.3333   (tiktok，SKU 未单独设置达人佣金率时)
```
> 「底线基数」这个合计值**只在 SKU 未单独设置达人佣金率时成立**。SKU 设了别的值时，底线基数 = 平台其他成本率 + **SKU 达人佣金率**（见 §4.1）。

**平台侧其他成本率**（已含平台佣金、**不含**达人佣金与 SPU 两率）：
```
shopee: 0.4165
```
完整分母还要再减 SPU 退货/货损率与目标利润率。

**各平台费率字段的用途**：

| 字段 | 利润测算 | 底线计算 |
|---|---|---|
| `default_fee_rate`（平台佣金率） | ✅ 用（`platform_fee = 净收入 × 该值`） | ❌ **不单独使用**（已含在 `other_cost_rate` 内） |
| `default_creator_commission_rate` | ❌ 不用（利润测算公式无达人佣金项） | ✅ 用（作为底线基数的一部分） |
| `other_cost_rate` | ❌ 不用 | ✅ 用（作为底线基数的一部分） |

**「参与底线计算」的含义**：底线计算只读取**当前 `platform_basis` 指向的那个平台**的费率（当前为 tiktok）。其余平台的费率：
- 仍被**利润测算**使用（利润测算按用户当前选择的平台取 `default_fee_rate`）
- **不参与**底线计算——除非把规则表的 `platform_basis` 切到该平台
- 因此 `amazon` 未配置费率**不影响** amazon SKU 的最低售价：amazon SKU 的底线照常按 tiktok 口径计算

`amazon` 在利润测算中 `default_fee_rate` 仍为 NULL → 平台费用算不出（与现状一致，非本次引入）。

---

## 3. 数据模型

### 3.1 `core.dim_platforms` — 新增 2 列 + 校准 1 列

```python
default_creator_commission_rate = Column(Numeric(12, 8), nullable=True)  # 平台默认达人/联盟佣金率（SKU 未单独设置时兜底）
other_cost_rate                 = Column(Numeric(12, 8), nullable=True)  # 平台其他成本率
```

`default_fee_rate` 语义**收窄为「平台佣金率」**并校准为实测值。`fee_rate_effective_from` / `fee_rate_source` / `fee_rate_version` 复用为这三项成本率共同的生效日期 / 来源 / 版本标记，不新增列。

`default_creator_commission_rate` 的语义是**「该平台的默认达人佣金率」**——它是 SKU 未单独设置佣金率时的**兜底值**，不是「平台统一执行的佣金率」（TikTok 后台是按商品设佣金区间的，平台级不存在统一值）。UI 文案必须写明这一点，避免运营误以为改了这个值就改了所有商品的佣金。

约束：
```sql
-- 命名沿用仓库约定：ck_<table>_<rule>（对照 dimensions.py:220-222 的 ck_dim_erp_sku_*）
CHECK (default_fee_rate IS NULL OR (default_fee_rate >= 0 AND default_fee_rate <= 1))
CHECK (default_creator_commission_rate IS NULL OR (default_creator_commission_rate >= 0 AND default_creator_commission_rate <= 1))
CHECK (other_cost_rate IS NULL OR (other_cost_rate >= 0 AND other_cost_rate < 1))
```

约束名分别为 `ck_dim_platforms_fee_rate_range` / `ck_dim_platforms_creator_commission_rate_range` / `ck_dim_platforms_other_cost_rate_range`。

### 3.2 `core.dim_erp_sku` — 新增 2 列

```python
creator_commission_rate    = Column(Numeric(12, 8), nullable=True)  # 该 SKU 达人佣金率，NULL = 用平台默认
min_selling_price_override = Column(Numeric(18, 2), nullable=True)  # 人工覆盖的最低售价
```

**`creator_commission_rate` 是达人佣金率的唯一录入入口**，在商品中心（SKU 资料页）填写与使用：
- **不做**从订单数据自动回填
- **不建**「平台商品ID → ERP SKU」映射表
- SKU 未设置时取 `dim_platforms.default_creator_commission_rate` 兜底（tiktok 6.06% / shopee 1.11%，实测大盘）

理由：TikTok 后台确实是**按商品设佣金区间**，平台级不存在统一值；订单数据里的达人佣金按平台商品ID聚合，而订单表 `商品SKU` / `平台SKU` / `SKU_ID` 三列全空、`core.bridge_erp_sku_keys` 也只映射「妙手目录→ERP SKU」，无法自动回填到 ERP SKU。人工在商品中心填写是当前唯一可靠路径。

约束：
```sql
CHECK (creator_commission_rate IS NULL OR (creator_commission_rate >= 0 AND creator_commission_rate <= 1))
CHECK (min_selling_price_override IS NULL OR min_selling_price_override > 0)
```

### 3.3 新表 `finance.sku_pricing_policies`

```python
class SkuPricingPolicy(Base):
    """公司级定价纪律规则，按 SKU 当前库龄档位配置。"""
    __tablename__ = "sku_pricing_policies"

    policy_id                 = Column(Integer, primary_key=True, autoincrement=True)
    min_age_days              = Column(Integer, nullable=False)                # 档位起点（库龄天数，含）
    tier_label                = Column(String(32), nullable=False)            # 档位显示名，如「滞销30天」
    discount_rate             = Column(Numeric(12, 8), nullable=False)      # 该档位的折扣率上限（库龄唯一决定）
    target_margin_rate        = Column(Numeric(12, 8), nullable=False)      # 目标利润率（净利口径：利润 ÷ 净收入）
    platform_basis            = Column(String(32), nullable=False)          # 成本基准平台
    effective_from            = Column(Date, nullable=False)
    effective_to              = Column(Date, nullable=True)
    status                    = Column(String(16), nullable=False, default="active")
    source                    = Column(String(128), nullable=True)
    version                   = Column(String(64), nullable=True)
    notes                     = Column(Text, nullable=True)
    created_at                = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at                = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("min_age_days", "effective_from", name="uq_sku_pricing_policy_tier_start"),
        CheckConstraint("min_age_days >= 0", name="ck_sku_pricing_policy_age_start"),
        CheckConstraint("discount_rate >= 0 AND discount_rate <= 1", name="ck_sku_pricing_policy_discount_rate"),
        CheckConstraint("target_margin_rate >= 0 AND target_margin_rate < 1", name="ck_sku_pricing_policy_target_margin"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_sku_pricing_policy_window"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_sku_pricing_policy_status"),
        Index("uq_sku_pricing_policies_current", "min_age_days", unique=True,
              postgresql_where=text("status = 'active' AND effective_to IS NULL")),
        Index("ix_sku_pricing_policy_scope", "min_age_days", "effective_from"),
        {"schema": "finance"},
    )
```

> ⚠️ **`Index` 不得传 `schema=` 关键字**。SQLAlchemy 2.0.41 的 `Index.__init__` 只接受 `name / *expressions / unique / quote / info / **dialect_kw`，传 `schema="finance"` 会抛
> `TypeError: Additional arguments should be named <dialectname>_<argument>, got 'schema'`，
> **在 `modules.core.db` import 期就崩**，导致所有依赖 `modules.core.db` 的后端模块与测试全挂。
> 索引的 schema 由 `__table_args__` 末尾的 `{"schema": "finance"}` 自动继承，编译结果为
> `CREATE INDEX ix_sku_pricing_policy_scope ON finance.sku_pricing_policies (min_age_days, effective_from)`。
> 仓库既有的 `WarehouseStorageRule` / `LogisticsProviderRule` 索引也都不带 `schema=`。

**字段命名对齐仓库既有「版本化规则表」约定**：`WarehouseStorageRule`（类定义 `business.py:805`，六件套字段在 `:816-821`）与 `LogisticsProviderRule`（类定义 `business.py:762`，六件套字段在 `:780-785`）均使用 `effective_from` / `effective_to` / `status` / `source` / `version` / `notes` 六件套，并用**部分唯一索引**（`postgresql_where`）保证「每作用域只有一条当前行」。`SkuPricingPolicy` 沿用同一约定：
- `source` / `version` / `notes` / `status` 与既有规则表字段名一致
- `uq_sku_pricing_policies_current` 部分唯一索引在**数据库层**保证每个库龄档位至多一条当前行（`status='active' AND effective_to IS NULL`），不依赖应用层逻辑
- 额外保留 `UNIQUE(min_age_days, effective_from)` 防止同一档位同一天出现两条

**档位键用 `min_age_days`（库龄起点）而不是固定枚举**：
- 边界（滞销阈值）因此是**可配数据**而非硬编码常量——用户明确要求「默认，库龄在多少天开始有对应的折扣」
- `tier_label` 只是显示名，不参与匹配
- 匹配规则见 §5.1「档位匹配规则」

**与 `turnover_class` 的关系**：规则表**不引用** `dim_erp_sku.turnover_class`。`turnover_class` 继续只用于参考仓储天数（快销 30 / 普通 60 / 慢销 90，见 `product_profit_service.py:12` 的 `TURNOVER_DAYS`），与定价完全无关。

规则变更需要真实版本历史（改一次影响 1118 个 SKU 的底价），因此用 `effective_from` / `effective_to` 软关闭历史行。

**ORM 注册步骤**（`AGENTS.md` 要求 ORM SSOT 为 `modules/core/db/schema.py`）：

1. `SkuPricingPolicy` 类加到 `modules/core/db/schema_parts/business.py`（与 `WarehouseStorageRule` 同文件）
2. `modules/core/db/schema.py` 的 `from .schema_parts.business import (...)` 中加入 `SkuPricingPolicy`（`schema.py:127`）
3. `modules/core/db/schema.py` 的 `__all__` 列表中加入 `"SkuPricingPolicy"`（`schema.py:351` 附近）
4. `modules/core/db/__init__.py` 无需改动——它是 `from .schema import *` 的薄包装（`__init__.py:14`），会自动带上 `__all__` 中的新名字

`backend/domains/business/routers/product_center.py` 从 `modules.core.db` 导入（`product_center.py:80`），注册后即可直接 `from modules.core.db import SkuPricingPolicy`。

---

## 4. 计算模型

### 4.1 公式

```
成本线 = 采购成本 C ÷ (1 − 平台其他成本率 − 达人佣金率 − SPU退货损失率 − SPU货损率 − 目标利润率)

纪律线 = 参考售价 × (1 − 当前档折扣率)

最低售价 = max(成本线, 纪律线, min_selling_price_override)
```

**其中「达人佣金率」= `dim_erp_sku.creator_commission_rate`，为 NULL 时取 `platform_basis` 平台的 `default_creator_commission_rate`。**

> ⚠️ 这里必须用**SKU 实际值**，不能写死平台默认值。同一 SKU 若把达人佣金率从默认 6.06% 改成 15%：
> - 按 SKU 实际值：分母 = 1 − 0.2727 − 0.15 − 0.0467 − 0.0158 − 0.25 = 0.2648 → 底线 10 ÷ 0.2648 = **37.76**
> - 若误用平台默认值 6.06%：分母 = 0.3542 → 底线 **28.23**
>
> 两者差 34%。因此公式框里的达人佣金项是**变量**，不是常量。

**「底线基数」这个词只在 SKU 未单独设置达人佣金率时成立**：
```
默认底线基数 = 平台其他成本率 + 默认达人佣金率 = 0.2727 + 0.0606 = 0.3333   (tiktok)
```
SKU 单独设了达人佣金率时，底线基数 = 平台其他成本率 + **SKU 达人佣金率**。UI 与文档里凡是写「底线基数」的地方，必须带上这个限定语。

**为什么用 SKU 实际值替换默认达人佣金率不会重复扣减**：`other_cost_rate` 的反推式（§2.3）已经从净利率里**减掉了默认达人佣金率**，所以 `平台其他成本率` 这一项**不含**达人佣金；分母里单独减一次 SKU 实际值，扣的正是达人佣金这一项，**没有重复**。

**⚠️ 分母里没有 `default_fee_rate`（平台佣金率）**。`other_cost_rate` 是从实测净利率反推的，而净利率早已扣掉平台佣金，所以平台佣金**已在桶内**。再减一次会重复计算：分母 0.3542 → 0.2805，例 1 底线 28.23 → 35.65（偏高 26%）。`default_fee_rate` 只服务利润测算。

**两个数各自的职责**（不重复）：

| 名称 | 公式 | 职责 | 是否硬拦截 |
|---|---|---|---|
| 纪律线 | 参考售价 × (1 − 当前档折扣率) | **折扣权限上限**。低于它说明「超出了当前库龄档位允许的折扣」 | ✅ 参与最低售价取大（低于最低售价即拦截） |
| 成本线 | 采购成本反解 | **价格底线**。低于它说明「在亏本卖」 | ✅ 参与最低售价取大 |

**护栏只有一层**：纪律线已经是最低售价的组成部分，所以**不需要额外的黄色软提示**——「低于最低售价」这一个判定同时覆盖了「超出折扣权限」和「亏本卖」两种情况。

**档位从哪来**（三者的率都取自同一档位）：

```
# 1) 取 SKU 当前库龄
#    ⚠️ join 键是 product_sku → dim_erp_sku.sku_key，不是 mart 的 sku_id
#    （mart.inventory_age_current.sku_id 是 varchar 的平台侧 id，与 dim_erp_sku.sku_id(integer) 不是一回事）
候选行 = mart.inventory_age_current 中 product_sku = dim_erp_sku.sku_key 的所有行
age_days = 候选行中 age_days 的**最小值**（同一 platform_code 下多行同样取最小）
无候选行（库龄不可得）→ age_days = None

# 2) 在当前生效的规则行里匹配档位
生效规则 = 满足「当前行」条件 且 min_age_days <= age_days 的行中 min_age_days 最大的一行
age_days = None → 命中 min_age_days 最小的一行（兜底档，正常是 min_age_days = 0 的「日常」档）

# 3) 无生效规则
无生效规则 → 该 SKU 的 min_selling_price = unavailable，missing_reasons 含 'missing_pricing_policy'
```

**为什么取 `age_days` 最小值（而不是按平台挑一行 / 取最大值）**：

- **库龄是货品层面的事实**，不是平台层面的事实。同一批货在多个平台看到的库龄差异来自快照时序（补货锚点重置的先后），不是货品真的有两批
- 取最小值 = 认为「这批货是最新进的」→ 命中**最浅**的档位 → 目标利润率最高 → **底线最高** = 最保守，不会亏本
- 取最大值会命中最深档位、目标利润率最低、底线最低，是**最激进**的方向，与「底线是护栏」的定位相反
- 这也让档位匹配**完全不依赖 `platform_basis`**，避免了「先要档位才知道用哪个平台、先要平台才知道档位」的循环依赖。`platform_basis` 只用于**成本线取哪个平台的费率**（§4.1）

**join 路径的事实依据**（实测，2026-10-20）：

| 事实 | 值 |
|---|---|
| `mart.inventory_age_current.sku_id` 类型 | `character varying`（**平台侧**商品 id 字符串） |
| `core.dim_erp_sku.sku_id` 类型 | `integer`（ERP 主键） |
| `mart.inventory_age_current` 主键 | `(platform_code, sku_key)`（`sql/mart/inventory_age_current.sql:26`），其中 `sku_key = COALESCE(platform_sku, product_sku, sku_id, product_id)`（`sql/mart/inventory_snapshot_company_daily.sql:8-13`） |
| **可用 join 键** | `mart.inventory_age_current.product_sku` → `core.dim_erp_sku.sku_key`（妙手商品编码，两侧同形） |
| 该 join 实测匹配率 | **1080 / 1094（98.72%）**，精确匹配（去空格忽略大小写结果相同）。**实测在 `core.staging_inventory` 上**（`mart.inventory_age_current` 现为 0 行，无法在该表上直接测） |
| 一对多风险 | **0**（不存在一个 `product_sku` 对应多个 `dim_erp_sku` 的情况；`dim_erp_sku.sku_key` 亦无重复） |
| 未匹配的 14 个 | 均为 ERP 主数据里没有的新品族（`A-00001-ACU camouflage`、`HJJ-XH-CTD01`、`SG-JWG-A` 等），非格式差异 |
| `core.bridge_erp_sku_keys` | 1118 行，`source_key` 与 `dim_erp_sku.sku_key` 完全同形（匹配 1118 行），可作等价桥接；但它**不提供**平台 SKU → ERP SKU 映射 |

**⚠️ 覆盖率风险（管道修通后需验收）**：`mart` 链路里 `product_sku = NULLIF(BTRIM(product_sku), '')`（`sql/mart/inventory_snapshot_company_daily.sql:15`），而 `sku_key = COALESCE(platform_sku, product_sku, sku_id, product_id)`（同文件 `:8-13`）——**以 `platform_sku` 为键的平台行，其 `product_sku` 可能为 NULL**，这类行对上述 join **不可见**，对应 SKU 会静默回落「日常」档（方向安全但覆盖率打折）。
→ 管道修通后须加一条验收断言：**tiktok / shopee 的库存行必须带 `商品SKU`**，否则该平台的库龄永远匹配不上。

其中：
- 平台其他成本率 = `platform_basis` 平台的 `dim_platforms.other_cost_rate`（已含平台佣金率，**不含**达人佣金与 SPU 两率）
- 达人佣金率 = `dim_erp_sku.creator_commission_rate`，NULL 时取 `platform_basis` 平台的 `default_creator_commission_rate`
- SPU 退货损失率 / 货损率 = 该 SKU 有效绑定 SPU 的 `dim_spu.return_loss_rate` / `logistics_damage_rate`
- 目标利润率 = 命中档位的 `target_margin_rate`
- **当前档折扣率 = 命中档位的 `discount_rate`**（纪律线用）
- **清货极限折扣率 = 规则表中 `min_age_days` 最大的当前生效行的 `discount_rate`**（= 30%，只用于「滞销可优惠」列展示，不参与底线计算）

### 4.2 自洽性验证

当「目标利润率 = 实测净利率」且「各 SKU 率 = 实测均值」时（此处按 SKU **未**单独设置达人佣金率、取平台默认 6.06% 计算）：

```
分母 = 1 − 0.2727(其他成本) − 0.0606(达人默认) − 0.0467(SPU退货) − 0.0158(SPU货损) − 0.1781 = 0.4261 = 实测采购成本率
⟹ 最低售价 = C ÷ 0.4261 = 当前平均售价
```

模型天然自校准：调高目标利润率 → 底线线性抬高；调低 → 放宽折扣空间。**这个自洽点只在「达人佣金率 = 平台默认」时成立**——当 SKU 单独设了达人佣金率，底线会按 §4.1 的变量口径相应变化。

### 4.3 计算示例

三个示例 SKU **均未设置** `creator_commission_rate`，故达人佣金率取平台默认 6.06%（底线基数 = 0.2727 + 0.0606 = 0.3333）。

**`166851422928`**（采购成本 10，参考售价 30，SPU 率取仓库均值 4.67% / 1.58%）：

| 库龄 | 命中档位 | 当前档折扣率 | 成本线 | 纪律线 | **最低售价** |
|---|---|---|---|---|---|
| 30 天 | 日常 | 10% | 28.23 | 27.00 | **28.23** |
| 75 天 | 滞销30天 | 15% | 26.03 | 25.50 | **26.03** |
| 100 天 | 滞销60天 | 20% | 23.57 | 24.00 | **24.00** |
| 130 天 | 滞销60天以上 | 30% | 19.83 | 21.00 | **21.00** |

成本线按各档目标利润率算：
```
30 天  (m=0.25): 10 ÷ (1 − 0.2727 − 0.0606 − 0.0467 − 0.0158 − 0.25) = 10 ÷ 0.3542 = 28.23
75 天  (m=0.22): 10 ÷ (1 − 0.2727 − 0.0606 − 0.0467 − 0.0158 − 0.22) = 10 ÷ 0.3842 = 26.03
100 天 (m=0.18): 10 ÷ (1 − 0.2727 − 0.0606 − 0.0467 − 0.0158 − 0.18) = 10 ÷ 0.4242 = 23.57
130 天 (m=0.10): 10 ÷ (1 − 0.2727 − 0.0606 − 0.0467 − 0.0158 − 0.10) = 10 ÷ 0.5042 = 19.83
```
纪律线 = 30 × (1 − 当前档折扣率)。**底线随库龄下沉**——「越滞销越该让利」直接体现在这里。

**`SKU-0001`**（采购成本 100，参考售价 500，日常档，SPU 率取仓库均值）：
> 注：该 SKU 在库中 `status='inactive'`，此处仅作**数据形态示例**（它与 `166851422928` 一样是仅有的两个有参考售价的 SKU 之一）；active 且有参考售价的 SKU 目前只有 `166851422928` 一个。
```
成本线 = 100 ÷ (1 − 0.2727 − 0.0606 − 0.0467 − 0.0158 − 0.25) = 100 ÷ 0.3542 = 282.33
纪律线 = 500 × (1 − 0.10) = 450.00
最低售价 = 450.00   来源：discount_guard
```

**`227764033069`**（采购成本 1.26，参考售价未填，日常档）：
```
成本线 = 1.26 ÷ 0.3542 = 3.56
纪律线 = 不可算（参考售价为空）
最低售价 = 3.56   来源：cost_floor
```

**SKU 单独设置达人佣金率时（以 `166851422928` 在「日常」档把佣金率改成 15% 为例）**：
```
成本线 = 10 ÷ (1 − 0.2727 − 0.15 − 0.0467 − 0.0158 − 0.25) = 10 ÷ 0.2648 = 37.76
纪律线 = 30 × 0.90 = 27.00
最低售价 = 37.76   来源：cost_floor
```
**同一个 SKU，达人佣金率从 6.06% 改到 15%，底线从 28.23 抬到 37.76**——这正是「达人佣金率必须进分母」的业务含义。

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
2. 成本线可算？需要：采购成本、SPU 有效绑定且两率齐全、平台 `other_cost_rate` 已配置、生效规则已命中（库龄档位有规则）、目标利润率与达人佣金率可解析
3. 纪律线可算？需要：参考售价非空且生效规则已命中
4. 取二者较大值；仅一条可算时取该条
5. 都不可算 → `unavailable`，同时返回 `min_selling_price_missing_reasons` 清单（对齐既有 `reference_cost_missing_reasons` 风格）

**`missing_reasons` 取值**：`missing_purchase_cost` / `missing_spu_binding` / `missing_spu_rates` / `missing_platform_cost_rate` / `missing_pricing_policy` / `missing_creator_commission_rate` / `non_positive_cost_denominator`。

**库龄缺失不是 `missing_reasons`**——它有独立的来源标记 `pricing_tier_source`：
- `age_data` —— 命中了真实库龄档位
- `fallback_no_age_data` —— 库龄不可得，回落到第 1 档（日常）

回落档的目标利润率最高（25%）、折扣率最浅（10%），所以**底线最保守（最高）→ 不会亏本**。这是刻意设计：库龄数据缺失时宁可把底线抬高，也不要给一个乐观的低价。

**边界**：
- 分母 `1 − 各项率 ≤ 0` → 不计算成本线，降级到纪律线，并在 `missing_reasons` 记 `non_positive_cost_denominator`
- 全部率之和 ≥ 1 → 视为配置错误，返回 `unavailable`

### 4.5 金额精度与量化边界

**⚠️ 费率不得走 `_money` 量化。** `_money` 的 `MONEY_QUANTUM = 0.01` 是**金额**精度；若把费率也过一遍 `_money`，`0.2727` 会被量化为 `0.27`，底线基数从 `0.0606 + 0.2727 = 0.3333` 变成 `0.0606 + 0.27 = 0.3306`，分母从 `0.3542` 变成 `0.3569`，§4.3 例 1 的底线从 **28.23 变成 28.02**，与本 spec 的示例和 §8.1「精确 Decimal 值」用例直接冲突。

规则：

| 量 | 处理方式 |
|---|---|
| 费率（`other_cost_rate` / 各类率 / 目标利润率 / 折扣率） | 只做 `Decimal(str(value))` 转换，**不量化**，保留全精度参与分母运算 |
| 最终金额（成本线、纪律线、最低售价、覆盖值） | 过 `_money`（`Decimal` + `ROUND_HALF_UP` + `MONEY_QUANTUM = 0.01`） |
| `DimPlatform.default_fee_rate` 等 `Float` 列 | 读取后立即 `Decimal(str(x))`，避免二进制浮点误差进入分母 |

复用 `backend/services/product_profit_service.py` 的 `_money`（`:38-39`）与 `MONEY_QUANTUM`（`:7`）做最终金额量化；**不要**复用它处理费率。

---

## 5. API 变更

### 5.1 规则表（库龄档位）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/api/sku-pricing-policies` | 登录 | 返回全部规则行（含历史），按 `min_age_days, effective_from` 排序 |
| GET | `/api/sku-pricing-policies/current` | 登录 | 返回当前生效的 4 行。**筛选条件必须与下方「当前行」判定完全一致**（复用同一个 helper/常量，禁止在两处各写一份谓词） |
| POST | `/api/sku-pricing-policies` | `_require_platform_fee_editor` | 新建规则行；若同档位已有生效行则拒绝（409），要求先关闭 |
| PUT | `/api/sku-pricing-policies/{min_age_days}` | `_require_platform_fee_editor` | 版本化更新。**具体行为有四条路径**（跨期新建 / 同日原地改 / 回溯拒绝 / 无当前行等价 POST），详见下方「版本化更新的多条路径」——实现时不要只按摘要这一句做 |

**规则行请求/响应模型字段**：`min_age_days` / `tier_label` / `discount_rate` / `target_margin_rate` / `platform_basis` / `effective_from` / `effective_to` / `status` / `source` / `version` / `notes`。

`PUT` 的具体行为见下方「版本化更新的多条路径」。

**数据库层并发保护**：`uq_sku_pricing_policies_current` 部分唯一索引保证每个库龄档位至多一条 `status='active' AND effective_to IS NULL` 的行。若两个请求并发 `PUT` 同一档位，后到者会撞唯一索引报错，实现需捕获 `IntegrityError` → `rollback` → 返回 409（与 `bulk_save_skus` 的 409 模式一致）。

**档位匹配规则**（服务端统一实现，前端不得自行推导）：

> ⚠️ §4.1 的「档位从哪来」与本节的伪码是**同一段逻辑的两处表述**。**实现时只写一处**（放 `backend/services/product_pricing_service.py`），另一处只作说明引用，避免两处漂移。

```
# 1) 取 SKU 当前库龄
#    ⚠️ join 键是 product_sku → dim_erp_sku.sku_key（不是 mart 的 sku_id，见 §4.1 的事实依据）
候选行 = mart.inventory_age_current 中 product_sku = dim_erp_sku.sku_key 的所有行
age_days = 候选行中 age_days 的最小值（跨平台、同平台多行均取最小，理由见 §4.1）
无候选行（库龄不可得）→ age_days = None

# 2) 在当前生效的规则行里匹配档位
生效规则 = 满足「当前行」条件 且 min_age_days <= age_days 的行中 min_age_days 最大的一行
age_days = None → 命中 min_age_days 最小的一行（兜底档，正常是 min_age_days = 0 的「日常」档）

# 3) 无生效规则
无生效规则 → 该 SKU 的 min_selling_price = unavailable，missing_reasons 含 'missing_pricing_policy'
```

「当前行」定义在 `GET /current` 与服务端选档逻辑中**必须完全一致**（同一个 helper / 同一组常量），否则 `/current` 返回的规则与护栏实际生效的规则会不一致。

**唯一谓词**（两处共用，禁止各写一份）：

```python
# 当前行 = status='active' AND effective_to IS NULL AND effective_from <= 今日
```

**必须用 `effective_to IS NULL` 而不是 `effective_to IS NULL OR effective_to > 今日`**：若用后者，一个 `active` 且 `effective_to` 设在未来的行会被 `/current` 列出、却被定价引擎忽略——正是本 spec 禁止的那种不一致。

因此 **不支持"未来生效"的规则行**：
- `POST` / `PUT` 新建行时，`effective_from` 不得晚于今日（晚于则 422 拒绝）
- `effective_to` 必须为 `NULL` 才能是 active 当前行；写入 `effective_to` 即表示该行已关闭（`status` 同步置 `'inactive'`）
- 这条约束同时保证 `uq_sku_pricing_policies_current` 部分唯一索引不会被"未来占位行"占住，从而不会卡住「关旧行 + 建新行」的路径

若同一档位出现多行同时满足上述条件（理论上由 `PUT` 的「关旧开新」保证唯一；出现多行说明数据被绕过 API 直接改动，属数据异常），取 `effective_from` 最大者，并在实现中记 warning 日志。

**版本化更新的多条路径**（`PUT /api/sku-pricing-policies/{min_age_days}`）：

| 场景 | 行为 | 原因 |
|---|---|---|
| 请求的 `effective_from` **严格大于**当前行的 `effective_from` | 版本化更新：关闭当前行（写 `effective_to` = 新 `effective_from`，`status='inactive'`）+ 新建一行 | 跨期变更需要留版本历史 |
| 请求的 `effective_from` **等于**当前行的 `effective_from` | **原地 UPDATE 当前行**（不新建版本），仍写审计 | 同日纠错必须可用。`UNIQUE(min_age_days, effective_from)` 决定了同日新建会撞唯一索引，故同日只能原地改 |
| 请求的 `effective_from` **小于**当前行的 `effective_from` | 422 拒绝 | 回溯变更超出范围，需手工改数据 |
| 该档位**没有**当前行 | 等价于 `POST`：直接新建一行 | `PUT` 在无当前行时不得 404——运营不该需要先 POST 再 PUT |

新行 `effective_from` 必须 **严格大于**（`>`）旧行，不能是 `>=`——否则同日新建会撞 `UNIQUE(min_age_days, effective_from)`，按规范返回 409，用户当天无法纠错。

**「档位起点 `min_age_days` 变更」是独立于版本期的操作**（改的是档位边界，不是生效时间）：

| 场景 | 行为 |
|---|---|
| 路径参数 `min_age_days` 与 body 不一致 | 422（以 body 为准，路径参数仅作定位；不一致说明调用方搞混了） |
| 改成**已存在**的起点 | 409（撞 `UNIQUE(min_age_days, effective_from)` 与 `uq_sku_pricing_policies_current`） |
| 改成**全新**的起点 | 关闭旧行（`effective_to` = 今日、`status='inactive'`）+ 新建一行（`min_age_days` = 新值、`effective_from` = 今日） |

**⚠️ 起点变更豁免「新行 `effective_from` 必须严格大于旧行」这条规则**。理由：该规则是为「只改率、不改边界」设计的（那种情况下同档位同日新建会撞 `UNIQUE(min_age_days, effective_from)`）。而改边界时 `min_age_days` 不同，**不会**撞该唯一约束，因此新行可以与旧行同一天生效。

这样「改档位边界」就是一次普通的关旧开新，不需要额外端点；`min_age_days` 变成新值即代表新档位。

**同一天内的操作优先级**（`PUT` 一次请求可能同时改边界和率）：

| 请求改了什么 | 走哪条路径 |
|---|---|
| 只改率（`min_age_days` 不变） | 原地 UPDATE 当前行（`effective_from` 不变） |
| 只改边界（`min_age_days` 变） | 关旧行 + 新建一行（`effective_from` = 今日） |
| 同时改边界和率 | 走「改边界」路径：关旧行 + 新建一行，新行带上新边界与新率 |

**错误契约**：

| 情况 | HTTP | 说明 |
|---|---|---|
| `effective_from` 晚于今日 | 422 | 不支持未来生效的规则行 |
| `effective_from` 小于当前行 | 422 | 回溯变更超出范围 |
| `min_age_days` 路径参数与 body 不一致 | 422 | 以 body 为准 |
| `min_age_days` 改成已存在的起点 | 409 | 撞 `UNIQUE(min_age_days, effective_from)` / `uq_sku_pricing_policies_current` |
| 撞 `UNIQUE(min_age_days, effective_from)` | 409 | 例如 `POST` 或「无当前行的 PUT」用了同档位**已关闭历史行**的日期 |
| 撞 `uq_sku_pricing_policies_current` | 409 | 并发 `PUT` 同一档位（`IntegrityError` → `rollback` → 409，与 `bulk_save_skus` 的 409 模式一致） |

### 5.2 平台成本率（扩展既有端点，不新增路由）

**决策：扩展既有 `PATCH /api/platforms/{platform_code}/fee-rate`，不新增 `/cost-rates` 路由。**

理由：
- 若保留旧路由 + 新增 `/cost-rates`，同一个平台会有**两条写路径**，旧路径只写 `default_fee_rate`，不写另两项费率 → 留下陈旧值，且用户可能改到"半套"数据
- 既有路由的路径字面量 `'@router.patch("/api/platforms/{platform_code}/fee-rate"'` 被 `backend/tests/test_product_center_p1_final.py:464` 用作 `source.index()` 的区间边界，**删除该路由会让这个既有测试直接抛 ValueError**

| 方法 | 路径 | 权限 | 变更 |
|---|---|---|---|
| PATCH | `/api/platforms/{platform_code}/fee-rate` | `_require_platform_fee_editor` | **扩展**：请求体新增 `default_creator_commission_rate` / `other_cost_rate` 两个可选字段，与既有 `default_fee_rate` / `fee_rate_effective_from` / `fee_rate_source` / `fee_rate_version` 一并写入，写审计 |

- 请求模型 `PlatformFeeRateUpdateRequest`（`backend/schemas/product_center.py:323`）新增两个 `Optional[float] = None` 字段
- **既有 4 个字段的写入语义必须一并改为「未传则保持原值」**。现状 `product_center.py:1990-1993` 是无条件赋值：
  ```python
  row.default_fee_rate = body.default_fee_rate
  row.fee_rate_effective_from = body.fee_rate_effective_from
  row.fee_rate_source = body.fee_rate_source
  row.fee_rate_version = body.fee_rate_version
  ```
  若不改成 `exclude_unset` 语义，则抽屉里只改「达人佣金率」也会把 `default_fee_rate` 写成 NULL、并把 `fee_rate_effective_from` 刷成当天——**保存一次就把平台佣金率清空**。实现必须改成「字段未传 → 不动该列」。
- 读：复用 `GET /api/sku-operating-dimensions`（`SkuOperatingPlatformOption` 新增两字段），**不新增 GET 路由**。注意该端点的 platforms 是**显式 dict 拼装**（`product_center.py:2250-2252`），两个新字段必须加进那个 dict，否则永远序列化为 `null`，抽屉「成本率合计」会显示 0。
- 路径名仍是 `fee-rate`（沿用既有），但语义扩展为「该平台的成本率组」；前端 API 方法名 `updatePlatformFeeRate` 保持不变
- **PATCH 响应回填全部五项**（`default_fee_rate` / `default_creator_commission_rate` / `other_cost_rate` / `fee_rate_effective_from` / `fee_rate_source` / `fee_rate_version`）。现状 `product_center.py:2000` 只回 4 项，实现时需一并补上新字段，前端保存后可直接用响应刷新表单而不必再拉一次 dimensions
- 仍只允许 `platform_role = 'sales'` 的平台（沿用既有 409 规则）
- `default_creator_commission_rate` / `other_cost_rate` 未传（`exclude_unset`）时保持原值不变，**不写 NULL**

### 5.3 SKU 读接口

`GET /api/skus` 响应 `ProductCenterItem` 新增 11 个字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `creator_commission_rate` | `Optional[float] = None` | 该 SKU 的达人佣金率（SKU 主数据字段，`dim_erp_sku`） |
| `current_discount_rate` | `Optional[float] = None` | **当前库龄档位的折扣率** → SKU 资料页「常规可优惠」列 |
| `clearance_max_discount_rate` | `Optional[float] = None` | **清货极限折扣率**（最深档的值，= 30%）→ SKU 资料页「滞销可优惠」列 |
| `min_selling_price` | `Optional[float] = None` | 生效的最低售价（`max(成本线, 纪律线, 覆盖值)`） |
| `min_selling_price_source` | `Optional[str] = None` | `manual_override` / `discount_guard` / `cost_floor` / `unavailable` |
| `min_selling_price_is_override` | `Optional[bool] = None` | 是否人工覆盖 |
| `min_selling_price_override` | `Optional[float] = None` | **人工覆盖值原值**（`dim_erp_sku.min_selling_price_override`） |
| `min_selling_price_missing_reasons` | `list[str] = []` | 无法计算时的原因清单 |
| `pricing_tier_label` | `Optional[str] = None` | 命中档位的显示名（如「滞销30天」「日常」） |
| `pricing_age_days` | `Optional[int] = None` | 该 SKU 当前库龄天数（`mart.inventory_age_current.age_days`） |
| `pricing_tier_source` | `Optional[str] = None` | `age_data` / `fallback_no_age_data` |

**`min_selling_price_override` 必须单独返回**，理由：
- 前端「最低售价」列的**可编辑输入框绑定的是覆盖值**，不是生效值。绑 `min_selling_price` 会导致用户输入被 `payloadSku()` 的只读字段剔除清单误删（见 §6.3）
- 不返回覆盖值，单元格就无法显示「这个 SKU 已经人工设过最低售价 = X」，运营会误以为系统算出来的就是最终值
- `max(成本线, 纪律线, 覆盖值)` 允许覆盖值**低于**成本线（人工有权拍板），此时生效值 ≠ 覆盖值，两者必须都能看到

**⚠️ 所有新增字段必须带默认值（`Optional[...] = None`），不得声明为必填。**

`ProductCenterItem` 声明了 `model_config = {"from_attributes": True}`（`backend/schemas/product_center.py:232`），且被直接用于校验**裸 ORM 行**：

- `product_center.py:1181` — `list_skus` 中 `ProductCenterItem.model_validate(row)`
- `product_center.py:1213` — `create_sku` 返回值
- `product_center.py:1231` — `update_sku` 返回值
- `product_center.py:1319` — `bulk_save_skus` 返回值

这些调用点传入的 `DimErpSku` 对象**没有** `min_selling_price` 等属性。Pydantic v2 在 `from_attributes=True` 下遇到缺失的必填字段会抛 `ValidationError`（而非填 None），会直接打断这四处既有流程。

因此：

- 字段一律 `Optional[...] = None`（`min_selling_price_missing_reasons` 用 `Field(default_factory=list)`）
- 计算结果只在 `list_skus` 中通过既有的 `payload.update({...})` 注入（与既有 `spu` / `logistics_damage_rate` / `data_completeness` 同一模式）
- `create_sku` / `update_sku` / `bulk_save_skus` 的返回值中这些字段为默认值即可——前端在这三处之后都会重新拉取列表（`saveSkuRows` 末尾调用 `loadSkus()`），不影响使用

**`GET /api/sku-operating-dimensions` 的 `platforms` 项**：Pydantic 类是 `SkuOperatingPlatformOption`（`backend/schemas/product_center.py:682-688`），需在该类新增 `default_creator_commission_rate` 与 `other_cost_rate` 两个 `Optional[float] = None` 字段，供前端展示成本率合计。

### 5.4 SKU 写接口

- `PATCH /api/skus/{sku_id}`：`SkuUpdateRequest` 新增 `creator_commission_rate`（`Optional[float]`，0≤x≤1）与 `min_selling_price_override`（`Optional[float]`，>0）。**必须用 `exclude_unset=True` 语义**，`null` 表示清除覆盖值（既有 `update_sku` 已是 `model_dump(exclude_unset=True)`，传 `null` 即可清空）。
- `POST /api/skus/bulk`：`SkuBulkItem` 同步新增两个字段，语义同上。
- `POST /api/skus`：`SkuCreateRequest` 同步新增两个字段。

**`creator_commission_rate` 有前端列**：它是达人佣金率的**唯一录入入口**（见 §3.2），因此 SKU 资料页新增第 4 列「达人佣金率」可编辑（§6.3）。留空 = 未单独设置 = 计算时取平台默认值兜底；UI 需在空值时用 placeholder 提示兜底值，并注明「留空表示不单独设置，按平台默认计算」。

### 5.5 利润测算护栏

`GET /api/platform-sku-profit/candidates` 每行新增：

| 字段 | 说明 |
|---|---|
| `min_selling_price` | 该 SKU 的全局最低售价（SKU 资料页同一个数） |
| `min_selling_price_source` | 来源标记 |
| `min_selling_price_is_override` | 是否人工覆盖 |
| `current_discount_rate` | 当前库龄档位的折扣率 |
| `clearance_max_discount_rate` | 清货极限折扣率（= 30%） |
| `pricing_tier_label` | 命中的库龄档位名 |
| `pricing_age_days` | 该 SKU 当前库龄天数 |
| `pricing_tier_source` | `age_data` / `fallback_no_age_data`（利润 tab 据此显示「兜底」提示） |
| `min_selling_price_below` | `expected_selling_price < min_selling_price` 时为 `True` |

`GET /api/platform-sku-profit/candidates` 是**按平台+仓库+运输方式**筛选的，但返回的 `min_selling_price` 是**SKU 全局底线**（按 `platform_basis` 的 tiktok 口径计算，与该行的平台/仓库/运输方式无关）。响应中应明确这一点，避免使用者误以为它随所选平台变化。

**⚠️ `min_selling_price_below` 是按服务端已存的 `expected_selling_price` 算的，用户在表格里改了预计售价后就会过期**。因此：
- 前端的标红**必须用当前输入框的值实时比较**，不能信这个布尔值
- 该布尔值仅用于首屏渲染与后端自检，前端不得作为唯一判断依据

`POST /api/platform-sku-profit/estimates` 增加拦截：

```json
HTTP 422
{
  "detail": {
    "code": "below_min_selling_price",
    "min_selling_price": 28.23,
    "expected_selling_price": 25.00,
    "message": "预计售价低于最低售价 28.23"
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
│ 版本       [v2]                                    │
└────────────────────────────────────────────────────┘
```

「成本率合计」= 平台佣金率 + 默认达人佣金率 + 平台其他成本率 = 40.70%，**仅作成本结构展示**，不是底线基数。

**默认底线基数（平台侧，SKU 未单独设置达人佣金率时）= 默认达人佣金率 + 平台其他成本率 = 33.33%**（平台佣金率已包含在 `other_cost_rate` 内，不重复计入）。完整分母还要再减 SPU 退货/货损率与目标利润率（以「日常」档 25% 为例）：

```
分母 = 1 − 0.0606(达人) − 0.2727(其他成本) − 0.0467(SPU退货) − 0.0158(SPU货损) − 0.25(目标利润率) = 0.3542
```

> 抽屉文案必须写明「**SKU 未单独设置达人佣金率时**」这个限定语——SKU 一旦单独设置了佣金率，实际分母里的达人佣金项就是 SKU 值，底线会不同（§4.1）。

抽屉提示文案必须写明这一点，避免财务按 40.70% 复算时与系统值对不上。

「默认达人佣金率」的 label 必须写明「**SKU 未单独设置时的兜底值**」，避免运营以为改它就改了所有商品的佣金。

**子 Tab 2「库龄档位规则」** — 4 行可编辑表格：

```
┌────────────┬──────────┬──────────┬──────────┐
│ 库龄起点    │ 档位名    │ 折扣率    │ 目标利润率│
├────────────┼──────────┼──────────┼──────────┤
│ 0 天       │ 日常      │  10%     │   25%    │
│ 60 天      │ 滞销30天  │  15%     │   22%    │
│ 90 天      │ 滞销60天  │  20%     │   18%    │
│ 120 天     │ 滞销60天以上│ 30%     │   10%    │
└────────────┴──────────┴──────────┴──────────┘
```

- 「库龄起点」列可编辑（改这一格就改了滞销阈值），「档位名」列可编辑
- 编辑任一格 → 保存时提交 `PUT /api/sku-pricing-policies/{min_age_days}`（版本化更新，变更起点走 §5.1 的「档位起点变更」路径）
- 表头需说明「库龄起点 = 从该天数起，本行规则生效」
- **折扣率是本档位的唯一折扣率**——折扣力度完全由库龄档位触发，没有「同档位两个额度」
- 抽屉需注明「**最深档（120 天）的折扣率 30% 同时就是 SKU 资料页「滞销可优惠」列的清货极限**」
- **档位名建议写成自解释形式**：`tier_label` 初始值用「库龄≥60天」「库龄≥90天」这类以库龄表达的文案，而不是「滞销30天」——因为「滞销30天」指的是「进入滞销后第 30 天」，而库龄起点是 60 天，运营容易读成「库龄 30 天」。若要保留「滞销30天」这类业务称呼，UI 必须在档位标签旁同时显示库龄天数（`pricing_age_days`）。

### 6.2 入口

| 位置 | 按钮 | 默认打开 | 条件 |
|---|---|---|---|
| 平台 SKU 利润测算 tab（现有按钮改名） | 定价设置 | 平台成本率 | `canManagePlatformFee`（admin/manager/finance） |
| SKU 资料 tab（新增按钮） | 定价设置 | 库龄档位规则 | `canManagePlatformFee` |

不新增独立页面或独立抽屉，保证「平台成本参数只有一个录入入口」。

### 6.3 SKU 资料 tab 新增 4 列

位置：紧跟「参考售价」列之后（团队改价时最常看的相邻列）。

| 列 | 渲染 | 可编辑 |
|---|---|---|
| 常规可优惠 | 只读 tag = `row.current_discount_rate` + 档位标签（`row.pricing_tier_label`，如「滞销30天」「日常」）<br>⚠️ 利润测算 tab 里同一字段叫「当前可优惠」，**统一用「当前可优惠」**，本列表头同步改名 | 否 |
| 滞销可优惠 | 只读 tag = `row.clearance_max_discount_rate`（清货极限，全 SKU 同一值）+ tooltip「清货极限」 | 否 |
| 最低售价 | **两段式**：<br>① 生效值只读文本 `row.min_selling_price` + 来源 tag<br>② 覆盖值输入框 `el-input-number` 绑 `row.min_selling_price_override`（`:min="0.01"` `:precision="2"` `:controls="false"`），空值时 placeholder 显示生效值<br>③ 「重置为自动值」按钮（仅当 `min_selling_price_is_override` 为真时显示） | 是（仅覆盖值） |
| 达人佣金率 | `el-input-number` 绑 `row.creator_commission_rate`（`:min="0"` `:max="100"` `:step="0.1"` `:precision="2"` `:controls="false"`），单位 % | 是 |

**绑定字段必须是 `min_selling_price_override`，不能是 `min_selling_price`**：

- `min_selling_price` 是**生效值**（`max(成本线, 纪律线, 覆盖值)`），是后端算出来的派生值，不可编辑
- 若把输入框绑到 `min_selling_price`，用户输入的值会在 `payloadSku()` 剔除只读字段时被**静默丢弃**——用户以为改了，保存后没反应
- 若绑到 `min_selling_price_override`，`GET /api/skus` 必须返回该字段（见 §5.3），否则单元格无法显示"已人工设过 = X"
- `max()` 允许覆盖值**低于**成本线（人工有权拍板），此时 `min_selling_price ≠ min_selling_price_override`，两者必须分开显示

**「达人佣金率」列**：单位是**百分比**（前端 `%`），后端字段是**小数**（`0.0606`），提交时用既有的 `toPercent` / `fromPercent` 互转（`ProductCenter.vue` 已有这两个 helper，`platformFeeDrawer` 在用）。

**⚠️ 清空该列必须提交 `null` 而不是 `0`**。既有 helper 的签名是：
```js
const fromPercent = (value, fallback = 0) => value == null || value === "" ? fallback : Number(value) / 100;
```
默认 `fallback = 0` 会把空值转成 **0** 并落库（DB CHECK 允许 0），计算时按 0% 而不是平台默认 6.06% 计算，**分母变大 → 底线被系统性压低 14.6%**（例 1：28.23 → 24.11）——方向是**压低（亏本风险）**，不是抬高。**该字段必须用 `fromPercent(value, null)`**（或等价写法），让空值原样传 `null` 落库，语义才是「未单独设置 → 用平台默认兜底」。

- 来源标记 tooltip 文案：
  - `manual_override` → 「人工设定」
  - `discount_guard` → 「参考售价 × (1 − 当前档折扣率)」
  - `cost_floor` → 「成本 + 目标利润率反解」
  - `unavailable` → 展示缺失原因（`min_selling_price_missing_reasons`）
- 档位来源（`pricing_tier_source`）：
  - `age_data` → 档位标签正常显示
  - `fallback_no_age_data` → 档位标签加「兜底」提示，tooltip 说明「库龄数据未就绪，暂按日常档计算」
- 档位标签旁可展示 `row.pricing_age_days`（库龄天数），有值时显示「滞销30天（库龄 75 天）」
- 编辑覆盖值 / 达人佣金率 → 写入对应行字段，走既有 `dirtyRows` + `/api/skus/bulk` 批量保存链路
- 「重置为自动值」→ 把 `row.min_selling_price_override` 置 `null`，恢复自动计算
- `blankSku()` 工厂（`ProductCenter.vue:925`）需同步新增 `creator_commission_rate: null` 与 `min_selling_price_override: null`，避免新建行携带未定义字段
- `payloadSku()`（`ProductCenter.vue:1341`）当前展开整行，需**剔除只读计算字段** `current_discount_rate` / `clearance_max_discount_rate` / `min_selling_price` / `min_selling_price_source` / `min_selling_price_is_override` / `min_selling_price_missing_reasons` / `pricing_tier_label` / `pricing_age_days` / `pricing_tier_source`。
  - `SkuBulkItem` 未设 `model_config`，Pydantic v2 默认 `extra="ignore"`，多余字段不会报错，但会让每次批量保存把未修改的 `creator_commission_rate` / `min_selling_price_override` 原值重写一遍，产生无谓的审计记录。
  - **`min_selling_price_override` 与 `creator_commission_rate` 必须保留在 payload 中**——它们是**可写字段**。`SkuBulkItem` 用 `model_dump(exclude_unset=True)`，显式传 `null` 才会把覆盖值清空。二者都不属于上面的只读剔除清单。

### 6.4 利润测算 tab 护栏

- 「预计售价」列右侧新增「最低售价」只读列（显示 `row.min_selling_price` + 来源 tag）
- 另在「竞品价格」列右侧新增「当前可优惠」只读列（显示 `row.current_discount_rate`）与「清货极限」只读列（显示 `row.clearance_max_discount_rate`）
  - **命名统一**：同一字段 `current_discount_rate` 在 SKU 资料页叫「常规可优惠」、在利润测算 tab 叫「当前可优惠」——**统一为「当前可优惠」**，SKU 资料页的列标题同步改名（它本来就在「常规可优惠」的位置上，改名后语义更准：它就是当前档位的折扣率）
  - `clearance_max_discount_rate` 已在 §5.5 下发，利润测算 tab 补上「清货极限」列，避免「拿到了字段但界面不显示」
- **护栏只有一层**（纪律线已是最低售价的组成部分，不需要额外的黄色软提示）：

| 条件 | 表现 | 是否拦截 |
|---|---|---|
| `expected_selling_price < min_selling_price` | 预计售价输入框**标红** + 行内提示「低于最低售价 {min_selling_price}」 | ✅ 硬拦截：「保存利润版本」按钮禁用 + tooltip 说明；后端 422 兜底 |
| `expected_selling_price >= min_selling_price` | 无提示 | ❌ |

- 后端 422 返回时，前端展示 `detail.min_selling_price` 与差额。既有 catch 分支（`ProductCenter.vue:1322`）只读 `detail.missing_fields`，**需要扩充分支**读 `detail.code === 'below_min_selling_price'` 时的 `detail.min_selling_price`，与 `missing_fields` 分支并存。

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
| **平台佣金不重复计** | 分母只含「平台其他成本率 + 达人佣金率 + SPU两率 + 目标利润率」。`default_fee_rate` **不得**单独进入分母——断言例 1 结果为 28.23，若误加平台佣金会变成 35.65 |
| **费率不量化** | 输入 `other_cost_rate=0.2727` 时，底线基数必须是 0.3333（不是 0.3306），例 1 结果为 28.23（不是 28.02）——守住 §4.5 的量化边界 |
| **达人佣金率进分母** | SKU 设 `creator_commission_rate=0.15` 时，例 1 底线 = 10 ÷ (1−0.2727−0.15−0.0467−0.0158−0.25) = **37.76**；不设时 = 28.23。两者必须不同 |
| 自洽性 | 目标利润率 = 实测净利率、各项率 = 实测均值时，底线 = C ÷ 采购成本率 |
| 分母 ≤ 0 | 不抛异常，降级到纪律线，`missing_reasons` 含 `non_positive_cost_denominator` |
| 纪律线 | 参考售价 × (1 − 当前档 `discount_rate`) |
| 取大 | 成本线与纪律线取大，人工覆盖优先级最高 |
| 降级链 | 采购成本缺失 / SPU 未绑定 / 平台成本率未配置 / 无生效规则 → `unavailable` + 原因清单 |
| **库龄档位匹配** | `age_days=75` 命中 `min_age_days=60` 档；`age_days=59` 命中 `min_age_days=0` 档；`age_days=200` 命中 `min_age_days=120` 档（最深档，无更深的档） |
| **库龄缺失回落** | 库龄不可得时命中 `min_age_days=0` 档，且 `pricing_tier_source = 'fallback_no_age_data'`；底线取该档的率（目标利润率 25%，最保守） |
| **档位边界可配** | 规则表 `min_age_days` 改动后，匹配结果随之变化（不依赖 `turnover_class`） |
| **定价不读 turnover_class** | 同一 SKU 的 `turnover_class` 改成任何值，底线结果**不变** |
| **折扣力度只由库龄决定** | 规则表每档只有一个 `discount_rate`；同一 SKU 的 `current_discount_rate` 随库龄档位变化，`clearance_max_discount_rate` 恒等于最深档值（30%） |
| 达人佣金回退 | SKU 未设 `creator_commission_rate` 时取 `platform_basis` 平台的默认；设了则用 SKU 值 |
| 覆盖值可低于成本线 | `min_selling_price_override` 小于成本线时，生效值 = 覆盖值，来源 = `manual_override` |
| 规则表约束 | `discount_rate` 越界 / `target_margin ≥ 1` / `min_age_days < 0` 均被拒 |
| 版本化更新 | `effective_from` 严格大于旧行时 → 旧行关闭 + 新行生效；等于旧行时 → 原地 UPDATE；小于旧行 → 422 |
| 并发 PUT | 撞 `uq_sku_pricing_policies_current` 时返回 409 |
| 护栏拦截 | 预计售价 < 最低售价 → 422 `below_min_selling_price`；≥ 则通过 |
| 草稿不拦截 | `POST /drafts` 在低于最低售价时仍返回 201 |
| 写接口审计 | 规则表 / 平台成本率 / SKU 覆盖值与达人佣金率的写操作均产生 `FactAuditLog` |
| 平台成本率部分更新 | 只传 `default_creator_commission_rate` 时，`default_fee_rate` / `fee_rate_effective_from` / `fee_rate_source` / `fee_rate_version` **保持原值不变**（不被写成 NULL、不被刷成当天） |
| 未来生效日期 | `effective_from` 晚于今日 → 422；`effective_to` 非空时 `status` 必须为 `inactive` |

### 8.2 契约测试

在 `backend/tests/test_product_center_schema_contract.py` 追加：
- `ProductCenterItem` 含 11 个新字段，**且全部为可选**（`field.is_required()` 为 `False`）——回归护栏，防止后续有人把它们改成必填导致 `model_validate(ORM row)` 抛 ValidationError
- `SkuUpdateRequest` / `SkuBulkItem` / `SkuCreateRequest` 含 2 个新字段
- `DimErpSku` 含 `creator_commission_rate` / `min_selling_price_override`
- `DimPlatform` 含 `default_creator_commission_rate` / `other_cost_rate`
- `SkuPricingPolicy` 表存在且约束齐全，且已从 `modules.core.db` 导出

### 8.3 迁移契约

**新建独立文件** `backend/tests/test_sku_pricing_guardrails_contract.py`（与 §8.1 的新文件风格一致；不并入 `test_turnover_storage_contract.py`，避免不同功能的迁移断言混在一起）：
- 迁移文件包含 `sku_pricing_policies` 建表语句
- 迁移文件包含 `dim_platforms` 两列新增
- 迁移文件包含 `dim_erp_sku` 两列新增
- 迁移文件包含 4 条规则初始数据与 2 条平台成本率初始数据
- 迁移文件包含 `downgrade()` 且同样有存在性守卫
- 迁移 revision 链正确：`down_revision == "current_schema_20260921_warehouse_storage_label_fee"`（实施时以 `alembic heads` 实际输出为准）

### 8.4 前端

在 `frontend/tests/productCenterUi.test.mjs` 追加：
- SKU 资料 tab 渲染 4 个新列
- 最低售价列的来源标记 tooltip 文案
- 最低售价列的可编辑输入框绑定 `min_selling_price_override`（**不是** `min_selling_price`）
- 达人佣金率列绑定 `creator_commission_rate`，且百分比 ↔ 小数转换走 `toPercent` / `fromPercent`
- 利润测算 tab 低于最低售价时输入框标红、保存按钮禁用
- 定价设置抽屉两个子 Tab 可切换，字段绑定正确
- `payloadSku()` 输出不含只读计算字段（含 `min_selling_price`），且显式保留 `min_selling_price_override: null` 与 `creator_commission_rate`

**必须同时修改的既有断言**（改名会打破它们）：

- `frontend/tests/productCenterUi.test.mjs:130` — `assert.match(source, /平台费率管理/)`。按钮与抽屉标题从「平台费率管理」改名为「定价设置」后该断言会失败，需改为匹配新标签（如 `/定价设置/`）。
- `frontend/tests/productCenterUi.test.mjs` 其余断言不受影响。

**无需改动的文档**：根目录 `API_CONTRACT.md` 与 `docs/API_CONTRACTS.md` 均为通用契约规范（响应格式、错误处理约定），**未列出商品中心的具体路由**，因此本次新增端点不需要更新它们。

---

## 9. 迁移

文件：`current_migrations/versions/20261020_sku_pricing_guardrails.py`

沿用 `20260916_sku_turnover_storage_rules_cny.py` 的幂等范式（`_has_table` / `_has_column` / `_has_constraint` / `_has_index` 守卫），并满足 `docs/DEVELOPMENT_RULES/DATABASE.md` §7.2 / §9.7 的迁移检查清单：

- `upgrade()` 与 `downgrade()` **都要写**，且 `downgrade()` 同样幂等
- 所有 `op.add_column()` / `op.create_index()` / `op.create_table()` / `op.create_check_constraint()` 都要有存在性守卫
- 输出用 `safe_print()`，不用 `print()`
- 验证链路：`alembic upgrade heads` → `alembic downgrade -1` → `alembic upgrade heads` 三步可重复执行无报错

```python
revision = "current_schema_20261020_sku_pricing_guardrails"
down_revision = "current_schema_20260921_warehouse_storage_label_fee"
```

`downgrade()` 需要：删除 `finance.sku_pricing_policies` 表（含其索引与约束）、删除 `core.dim_platforms` 与 `core.dim_erp_sku` 的 4 个新列。注意 `down_revision` 指向 `current_schema_20260921_warehouse_storage_label_fee`——**实施时需再次确认当前 head**（迁移链存在多个分支时以 `alembic heads` 实际输出为准）。

内容：
1. 建 `finance.sku_pricing_policies` 表（含 5 个 CHECK、1 个 UNIQUE、2 个 INDEX，其中 `uq_sku_pricing_policies_current` 为部分唯一索引）
2. `core.dim_platforms` 加 `default_creator_commission_rate` / `other_cost_rate` 两列 + 3 个 CHECK（命名 `ck_dim_platforms_*`）
3. `core.dim_erp_sku` 加 `creator_commission_rate` / `min_selling_price_override` 两列 + 2 个 CHECK（命名 `ck_dim_erp_sku_*`）
4. 插入 **4 条** `finance.sku_pricing_policies` 初始规则（`effective_from` = 执行日，`status = 'active'`，`source = 'industry_benchmark_2026'`，`version = 'v1'`）：

   | min_age_days | tier_label | discount_rate | target_margin_rate | platform_basis |
   |---|---|---|---|---|---|
   | 0 | 日常 | 0.10 | 0.25 | tiktok |
   | 60 | 滞销30天 | 0.15 | 0.22 | tiktok |
   | 90 | 滞销60天 | 0.20 | 0.18 | tiktok |
   | 120 | 滞销60天以上 | 0.30 | 0.10 | tiktok |

   > `platform_basis` 是规则表的 `nullable=False` 列，但**只用于成本线取哪个平台的费率**，不参与档位匹配（避免「先要档位才知道平台」的循环，§4.1）。当前所有档位统一为 `tiktok`。

5. 更新 `core.dim_platforms` 初始成本率（当前两行均为 `default_fee_rate=0.02, fee_rate_source='manual', fee_rate_version='v1'`）：
   - tiktok：`default_fee_rate = 0.0737`、`default_creator_commission_rate = 0.0606`、`other_cost_rate = 0.2727`、`fee_rate_source = 'b_class_measured_2026_01_07'`、`fee_rate_version = 'v2'`
   - shopee：`default_fee_rate = 0.1487`、`default_creator_commission_rate = 0.0111`、`other_cost_rate = 0.4165`、同上

   `fee_rate_effective_from` **保留原值**（tiktok `2026-09-01`、shopee `2026-09-15`）——本次是纠正错误取值而非新增未来费率，保留原值仅为**审计连续性**：现有利润测算代码直接取 `platform.default_fee_rate`，并不按生效日期选版本，历史 `finance.sku_profit_estimates` 也不重算，因此回溯生效日期对历史测算没有实际影响。

`dim_platforms.default_fee_rate` 的校准值**必须用 SQL UPDATE 显式写入**，不能依赖 ORM 默认值。

`amazon`（role=sales）与 `miaoshou`（role=source）、`验证码测试账号`（role=test）三行不配置成本率。这**不影响**这些 SKU 的最低售价——底线按 `platform_basis`（当前 tiktok）的费率计算，与该 SKU 在哪个平台卖无关。

**本次迁移不写 `core.dim_erp_sku.creator_commission_rate`**——1121 个 SKU 全部留空，由平台默认值（tiktok 6.06%）兜底，底线上线即可用。运营按品在 SKU 资料页逐个覆盖。

---

## 10. 已知限制

1. **成本线不含逐 SKU 精算的物流与仓储**。`weight_kg` 0/1121、`unit_volume_cbm` 3/1121 有值，改用平台级 `other_cost_rate`。尺寸数据补齐后可升级为逐 SKU 精算，届时 `other_cost_rate` 退化为兜底值。**这意味着当前底线对大件/重货 SKU 偏低。**
2. **成本线不含广告费的独立建模**。广告成本已包含在 `other_cost_rate` 内（TikTok 14.74%），但利润测算里的广告费率是「广告前利润的分配比例」口径，两者不可直接互换。
3. **达人佣金未设置时用平台默认值**。实测波动 3.7%–33.8%，平台均值（tiktok 6.06%）对高佣金商品偏低。本次不做自动回填（订单表 `商品SKU`/`平台SKU`/`SKU_ID` 三列全空，无法映射到 ERP SKU），由运营在 SKU 资料页逐个设置。
4. **参考售价 0.2% 填充率**，纪律线当前几乎不生效，绝大多数 SKU 走成本线。参考售价补齐后纪律线自动叠加，无需改代码。
5. **⚠️ 库龄数据管道当前是空的，本次上线时全部 SKU 落在「日常」档**。`mart.inventory_age_current` 目前 0 行（源表 `semantic.fact_inventory_snapshot` 也是 0 行，采集层 2026-09 重写为 V2 canonical 后同步层与 SQL 三层未同步）。因此：
   - 本次交付后 1118 个 SKU 的 `pricing_tier_source = 'fallback_no_age_data'`，全部按「日常」档（折扣率 10%、目标利润率 25%）计算——**这是最保守的档，底线最高，不会亏本**
   - 库龄管道修通后，档位按真实库龄自动下沉，**无需改任何代码**——join 路径（`mart.inventory_age_current.product_sku` → `core.dim_erp_sku.sku_key`，实测匹配 1080/1094）已在 §4.1 定稿，管通即生效
   - 库龄管道修复是独立任务，不在本 spec 范围内
6. **`other_cost_rate` 是黑盒数字**。它是恒等式反推值，财务无法从 UI 看出构成；子 Tab 1 应展示「成本率合计」并注明推导方式。
7. **校准 `default_fee_rate` 会改变利润测算结果**（TikTok 利润下降约 5.4 个百分点，Shopee 约 12.9 个百分点）。历史 `finance.sku_profit_estimates` 版本不被改写，但新旧测算不可直接比较，需在 UI 上标注 `fee_rate_version`。
8. **`amazon` 未配置自身成本率**，在**利润测算**中 `default_fee_rate` 仍为 NULL → 平台费用算不出（与现状一致，非本次引入）。但这**不影响** amazon SKU 的最低售价：底线按 `platform_basis`（当前 tiktok）的费率计算，与该 SKU 在哪个平台卖无关。
9. **底线是公司统一口径，不是按售卖平台逐个算的**。若将来要「按每个平台各自算底线」，需要把 `platform_basis` 从规则表列改为 SKU×平台维度，工作量与数据模型都要重做，属于 V2 范围。
10. **`turnover_class` 不参与定价**。它继续只用于参考仓储天数（快销 30 / 普通 60 / 慢销 90，见 `product_profit_service.py:12`）。该字段 1121 个 SKU 仅 3 个有值，且**从未建立过 SKU 的快销/普通/慢销经营分类**——定价档位已改用库龄阶梯，不再依赖它。
