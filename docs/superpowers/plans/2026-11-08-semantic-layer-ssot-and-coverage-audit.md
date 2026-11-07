# 语义层单一事实源 + 口径建模 + 覆盖率巡检

> 日期：2026-11-08
> 范围：`b_class raw -> semantic -> mart` 链路中的 **products 域**（语义层标准化层）
> 触发：本会话收口时发现 `semantic.fact_products_atomic` 里 shopee 25810 行的标准字段**全部为空**，
> 而看板与接口都正常出数（全是 0），**没有任何告警**。

---

## 0. 结论

问题不是"别名表少了几行"，而是**products 域从未建立过"列 → 标准字段"的语义对齐**，
加上**缺失被 `COALESCE(...,0)` 伪装成业务上的 0**，于是静默失真了半年。

对照组证明机制本身没问题：`semantic.fact_orders_atomic`（shopee 30607 行 / tiktok 5567 行）
的 `product_id / order_id / sales_amount / shop_id` **100% 命中**。

⇒ 修复必须落在 **products 域 + 缺失可见性** 两件事上，不是全局重构。

---

## 1. 实测证据（生产开发库，2026-11-08）

### 1.1 症状

| 视图 | 平台 | 行数 | product_id | sales_amount | order_count | impressions | conversion_rate |
|---|---|---|---|---|---|---|---|
| `semantic.fact_products_atomic` | shopee | 25810 | **NULL 25810** | **0 25810** | **0 25810** | **0 25810** | **0 25810** |
| `semantic.fact_products_atomic` | tiktok | 824 | 824 | 650 为 0 | 650 为 0 | **824 为 0** | **824 为 0** |
| `semantic.fact_orders_atomic`（对照） | shopee / tiktok | 30607 / 5567 | 全命中 | 全命中 | 全命中 | — | — |

`mart.product_day_kpi`：shopee 1 行（全 0）、tiktok 47 行（sales 2602.02）。
该视图只取 `granularity='daily'`，而 shopee 商品数据在 `monthly` ⇒ **看板直接损失有限**，
真正的损失在语义层本身与今后新建的商品维度分析。

### 1.2 「列 → 语义键」有 5 个载体，各自只管一段链路

| # | 载体 | 谁在用 | 对 shopee 真实 45 个表头的命中率 |
|---|---|---|---|
| ① | `semantic.semantic_field_aliases`（DB 表；seed 自 `sql/semantic/semantic_alias_registry.sql`） | **语义视图取数的唯一事实源**（精确匹配） | **0 / 45** |
| ② | `backend/services/semantic_alias_registry.py::BUILTIN_ALIASES` | 模板语义覆盖检查 | 1 / 45 |
| ③ | `backend/services/semantic_field_registry.py`（`SEMANTIC_FIELD_DEFINITIONS` + `DOMAIN_COLUMN_SEMANTIC_OVERRIDES`） | 列名→语义键**推断链路**（含归一化匹配） | 4 / 45 |
| ④ | `backend/services/template_alias_registry.py`（入库前改名归一） | 入库时改表头 | **实际命中 0 条** |
| ⑤ | 模板版本行的 `header_bindings`（用户确认后沉淀为别名） | 模板 → 别名沉淀 | products 域指标列未确认过 |

**漂移已经发生**：DB products 域 47 条 vs Python 50 条，Python 独有
「已付款订单 / 已确认订单 / 已确定订单」三条（`semantic_alias_registry.py:41-43`）。

### 1.3 「口径」不是措辞差异（业务事实，数据为准）

| 对比 | 实测 | 结论 |
|---|---|---|
| 「已下订单」vs「已付款订单」 | 平均差 **5.15%**，最大差 **175.89**（7090 行可比） | **两个业务事实**：下单 vs 完成支付 |
| 「已确定订单」vs「已下订单」 | MYR 差 4.25%、PHP 差 4.10% | 「已确定」≈「已下」的**旧叫法**（平台改版漂移） |

样例（同商品同月）：下单 2,037.40 / 付款 2,004.00；件数 61 vs 60；转化率 1.88% vs 1.71%。

### 1.4 不同币种店铺提供的列集合不同

| currency_code | 行数 | 「已下订单」列有值 | 「已付款订单」列有值 | 「已确定订单」列有值 |
|---|---|---|---|---|
| SGD | 16601 | 7117 | 7117 | 0 |
| MYR | 3136 | 1312 | **0** | 1312 |
| PHP | 6072 | 2838 | **0** | 2838 |

⇒ **MYR/PHP 店铺（9208 行，36%）没有"已付款"口径**，只有"已下单 / 已确定"两套。
这类缺口**只能用 NULL + 告警**表达，**不能拿旧口径冒充**。

