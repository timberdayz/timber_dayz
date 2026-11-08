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

---

## 15. 执行结果（2026-11-08 收口）

本节记录**实测结论**与**落地结果** —— 前面阶段 A~F 的设计在执行中被实测数据
修正过两处关键判断，这里写清楚最终按什么口径落地。

### 15.1 两个被实测推翻的初始判断

| 初始判断 | 实测结论 | 依据 |
| --- | --- | --- |
| `.N` 后缀是 Excel 重名序号，剥掉即可 | **`.N` 是报表「第 N 块」** | tiktok 商品月报 777 行：基础列 `商品曝光次数` == `.1+.2+.3+.4` 成立 **701 行**；`GMV` == `GMV.1+.2+.3` 成立 **684 行** ⇒ `.N` 是子块，不是重名列 |
| 报表是「多区块拼接」，同一商品多行需按区块筛选 | **报表是「商品汇总行 + SKU 明细行」两级结构**；重复的真正来源是**同一份报表被反复采集** | 汇总行 11612 + 明细行 14197 = 25809；汇总行 `已下订单` 数字率 11612/11612，明细行 0/14197；文件内 (shop, period, product) **恰好 1 个汇总行**（4960/4960 组）；汇总行销售额 == 明细行之和（6258 组里 **6217 组 = 99.3%**） |

⇒ 两条修正直接决定了落地口径：**分块列不落标准字段**（落 unknown）、
**同商品按业务身份去重并让汇总行吸收明细行**。

### 15.2 根因与修复对照

| # | 根因 | 修复 | 实测效果 |
| --- | --- | --- | --- |
| 1 | 真实表头带币种后缀（`销售额（已付款订单） (SGD)`），别名表登的是无后缀写法 ⇒ 逐字取键命中 0 | 字典**逐字登记**真实表头（含币种变体） | shopee `sales_amount` 非零行 **0 → 6565**，金额合计 **0.00 → 570046.23**（旧口径，含翻倍） |
| 2 | 视图 `COALESCE(x, 0)` 把「没解析出来」伪装成「业务上真的是 0」 | 去掉 `COALESCE`，解析不出 = NULL | shopee 月报 `sales_amount` **1187 行为 NULL**（MYR/PHP 店铺没有已付款口径）⇒ 不再显示为 0 |
| 3 | 去重按 `data_hash` ⇒ 反复采集一行都去不掉（订单放大 ×2.67） | 改按**业务身份**（平台/店铺/粒度/周期/商品/规格）去重，取最新一份 | shopee 月报行数 **25809 → 3990** |
| 4 | 汇总行与明细行同时计入 ⇒ 销售额翻倍（×5.33） | 汇总行**吸收**明细行（`summary_only` CTE） | 视图内明细行 5294 → 0；金额不再翻倍 |
| 5 | 只保留已付款口径 ⇒ MYR/PHP 店铺（9208 行，36%）的销售额「没有数据」 | 已下单口径**并列**成独立列 | 新增 `sales_amount_placed` / `order_count_placed` 等 4 列，合计 **4063760.93** 可见 |
| 6 | 口径沿革旧词（「已确定订单」）与当前措辞同置信度 ⇒ 同表两列并存时**选谁是随机的** | 旧词置信度降级 **0.900**（由 `PLATFORM_CALIBER_HISTORY` 派生） | 7 条沿革旧词别名自动降级 |

### 15.3 落地形态

* **唯一事实源**：`backend/services/semantic_field_registry.py` 的字典
  （61 个标准字段 + products 域 30 组真实表头别名）。
* **别名表**：`scripts/generate_semantic_alias_seed.py` 由字典派生
  （182 条），`--check` 可比对 `sql/semantic/semantic_alias_registry.sql`。
* **视图**：`sql/semantic/products_atomic.sql`
  （真实表头解析 / NULL 化 / 两套口径并列 / 汇总行去重 / `row_kind` / `parse_status`）。
* **迁移**：
  * `current_schema_20261130_semantic_alias_normalized_resolution`（PG 侧归一化能力，34 条 fail-closed 自检）；
  * `current_schema_20261201_semantic_products_row_kind_caliber`（别名资产 + 视图 + 物化视图 + mart 重建）；
  * `current_schema_20261202_semantic_alias_prune`（别名表事实源收敛：重落资产 + 清理陈旧 builtin 行）。
* **巡检**：`backend/services/semantic_coverage_audit_service.py`
  —— 按「平台 × 粒度」统计每个标准字段的**解析率**，阈值告警；
  空壳行与解析失败严格二分（空壳行不计入解析失败告警）。

### 15.4 口径纪律（不可退让的三条）

1. **口径成对**：已付款与已下单落到**不同**标准字段，实测两者销售额平均差 **5.15%**、最大差 **175.89**。
2. **分块列不落字段**：`.N` 是子块，归一化会让它与基础列同名 ⇒ 命中即失真 ⇒ 落 unknown。
3. **解析不出 ≠ 0**：视图不再 `COALESCE(...,0)`；解析失败落 NULL，`parse_status` 可见。

### 15.5 剩余项（V2，不在本次范围）

| 项 | 现状 | 建议 |
| --- | --- | --- |
| `mart.product_day_kpi` 只取 `daily` 粒度 | shopee 商品数据在 `monthly` ⇒ 看板看不到 shopee 商品 KPI（mart 仅 48 行） | mart 增补 monthly 口径或建商品月 KPI |
| tiktok 渠道维度 | `.N` 分块是渠道子集，但**无法命名**（基础列≈分块之和，直播/视频是另一维度） | 先做列转行 + 显式渠道列（`（直播）`/`（视频）`），`.N` 分块保持 unknown |
| tiktok 转化率 | CTOR 与去重点击成交转化率**分母不同**（615/777 同值，样例 8.57% vs 9.09%） | 已独立成 `click_to_order_rate` / `unique_click_to_order_rate` 两个字段，**不进** `conversion_rate` |
| SKU 明细层 | 本次汇总行吸收了明细行 ⇒ SKU 粒度不进语义视图 | 若要看 SKU 级指标，另建 `fact_product_sku_atomic` |
| 「已确认订单」 | 真实数据里无实测支撑 ⇒ 刻意不折算、不登记 | 保持 unknown |

## 16. 收口（2026-11-08 最后一轮：回归清零 + 事实源收敛）

本轮把**全量回归从 9 failed 收到 0 failed**；收口过程中又挖出一个**事实源漂移**
（别名表认着一套字典里没有的映射），一并收敛。

### 16.1 回归失败的 4 类处置

