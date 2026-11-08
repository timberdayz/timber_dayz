# 语义层列映射单一事实源（SSOT）优化方案 · orders 域落地

> 制定日期：2026-11-08
> 触发事件：Walter 采集 11 月数据后看板 shopee 月粒度 GMV 显示 0，审查发现 **4 份列名清单各自维护、互相漂移**，导致平台成本类字段整体落空、**平台成本被当成 0 ⇒ 利润虚高**。
> 版本目标：v7.16.1（修复批次，不含新功能）
> 关联文档：`docs/superpowers/plans/2026-11-08-semantic-layer-ssot-and-coverage-audit.md`（§17 发布记录）

---

## 0. 一句话结论

**不要再补第 5 份表头清单。** orders 域的列映射要接到 products 域已经跑通的 `semantic.resolve_alias_normalized()` 上，让 `backend/services/semantic_field_registry.py` 成为**唯一事实源**，别名表 / 视图 SQL / 入库归一化 / 巡检全部改成它的派生物。

---

## 1. 现在的问题：4 份清单，各说各话

| # | 清单位置 | 管什么 | 当前状态 |
|---|---|---|---|
| ① | `backend/services/semantic_field_registry.py` → `SEMANTIC_FIELD_DEFINITIONS` | 标准字段定义 + 全局别名 | `paid_amount` 别名只有 `实付金额/paid amount/buyer paid amount`，**没有「买家支付」** |
| ② | 同文件 → `DOMAIN_SEMANTIC_ALIASES["orders"]` | orders 域专用别名 | `paid_amount` 登记了「买家支付/买家支付(rmb)」✔，**但只被契约推断用，从不参与取数** |
| ③ | `sql/semantic/orders_atomic.sql`（第 109–234 行） | **真正取数的地方**：每个字段一串手写 `COALESCE(raw_data->>'表头', ...)` | 写的是旧表头（「仓库操作费」），源表是「仓库操作费(RMB)」⇒ **全部落空** |
| ④ | `backend/services/orders_ingestion_normalizer.py` → `ORDER_LEVEL_AMOUNT_FIELDS` | 多 SKU 时"第二行起清空哪些订单级金额" | 手工维护 40+ 个表头，**与 ③ 又是两份** |

⇒ **products 域已经解决了这个问题**（`products_atomic.sql:81` 用 `semantic.resolve_alias()`），**orders 域没跟上**。

### 1.1 实测证据（开发库，2026-11）

| 现象 | 数据 |
|---|---|
| 费用类字段（仓库操作费 / 运费 / 平台佣金 / 服务费 / 广告成本 …） | **全部 NULL** |
| `platform_total_cost_itemized`（`orders_atomic.sql:636-643`，6 个费用相加，每个都 `COALESCE(...,0)`） | **恒为 0** ⚠️ |
| ⇒ 平台成本被记成 0 | **利润虚高**（比"算不出"更危险） |
| `sales_amount`（源表已无「订单金额/成交金额」这类列） | **恒 0**（NULL 被出口 `COALESCE(...,0)` 打成 0） |
| `paid_amount` / `profit` / `order_original_amount` / `purchase_amount` | ✔ 正确 |
| 币种一致性 | ✔ shopee 629/629 行都有「买家支付(RMB)」，0 行只有原币；tiktok 同 |
| 多 SKU 订单金额 | ✔ 逐行合计 44,284.69 == 按单合计 44,284.69，**虚增 0** |

### 1.2 根因一句话

> **源表把金额列统一加了 `(RMB)` 后缀，而 ③ 里的清单还是旧写法；两边一改一不改，就整体错位了。**

---

## 2. 目标架构（SSOT）

