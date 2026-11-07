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