### 1.5 入库层其实已经把列标准化了（但只对部分平台）

| 表 | 结构化列 | 有值情况 |
|---|---|---|
| `b_class.fact_shopee_products_monthly` | 69 个（`商品编号`/`商品`/`Current_Item_Status`/`销售额_已付款订单`/`件数_已付款订单`/`转化率_已付款订单`…） | **有值** |
| `b_class.fact_tiktok_products_monthly` | 240 个（`商品_ID`/`商品交易总额`/`成交件数`/`订单数`/`商品曝光次数`/`商品点击量`…） | **基本为空**（`商品_ID`/`订单数` 有值，`商品交易总额`/`成交件数` 空） |
| `b_class.fact_miaoshou_products_*` | **无结构化列**（只有 raw_data） | — |

原因（模板层查证）：

- `core.field_mapping_templates` 里 **只有 published 版本带 `core_fields` / `header_bindings`**，
  所有 archived 版本 `core_len = 0`；
- shopee monthly 25809 行里 **15884 行 `template_id` 为 NULL**（13 个文件，老入库路径不记模板版本）；
- published 模板的 `core_fields` 里 `semantic_key` **全是 null**
  （`{"in_hash": true, "raw_name": "商品编号", "semantic_key": null}`）——
  **core_fields 只定义"行身份字段"，不承载"业务指标 → 标准字段"**。

⇒ 结论：**products 域的业务指标从来没走过"用户确认语义对齐"这条路**，
所以别名表里没有这些列，语义层只能靠猜 ⇒ 猜不中 ⇒ 全 0 ⇒ 被 `COALESCE` 吞掉。

### 1.6 其它两个数据侧事实

- **2026-07 的 10204 行是全空壳行**：所有列（含 `商品编号`）皆空，`raw_data` 为 `{}`。
  这类行**不是解析失败**，是"根本没拿到数据"，必须与解析缺失**区分开**。
- `mart.product_day_kpi` 只取 daily 粒度 ⇒ 修好语义层后**看板数字不会立刻变**，
  受益的是语义层与新建的商品分析。**验收不能按"看板变好"来判。**

---

## 2. 目标架构

### 2.1 业务概念模型（最终版）

```
坐标：平台 × 数据域 × 粒度 × 店铺
   ↓
行身份 = 复合业务键（不是实体身份）        ← 已正确
   ↓
标准字段 = identity / dimension / metric / time / attribute   ← 已正确
   ↓
【新增】口径维度 caliber = placed(已下单) / paid(已付款) / legacy(已确定·已确认旧词)
   ↓
【新增】渠道维度 channel = 商城 / 直播 / 视频 / 商品卡（仅 tiktok 商品域）
   ↓
列名 → 标准字段（× 口径 × 渠道）        ← 本次要建的
```

关键区分：**shopee 的「已下/已付」是口径；tiktok 的「商城/直播/视频/商品卡」是渠道维度。**
两类问题不能混进同一张别名表。

### 2.2 单一事实源（SSOT）落点

| 层 | 事实源 | 派生物 |
|---|---|---|
| 标准字段 + 别名 + 口径沿革 + 平台源列映射 | `backend/services/semantic_field_registry.py`（代码声明式） | ① DB seed ② 推断索引 ③ 覆盖检查输入 ④ PG 侧解析函数的行为定义 |
| 用户裁决（同一列名两个语义键） | `semantic.semantic_field_aliases` 的 `status='conflict'` 行 | — |
| 用户确认过的绑定 | 模板版本行 `header_bindings`（`semantic_review_status='confirmed_semantic'`） | 沉淀进 DB 别名表 |

**要消除的手写副本**：
`BUILTIN_ALIASES`（②）、`sql/semantic/semantic_alias_registry.sql` 的 INSERT 段（①的 seed）、
`template_alias_registry.py`（④，已停在旧口径、命中 0）。

### 2.3 取数策略（两层来源 + 显式缺失）

```
标准字段取值 = 结构化列（有值就用，shopee 命中）
             → raw_data 归一化匹配（tiktok / miaoshou 命中）
             → NULL（不 COALESCE 成 0）
```

归一化规则（Python 与 PG 两侧**同一套**，这是收敛的关键）：
去首尾空白 → 全角标点转半角 → 去末尾币种括号后缀 `(SGD)` → 去末尾 `.N` 序号后缀
（Excel 重名列，tiktok 的 `商品曝光次数.1`）→ 去下划线 → 去必填星号 → 大小写折叠。

