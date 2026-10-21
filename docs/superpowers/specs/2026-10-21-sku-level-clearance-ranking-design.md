# SKU 级滞销排名设计（SKU-Level Clearance Ranking）

**日期:** 2026-10-21
**状态:** 待实施
**上游依赖:** `docs/superpowers/specs/2026-10-21-inventory-aging-pipeline-recovery-design.md`（库龄管道恢复 —— **本 spec 的数据前提**）
**定位:** 把滞销排名从**店铺 × 月**粒度扩到 **SKU** 粒度，并让它与商品中心的定价底线串起来。

---

## 1. 背景与目标

### 1.1 现状

`GET /api/dashboard/clearance-ranking`（业务概览页的「滞销清理排名（月度）」）返回的是**店铺级**汇总：

| 字段 | 含义 | SKU 级能否用 |
|---|---|---|
| `ranking_month` / `platform_code` / `shop_id` / `shop_name` | 月份 + 平台 + 店铺 | 店铺级 |
| `clearance_amount` / `clearance_quantity` | 该店铺该月的销售额/销量 | **不是滞销金额**，是销量 |
| `stagnant_sku_count` | 该店铺有多少个滞销 SKU | 只是个计数 |
| `max_stagnant_age_days` | 该店铺最长的滞销天数 | 只是最大值 |
| `risk_level` / `rank` | 风险等级 / 排名 | 店铺级 |
| `platform_sku` / `product_sku` / `product_name` | — | **全是 `NULL::text`** |

**运营要回答的问题，这个接口答不了：**

- 「到底是哪几个 SKU 压着钱？」（只有计数，没有清单）
- 「这个 SKU 压了多久？」（只有店铺级最大值）
- 「这个 SKU 现在能打几折清？最低售价是多少？」（**完全没有**）
- 「清掉它最多能回收多少钱？」（没有）

### 1.2 本 spec 的目标

1. 新增一个 **SKU 级滞销清单**读模型，一行一个 SKU，带库龄、库存金额、风险等级
2. 清单上**直接带出定价信息**（当前可优惠折扣率、滞销可优惠折扣率、最低售价）—— 让「滞销」和「怎么清」在同一张表里
3. 把滞销判定口径**从「最近两帧间隔」升级为「真库龄」**
4. 保持既有店铺级排名**完全不变**（业务概览页不回归）

---

## 2. 口径决策：三个「滞销天数」必须分清

这是本 spec 最容易出错的地方。仓库里现在有**三个**看起来都叫「滞销天数」的指标，口径完全不同：

| 指标 | 出处 | 算法 | 是不是真库龄 |
|---|---|---|---|
| `age_days` | `mart.inventory_age_current` | 从**第一次有库存**那天起累加；补货归零、卖空重现归零 | ✅ **真库龄** |
| `estimated_stagnant_days` | `mart.inventory_snapshot_change` | 只看**最近两帧**的间隔，且要求这期间库存没变 | ❌ 采样间隔的函数 |
| `estimated_turnover_days` | `mart.inventory_backlog_base` | `可用库存 ÷ 近30天日均销量` | ❌ 动销速度的函数 |

**关键事实：`estimated_stagnant_days` 不是累计的。**

`sql/mart/inventory_snapshot_change.sql` 的 `top_two_history` 只取 `snapshot_rank <= 2`，然后
`estimated_stagnant_days = GREATEST(snapshot_date - previous_snapshot_date, 0)`（库存未变时）。

→ 采集越频繁，这个数**越小**。3 天采集时它 ≤ 3；7 天采集时 ≤ 7。**它衡量的是「上次动过是什么时候」，不是「这批货压了多久」。**

而且既有店铺级滞销的判定门槛 `h.age_days >= 30`（`sql/api_modules/clearance_ranking_module.sql:58`）
用的是 `GREATEST(estimated_stagnant_days, estimated_turnover_days)` —— 也就是说，**当前滞销排名实际是靠动销速度在判，不是靠库龄。**