```
        ┌──────────────────────────────────────────────────────────┐
        │  backend/services/semantic_field_registry.py             │
        │  ★ 唯一事实源 ★                                          │
        │   · 标准字段定义（label / kind / domain / caliber）        │
        │   · orders 域真实表头别名（裸名，不带币种后缀）            │
        │   · 标记：order_level_amount / nullable / retired        │
        └───────────┬──────────────┬──────────────┬───────────────┘
                    │              │              │
     ①seed 生成器   │   ②归一化资产 │   ③入库归一化 │   ④巡检
   generate_semantic │ semantic_alias │ ORDER_LEVEL_   │ 巡检服务的
   alias_seed.py     │ _normalize_    │ AMOUNT_FIELDS  │ "应有表头"
        │            │ asset.sql      │ (派生)         │ (派生)
        ▼            ▼              ▼               ▼
 semantic.semantic_  resolve_alias_  fact_orders_    覆盖率巡检
 field_aliases 表    normalized()    atomic.sql      报告
        │            │              │               │
        └────────────┴──────┬───────┘               │
                            ▼                       ▼
                  视图取数 = 唯一入口         解析率 0% 时
                  resolve_alias_normalized    直接列出真实表头候选
```

### 2.1 为什么 `resolve_alias_normalized()` 能治本

`sql/semantic/semantic_alias_normalize_asset.sql` 里的 `semantic.normalize_alias()` 已经实现了：

1. 全角标点 → 半角（`（）` → `()`）
2. **末尾三个字母的币种括号去掉** —— `(SGD)` / `(RMB)` / `(rmb)`
3. 末尾"像币种"的其它括号去掉（含 `元/币/美元/人民币/美金/欧元/日元`）
4. 去必填星号、**去所有空白（含全角空格）**、去下划线
5. 去末尾 `.N` 序号后缀（Excel 重名列）
6. 小写折叠