| # | 失败用例 | 根因 | 处置 | 依据 |
| --- | --- | --- | --- | --- |
| 1 | `test_products_semantic_field_rules_sql` ×4 | 文档口径里的四个裸别名（`revenue` / `qty` / 「订单数量」/ `CVR`）只存在于**旧手写 seed**，字典里没有 ⇒ 派生结果认不出 | 补进字典的 `aliases`（字典是唯一事实源）⇒ seed 自动带上 | seed 由字典派生，`--check` 一致（182 条） |
| 2 | `test_core_fields_guardrails::test_migration_embedded_canonical_keys_match_registry` | 迁移 `20261125` 内嵌的规范键表是**已执行的一次性快照**，注册表之后又加了 20 个标准字段 ⇒ 「两边相等」不再成立 | 守护改成**子集语义**（迁移 ⊆ 注册表）+ 运行期必须认得迁移引用的每个键 | 实测：用当前注册表重新推导存量 `core_fields`，差异**全部**来自 `required` 标志（20261127 之后域级契约把 `order_id` / `metric_date` 标成 required）⇒ 重写存量行等于**新增漂移阻断源** ⇒ 不做 |
| 3 | `test_shop_identity_resolver` ×2 | 去重分区断言写死「按原始键去重」，而 products 已按实测改成**业务身份去重** | 断言改成**按链路声明**（products = 业务身份；services / inventory = 原始键），并显式禁止用解析后的 `shop_id` 去重 | 重复采集 3877/12122 组、订单放大 ×2.67（§15.2 根因 3） |
| 4 | `test_semantic_numeric_guard` ×1 + `test_workbench_template_update_flow` ×1 | ① `leveled` CTE 的 `MAX(CASE…)` 用了 `ELSE 0`；② 阶段 A 给 `item_status` 登记了泛化别名「状态」 | ① 改 `ELSE NULL` 并同步过滤条件 `IS NULL`；② 从字典里删掉「状态」 | 状态类列名一旦被认成语义键就会污染身份推断 |

### 16.2 又挖出的事实源漂移：别名表认着字典里没有的映射

* 表里 195 条 `source='builtin'` 行，字典只认 182 条 ⇒ **13 条陈旧**；
* 原因：seed 只会 INSERT / UPSERT，**不会删除** —— 字典里删掉的别名永远留在表里；
* 后果之一：`item_status` 的「状态」/ `status` 还在表里 ⇒ 状态类列名会被认成语义键；
* 后果之二：其余 11 条是历史手写 seed 留下的英文 / 中文别名，实测在 `raw_data` 里 **0 次出现**，
  且大多与字典别名在归一化后等价（`Sales Amount` ≡ `sales amount`）⇒ 清理不丢能力。

**处置**：

1. 字典吸收两个**无歧义**的旧表头（「商品标题」→ `product_name`、「件数」→ `sales_volume`）；
   有歧义的（`title` / `item_id`）**不吸收** —— 宁可落 unknown，也不猜；
2. seed 段末尾追加**陈旧 builtin 行清理**（由 `scripts/generate_semantic_alias_seed.py` 生成，
   `--check` 一并比对）：只删 `source='builtin'` 且不在当前 seed 里的行；
   `template_confirmed` / `manual` / `conflict` 是**用户确认过的**，谁也不许动；
3. 迁移 `current_schema_20261202_semantic_alias_prune` 落库并自检
   （表里 builtin 行数必须与字典**完全一致**）。

⇒ 迁移后：182 条 builtin（= 字典）+ 28 条 `template_confirmed` = 210 条，**陈旧 0 条**。

### 16.3 本轮最终口径

| 主题 | 口径 |
| --- | --- |
| 事实源 | `backend/services/semantic_field_registry.py`（61 个标准字段；products 域 30 组真实表头） |
| 别名 | 字典派生（`build_domain_alias_records`）⇒ seed ⇒ DB；DB 的 builtin 行必须与字典**完全一致** |
| 解析不出 | = NULL（unknown），不伪装成 0；`parse_status` 可见 |
| 分块列 | `.N` 是报表子块 ⇒ 不落标准字段 |
| 口径 | 已付款 / 已下单 落到不同标准字段；旧词置信度 0.900 |
| 去重 | products 按业务身份（取最新一份）+ 汇总行吸收明细行；services / inventory 保持按原始键 |
| 巡检 | 按「平台 × 粒度」算解析率；空壳行与解析失败严格二分 |

### 16.4 第三层收敛：别名行缺 `normalized_alias`（PG 侧归一化解析看不见新别名）

别名表有两列：`raw_alias`（人能读懂的写法）与 `normalized_alias`（**实际用于匹配**的形态）。
`semantic.resolve_alias_normalized()` 是按 `normalized_alias` 匹配的
（`alias.normalized_alias IS NOT NULL AND normalized_keys ? alias.normalized_alias`）。

实测出的洞：别名 seed 的 INSERT 列清单里**没有** `normalized_alias`
⇒ 字典新增的别名落库时该列是 NULL ⇒ **归一化解析看不见这些行**。
受影响的 6 条：`revenue` / `qty` / `CVR` / 「订单数量」/「商品标题」/「件数」。

**处置**：

1. `scripts/generate_semantic_alias_seed.py`：seed 多带一列 `normalized_alias`，
   `ON CONFLICT` 一并更新（与 B1 资产的 INSERT 列序一致）；
2. B1 归一化资产**由字典重生成**（`scripts/generate_semantic_alias_normalize_asset.py`），
   不再手改 ⇒ 资产里也不再有字典已撤回的「状态」；
3. 迁移 `current_schema_20261203_semantic_alias_normalized_refresh` 落库并自检：
   * products 域 builtin 行数 == 字典派生行数（不多不少）；
   * products 域**没有** `normalized_alias IS NULL` 的行；
   * 字典已撤回的别名（「状态」）确实不在表里。

⇒ 迁移后：products 域 182 条 builtin，全部带归一形态，「状态」0 条。

### 16.5 迁移链（本轮新增三条，单向 fail-closed）

| 迁移 | 作用 |
| --- | --- |
| `current_schema_20261201_semantic_products_row_kind_caliber` | 别名资产 + 新视图 + 物化视图重建 + mart 重建 |
| `current_schema_20261202_semantic_alias_prune` | 落别名资产 + **清理陈旧 builtin 行**（事实源收敛） |
| `current_schema_20261203_semantic_alias_normalized_refresh` | 补齐 `normalized_alias` + 重落归一化资产（函数 + seed） |

三条都不支持 downgrade（降级要么把漂移写回库，要么让表认不出真实表头 —— 两者都是造数）。

### 16.6 巡检实跑结果（阶段 E 验收）

在开发库上实跑 `SemanticCoverageAuditService.audit(domain="products")`：

| 平台 × 粒度 | 行数 | 空壳行 | 解析失败行 | 结果 |
| --- | --- | --- | --- | --- |
| shopee / daily | 1 | 0 | 0 | 全字段 100% |
| shopee / monthly | 3990 | 0 | 0 | 身份/流量字段 100%；已付款口径 4 个字段 **70.25%**（1187 行无已付款口径 = MYR/PHP 店铺） |
| tiktok / daily | 47 | 0 | 0 | `conversion_rate` **0%** ⇒ 告警 |
| tiktok / monthly | 771 | 0 | 0 | `conversion_rate` **0%** ⇒ 告警 |

告警文案（实测）：

```
! tiktok/daily 的 conversion_rate 解析率 0%，疑似语义映射缺失
! tiktok/monthly 的 conversion_rate 解析率 0%，疑似语义映射缺失
```