**决策：SKU 级滞销清单以 `mart.inventory_age_current.age_days` 为主口径。**

理由：
- 它是**累计**的，采集变密不会让它变小
- 它是**商品中心定价用的同一个数**（`_load_age_days_by_sku` 读的就是它）→ 滞销清单和定价不会出现「这个品算滞销但按日常档打折」的自相矛盾
- 它有 `age_anchor_date`（起算日）和 `reset_reason`（为什么重置）→ 运营能追责到「这批货到底是哪天进的」

`estimated_turnover_days` 保留为**辅助列**（动销速度是独立信息，运营需要它判断「还能不能卖得动」），但**不参与主判定**。

既有店铺级读模型 `api.clearance_ranking_module` **不改**（口径问题记录在 §7，本次不动它）。

---

## 3. 方案

### 3.1 新增读模型 `api.sku_clearance_ranking_module`

**一张新视图，不新建表。**

```sql
CREATE OR REPLACE VIEW api.sku_clearance_ranking_module AS
WITH age AS (
    -- 库龄主口径：每个 (platform_code, sku_key) 一行
    SELECT
        a.snapshot_date,
        a.platform_code,
        a.sku_key,
        a.product_sku,
        a.product_name,
        a.current_qty,
        a.on_hand_qty,
        a.inventory_value,
        a.warehouse_count,
        a.age_anchor_date,
        a.age_days,
        a.bucket,
        a.reset_reason
    FROM mart.inventory_age_current a
    WHERE a.product_sku IS NOT NULL
),
turnover AS (
    -- 动销辅助：仓库行聚合到 SKU
    -- ⚠️ **实施期调整（2026-10-22）**：原稿这里读 mart.inventory_backlog_base，
    --    但那个视图的 sales_30d 要 8.8 秒（详见 §3.1a），
    --    改读 mart.inventory_snapshot_change（等价、48ms）+ 单独的销售聚合。
    SELECT
        platform_code,
        product_sku,
        SUM(available_stock)      AS available_stock,
        SUM(on_hand_stock)        AS on_hand_stock,
        SUM(inventory_value)      AS inventory_value,
        MAX(daily_avg_sales)      AS daily_avg_sales,
        CASE
            WHEN MAX(daily_avg_sales) > 0
            THEN ROUND(SUM(available_stock)::numeric / MAX(daily_avg_sales), 2)
            WHEN SUM(available_stock) > 0 THEN 9999
            ELSE 0
        END                      AS estimated_turnover_days,
        MAX(is_stagnant)                AS is_stagnant,
        MAX(estimated_stagnant_days)    AS estimated_stagnant_days,
        MAX(stagnant_snapshot_count)    AS stagnant_snapshot_count
    FROM mart.inventory_snapshot_change
    WHERE product_sku IS NOT NULL
    GROUP BY platform_code, product_sku
),
current_policy AS (
    -- 规则表「当前行」谓词与 product_center._policy_current_predicate() 保持一致
    SELECT min_age_days, tier_label, discount_rate, target_margin_rate
    FROM finance.sku_pricing_policies
    WHERE status = 'active'
      AND effective_to IS NULL
      AND effective_from <= CURRENT_DATE
),
hit_tier AS (
    -- 命中档位：与 product_pricing_service.select_age_tier() 同口径
    SELECT
        a.platform_code, a.product_sku, a.age_days,
        t.tier_label,
        t.discount_rate       AS current_discount_rate,
        t.target_margin_rate  AS current_target_margin_rate
    FROM age a
    LEFT JOIN LATERAL (
        SELECT p.* FROM current_policy p
        WHERE p.min_age_days <= a.age_days
        ORDER BY p.min_age_days DESC
        LIMIT 1
    ) t ON TRUE
),
deepest_policy AS (
    SELECT discount_rate AS clearance_max_discount_rate
    FROM current_policy
    ORDER BY min_age_days DESC
    LIMIT 1
),
erp AS (
    SELECT sku_id, sku_key, sku_name,
           default_purchase_cost, reference_selling_price, min_selling_price_override
    FROM core.dim_erp_sku
)
SELECT
    a.snapshot_date,
    a.platform_code,
    a.product_sku,
    a.sku_key,
    COALESCE(erp.sku_name, a.product_name) AS product_name,
    a.current_qty,
    a.on_hand_qty,
    a.inventory_value,
    a.warehouse_count,
    a.age_anchor_date,
    a.age_days,
    a.bucket                                  AS age_bucket,
    a.reset_reason,
    t.estimated_turnover_days,
    t.daily_avg_sales,
    t.is_stagnant,
    t.estimated_stagnant_days,
    t.stagnant_snapshot_count,
    CASE
        WHEN a.age_days >= 180 OR t.stagnant_snapshot_count >= 3 THEN 'high'
        WHEN a.age_days >= 90  OR t.stagnant_snapshot_count >= 2 THEN 'medium'
        ELSE 'low'
    END                                        AS risk_level,
    -- 清货优先级：库存金额为主，库龄加权
    ROUND(
        COALESCE(a.inventory_value, 0) * 0.5
        + a.age_days * 10
        + COALESCE(t.estimated_turnover_days, 0) * 2
    , 2)                                       AS clearance_priority_score,
    erp.sku_id,
    erp.default_purchase_cost,
    erp.reference_selling_price,
    erp.min_selling_price_override,
    ht.tier_label                             AS pricing_tier_label,
    ht.current_discount_rate,
    ht.current_target_margin_rate,
    dp.clearance_max_discount_rate,
    -- 最低售价：与 product_pricing_service.compute_sku_pricing() 同公式
    CASE
        WHEN erp.min_selling_price_override IS NOT NULL
        THEN erp.min_selling_price_override
        ELSE GREATEST(
            CASE WHEN erp.default_purchase_cost IS NOT NULL
                  AND (1 - COALESCE(p.other_cost_rate,0)
                         - COALESCE(erpv.creator_commission_rate, p.default_creator_commission_rate, 0)
                         - COALESCE(spu.return_loss_rate,0)
                         - COALESCE(spu.logistics_damage_rate,0)
                         - COALESCE(ht.current_target_margin_rate,0)) > 0
                 THEN ROUND(erp.default_purchase_cost /
                      (1 - COALESCE(p.other_cost_rate,0)
                           - COALESCE(erpv.creator_commission_rate, p.default_creator_commission_rate, 0)
                           - COALESCE(spu.return_loss_rate,0)
                           - COALESCE(spu.logistics_damage_rate,0)
                           - COALESCE(ht.current_target_margin_rate,0)), 2)
            END,
            CASE WHEN erp.reference_selling_price IS NOT NULL
                 THEN ROUND(erp.reference_selling_price * (1 - COALESCE(ht.current_discount_rate,0)), 2)
            END
        )
    END                                        AS min_selling_price,
    -- 清货回款上限：按当前档位折扣率能收回的现金（参考售价缺失时为 NULL）
    CASE
        WHEN erp.reference_selling_price IS NOT NULL
        THEN ROUND(erp.reference_selling_price * (1 - COALESCE(ht.current_discount_rate,0)) * a.current_qty, 2)
    END                                        AS clearance_recovery_amount
FROM age a
LEFT JOIN turnover t
       ON t.platform_code = a.platform_code AND t.product_sku = a.product_sku
LEFT JOIN hit_tier ht
       ON ht.platform_code = a.platform_code AND ht.product_sku = a.product_sku
CROSS JOIN deepest_policy dp
CROSS JOIN LATERAL (SELECT other_cost_rate, default_creator_commission_rate
                     FROM core.dim_platforms WHERE platform_code = 'tiktok') p
LEFT JOIN erp ON erp.sku_key = a.product_sku
LEFT JOIN erp erpv ON erpv.sku_key = a.product_sku
LEFT JOIN core.bridge_spu_sku b
       ON b.sku_id = erp.sku_id AND b.binding_status='active' AND b.effective_to IS NULL
LEFT JOIN core.dim_spu spu ON spu.spu = b.spu
;
```