**口径沿革**在归一化之后、匹配之前生效：先按沿革表把「已确定订单」折成「已下单」、
「已确认订单」折成「已付款」，再去找标准字段。

---

## 3. 实施阶段

> 每阶段独立提交、独立验收；迁移一律走 `python scripts/run_current_schema_migrations.py`，
> 迁移文件自包含（不 import `backend.*`），已执行迁移不可改。

### 阶段 A · 字典升级（纯代码，无迁移）

- `SEMANTIC_FIELD_DEFINITIONS` 增补口径/渠道元数据；
- 新增 `PLATFORM_CALIBER_HISTORY`（平台口径沿革）；
- 新增 `PLATFORM_SOURCE_COLUMNS`（平台 × 域 × 粒度 → 标准字段 ← 源列名）；
- 新增归一化规则中「`.N` 序号后缀」的处理。

验收：`backend/tests/data_pipeline/test_semantic_translation_guardrails.py` +
新增字典契约测试全绿。

### 阶段 B · 别名单一来源生成器

- 由字典生成 DB seed SQL、推断索引、覆盖检查输入；
- `BUILTIN_ALIASES` 改为**从字典派生**（不再手写）；
- `sql/semantic/semantic_alias_registry.sql` 的 INSERT 段改为生成产物；
- 契约测试锁死"四份不再分叉"。

验收：新增契约测试（DB seed ↔ Python 派生 ↔ 生成器输出 三方一致）。

### 阶段 C · PG 侧解析能力（迁移）

- `semantic.resolve_alias` 扩展为**归一化匹配**（`CREATE OR REPLACE`，保持 OID 以免影响依赖视图）；
- 新增口径沿革折算；
- seed 归一化后的别名形态。

验收：迁移在开发库成功执行；`semantic.fact_orders_atomic` 结果**不变**（回归保护）；
新增测试断言 shopee/tiktok 的 products 命中率提升。

### 阶段 D · products 视图改取数 + NULL 化（迁移）

- 视图按平台分支读取**各自的结构化列**，无则回退 raw_data 归一化匹配；
- 未解析 → **NULL**，不再 `COALESCE(...,0)`；
- 视图末尾追加解析状态列（`CREATE OR REPLACE VIEW` 不允许改已有列位置，只能追加末尾）；
- 物化视图 `fact_products_atomic_mv` 重建。

验收：逐行对账（b_class 结构化列 vs 语义视图）；
shopee/tiktok 的 `product_id` 解析率 > 0；MYR/PHP 的 `sales_amount` 仍为 NULL
且被巡检**点名**（不是被吞掉）。

### 阶段 E · 覆盖率巡检 + 告警（服务层）

- `backend/services/semantic_coverage_audit_service.py`：按 平台 × 粒度 × 标准字段 出解析率；
- **区分"解析缺失"与"空壳行"**（后者不计入解析失败告警）；
- 阈值告警（默认 0.5）。

验收：服务测试全绿；实跑输出能准确点名 shopee/monthly 的缺口与 tiktok 的 impressions 缺口。

### 阶段 F · 渠道维度建模（tiktok 行级拆分）

- 一个商品行按 商城 / 直播 / 视频 / 商品卡 拆成多行，`channel` 作为维度列；
- **前置验证**：tiktok 总计是否等于分渠道之和（实测列全空，需先修 tiktok 取数再验证）。

验收：`fact_products_atomic` 行数上升但 `mart` 汇总口径不变（总计与分渠道不可同时聚合）。

### 阶段 G · 数据侧疑点查证

1. 同一商品跨报表版本疑似重复计数（样例：同商品同月同值出现多行）——需确认行粒度是否为「商品 × 规格」；
2. 2026-07 的 10204 行空壳行——需查采集侧为何写入空行。

---

## 4. 风险与告知

1. **数字会突然出现**：修好后 shopee 商品指标从 0 变真实值。业务方需提前知晓。
2. **口径切换会改变下游数字**：`sales_amount` 取"已付款"后，数值与现在（全 0）不可比，
   也与"已下单"口径不可比。MYR/PHP 店铺将保持 NULL（**不冒充**）。
3. **视图是下游共享资产**：`mart.product_day_kpi` 等消费方会看到 NULL 传播。
4. **物化视图需重建**（数据量 25810 行，迁移里实测 COPY 约 23 秒）。

## 5. 本轮不做（记 V2）

- `semantic.fact_orders_atomic` 等其它域的别名收敛（等 products 域验证通过再推）；
- 渠道维度在 orders / analytics 域的推广；
- 语义层"缺失 → unknown"在 api 层的呈现规范（当前只做到语义层 NULL + 巡检）。