**与原计划的一处偏差（实测纠正）**：原计划预期「tiktok 的 `impressions` 有缺口」，
实测 `impressions` 已 **100%** —— 字典按真实表头登记后这个缺口已经补上。
tiktok 现在的真实缺口是 **`conversion_rate`**：tiktok 报表里没有「已付款口径转化率」，
它的转化率是 **CTOR 族**（`去重点击成交转化率` / `转化率 (加入购物车率)` …），
已在阶段 A 独立成 `click_to_order_rate` / `unique_click_to_order_rate`，
**刻意不进** `conversion_rate`（两者分母不同，实测样例 8.57% vs 9.09%）。

⇒ 这正是「歧义宁可落 unknown + 报警」要的效果：巡检把 tiktok 缺 `conversion_rate`
这件事**点名**出来，而不是让它悄悄变成 0。


---

## 17. v7.16.0 发布与生产验收（2026-11-08）

### 17.1 发布内容与版本号

版本号取 **v7.16.0**（minor）：v7.15.5 之后累积 44 个提交（含语义层阶段 A~G、
看板自锁修复、口径列等能力变更），加上本次发布收口批次 `b9b4857d`。

| 批次 | 提交 | 内容 |
| --- | --- | --- |
| 阶段 A | `a251ae61` | 字典升级：口径维度 + products 域 30 组真实表头 + 别名派生 |
| 阶段 B1 | `1da9819e` | PG 侧归一化解析能力 + 契约测试 |
| 阶段 A~G 汇总 | `abf56542` | 语义层收口：视图重写 / 别名单一来源 / 覆盖率巡检 / 3 条迁移 |
| 发布收口 | `b9b4857d` | black 格式化 141 文件 + 26 处 lint 修复 + 门禁 4 误报修复 + 契约测试 10 条 |

### 17.2 发布门禁本地预跑（全部通过）

| 门禁 | 脚本 | 结果 |
| --- | --- | --- |
| 1 关键表外键 | `scripts/test_migration_foreign_keys.py` | exit 0 |
| 2 生产迁移契约 | `scripts/verify_production_migration_contracts.py` | exit 0（3 passed，本地 postgres:15 容器） |
| 3 API 契约 | `scripts/validate_api_contracts.py` | exit 0（无 router 改动） |
| 4 前端 API 方法 | `scripts/validate_frontend_api_methods.py` | exit 0（**修掉误报后**） |
| 5 数据库字段 | `scripts/validate_database_fields.py` | exit 0 |
| 6 库存账龄流水线 | 6 个测试文件 | 31 passed |
| 7 远程部署契约 | `scripts/verify_remote_deploy_contracts.py` | exit 0 |

**门禁 4 的误报根因与修法**（本轮唯一改动门禁脚本本身的地方）：
`scripts/validate_frontend_api_methods.py` 用 `r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{'`
提取方法定义，参数列表里出现括号（`api.saveTemplate` 的中文注释
`// [*] 版本级核心字段清单(两级勾选的结果)。`）会让 `[^)]*` 提前截断 ⇒
`api.saveTemplate` 被判「缺失」⇒ 门禁 exit 1 ⇒ 阻断 tag 流水线。

修法三步：① 注释与字符串字面量做**等长掩码**；② 用**括号深度扫描**定位配对右括号；
③ 过滤 JS 关键字（原来 `if`/`for`/`catch`/`delete` 被当成方法名）。

修前 vs 修后（`temp/gate4_method_diff.txt`）：

```
old=277 new=274
only_old=['catch', 'delete', 'for', 'if']   # 关键字误匹配，去掉是对的
only_new=['saveTemplate']                   # 真实方法，补回来了
```

配套契约测试 `backend/tests/test_validate_frontend_api_methods_contract.py`（10 条），
锁定「参数含括号仍能识别」「函数体调用不算方法定义」「字符串里的括号不干扰」
「JS 关键字不计入」。

### 17.3 门禁 4 修好后暴露的一个真 bug（本轮修掉）

修完门禁 4 后全量回归出现 **8 个新增失败**，全部在
`backend/tests/data_pipeline/test_semantic_coverage_audit.py`：

```
semantic_coverage_audit_service.py:376: AttributeError: 'function' object has no attribute 'standard_field'
```

根因：修 ruff F402 时把 `build_coverage_report` 里的循环变量 `field` 改名成 `field_spec`，
**只改了循环头**，循环体里两处 `field.standard_field`（构造 entry 与拼 warning 文案）
没同步 ⇒ 运行时 `field` 落到模块级同名函数上。

已用 AST 定位函数边界后精确修复（`temp/fix_coverage_field_spec.py`），并补了一个
**半应用重命名的通用扫描**（`temp/scan_half_rename.py`：比对 HEAD 与工作区的 AST，
找「旧名被删但仍被 Load 引用」的函数）⇒ 142 个改动文件扫描结果
`NO_HALF_RENAME_SUSPECTS`。

> 教训：变量改名必须**函数级**核对，不能只改循环头；改名后必须跑目标测试，
> 不能只看 lint 是否变绿。

### 17.4 回归证据

| 项 | 值 |
| --- | --- |
| 用例总数 | 4954 passed / 7 skipped / 0 failed（278.7s） |
| junit 差分（基线 `temp/junit_final.xml` vs 本轮 `temp/junit_rel2.xml`） | NEW failures = **0**，FIXED = 0，COMMON = 0 |
| 用例增减 | ADDED 91（新语义层测试 + 门禁契约测试），REMOVED 1（`test_resolved_chains_still_deduplicate_on_source_key` → 改名为 `..._on_declared_partition`） |
| black --check / ruff check | 对本次推送范围 182 个 py 文件全部通过 |

### 17.5 发布与部署链路

```
b9b4857d  →  sync_main_mirrors.ps1 -Sync  →  GitHub main + CNB main 同为 b9b4857d
git tag -a v7.16.0  →  git push origin v7.16.0  →  GitHub + CNB 双远端均收到标签
```

GitHub Actions `Deploy to Production`（run **42407274803**）结论 **success**：

| Job | 结论 |
| --- | --- |
| check-config | success |
| Validate Data Flow (Release Gate) | **success**（7 条门禁全过，含修好的门禁 4） |
| Build and Push Images (Release Tag) | success（backend / backend-full / frontend + CNB 推送） |
| Deploy to Production (Tag Release) | success（`[OK] Deployment completed. Tags: Backend=v7.16.0, Frontend=v7.16.0`） |

### 17.6 生产只读复核（SSH 隧道 + `SET default_transaction_read_only = on`，全程无写入）