> ⚠️ 上面是**结构草图**，`min_selling_price` 那一坨在实现时要按可读性拆成 CTE，并逐条对齐 `backend/services/product_pricing_service.py` 的公式与降级链（分母 ≤ 0 时返回 NULL、缺料时不硬算）。
>
> **更稳的替代方案（推荐）**：如果视图里的价格计算不好维护，改为**视图只出库龄/库存/动销/ERP 关联，价格字段由后端 service 调用 `product_pricing_service` 的纯函数补齐**。这样定价口径只有一处（`compute_sku_pricing`），不会有两处公式漂移。**实施时按 §6 Task 5 的判断二选一。**

### 3.1a 视图性能：实施期实测（2026-10-22）

**这一节是实施期补的，原设计稿没预见到。**

HTTP 层验证时第一次请求 **11 秒**，第二次 15 秒。逐段拆解：

| 环节 | 耗时 |
|---|---|
| `mart.inventory_age_current` | 2 ms |
| `mart.inventory_snapshot_change` | 26 ms |
| `mart.inventory_backlog_base`（含销售 CTE） | **2244 ms** |
| `semantic.fact_orders_atomic` 全量求值 | **20990 ms** |
| 视图明细查询（调整前） | **8867 ms** |

**根因**：`mart.inventory_backlog_base` 的 `sales_30d` 用
`metric_date::date >= CURRENT_DATE - INTERVAL '30 days'` 过滤，`::date` 转换让谓词
**下不进** `semantic.fact_orders_atomic` 的 UNION ALL 分支 → shopee/tiktok 的 2.8 万行订单
全量做去重窗口（`row_number() OVER (PARTITION BY platform_code, shop_id, data_hash ...)`）。