⇒ **`「仓库操作费(RMB)」归一化后 = `「仓库操作费」`**，`「买家支付(RMB)」` → `「买家支付」`，`「TikTok 平台佣金(RMB)」` → `「tiktok平台佣金」`。

**只要别名表登记"裸名"，源表将来加币种后缀、加空格、改全角，我们都不用改代码。**

---

## 3. 字典要登记什么（orders 域）

> 原则：**只登记"裸名"**（去掉币种后缀后的形式）。归一化匹配会自动覆盖带后缀的变体。

### 3.1 金额与利润（orders 域）

| 标准字段 | 裸表头（登记值） | 对应真实源表列 | 状态 |
|---|---|---|---|
| `paid_amount` | `买家支付` / `买家实付金额` | 「买家支付(RMB)」/「买家实付金额(RMB)」 | ✔ 已有，补 `买家实付金额` |
| `profit` | `利润` | 「利润(RMB)」 | ✔ 已有 |
| `order_original_amount` | `订单原始金额` | 「订单原始金额(RMB)」 | ✔ 已有 |
| `purchase_amount` | `采购成本` | 「采购成本(RMB)」 | ✔ 已有 |
| `sales_amount` | — | 源表无对应列 | **待决策，见 §4.1** |
| `warehouse_operation_fee` | `仓库操作费` | 「仓库操作费(RMB)」 | ❌ 缺 |
| `shipping_fee` | `买家支付运费` / `卖家支付运费` / `运费成本` | 三个真实列 | ❌ 缺（**一列对多个语义键，需决策**） |
| `promotion_fee` | `广告成本` | 「广告成本(RMB)」 | ❌ 缺 |
| `platform_commission` | `联盟佣金` / `Shopee平台佣金` / `TikTok平台佣金` | 三个真实列 | ❌ 缺 |
| `platform_service_fee` | `服务费` | 「服务费(RMB)」 | ❌ 缺 |
| `platform_voucher` | `卖家voucher` / `Shopee voucher` / `Shopee币抵扣` | 三个真实列 | ❌ 缺 |
| `platform_deduction_fee` | `平台扣费` | 源表无（tiktok 有 `平台补偿`/`平台惩罚`） | ⚠️ 待确认 |

### 3.2 身份与维度（orders 域）

| 标准字段 | 裸表头 |
|---|---|
| `order_id` | `订单编号` / `订单号` ✔ 已有 |
| `product_id` | `产品ID` ✔ |
| `platform_sku` | `平台SKU` ✔ |
| `sku_id` | `SKU ID` ✔ |
| `product_sku` | `商品SKU` ✔ |
| `product_name` | `商品名称` ✔ |
| `shop_id` | `店铺` ✔ |
| `order_date` | `下单时间` ✔ |
| `payment_time` | `付款时间` ✔ |
| `order_status` | `订单状态` ✔ |

---

## 4. 需要 Walter 拍板的两个口径决策

### 4.1 `sales_amount` 怎么办？

现状：`sales_amount` 是"销售额（已付款口径）"标签，但源表已无对应列 ⇒ **恒 0**，同时又和 `paid_amount` 抢同一个业务含义。

| 选项 | 说明 | 影响 |
|---|---|---|
| **A（推荐）** | **废掉 `sales_amount`**，只保留 `paid_amount`（买家实付）+ `order_original_amount`（订单原始额） | 语义最干净；`products` 域的 `sales_amount` 不受影响（不同域） |
| B | 把 `sales_amount` 改接「订单原始金额(RMB)」，标签改成"订单原始金额（未减优惠）" | 与 `order_original_amount` 完全重复 |
| C | 保留现状 | 留一个恒 0 的死字段，未来一定有人误用 |

### 4.2 平台成本恒 0 怎么处理？

现状：`platform_total_cost_itemized = COALESCE(运费,0)+COALESCE(推广费,0)+…` ⇒ 费用缺失时**静默记 0**。

| 选项 | 说明 |
|---|---|
| **A（推荐）** | 缺项就整体为 **NULL**（"成本不可知"），由巡检点名；下游按"成本已知/未知"分开处理 |
| B | 保持 0，但加一列 `platform_total_cost_coverage`（已知成本占项数），看板显示"成本仅含 2/6 项" |

> ⚠️ 这条**会改变利润数字**：现在显示的利润是"没有扣平台成本"的虚高值；改成 NULL 后，**利润会变成一个带告警的数**，而不是一个看起来正常的数。这正是我们要的——但要提前告知运营。

---

## 5. 实施阶段（每阶段可独立验证、独立回滚）

### 阶段 1 · 字典扩充（只加不改行为）

- **改**：`backend/services/semantic_field_registry.py`
  - `ORDER_SEMANTIC_ALIASES` 补齐 §3.1 的全部裸表头
  - `SEMANTIC_FIELD_DEFINITIONS` 给 orders 域字段补 `order_level_amount` / `nullable` 标记
- **不改**：任何 SQL、任何视图
- **验收**：`python scripts/generate_semantic_alias_seed.py --check` 通过（字典与资产一致）；现有回归全绿
- **风险**：0（纯数据登记）

### 阶段 2 · orders 视图取数切到别名表（治本）

- **改**：`sql/semantic/orders_atomic.sql`
  - 把 12 个字段的手写 `COALESCE(raw_data->>'...')` 换成
    `semantic.resolve_alias_normalized(raw_data, 'orders', '<standard_field>', platform_code, granularity)`
  - **保留** `raw_data->>'...'` 的精确匹配作为第一优先级（函数内部已按 confidence/source 排序）
- **不改**：`products_atomic.sql`（已是这套）
- **迁移**：`current_schema_20261206_semantic_orders_alias_resolve`
  - 落别名资产 + 重建 `semantic.fact_orders_atomic` 及其物化视图
- **验收**：
  - 费用类字段解析率 **从 0% → >0%**（shopee monthly 6 个费用字段）
  - `platform_total_cost_itemized` 不再恒 0
  - GMV / 订单数**不变**（44,284.69 / 629 不许动）
  - 全量回归零新增失败
- **回滚**：视图是 `CREATE OR REPLACE VIEW`，回滚资产即可

### 阶段 3 · 出口去掉假 0

- **改**：`sql/semantic/orders_atomic.sql` 第 631–643 行
  - `COALESCE(sales_amount, 0)` → `sales_amount`（NULL 就是 NULL）
  - `platform_total_cost_itemized` 的 6 项相加：**缺项时整体 NULL**，并新增 `platform_total_cost_known_items`（已知成本项数 0–6）
- **改**：`sql/semantic/analytics_atomic.sql` 同类问题（曝光/点击等缺失列记 0）
- **必须同步排查下游**：`mart.*_kpi`、`api.business_overview_*`、看板空周期判定（`_is_empty_period_rows` 的 core_keys）—— NULL 变多后"空周期"判定会变，需要回归
- **验收**：
  - 缺失字段显示为 `--` 而不是 `0`
  - 看板在"成本不可知"时给出提示而不是一个虚高利润
  - 订单域巡检告警从 34 条降到 0

### 阶段 4 · 入库归一化派生 + 多 SKU 稳健性

- **改**：`backend/services/orders_ingestion_normalizer.py`
  - `ORDER_LEVEL_AMOUNT_FIELDS` **从字典派生**（`order_level_amount=True` 的标准字段的全部裸表头 + 其带后缀变体），不再手工维护
  - **稳健性**：订单号缺失时**不再继承上一行**（改为该行独立，`__missing_order_id__:<index>`），宁可多算也不要少算
- **验收**：
  - 多 SKU 订单金额虚增仍为 0
  - 构造"订单号缺失"的样本，确认不发生跨单错配
  - 构造"同订单 3 个 SKU"样本，确认只有第 1 行带金额

### 阶段 5 · 巡检改造（让缺失可诊断）

- **改**：`backend/services/semantic_coverage_audit_service.py`
  - 解析率 0% 时，**直接列出该字段的真实表头候选**（从 `raw_data` 的键里找归一化后最接近的 N 个）
  - 输出形如：`platform_commission 解析率 0%，疑似列名未登记；源表实际列名候选：联盟佣金(RMB) / Shopee平台佣金(RMB)`
- **改**：巡检覆盖 orders 域全部费用字段（当前 `ORDERS_STANDARD_FIELDS` 只列了 6 个）
- **验收**：拿当前的数据跑一遍，巡检输出能**直接指出"仓库操作费"vs"仓库操作费(RMB)"这种错位**

### 阶段 6 · 来源治理与可观测（可拆到 v7.17）

- **表名与来源**：`fact_shopee_orders_*` / `fact_tiktok_orders_*` 实际由 miaoshou 采集器写入（已实测 `shop_account_id` 全为 `miaoshou_real_001`）
  - 在采集配置与文档里明确标注"**shopee/tiktok 订单由 miaoshou 采集器提供**"
  - 视图只 UNION 真正在用的表（现在 9 张里 5 张为空）
- **看板状态位**：采集完成 → 语义层就绪之间有 ~70 秒窗口（11-08 实测 12:29:00 → 12:31:03），看板显示"数据更新中 / 上次更新时间"，避免对着 0 猜
- **巡检在采集侧也提示**：shopee 采集配置不含 orders 域时，直接提示"shopee 订单需由 miaoshou 采集器提供"

---

## 6. 迁移链（单向 fail-closed，无 downgrade）

| 迁移 | 内容 |
|---|---|
| `current_schema_20261206_semantic_orders_alias_resolve` | 别名资产（orders 域扩充）+ `semantic.fact_orders_atomic` 重建 + 物化视图重建 + mart 重建 + 出口去 COALESCE + `platform_total_cost_known_items` 新列 |

> 阶段 2 与阶段 3 最终**合并成一条迁移**（20261206）：改的是同一个视图，
> 阶段 3 还新增了列 ⇒ 物化视图必须 drop + 重建，拆开会出现「已切别名但出口
> 仍是假 0」的**半截状态**，而且要重建两次（生产实测单次全量重算 114.6 秒）。
>
> revision id 从 20261204 顺延到 20261206：并行分支先落地了
> `current_schema_20261205_warehouse_name_aliases` ⇒ 本迁移必须接在新 head 之后，
> 否则 `alembic get_heads()` 会返回**两个 head**（部署脚本 fail-closed 拒绝执行）。
> **已执行的迁移不可改** ⇒ 走「新增一条」而不是「改历史」。

> 迁移**自包含**（不 import backend），资产从 `sql/` 读；revision id ≤ 64 字符。

---

## 7. 测试与守护

| 测试 | 断言 |
|---|---|
| `backend/tests/data_pipeline/test_semantic_alias_single_source.py`（扩） | orders 域每条别名都能在字典里找到，反向亦然（**双向**，防止再漂移） |
| `backend/tests/data_pipeline/test_semantic_orders_column_resolution.py`（新） | 真实表头样本（含 `(RMB)`、全角、空格、下划线、`.N`）都能解析到正确标准字段 |
| `backend/tests/data_pipeline/test_semantic_coverage_audit.py`（扩） | 巡检在解析率 0% 时给出真实列名候选 |
| `backend/tests/data_pipeline/test_orders_multi_sku_amount.py`（新） | 多 SKU：虚增 0；订单号缺失不跨单错配 |
| `backend/tests/data_pipeline/test_atomic_materialized_views.py`（扩） | 物化视图体仍是 `SELECT * FROM <plain view>`；费用列不再恒 0 |
| 资产一致性 | `python scripts/generate_semantic_alias_seed.py --check` |

---

## 8. 发布与验收

1. 本地：目标测试 + 全量回归 + **junit 差分零新增失败**
2. 迁移：开发库跑 `scripts/run_current_schema_migrations.py`
3. **口径复核（关键）**：迁移前后对比 shopee/tiktok 2026-11 的
   `GMV / 订单数 / 客单价 / 利润` ⇒ **GMV 与订单数必须一字不变**；利润按预期变化（因为开始扣真实平台成本）
4. 巡检：orders 域告警应从 34 条 → 0 条
5. 发布：`sync_main_mirrors.ps1 -Sync` → tag `v7.16.1` → 部署 → 生产只读复核

---

## 9. 风险与回滚

| 风险 | 概率 | 缓解 |
|---|---|---|
| 归一化匹配把两个不同列误配（如「仓库操作费」vs「仓库操作费补贴」） | 中 | 归一化后发生碰撞时**取字典序最小**并**记录 warning**；阶段 2 先只切费用类字段灰度验证 |
| 去掉 COALESCE 后下游"空周期"判定变化，看板出现新的空态 | 中 | 阶段 3 单独一条迁移；先在开发库跑全量看板接口回归 |
| 利润数字变化被运营误读为"数据出错" | 高 | **提前公告**：现在的利润是没扣平台成本的虚高值，改完才是真实利润；看板加"成本已知项数"提示 |
| 大范围改动影响面超出预期 | 低 | 阶段化、每阶段可回滚；视图 `CREATE OR REPLACE` 可秒回 |

---

## 10. 记入 V2（本次不做）

| # | 事项 | 理由 |
|---|---|---|
| V2-4 | `fact_*_orders_*` 表按采集器重新命名 | 改名涉及迁移与大量查询，收益是"可读性"，风险中等；先在文档与配置里标注来源 |
| V2-5 | 多 SKU 订单的**按行金额分摊** | 现在是"整单金额 + 其余行空"，业务上正确；但"每个 SKU 分摊多少"是另一个需求 |
| V2-6 | `scripts/validate_migrations_fresh_db.py` 空库校验 | 20261116 迁移要求 6 个 TikTok 账号存在；不在 CI 内，不阻断发布 |
| V2-7 | `ingestion_worker.py::_ingest_traffic_store_file` 的 `emit` 闭包死代码 | 2026-01-07 起存在，早于 v7.15.5，非本轮引入 |