| 验收项 | 生产实测 | 结论 |
| --- | --- | --- |
| 容器健康 | backend-api / frontend / nginx / celery-worker / celery-beat / postgres / redis **全部 healthy** | ✅ |
| 镜像 tag | backend 与 frontend 均为 `v7.16.0` | ✅ |
| 后端就绪 | `/healthz/ready` → `{"status":"ready","version":"v7.16.0","checks":{"database":{"status":"connected"},"dashboard":{"status":"ready"}}}` | ✅ |
| nginx `/health` | 同上，version v7.16.0 | ✅ |
| celery 崩溃循环 | 日志无 `VersionMismatch` / Traceback；`celery@… ready` + `Connected to redis://…` | ✅ |
| 迁移版本 | `public.current_schema_alembic_version` = **`current_schema_20261203_semantic_alias_normalized_refresh`** | ✅ |
| 迁移状态 | 部署日志 `migration_status: up_to_date`、`all_tables_exist: true`、`missing_tables: []`、`missing_columns: []` | ✅ |
| Phase 2.7 视图重建 | **成功 39 个，失败 0 个**，自愈重建物化视图 1 个（`semantic.fact_analytics_atomic_mv`），含本轮 `semantic.fact_products_atomic` | ✅ |
| Phase 3a / 3a' 库存重建 | `[OK] Inventory age full rebuild completed` / `[OK] Inventory state full rebuild completed`；`mart.inventory_age_current` 522 行、`mart.inventory_state` **1232 行** | ✅ |
| 别名表完整性 | `semantic.semantic_field_aliases` **182 条**，`normalized_alias` 缺失 **0** | ✅ |
| products 视图 | 6150 行，`parse_status` 全 ok，`row_kind` 全 `product_summary`，`sales_amount_placed` 非空 5326 行 | ✅ |
| 退役权限 | `core.dim_roles.permissions` 中 `finance-reports`/`fx-management`/`fiscal-periods`/`store-management`/`store-analytics` 引用数 = **0** | ✅ |
| 监控存在性 | `ops.data_freshness_log` 51 条**全 success**；`ops.data_lineage_registry` 89 条边 | ✅ |

### 17.7 生产侧巡检实跑（`SemanticCoverageAuditService`，只读）

巡检服务在生产容器内直接跑通，产出解析率与告警：

**products 域**（entries 36，空壳 0，解析失败 0）

| 平台 × 粒度 | 行数 | 告警 |
| --- | --- | --- |
| shopee / daily | 213 | `order_count`/`sales_amount`/`sales_volume`/`conversion_rate` 解析率 36% |
| shopee / monthly | 5113 | 无告警 |
| tiktok / daily | 47 | `conversion_rate` 0% |
| tiktok / monthly | 777 | `conversion_rate` 0% |

**orders 域**（entries 96，空壳 0，解析失败 0）：34 条告警集中在
`warehouse_operation_fee` / `shipping_fee` / `promotion_fee` / `platform_commission` /
`platform_deduction_fee` / `platform_voucher` 的解析率 0%。

口径并列的实测效果（products 视图，已付款 vs 已下单两套口径）：

| 平台 × 粒度 | 总行数 | 已付款口径非空 | 已下单口径非空 |
| --- | --- | --- | --- |
| shopee / daily | 213 | 76 | 213 |
| shopee / monthly | 5113 | 3622 | 5113 |
| tiktok / daily | 47 | 47 | 0 |
| tiktok / monthly | 777 | 777 | 0 |

⇒ shopee 两套口径并存生效；tiktok 天然没有「已下单」口径（0 行），
`conversion_rate` 缺失是 CTOR 族的**设计性缺口**，由巡检点名告警，
符合「歧义宁可落 unknown + 报警，绝不静默猜」。

### 17.8 本轮记入 V2 的遗留（不在本次发版内）

| # | 事项 | 判定依据 |
| --- | --- | --- |
| V2-1 | `scripts/validate_migrations_fresh_db.py` 在**空库**上仍失败 | 20261116 迁移要求 6 个 TikTok 账号存在，空库没有；该脚本**不在任何 CI 工作流**里，不阻断 tag 流水线；生产 6/6 账号满足 ⇒ 按 V2 单独处理，且**已执行迁移不可改** |
| V2-2 | `modules/services/ingestion_worker.py::_ingest_traffic_store_file` 的 `def emit` 定义在 for 循环外且仅自调用 ⇒ 其体内逐行写入是死代码 | `blame` 显示来自 2026-01-07 的 `634a90ef`，**早于 v7.15.5**，非本轮引入 ⇒ 本次仅做最小 lint 修复（`nonlocal succeeded_rows`），结构问题单独处理 |
| V2-3 | 语义覆盖率巡检**尚未接入 HTTP 端点** | 本轮交付的是服务层能力（`SemanticCoverageAuditService`），已在生产容器内跑通；要变成常驻监控需要挂 `GET /api/data-pipeline/semantic-coverage` 之类的只读路由 + 前端面板，本轮不做 |

---

## 18. 阶段 6：来源治理 + 看板状态位（2026-11-08）

> 阶段归属：`docs/superpowers/plans/2026-11-08-semantic-column-map-ssot-plan.md` §5 阶段 6
> （来源治理与可观测，方案 §10 明确「本轮**不重命名表**」⇒ 只做标注 + 提示）。
> 本阶段**没有数据库迁移**、没有改视图、没有改既有接口字段语义。

### 18.1 事实：shopee / tiktok 的订单由 **miaoshou 采集器**提供

| 证据 | 结论 |
| --- | --- |
| 2026-11 数据里 `b_class.fact_shopee_orders_*` / `fact_tiktok_orders_*` 的 `shop_account_id` **全为 `miaoshou_real_001`** | 这些表的数据由 miaoshou 采集器写入 |
| `fact_miaoshou_orders_*` 与 shopee/tiktok 的 manual 表在 2026-11 都是 **0 行** | 「按平台各采各的」这个心智模型是错的 |
| 采集落盘 12:24:57 → `semantic.fact_orders_atomic_mv` 12:29:00 → `semantic.fact_orders_monthly_atomic_mv` 12:31:03 | 采集完成 → 语义层就绪之间约 **70 秒**（月粒度约 6 分钟） |

⇒ **表名里的平台前缀 ≠ 采集器**。排查「订单数据没有 / 不对」时要去 **miaoshou 采集侧**看，
而不是去 shopee / tiktok 的采集配置里找 orders 域。

### 18.2 来源标注落点（任务 6.1）

| 落点 | 内容 |
| --- | --- |
| `backend/services/collection_contracts.py` | **代码级 SSOT**：`ORDER_SOURCE_PROVIDER_BY_PLATFORM = {"shopee": "miaoshou", "tiktok": "miaoshou"}` + `get_order_source_provider()` / `build_order_source_note()` / `build_missing_order_source_note()` |
| `backend/services/data_pipeline/order_source_governance.py` | 巡检：`audit_collection_config_order_sources()`（纯函数）+ `collect_collection_order_source_audit()`（读 `core.collection_configs`） |
| `GET /api/collection/config-order-source` | **采集侧**巡检接口（新增，只读）：shopee / tiktok 的采集配置**不含 orders 域**时直接提示「shopee 订单需由 miaoshou 采集器提供」；反过来若配置里**声明了** orders 域，则提示与 miaoshou 采集器**重复采集** |
| `backend/schemas/collection_order_source.py` | 上述接口的响应契约（独立模块 ⇒ 不去动 `backend/schemas/collection.py` 的历史排版债务） |

⚠️ 采集配置是**数据库表**（`core.collection_configs`）⇒ 按方案要求**不改迁移、不改表数据**，
只在代码里登记来源约定并做校验 + 提示。