`sql/mart/inventory_*.sql` 在禁改清单里，**不动它**，改我自己的视图：

1. **库存/滞留列**改从 `mart.inventory_snapshot_change` 取（不再经过 `inventory_backlog_base`）。
   `inventory_snapshot_change` 与 `inventory_snapshot_latest` 共用同一个 `company_daily` CTE
   和同一个 `ROW_NUMBER() ... PARTITION BY platform_code, platform_sku, product_sku, warehouse_name
   ORDER BY snapshot_date DESC, ingest_timestamp DESC`，`latest` 取 rn=1、`change` 取 rank=1 值
   → **available_stock / on_hand_stock / inventory_value 完全等价**，代价 48 ms。
2. **销售聚合限定在「有库存的平台」**：
   `platform_code = ANY(ARRAY(SELECT DISTINCT platform_code FROM mart.inventory_age_current))`。
   子查询是 InitPlan → 常量数组 → 谓词能下推到 `fact_orders_atomic` 的 UNION ALL 分支，
   只扫对应平台的事实表。**不改变任何数字**：销售与库存的连接键含 `platform_code`，
   没有库存的平台其销售行本来也匹配不上。

**实测**：视图明细查询 **8867 ms → 44.9 ms**（热 34.3 ms），端点整体 **11 秒 → ~90 ms**。
数字不变性：改造前后全量输出（495 行 × 24 列）CSV 逐格对比 → **0 处差异**。

**顺带修掉一个潜伏口径 bug**：原草图里 `SUM(daily_avg_sales)` 是把 **SKU 级**动销**按仓库行**求和
（`sales_30d` 按 `(platform_code, platform_sku, product_sku)` 聚合，每个仓库行都带同一份），
同一 SKU 有 N 个仓库就放大 N 倍，`estimated_turnover_days` 会被低估 N 倍。
现在动销在 SKU 级算一次，不再按仓库重复计数。（当前 `daily_avg_sales` 全为 0，
今天看不出来，**等订单数据接上就会显形**。）

**回归门禁**：`backend/tests/data_pipeline/test_sku_clearance_ranking.py` 加 3 条视图 SQL 静态断言 ——
不得引用 `mart.inventory_backlog_base`、销售必须限定平台、定价公式不得写进 SQL。

### 3.2 字段契约

| 字段 | 类型 | 业务含义 |
|---|---|---|
| `snapshot_date` | date | 这批滞销数据基于哪天的快照 |
| `platform_code` | text | 平台（目前只有 `miaoshou` 有数据） |
| `product_sku` | text | **ERP SKU 编码**（join `core.dim_erp_sku.sku_key` 的键） |
| `sku_key` | text | 快照侧主键 |
| `product_name` | text | 商品名（优先 ERP 主数据名，回落快照里的名字） |
| `current_qty` | bigint | 可用库存 |
| `on_hand_qty` | bigint | 在库库存 |
| `inventory_value` | numeric | **库存金额**（清货优先级的第一权重） |
| `warehouse_count` | int | 占几个仓 |
| `age_anchor_date` | date | **这批货从哪天开始压** |
| `age_days` | int | **压了多少天**（主口径） |
| `age_bucket` | text | 库龄档位 `0-30`/`31-60`/`61-90`/`91-180`/`180+` |
| `reset_reason` | text | **为什么重置**：`first_positive`/`stock_increase`/`reappeared_after_zero`/`zero_stock`/`continued` |
| `estimated_turnover_days` | numeric | 预计周转天数（动销速度，辅助） |
| `daily_avg_sales` | numeric | 近 30 天日均销量 |
| `is_stagnant` | bool | 最近两帧库存是否没动 |
| `estimated_stagnant_days` | int | 最近两帧间隔（辅助，不参与主判定） |
| `stagnant_snapshot_count` | int | 连续未动的快照次数 |
| `risk_level` | text | `high`/`medium`/`low`（按 `age_days` 判定，见 §3.3） |
| `clearance_priority_score` | numeric | **清货优先级**（库存金额×0.5 + 库龄×10 + 周转天数×2） |
| `sku_id` | int | ERP 主键（能匹配上时） |
| `default_purchase_cost` | numeric | 采购成本 |
| `reference_selling_price` | numeric | 参考售价（**99.8% 为 NULL**） |
| `min_selling_price_override` | numeric | 人工覆盖的最低售价 |
| `pricing_tier_label` | text | 命中的定价档位名（日常/滞销30天/…） |
| `current_discount_rate` | numeric | **当前可优惠折扣率**（随库龄变） |
| `current_target_margin_rate` | numeric | 当前档的目标利润率 |
| `clearance_max_discount_rate` | numeric | 滞销可优惠折扣率（最深档，恒 30%） |
| `min_selling_price` | numeric | **最低售价** |
| `clearance_recovery_amount` | numeric | **按当前档折扣率清货的现金回款上限**（参考售价缺失时 NULL） |

### 3.3 风险等级判定（改用库龄）

| 等级 | 条件 | 业务含义 |
|---|---|---|
| `high` | `age_days >= 180` 或 `stagnant_snapshot_count >= 3` | 压了半年以上，必须处理 |
| `medium` | `age_days >= 90` 或 `stagnant_snapshot_count >= 2` | 压了三个月，考虑处理 |
| `low` | 其他 | 正常周转 |

> 与既有店铺级口径的差异：店铺级用 `estimated_stagnant_days`（≤ 采样间隔）比 30/60/90，SKU 级用**真库龄**比 90/180。
> 阈值档位（90/180）与定价档位（90/120）对齐，保证「滞销清单里标 high 的，在商品中心也一定不按日常档打折」。

### 3.4 后端服务与端点

**服务方法**（`backend/services/postgresql_dashboard_service.py`）：