### 18.3 看板状态位（任务 6.2）

新增**只读**服务 `backend/services/data_pipeline/semantic_readiness_service.py`，
状态位挂在看板 `meta.semantic_readiness`（**新增字段**，既有 `meta.data_status`
的空周期 / 降级语义**完全不变**）：

| 字段 | 含义 |
| --- | --- |
| `status` | `fresh`（语义层已包含最新采集）/ `updating`（采集已完成、语义层未就绪）/ `stale`（超阈值）/ `unknown`（既无采集入库记录也无语义层刷新记录，判不了） |
| `last_ingest_at` | 最新一次采集入库时间（源表 `max(ingest_timestamp)`） |
| `last_semantic_ready_at` | 语义层最近一次**刷新成功**时间 |
| `pending_seconds` / `updating_window_seconds` / `max_age_days` / `business_age_days` / `source_status` | 判定过程的中间量，便于排查 |

判定顺序（先判源数据新旧，再判语义层是否跟上）：

1. 源数据超出新鲜度阈值 ⇒ `stale`（`source_data_exceeds_freshness_threshold`）
2. 既无采集入库记录、又无语义层刷新记录 ⇒ `unknown`
3. 有语义层刷新记录但无采集入库记录 ⇒ `fresh`（没有待处理的采集）
4. `last_semantic_ready_at ≥ last_ingest_at` ⇒ `fresh`
5. 语义层未跟上且等待时长 ≤ 宽容窗口（默认 30 分钟，可用
   `SEMANTIC_READINESS_UPDATING_WINDOW_SECONDS` 覆盖）⇒ `updating`
6. 语义层未跟上且已超窗口 ⇒ `stale`

**复用既有机制（不另起一套并行状态）**：

- 「语义层什么时候就绪」→ `ops.data_freshness_log.last_succeeded_at`
  （与 `refresh_validation._target_is_fresh_enough` 同一份口径）；
- 「源数据有多旧」→ `source_freshness_service.classify_source_freshness()` +
  `max_age_days_for()`（阈值、链级例外、环境变量覆盖全部继承）；
- 「哪些源表在用」→ 与看板 freshness 侧同一份订单源表清单（9 张）。

暴露面：

- 看板：`meta.semantic_readiness`（`business-overview/kpi` 与 `business-overview/bootstrap`）；
- 巡检：`GET /api/data-pipeline/semantic-readiness`；
- 前端：`BusinessOverview.vue` 在 `updating` / `stale` 时显示「数据更新中（语义层尚未就绪）」告警
  （**新增**告警，既有 freshness / degraded / identity 三类告警不变）。

### 18.4 本阶段明确不做

| # | 事项 | 理由 |
| --- | --- | --- |
| V2-4（沿用） | 重命名 `fact_*_orders_*` 表 | 方案 §10 已决定：改名涉及迁移与大量查询，收益仅可读性、风险中等 ⇒ 本轮只标注 + 提示 |
| — | 改 `sql/semantic/orders_atomic.sql` 的 UNION 表清单 | 由主会话处理（避免与主会话冲突） |
| — | 改 `backend/services/semantic_coverage_audit_service.py` | 阶段 5 由另一位同事负责；本阶段的采集侧提示落在自己的文件里 |
| — | 数据库迁移 | 采集配置在 `core.collection_configs`（数据库表）⇒ 只做代码标注 + 校验，不改表数据 |

## 19. 阶段 1~5 实施记录（2026-11-08）

本节记录 orders 域「语义层单一事实源（SSOT）+ 覆盖率巡检」六个阶段的**实际落地
结果与验收证据**。方案见 `docs/superpowers/plans/2026-11-08-semantic-column-map-ssot-plan.md`
（提交 `004e1a62`），本节只记「做成了什么 / 怎么证明 / 什么没做」。

### 19.1 实施顺序与两处合并决策

| 阶段 | 交付物 | 状态 |
| --- | --- | --- |
| 1 字典扩充 | `backend/services/semantic_field_registry.py` | 完成 |
| 2 视图取数切别名表 | `sql/semantic/orders_atomic.sql`、`sql/semantic/orders_monthly_atomic_mv.sql`、`scripts/generate_semantic_alias_seed.py` | 完成 |
| 3 出口去假 0 | 同上两个 SQL 资产 | 完成 |
| 4 入库归一化派生 | `backend/services/orders_ingestion_normalizer.py` | 完成 |
| 5 巡检输出真实列名候选 | `backend/services/semantic_coverage_audit_service.py` | 完成 |
| 6 来源治理 + 看板状态位 | 见 §18 | 完成 |

**合并决策 1：阶段 2 + 阶段 3 合并成一条迁移（20261206）。**
两条改的是**同一个视图**，阶段 3 还新增了列 ⇒ 物化视图必须 drop + 重建（REFRESH
会因列集变化报错）。拆开 = 物化视图重建两次（生产实测单次全量重算 114.6 秒），
中间还会出现「已切别名但出口仍是假 0」的**半截状态**。

**合并决策 2：迁移 20261206 同时承担「别名资产落地 + 视图/MV/下游重建」。**
迁移路径唯一：`python scripts/run_current_schema_migrations.py`（fail-closed、无
downgrade）。迁移里 `DROP MATERIALIZED VIEW` **刻意不带 CASCADE**，避免误伤不在
刷新登记表里的对象。

### 19.2 阶段 1 · 字典扩充（SSOT）

`backend/services/semantic_field_registry.py` 是**唯一事实源**，别名表 / 视图 SQL /
入库归一化 / 巡检全部由它派生。

**实测得来的三条硬事实（决定了下面所有设计）**：

1. 源表每个金额列**成对出现**：`X`（原币）与 `X(RMB)`（人民币），均值差 2~3 倍
   （买家支付 240.11 vs 72.03；利润 27.98 vs 11.06；仓库操作费 11.56 vs 4.99；
   订单原始金额 269.53 vs 78.72；卖家支付运费 -40.36 vs -14.13；广告成本 20.51 vs 6.71）
   ⇒ 裸名与 `(RMB)` 是**两个不同的业务事实**，不是同一个字段的两种写法。
2. `normalize_alias("X(RMB)") == normalize_alias("X")` ⇒ orders 域**必须逐字匹配**
   （`semantic.resolve_alias`），禁用 `resolve_alias_normalized`。
3. 平台间同业务不同列名：shopee `买家支付(RMB)` / tiktok `买家实付金额(RMB)`；
   `Shopee平台佣金(RMB)` / `TikTok 平台佣金(RMB)`；`卖家支付运费(RMB)` / `商家运费(RMB)`；
   `订单原始金额(RMB)` / `产品原价(RMB)`。

**落点**：

- `ORDER_SEMANTIC_ALIASES` 重写为真实源表头（**只登 `(RMB)` 变体** + 身份/维度列）；
- 新增 `ORDER_PLATFORM_ALIASES`（结构：平台 → {字段: 别名}），解决「同业务不同列名」；
- 新增 `DOMAIN_PLATFORM_SEMANTIC_ALIASES`、`DOMAIN_CLOSED_ALIAS_DOMAINS`、
  `ORDER_PLATFORM_COST_COMPONENT_FIELDS`、`ORDER_RETIRED_FIELDS`；