```python
async def get_sku_clearance_ranking(
    self,
    *,
    min_age_days: int = 60,
    max_age_days: int | None = None,
    risk_level: str | None = None,
    platform_code: str | None = None,
    keyword: str | None = None,
    sort_by: str = "clearance_priority_score",
    sort_order: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]
```

返回：

```json
{
  "summary": {
    "sku_count": 118,
    "total_quantity": 8420,
    "total_inventory_value": 412300.00,
    "by_risk_level": {"high": 12, "medium": 34, "low": 72},
    "by_age_bucket": {"31-60": 20, "61-90": 45, "91-180": 38, "180+": 15},
    "missing_reference_price_count": 116
  },
  "items": [ /* 见 §3.2 */ ],
  "total": 118,
  "limit": 100,
  "offset": 0
}
```

> `missing_reference_price_count` 是**故意的**：它把「参考售价没补齐」这个主数据缺口直接暴露在业务界面上，运营一眼知道哪些滞销品算不出清货回款。

**端点**（`backend/domains/business/routers/inventory_domain.py`，与既有 `/inventory/aging` 同域）：

```
GET /api/inventory/clearance-ranking
  ?min_age_days=60
  &max_age_days=
  &risk_level=high
  &platform_code=
  &keyword=
  &sort_by=clearance_priority_score
  &sort_order=desc
  &limit=100
  &offset=0
```

**只读端点，不需要权限门**（与既有 `/inventory/aging` 一致）。

**Pydantic 契约**放 `backend/schemas/inventory_domain.py`（不在 router 里内联）。

### 3.5 前端

**位置**：`frontend/src/domains/business/views/inventory/InventoryAging.vue` —— 库龄看板页内加一个「**滞销清单**」页签。

理由：库龄和滞销清单是同一份数据的两个视角（一个按档位看总量，一个按 SKU 看明细），放一起比放进业务概览更合理；而且这一页已经有 `inventoryDomainApi` 的调用与 echarts 图表，扩展成本最低。

**API 封装**：`frontend/src/api/inventoryDomain.js` 加

```js
async getClearanceRanking(params = {}) {
  return await api._get('/inventory/clearance-ranking', { params })
}
```

**页面结构：**

| 区域 | 内容 |
|---|---|
| 汇总卡 | 滞销 SKU 数 / 压资金额 / 在库数量 / 高风险数 |
| 风险分布条 | high / medium / low 的 SKU 数与金额 |
| 档位分布 | 按 `age_bucket` 的 SKU 数与金额 |
| 明细表 | 见下 |
| 数据缺口提示 | 「N 个 SKU 缺参考售价，无法计算清货回款」 |

**明细表列：**

| 列 | 字段 | 宽度 |
|---|---|---|
| 优先级 | `clearance_priority_score` | 90 |
| SKU | `product_sku` | 150 |
| 商品名 | `product_name` | 220 |
| 库龄 | `age_days`（带 `age_bucket` 标签） | 140 |
| 起算日 | `age_anchor_date` | 110 |
| 重置原因 | `reset_reason`（中文化） | 110 |
| 可用库存 | `current_qty` | 100 |
| 库存金额 | `inventory_value` | 120 |
| 周转天数 | `estimated_turnover_days` | 100 |
| 日均销量 | `daily_avg_sales` | 100 |
| 风险 | `risk_level`（标签） | 90 |
| 档位 | `pricing_tier_label` | 110 |
| 当前可优惠 | `current_discount_rate` | 110 |
| 最低售价 | `min_selling_price` | 110 |
| 清货回款 | `clearance_recovery_amount`（NULL 显示「缺参考售价」） | 130 |

**筛选**：库龄下限（默认 60 天）、风险等级、平台、关键词（SKU/商品名）、排序（优先级/库龄/金额/周转天数）。

### 3.6 命中不到 ERP 主数据的 SKU

`product_sku` → `dim_erp_sku.sku_key` 命中率实测 99.64%（4 个新品族匹配不上）。

**处置：清单里照常显示**（库龄、库存、金额都在），但定价字段（档位、折扣率、最低售价）留空并标「未匹配主数据」。**不隐藏这些行** —— 滞销清单漏掉新品恰恰是最要命的。

---

## 4. 数据前提

**本 spec 依赖库龄管道先修好。** 管道未通时：

- `mart.inventory_age_current` 是空的 → 视图返回 0 行 → 端点返回空清单（**不是报错**）
- 前端显示「暂无滞销数据」

这不是缺陷，是数据还没到。实施顺序见 §6。

---

## 5. 验收标准

| # | 断言 | 方式 |
|---|---|---|
| 1 | 视图可创建 | `sql/api_modules/sku_clearance_ranking_module.sql` 执行无错 |
| 2 | 管道通后有数据 | `SELECT count(*) FROM api.sku_clearance_ranking_module` > 0 |
| 3 | 一行一个 SKU | `SELECT count(DISTINCT product_sku) = count(*)` |
| 4 | 库龄主口径正确 | 抽样核对 `age_days` = `snapshot_date - age_anchor_date`（无补货的 SKU） |
| 5 | 档位与定价一致 | 抽样 SKU 的 `pricing_tier_label` / `current_discount_rate` / `min_selling_price` 与商品中心 `GET /api/skus` 返回的同 SKU **完全一致**（这是硬性一致性要求） |
| 6 | 风险等级符合规则 | `age_days >= 180` 的行 `risk_level` 必须是 `high` |
| 7 | 端点可用 | `GET /api/inventory/clearance-ranking?min_age_days=60` 返回 200 + 结构完整 |
| 8 | 筛选生效 | `risk_level=high` 只返回 high；`min_age_days=120` 排除 age_days < 120 |
| 9 | 未匹配主数据的 SKU 仍在清单里 | 用 `HJJ-XH-CTD01` 验证：出现在结果中，定价字段为空 |
| 10 | 缺参考售价可见 | `summary.missing_reference_price_count` > 0，且明细里对应行 `clearance_recovery_amount` 为 NULL |
| 11 | 既有店铺级排名未回归 | `GET /api/dashboard/clearance-ranking` 返回结构与行数不变 |
| 12 | 库龄看板页正常 | `InventoryAging.vue` 原有页签功能不变 |

---

## 6. 实施顺序（与库龄管道 spec 的关系）

| Task | 内容 | 依赖 |
|---|---|---|
| 1 | 库龄管道修复（模板 v3 → 清废文件 → 放行 2764 → 开调度 → 端到端验收） | — |
| 2 | **等待第二帧快照落地**（第二次采集） | Task 1 |
| 3 | 建 `api.sku_clearance_ranking_module` 视图 | Task 1（可与 Task 2 并行开发） |
| 4 | 后端 service + 端点 + Pydantic 契约 + 单测 | Task 3 |
| 5 | **口径二选一决策**：价格字段放视图里，还是放 service 里调 `product_pricing_service` | Task 4 前定 |
| 6 | 前端 API 封装 + 滞销清单页签 | Task 4 |
| 7 | 一致性验证（验收项 5） | Task 6 |

> **Task 5 的决策建议：优先「价格字段放 service」**（视图只出库龄/库存/动销/ERP 关联）。
> 理由：定价公式已经在 `backend/services/product_pricing_service.py` 里是**纯函数 + 单测覆盖**，
> 在 SQL 视图里重写一遍等于制造第二份口径，必然随规则表演进而漂移。视图里算出来的 `min_selling_price`
> 与商品中心不一致，是最容易在评审时被忽略、但在业务上最伤的一种 bug。

---

## 7. 明确不做的事