- `ORDER_STANDARD_FIELDS` 改为从字典派生（不再手写清单）；
- 新增字段定义：`order_original_amount` / `warehouse_operation_fee` / `shipping_fee` /
  `promotion_fee` / `platform_deduction_fee` / `platform_voucher` / `platform_service_fee` /
  `refund_amount` / `estimated_settlement_amount` / `settled_amount` / `seller_voucher` /
  `order_status` / `product_sku`；`paid_amount` / `profit` / `purchase_amount` /
  `platform_commission` 带 `order_level_amount: True`；`sales_amount` 标记 `retired: True`；
- 新增封闭域逐字索引 `_build_exact_closed_domain_alias_index()`：
  `infer_semantic_key_for_domain` 对 orders 域**只做逐字匹配**，认不出返回 `None`
  （实测 `买家支付(RMB)`→`paid_amount`、`买家支付`→`None`、`利润(RMB)`→`profit`、
  `利润`→`None`）；
- 封闭域分支额外命中**用户人工确认过的全局别名**（域 `*`）—— 「一处生效」是产品
  承诺；但**只取确认过的**部分，builtin 的全局裸名在 orders 域指的是原币列，
  放进来等于静默混币种。

### 19.3 阶段 2 · 视图取数切别名表

- `sql/semantic/orders_atomic.sql`：`mapped` CTE 的取数链**全部**换成
  `semantic.resolve_alias(raw_data, data_domain, '<field>', platform_code, granularity)`
  （22 处）；`sales_amount_raw` 改为 `NULL::text`。
- `sql/semantic/orders_monthly_atomic_mv.sql`：`paid_amount` / `profit` /
  `product_quantity` 三条链换成 `resolve_alias`；raw/mapped/normalized/resolved CTE
  补齐 `data_domain` / `granularity`。
- `backend/services/semantic_alias_registry.py`：`build_domain_alias_records` 支持
  **平台维度**（`platform_code` 入记录）、封闭域不补全局裸名、平台字段不登记通用别名。
- `scripts/generate_semantic_alias_seed.py`：`SEED_COLUMNS` 增 `platform_code`；
  `SEED_DOMAINS = ("products", "orders")`；正则/解析/比对/剪枝全部带平台维度。
- `sql/semantic/semantic_alias_registry.sql` 由生成器产出（**212 条** seed：
  orders 域通用行 + 11 行平台行），并修掉一个潜在缺陷：建表语句原本漏
  `normalized_alias` 列（该列由迁移 20261130 单独 ALTER 出来 ⇒ 空库执行资产会炸），
  现已补进 `CREATE TABLE`。
- 排序规则：`semantic.resolve_alias` 按「平台精确匹配 → 粒度精确匹配 → 置信度 →
  来源 → id」⇒ 平台精确匹配优先于通用行。

### 19.4 阶段 3 · 出口去假 0

硬原则：**歧义宁可落 unknown + 报警，绝不静默猜**。

- `sales_amount` **废止**（保留列、恒 NULL）：源表没有「销售额/成交金额」这一列，
  以前命中的是 tiktok 的「总收入」（原币）⇒ 与 `paid_amount` 抢同一个业务含义、
  币种还不对。
- `paid_amount` / `profit` / `product_quantity` / `buyer_count` 去掉 `COALESCE(..., 0)`
  —— 缺项就是 NULL（「不知道」），由下游判断完整度。
- 新增末尾列 `platform_total_cost_known_items`（0..6，统计 6 个成本项里非空个数）；
  `platform_total_cost_itemized` 保持「**已知项之和**」。

> 为什么不把 `platform_total_cost_itemized` 改成「6 项全齐才给值」：那样所有行恒
> NULL ⇒ 指标作废。方案 §4.2 的选项 B（已知项之和 + 完整度列）既能算、又不撒谎。

### 19.5 阶段 4 · 入库归一化派生

- `ORDER_LEVEL_AMOUNT_FIELDS` 改为**从字典派生**（159 项），不再手工维护 40+ 个
  表头 —— 字典加字段时清单自动跟随（这正是 SSOT 的价值）。
- 订单号缺失的行**不再继承上一行**：改为该行独立成行，占位符
  `__missing_order_id__:<行号>`。继承会同时造成「跨单错配」与「少算」两个错误；
  现在是**宁可多算也不错配/不少算**。
- 派生口径由**实测裁决**（多行订单内取值形态：`head_only` = 源表合并单元格 =
  订单级；`repeat_same` / `vary` = 行级）：
  `买家支付(RMB)` / `订单原始金额(RMB)` / `服务费(RMB)` / `Shopee平台佣金(RMB)` 等
  为**订单级**；`销售数量` / `采购成本(RMB)` / tiktok `产品原价(RMB)` 为**行级**
  ⇒ 刻意**不清空**。
- 量化影响（**仅对新入库数据生效**，存量需重跑入库）：
  `Shopee平台佣金(RMB)` 303,398.64 → 229,672.83（-24.3%）；
  `服务费(RMB)` 73,781.88 → 54,495.81（-26.1%）；
  `Shopee voucher(RMB)` 152,459.34 → 114,895.89（-24.6%）；
  `卖家voucher(RMB)` 49,740.41 → 35,600.47（-28.4%）；
  `预估回款金额(RMB)` 445,793.41 → 423,098.87（-5.1%，旧清单误写成「预计回款金额」
  = 错字，从未生效）。

### 19.6 阶段 5 · 巡检输出真实列名候选

- orders 域解析率改走 `semantic.resolve_alias`（**与视图同路径**，不再另算一套）；
- 解析率 0% 时输出**源表真实列名候选**（保留原始列名，含 `(RMB)` 后缀、全角括号、
  `.1` 分块后缀），排序确定性（相似度 + 原始列名）；
- orders 域字段集合从字典 `ORDER_STANDARD_FIELDS` 派生，products 域从
  `DOMAIN_SEMANTIC_ALIASES["products"]` 派生（排除项逐条注明原因）；
- 新增**平台维度诊断**（`SemanticCoverageReport.platforms`），例如
  「shopee 平台有 2/26 个标准字段在所有粒度下都解析不出来」。

### 19.7 开发库实跑与口径复核（硬验收）

迁移 `current_schema_20261206_semantic_orders_alias_resolve` 在开发库**实跑成功**
（`[OK] Current-schema migration action completed: upgrade`）。物化视图重建耗时：
订单 MV + 索引 + 月度 MV **55.7 秒**（本机；生产实测单次 114.6 秒）⇒ 迁移全程临时
把 `statement_timeout` 抬到 30 分钟。

**口径复核（迁移后，一字未变）**：

| 口径 | shopee | tiktok |
| --- | --- | --- |
| `mart.platform_month_kpi` 2026-11 GMV | **44,284.69** | 9,811.54 |
| `mart.platform_month_kpi` 2026-11 订单数 | **629** | 138 |
| `mart.platform_month_kpi` 2026-11 利润 | 11,520.99 | 3,699.21 |
| `semantic.fact_orders_atomic` monthly SUM(paid_amount) | 1,993,149.50（29,629 行） | 402,284.04（5,254 行） |
| `semantic.fact_orders_atomic` monthly SUM(profit) | 285,493.11 | 63,322.64 |