| 不做 | 原因 |
|---|---|
| 不改 `api.clearance_ranking_module`（店铺级） | 业务概览页在用；口径问题是它自己的事，本次只记录不改（见 §2） |
| 不改 `mart.inventory_backlog_base` / `inventory_snapshot_change` | 视图层定义是对的，够用；`estimated_stagnant_days` 的采样间隔特性作为已知事实记录 |
| 不做「滞销天数阈值筛选」在既有店铺级接口上生效 | 那个接口的 `min_days` 参数目前是**空转的**（`postgresql_dashboard_service.get_clearance_ranking` 把它放进 params 但 where 子句没用）—— 属 `docs/API_CONTRACTS_TASK_COMPLETION_STATUS.md` 的「⏳ 10.2.1 待实现」，本次不碰。**但本 spec 的新端点 `min_age_days` 必须真的生效**（验收项 8） |
| 不做清货执行动作（改价、下架、创建清货单） | 本 spec 只出清单和决策依据，执行动作另开任务 |
| 不做「滞销预警推送」 | 需要通知渠道设计，另开任务 |
| 不补参考售价 | 主数据录入工作，另开任务；但本清单会把缺口显式暴露出来 |

---

## 8. 风险与未知项

| 风险 | 说明 | 应对 |
|---|---|---|
| **价格口径在视图与 service 之间漂移** | 视图里重写定价公式 = 第二份口径 | §6 Task 5 建议放 service；验收项 5 做跨接口一致性比对 |
| **视图性能** | `api.sku_clearance_ranking_module` 跨 `mart` / `core` / `finance` 四层 join，且 `mart.inventory_backlog_base` 本身含 30 天订单聚合 | ✅ **已处理（2026-10-22）**：实测 8867ms → 44.9ms，详见 §3.1a；并加了单测门禁禁止退回慢路径 |
| **单帧阶段清单没意义** | 只有一帧快照时 `age_days` 全 0，`min_age_days=60` 会返回空 | 端点不报错，返回空清单 + `summary` 里说明快照数；等第二帧 |
| **`estimated_stagnant_days` 随采集变密而变小** | §2 | 已明确不参与主判定 |
| **清货回款几乎全为 NULL** | `reference_selling_price` 填充率 0.2% | 已知；用 `missing_reference_price_count` 显式暴露，把补料优先级可视化 |
| 妙手 SKU 编码与 ERP 主编码格式差异 | 实测 4 个新品族匹配不上 | 清单照常显示，定价字段留空；主数据补齐另开任务 |
| Shopee / TikTok 无库存采集 | 两张 b_class 表永久 0 行 | 本清单目前只覆盖妙手；交付说明写明 |

---

## 9. 参考文档

| 文档 | 用途 |
|---|---|
| `docs/superpowers/specs/2026-10-21-inventory-aging-pipeline-recovery-design.md` | **上游**：库龄管道恢复（本 spec 的数据前提） |
| `docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md` | 定价底线设计（档位口径、最低售价公式） |
| `docs/superpowers/specs/2026-04-09-snapshot-continuous-inventory-aging-design.md` | 快照连续库龄主设计 |
| `sql/mart/inventory_age_current.sql` | 库龄表结构 |
| `sql/mart/inventory_backlog_base.sql` | 滞销底座（动销口径来源） |
| `sql/mart/inventory_snapshot_change.sql` | 最近两帧对比（`estimated_stagnant_days` 出处） |
| `sql/api_modules/clearance_ranking_module.sql` | 既有店铺级滞销读模型 |
| `backend/services/product_pricing_service.py` | 定价纯函数（最低售价公式唯一来源） |
| `backend/domains/business/routers/product_center.py:2165` | 规则表「当前行」谓词定义 |
| `backend/domains/business/routers/inventory_domain.py` | 库存域路由（新端点落点） |
| `frontend/src/domains/business/views/inventory/InventoryAging.vue` | 库龄看板页（新页签落点） |
| `docs/API_CONTRACTS_TASK_COMPLETION_STATUS.md` | 滞销相关 API 完成状态 |