**按预期变化（口径修正，非回归）**：

| 口径 | 迁移前 | 迁移后 | 说明 |
| --- | --- | --- | --- |
| shopee `platform_total_cost_itemized` | 631,035.08 | **219,325.13** | 旧链命中的是**原币**服务费；按 `(RMB)` 重算才是人民币口径 |
| tiktok `platform_total_cost_itemized` | -19,810.77 | **-6,479.59** | 同上 |
| shopee 已知成本项数 | — | 4.36 / 6（均值） | 新列 `platform_total_cost_known_items` |
| tiktok 已知成本项数 | — | 2.40 / 6（均值） | tiktok 无平台代金券/平台服务费/平台扣费列 |

别名资产一致性：`python scripts/generate_semantic_alias_seed.py --check` → **212 条一致**。
开发库别名落地：orders builtin 行 + 模板确认行 active；与人民币口径冲突的模板确认行
（`profit←利润`、`platform_sku←商品SKU`）置为 `disabled`（**保留记录、可审计**）。

### 19.8 数量语义键回退（product_quantity → sales_volume）

实施中发现「订单域的件数列到底叫哪个语义键」在三处口径不一致：

| 位置 | 原值 | 现值 |
| --- | --- | --- |
| `DEFAULT_CONTRACTS["orders"]` | `product_quantity` | **`sales_volume`** |
| 模板确认（weekly） | `销售数量 → sales_volume` | 不变 |
| 历史别名表 | `销售数量 → sales_volume` | 不变 |

⇒ 以**契约 + 模板确认 + 历史别名表**三处一致的 `sales_volume` 为准；视图的**物理
列名** `product_quantity` 保留（视图不能删列），但改从 `sales_volume` 语义键取数 ——
**语义键与物理列名不必同名，语义键才是口径**。字典里 `sales_volume` 的 `domain`
改为 `orders`，并带 `order_level_quantity: True`（只做登记，不参与「第 2+ 行清空」，
因为实测「销售数量」是行级件数）。

### 19.9 本轮补齐的刷新链路依赖（否则部署会炸）

orders 域视图正文改走 `semantic.resolve_alias()` ⇒ **别名资产必须先落地**，否则
建视图报 `function semantic.resolve_alias does not exist`。已在
`backend/services/data_pipeline/refresh_registry.py` 补齐：

- `PIPELINE_DEPENDENCIES`：`semantic.fact_orders_atomic`、
  `semantic.fact_orders_monthly_atomic_mv` 增加 `semantic.alias_registry` 依赖；
- `ASSET_PREREQUISITES`：同两个目标增加 `semantic.alias_registry` 前置。

### 19.10 本轮明确不做（V2 清单）

| # | 事项 | 理由 |
| --- | --- | --- |
| V2-a | `sql/semantic/analytics_atomic.sql` 的同类「假 0」问题 | **不在 orders 域范围**。analytics 域取数仍是手写 COALESCE 链，其 0 多为「确实无流量」的真 0；直接去掉 COALESCE 而不先补 analytics 别名，会让整个流量看板变 NULL 态。⇒ 先补 analytics 域别名，再做出口清理 |
| V2-b | 字典登记缺口：`联盟佣金(RMB)` / `总收入(RMB)` / `回款金额(RMB)` | 实测存在且多为订单级，但字典未登记 ⇒ 不在派生集合。补登属字典语义变更 + 需重生成别名 seed |
| V2-c | `platform_deduction_fee` | 两平台源表都无对应列 ⇒ 该字段恒缺，由巡检点名（不猜值） |
| V2-d | `sql/metabase_models/orders_model.sql` | 仍是手写 COALESCE 链（本轮只守护了它的字段优先级，未改造） |
| V2-e | 巡检 alias 模式性能 | orders 域 alias 模式聚合 26 字段约 92 秒（`resolve_alias` 逐行调用所致）；属口径切换的固有成本，未做 SQL 层优化 |
| V2-f | 重命名 `fact_*_orders_*` 表 | 沿用方案 §10 决策：收益仅可读性、风险中等 |

### 19.11 回归

- 语义子集：`backend/tests/data_pipeline -k "semantic or alias or coverage or atomic_materialized"`
  全绿；新增测试 `test_semantic_orders_column_resolution.py`（54 条）、
  `test_orders_multi_sku_amount.py`（11 条）、`test_semantic_readiness_status.py`（23 条）。
- 既有守护测试同步更新（口径变了，断言必须跟着变，而不是把断言改松）：
  `test_orders_rmb_field_priority_sql.py`（改为守护「只走别名表 + 只登 `(RMB)` 变体」）、
  `test_semantic_coverage_audit.py`（按 alias 模式重写）、`test_semantic_alias_single_source.py`
  （别名表 8 列）、`test_semantic_translation_guardrails.py`（封闭域逐字路径）、
  `test_b_cost_analysis_semantic_sql.py`（新成本口径 + 完整度列）、
  `test_orders_semantic_mapping.py`（真实源表头样本）。
- 全量回归 + junit 失败用例集合差 = **零新增失败**（结论见本次提交记录）。
- `black --check` / `ruff check` 全绿。

### 19.12 实施过程中踩到并修掉的五个坑（都是「口径变了 ⇒ 连带效应」）

这一节记录实施期真实踩到的坑 —— 它们的共同点是：**改一处口径，会在别处
冒出「看起来莫名其妙的回归」**。每一条都给出了根因与修法。

#### 坑 1 · 别名资产的清理段必须拆成两段（否则空库演练炸）

- **现象**：`backend/tests/test_schema_cleanup_rehearsal.py` 与
  `test_dim_shops_public_retirement_rehearsal.py` 报
  `RuntimeError: 别名表与字典不一致: 表里 builtin 行 179 条, 字典派生 0 条`。
- **根因**：迁移 20261202 / 20261203（**已执行**）的 fail-closed 自检把
  「``-- 陈旧 builtin 行清理`` 段里 **3 元组**的个数」当作「字典派生的
  **products 域** builtin 行数」，与表里 `data_domain='products'` 的行数比对。
  而本轮别名资产为了支持**平台维度**，清理段的键从 3 元组
  `(domain, field, alias)` 变成了 4 元组 `(domain, field, alias, platform_code)`
  ⇒ 旧正则数到 0 条。
- **修法（不动已执行迁移）**：清理段拆成两段 ——
  第一段（`-- 陈旧 builtin 行清理`）**只含 products 域、仍是 3 元组**
  （保持已执行迁移依赖的形状）；第二段（`-- 陈旧 builtin 行清理(其它域, 含平台维度)`）
  含 orders 域、**4 元组**（平台限定行是另一条记录，少了 `platform_code` 会误删）。
  两段都在资产里 ⇒ 迁移整份执行资产 ⇒ 其它域的陈旧行照样被清。
  生成器 `scripts/generate_semantic_alias_seed.py` 的 `render_prune_sql()`
  现在按这个口径出两段，`extract_prune_sql()` 一起提取两段做 `--check`。

#### 坑 2 · 封闭域要补「纯 ASCII 别名」通道

- **现象**：模板里的英文列名（`order_no` / `sold_qty` / `buyer_paid` /
  `profit_amount` / `shop_name`）在 orders 域**认不出来**了 ⇒ 契约用例报
  `missing_required_keys` 多出 `order_id`。
- **根因**：封闭域只做**逐字**匹配（这是必须的 —— 否则「利润」会认成
  「利润(RMB)」的原币列），而英文别名在字典里写的是 `order id`（带空格），
  逐字匹配不到 `order_no`。
- **修法**：按域补一份**只收不含中文的别名**的归一化索引
  （`closed_domain_ascii_alias_index()`）：
  - 只收**该域用到的字段** ⇒ 不跨域污染；
  - 只收**不含中文**的别名 ⇒ 中文裸名永远进不来 ⇒ 不会认到原币列。

#### 坑 3 · orders 域的**英文别名**不能丢

- **现象**：同上（英文列名失联）。
- **根因**：阶段 1 重写 `ORDER_SEMANTIC_ALIASES` 时按「只登真实源表头」
  的原则，把**英文别名**一起删了 ⇒ 既有能力回归。
- **修法**：把英文/数字别名补回（`order_id` / `order_no` / `order no` /
  `shop_name` / `sold_qty` / `buyer_paid` / `profit_amount` / `quantity` …）。
  **英文别名没有币种歧义** ⇒ 逐字匹配也安全；
  **中文裸名仍然不登**（那是原币列）。别名 seed 由 212 条变成 230 条。

#### 坑 4 · 状态类字段不能进语义推断（但仍要留在别名表里）

- **现象**：`backend/tests/test_workbench_template_update_flow.py` 报
  `products.订单状态 不该被认成身份键` / `orders.订单状态 不该被认成身份键`。
- **根因**：`order_status` 是阶段 1 新增的 orders 域维度字段，它的别名
  「订单状态」进了**全局**别名表 ⇒ 任何域的「订单状态」列都会被认成语义键
  ⇒ 状态一变就算新行 ⇒ 污染身份推断与去重。
- **修法**：字典里给状态类字段加 `inferable: False`
  （`is_inferable_semantic_key()`）——
  推断侧跳过它（字典索引 + 运行时别名索引都跳），
  但**别名表照旧登记** ⇒ 视图照样能取到订单状态的值。
  两件事口径不同：**别名表是「取数」的事实源，推断是「这列是不是语义键」的判断**。

#### 坑 5 · 别名资产与视图的依赖，**必须写进刷新链路**

- **一度**：怕「每次刷新 orders 域都重跑别名资产」（230 行 upsert + prune），
  于是把 `backend/services/data_pipeline/refresh_registry.py` 改成**零改动**，
  只靠部署时的 fail-closed 迁移（`run_current_schema_migrations.py`）先落
  别名资产 ⇒ 结果在**测试库**里报
  `function semantic.resolve_alias(jsonb, character varying, unknown, ...) does not exist`
  （测试库并没有先跑那条迁移）。
  只靠「部署时先落迁移」⇒ **单刷一个 orders 视图**时别名函数不在库里 ⇒ 建视图失败。
- **最终**：依赖**入链**，两处都声明（缺一不可）：
  - `PIPELINE_DEPENDENCIES`（**刷新顺序**：谁先刷）——
    `semantic.fact_orders_atomic` 与 `semantic.fact_orders_monthly_atomic_mv`
    的依赖里都加上 `semantic.alias_registry`；
  - `ASSET_PREREQUISITES`（**建对象前置**：资产文件必须先跑）—— 同上两个目标，
    保证单独刷新任何一个 orders 视图时，别名表 + `semantic.resolve_alias()`
    一定已经在库里。
- **代价**（已知且接受）：数据刷新时多跑一次**幂等**的别名资产（230 行 upsert
  + prune）。⇒ 两个守护用例的断言从「一个文件都不许执行」改成
  「**只允许**执行别名资产 + **不许**执行物化视图的资产文件」——
  守护强度**不降反升**（多了一条「物化视图绝不重建」的白名单）。

### 19.13 本轮同步到开发库的最终状态

| 对象 | 状态 |
| --- | --- |
| 别名资产 | 230 条（orders 域通用 + 平台行 + 英文别名行）；`generate_semantic_alias_seed.py --check` 一致 |
| 订单视图 / 物化视图 | 已重建并刷新（月度 MV 重建 58.4 秒） |
| `mart.platform_month_kpi` 2026-11 shopee | GMV **44,284.69** / 订单数 **629** / 利润 11,520.99 —— 与改造前**一字未变** |
| `mart.platform_month_kpi` 2026-11 tiktok | GMV 9,811.54 / 138 / 3,699.21 —— 不变 |
| `semantic.fact_orders_atomic` monthly shopee | SUM(paid_amount) 1,993,149.50 / SUM(profit) 285,493.11 / 29,629 行 / 件数 32,415 |
| `semantic.fact_orders_atomic` monthly tiktok | 402,284.04 / 63,322.64 / 5,254 行 / 件数 5,351 |
| 平台成本 | shopee 219,325.13（已知项 4.36/6）；tiktok -6,479.59（2.40/6） |

### 19.14 收尾：别名资产依赖入链 + 守护用例加强式更新 + 迁移接新 head

| 事项 | 处理 |
| --- | --- |
| `refresh_registry.py` 恢复 `semantic.alias_registry` 依赖 | `PIPELINE_DEPENDENCIES` 2 处 + `ASSET_PREREQUISITES` 2 处（含**新增**月度 MV 条目） |
| `test_refresh_runner.py` | 依赖表断言改为**精确列表**（含 `semantic.alias_registry`）；新增「别名资产必须排在 orders 视图**之前**」的顺序断言；新增 `ASSET_PREREQUISITES` 断言；步骤计划期望值更新 |
| `test_refresh_view_skip_and_lock_retry.py` | 物化视图两条用例：断言从 `executed_files == []` 改为「**只允许** `sql/semantic/semantic_alias_registry.sql`」+「**不许**出现月度 MV 的资产文件」 |
| `test_orders_semantic_field_rules_sql.py` | `profit` 别名断言从「只能等于 `("利润(RMB)",)`」改为「**含** `利润(RMB)` + **不含**中文裸名 `利润` + **含** `profit_amount`」 |
| 迁移 revision id | `current_schema_20261204_...` → **`current_schema_20261206_...`**（`down_revision` = `current_schema_20261205_warehouse_name_aliases`）⇒ `alembic get_heads()` **单 head** |

> **迁移为什么改名**：并行分支先把 `current_schema_20261205_warehouse_name_aliases`
> 落地到 main ⇒ 本迁移若仍用 20261204，`alembic get_heads()` 会返回**两个 head**，
> 部署脚本的 fail-closed 校验直接拒绝执行 ⇒ 顺延到 20261206 并把
> `down_revision` 指向新 head。**已执行的迁移不可改**，所以只能「新增一条」
> 而不是「改历史」。
