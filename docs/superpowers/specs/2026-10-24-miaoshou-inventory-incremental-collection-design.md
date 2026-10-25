# 库存数据域增量采集改造设计

> 状态：设计稿（待评审）
> 日期：2026-10-24
> 关联：概念对齐（`output/inventory-incremental-concept.html`）、真实页面取证（`output/inventory-updated-filter-evidence.html`）

---

## 1. 背景与目标

### 1.1 问题

妙手「仓库清单」页当前采集全量库存快照（1113 行 / 56 页）。随着采集频次上升（每隔几天一次），
全量采集带来三方面压力：采集耗时长、入库写入量大、下游 SQL 刷新重。

### 1.2 目标

1. 采集端：支持按「更新时间」维度 + 日期区间做增量采集。
2. 落盘端：从「批次快照堆叠」改为「观测层（只存变动）+ 状态层（永续完整）」双层模型。
3. 使用端：下游取「最新」的排序键从批次级 `metric_date` 改为行级 `observed_at`。

### 1.3 非目标

- 不改订单域采集（miaoshou 订单域从未成功入库，是独立问题）。
- 不改其他平台（shopee / tiktok）的库存域。
- 不做库龄口径修正、周转天数口径修正（另立任务，但本设计为其留出数据基础）。

---

## 2. 已取证的事实基线

### 2.1 真实页面交互契约（2026-10-24 取证）

筛选区字段锚点：`[data-field='dateRangeType-dateRangeValue']`，其内含两个子控件：

| 子控件 | DOM | 说明 |
|---|---|---|
| 维度下拉 | `div.jx-select` | 浮层 `div.jx-select-dropdown.pro-select-popper` → `ul[role=listbox]` → `li[role=option]` |
| 日期区间 | `div.jx-date-editor.jx-date-editor--datetimerange` | 2 个 `input.jx-range-input`（placeholder=开始时间/结束时间） |

维度下拉只有两个选项：`创建时间`、`更新时间`。当前值集中在同一个属性上：

```
div.jx-select[modelvaluegroup="gmtModified,2026-09-04 00:00:00,2026-10-08 23:59:59"]
```

即 **一个字段同时承载「维度码 + 起止时间」**。维度码：更新时间 = `gmtModified`，创建时间 = `gmtCreate`。

日期面板：`div.jx-picker-panel.jx-date-range-picker.has-sidebar.has-time`，
含 5 个快捷项 `button.jx-picker-panel__shortcut`（今天/昨天/近7天/近30天/近90天），
页脚 `button.jx-picker-panel__link-btn` 两个：「清空」（text 样式）、「确定」（plain 样式）。

搜索按钮：`button.jx-button--primary.jx-button--small.pro-button.J_queryFormSearch`（`type=submit`）。

### 2.2 关键行为（实测）

| 行为 | 证据 |
|---|---|
| **必须先切维度** | 01 空态截图显示默认是「创建时间」。不切则日期区间筛的是创建时间，页面照常显示结果、不报错 |
| **必须点「确定」** | 改完 `input.jx-range-input` 的值后 `modelvaluegroup` **不变**；点「确定」后才写入新区间 |
| 维度选错的量级差 | 同一区间 9/4~10/8：按更新时间命中 147 个 SKU，按创建时间只命中 **3** 个 |
| 导出即筛选结果 | 用户 2026-10-24 实测确认：「导出搜索的商品」导出的是点击搜索后确定时间范围内的商品 |

### 2.3 数据侧交叉验证

以 file 3004（1113 行，2026-10-24 采集）回放录制窗口：

| 口径 | 结果 | 对照页面 |
|---|---|---|
| 全量 | 1113 行 / 11109 库存 | 01 空态截图 1112 SKU / 11095（差 1 行 = 采集到录制之间的实时变动） |
| 更新时间 9/4~10/8 | 148 行 / **147 去重 SKU** / 1518 库存 | 04 截图 SKU总数 **147** / 库存总数量 1507 ✓ |
| 创建时间 9/4~10/8 | 3 行 | —— |

行数比去重 SKU 多 1，因存在跨仓 SKU（37 个 SKU 分布在 2 个仓）。

### 2.4 落盘现状事实

| 项 | 现状 |
|---|---|
| `b_class.fact_miaoshou_inventory_snapshot` | 物理表，2339 行（file 2764: 1226 + file 3004: 1113） |
| 平铺列 | `更新时间` / `创建时间` / `更新人员` / `创建人员` 均 1113 全覆盖（非 NULL） |
| `raw_data` | jsonb，含 `更新时间`（text 格式 `2026-10-20 14:57:18`）、`创建时间` 等原始键 |
| `semantic.fact_inventory_snapshot` | **视图，未暴露行级时间列** |
| `mart.inventory_snapshot_latest` | 视图，`ROW_NUMBER() PARTITION BY (platform_code, platform_sku, product_sku, warehouse_name) ORDER BY snapshot_date DESC, ingest_timestamp DESC` |
| `mart.inventory_current` | 视图，同上但分区多一个 `shop_id` |
| `mart.inventory_snapshot_history` | 视图，从 `semantic.fact_inventory_snapshot` 投影 |
| `data_hash` | 每批内行级唯一；**跨批次无重复**（两批 0 冲突） |
| 写入路径 | `backend/services/data_ingestion_service.py` 按 `header_columns` 动态建列；inventory 域表头名原样保留（`normalize_field_name_for_domain` 对 inventory 直接返回原名） |

### 2.5 现有缺陷（增量会放大）

1. **metric_date 批次级错戳**：`metric_date` 来自采集配置的 `custom_date_start`。
   config 27 写 2026-09-01，旧批次 2764 写 2026-09-14 → 09-14 压过 09-01，
   最新批次 1113 行只贡献 **4 行**进 `mart.inventory_snapshot_latest`。
2. **库龄锚点错误**：`mart.inventory_age_current.age_days` 用 `snapshot_date` 作锚，
   实测 max 仅 13 天、`>30 天` 的 SKU 为 0 → 商品中心 56% SKU 走 `fallback_no_age_data` 兜底。
3. **周转天数哨兵值**：`mart.inventory_backlog_base` 的 30 天销量取自 `semantic.fact_orders_atomic`，
   该表 31012 行无 miaoshou 数据 → 499 行 `estimated_turnover_days = 9999`，risk_level 全 high。

---

## 3. 目标架构

### 3.1 三层结构

```
采集层  妙手仓库清单页
         └─ 维度下拉 → 更新时间(gmtModified)
         └─ 日期区间 → [start, end]
         └─ 搜索 → 导出搜索的商品
                    ↓ 导出文件（仅筛选结果，含「更新时间」「创建时间」列）
─────────────────────────────────────────────────────────────
观测层  b_class.fact_miaoshou_inventory_snapshot   （物理表，只增）
         每行 = 一次观测 (SKU × 仓库 @ observed_at)
         observed_at ← raw_data['更新时间']（行级）
         增量下每批只写 N 行
─────────────────────────────────────────────────────────────
状态层  mart.inventory_current                    （视图，upsert 语义）
         每 SKU × 仓库 永续一行
         按 observed_at DESC 取最新观测
─────────────────────────────────────────────────────────────
派生层  mart.inventory_snapshot_change / age_current / age_history / backlog_base
```

### 3.2 核心语义变更

| 概念 | 现状 | 目标 |
|---|---|---|
| 事实粒度 | 一行 = 一次观测（但 metric_date 是批次级） | 一行 = 一次观测，**observed_at 是行级** |
| 「最新」判定 | `snapshot_date DESC, ingest_timestamp DESC` | `observed_at DESC, ingest_timestamp DESC` |
| 状态完整性 | 只有全量批次才完整 | 状态层 upsert，**增量下也永续完整** |
| 库龄锚点 | `snapshot_date`（快照日） | 行级「创建时间」（真实入库时间） |
| 采集窗口 | 全量 | `[水位线, 采集时刻]`，断档超阈值回退全量 |

---

## 4. 采集层设计

### 4.1 新增组件：`miaoshou/inventory_date_filter`

职责：把「维度 + 区间」这个复合控件设置到指定状态，并返回可断言的落地证据。

#### 4.1.1 选择器（全部来自 2026-10-24 实测）

```python
# 字段锚点
DATE_RANGE_FIELD_SELECTOR = "[data-field='dateRangeType-dateRangeValue']"

# 维度下拉
DATE_RANGE_DIM_SELECT = f"{DATE_RANGE_FIELD_SELECTOR} .jx-select"
DATE_RANGE_DIM_WRAPPER = f"{DATE_RANGE_FIELD_SELECTOR} .jx-select__wrapper"
DATE_RANGE_DIM_VALUE_ATTR = "modelvaluegroup"
DATE_RANGE_DIM_OVERLAY = ".jx-select-dropdown:visible"
DATE_RANGE_DIM_OPTION = ".jx-select-dropdown__item"   # role=option

# 维度码（写入 modelvaluegroup 第一段）
DIM_UPDATED_AT = "gmtModified"
DIM_CREATED_AT = "gmtCreate"

# 日期区间
DATE_RANGE_EDITOR = f"{DATE_RANGE_FIELD_SELECTOR} .jx-date-editor--datetimerange"
DATE_RANGE_INPUT = f"{DATE_RANGE_FIELD_SELECTOR} input.jx-range-input"   # [0]=开始 [1]=结束
DATE_RANGE_PANEL = ".jx-picker-panel.jx-date-range-picker:visible"
DATE_RANGE_CONFIRM = ".jx-picker-panel__footer button.jx-picker-panel__link-btn.is-plain"  # 「确定」
DATE_RANGE_CLEAR = ".jx-picker-panel__footer button.jx-picker-panel__link-btn.is-text"    # 「清空」
DATE_RANGE_SHORTCUT = ".jx-picker-panel__shortcut"

# 搜索按钮
SEARCH_BUTTON = "button.J_queryFormSearch"
```

> ⚠️ 「确定」用 `.is-plain` 区分，「清空」是 `.is-text`。两者 class 前缀相同，必须用完整 class 区分，
> 否则会误点「清空」。

#### 4.1.2 执行流程

```
① 打开维度下拉
   click(DATE_RANGE_DIM_WRAPPER)
   wait_visible(DATE_RANGE_DIM_OVERLAY)

② 选「更新时间」
   click(DATE_RANGE_DIM_OVERLAY >> text="更新时间")
   wait_hidden(DATE_RANGE_DIM_OVERLAY)

③ 断言维度已切换
   mvg = get_attribute(DATE_RANGE_DIM_SELECT, "modelvaluegroup")
   assert mvg.startswith("gmtModified")      ← 失败则抛错，不得继续

④ 填起始时间
   click(DATE_RANGE_INPUT >> nth=0)
   wait_visible(DATE_RANGE_PANEL)
   fill / type(DATE_RANGE_INPUT >> nth=0, start_text)

⑤ 填结束时间
   fill / type(DATE_RANGE_INPUT >> nth=1, end_text)

⑥ 点「确定」
   click(DATE_RANGE_CONFIRM)
   wait_hidden(DATE_RANGE_PANEL)

⑦ 断言区间已提交
   mvg = get_attribute(DATE_RANGE_DIM_SELECT, "modelvaluegroup")
   assert start_text in mvg and end_text in mvg   ← 失败则抛错

⑧ 返回落地证据
   { "dimension": "gmtModified", "range_start": ..., "range_end": ... }
```

**每一步都必须断言，不能靠 sleep。** 妙手在这两处都不报错：
- 维度没切 → 静默筛错维度
- 没点确定 → 静默不生效

#### 4.1.3 时间格式

页面接受 `YYYY-MM-DD HH:mm:ss`。建议：
- 起始：`{start_date} 00:00:00`
- 结束：`{end_date} 23:59:59`

与订单域 `date_picker.py` 的 `apply_custom_range` 保持一致，但**必须额外做维度切换**。

### 4.2 组件编排（`inventory_export.py`）

现状流程：`navigation → 仓库全选 → 搜索 → 等结果 → 导出菜单 → 字段全选 → 导出 → 下载`

目标流程：

```
navigation
  → 仓库全选（现有 warehouse_filters，不变）
  → ★ 时间维度 + 区间筛选（新组件）
  → 搜索（_click_search，定位改为 button.J_queryFormSearch 优先）
  → 等结果刷新 + ★ 断言 SKU 总数变化
  → 导出菜单 → 导出搜索的商品 → 字段全选 → 导出 → 下载
```

### 4.3 结果刷新判定

搜索后必须确认筛选真的生效。当前 `_wait_search_results_ready` 只等「SKU总数」「库存总价值」**可见**，
这无法区分「旧结果还在」和「新结果已到」。

改造要求：
1. 搜索**前**记录 SKU 总数的文本值。
2. 点击搜索后，等待该文本**发生变化**（或至少等待网络空闲 + 文本稳定）。
3. 断言新 SKU 总数 > 0（防止筛出空集却静默落库）。

> 录制证据：搜索前 `SKU总数: 1112`，搜索后 `SKU总数: 147`。数字会变，可作为变化信号。

---

## 5. 落盘层设计

### 5.1 观测层：暴露行级 `observed_at`

`semantic.fact_inventory_snapshot` 视图新增一列 `observed_at`，取值优先级：

```sql
COALESCE(
    NULLIF(raw_data->>'更新时间', '')::timestamptz,   -- 妙手：行最后修改时间
    NULLIF(raw_data->>'创建时间', '')::timestamptz,   -- 兜底：行创建时间
    metric_date::timestamptz                         -- 兜底：批次日
) AS observed_at
```

同时新增 `created_at`（行级创建时间），供库龄使用：

```sql
NULLIF(raw_data->>'创建时间', '')::timestamptz AS created_at
```

> 兼容性：shopee / tiktok 的库存导出没有「更新时间」列，COALESCE 会落到 `metric_date`，
> 行为与现在完全一致，**不改变这两个平台的任何结论**。

> 存储位置：平铺列 `更新时间` / `创建时间` 已经存在且 100% 覆盖，**不需要新增物理列**。
> 只需在语义层把它们投影出来。

### 5.2 状态层：`mart.inventory_current` 改排序键

```sql
ROW_NUMBER() OVER (
    PARTITION BY platform_code, COALESCE(shop_id,''), COALESCE(platform_sku,''),
                 COALESCE(product_sku,''), COALESCE(warehouse_name,'')
    ORDER BY observed_at DESC NULLS LAST, ingest_timestamp DESC
) AS rn
```

对比现状（`ORDER BY metric_date DESC, ingest_timestamp DESC`）的实测差异：

| 排序键 | 最新批次(3004) 贡献 | 旧批次(2764) 贡献 |
|---|---|---|
| `metric_date`（现状） | **4 行** | 1226 行 |
| `observed_at`（目标） | **469 行** | 761 行 |

### 5.3 `mart.inventory_snapshot_latest` 改排序键

同样改为 `observed_at DESC NULLS LAST, ingest_timestamp DESC`。
分区键不变（`(platform_code, platform_sku, product_sku, warehouse_name)`）。

### 5.4 历史数据回填

现有 2339 行（两批）**不需要重采**：

1. `observed_at` 从 `raw_data->>'更新时间'` 直接算出（两批 100% 有值）。
2. 按新排序键重算 `mart.inventory_snapshot_latest` / `inventory_current` → 得到正确的当前状态。
3. 错戳的 `metric_date`（2764 = 2026-09-14、3004 = 2026-09-01）**保留原值**，
   它在新模型里只作为兜底排序键，不再是主键。

> 是否要订正历史 `metric_date`（即 P0-2 那件事）？**建议不订正**。
> 新模型下 `metric_date` 只表示「这批采集的配置区间」，错戳不再产生正确性影响；
> 订正历史值反而会丢失「当时配置是什么」的可追溯性。若仍要订正，需单独评估。

### 5.5 `mart.inventory_snapshot_history` 的定位调整

它现在是「每批次每 SKU 一行」的视图。增量后语义变成「每次观测一行」，行数会随增量批次线性增长。
这正是观测层应有的行为，**不需要改结构**。

### 5.6 B2 落盘层 · 已落地实现与实测（2026-10-24 晚间）

#### 5.6.1 改了什么

| 层 | 改动 |
|---|---|
| `semantic.fact_inventory_snapshot` | 新增 **6 列**：`observed_at`（行级最后修改时间）、`created_at`（记录创建时间）、`checklist_sales_7d/30d/60d/90d`（妙手滚动销量窗口） |
| `mart.inventory_snapshot_history` | 透传 6 列 |
| `mart.inventory_snapshot_latest` / `mart.inventory_current` | 排序键 `metric_date` → **`observed_at DESC NULLS LAST, ingest_timestamp DESC`**；透传 6 列 |
| `mart.inventory_snapshot_change` / `mart.inventory_snapshot_company_daily` | 排序键同上 |
| **新表** `mart.inventory_state` | 每 SKU×仓 一行，存当前库存 + 销量 + **三个时间戳** |
| **新服务** `inventory_state_refresh_service` | 双闸判定 + upsert 状态层 |
| **新纯函数** `inventory_stall_service` | 停滞时长与分档的**唯一实现** |

**时间戳的时区**：妙手「更新时间 / 创建时间」是**北京时间墙上时间**，
数据库会话时区是 UTC → 语义层显式 `AT TIME ZONE 'Asia/Shanghai'`，
不依赖会话时区。实测佐证：妙手最大更新时间 12:13:32（北京时间）
与入库时刻 04:39:53 UTC（= 12:39 北京）相差 26 分钟，完全自洽。

**新增列必须追加在视图末尾**：`CREATE OR REPLACE VIEW` 不允许改变已有列的位置，
中途插入会报 `cannot change name of view column`。

#### 5.6.2 三个时间戳各司其职

| 字段 | 来源 | 作用 |
|---|---|---|
| `stock_changed_at` | 妙手 `observed_at`，**只在闸 2 判定库存真变了时推进** | **停滞时长的分子** |
| `row_seen_at` | 我方 `ingest_timestamp` | 本行最近一次被采集看到的时间（兼作水位线） |
| `row_written_at` | 妙手 `observed_at` | 仅留档，**不参与任何判定** |

#### 5.6.3 ⚠️ 落地时发现并修掉的三个真问题

**问题 1：增量模式下同一天多批采集 → 库存被重复累加**

`mart.inventory_snapshot_latest` / `inventory_snapshot_change` 原来用
`SUM(available_stock)` 按 (snapshot_date, SKU×仓) 聚合。增量模式下同一天可能落多批
→ 同一行被**加了好几次**，库存凭空翻倍。
**修法**：先按 (snapshot_date, SKU×仓) 用 `ROW_NUMBER()` 取**最新一行**，再输出。
已由 `backend/tests/data_pipeline/test_inventory_snapshot_views_behavior.py`
在真实 PostgreSQL 容器上守住（断言结果是 12 而不是 22）。

**问题 2：妙手时间戳会被批量污染，取「时间戳最大」会选中被污染的旧批次**

实测：file 2764 有 535 行（43.7%）的更新时间被一次 bulk UPDATE 覆盖成
`2026-05-08 10:36:36~39`；**1109 个共同键里「更新时间相同」的是 0 行**，
其中 644 行的 2764 值反而比 3004 更新 —— 时间倒流，不可能。
**修法**：状态层取「**最近一次被采集看到**」的那行（按 `ingest_timestamp` 排），
而不是「时间戳最大的那次」。

> 这条是落地时才发现的：之前只验证过「妙手时间戳会被污染」，
> 没验证过「污染会让『取最大值』选错行」。增量模式下这会让重度积压档**整档消失**
> （实测 500 行 → 14 行）。修正后与独立基线完全对齐。

**问题 3：首次观测的 `stock_changed_at` 不能用妙手时间戳**

首次观测时没有「上一批」可比，闸 2 无从判断。此时用妙手时间戳做初值，
一旦该批次被污染就会**直接污染状态层**。
**修法**：首次观测取「该键最新一次被采集看到」那行的 `observed_at`；
后续批次严格按闸 2 推进。

#### 5.6.4 落地实测结果（file 2764 + 3004，1230 个 SKU×仓）

| 校验项 | 结果 |
|---|---|
| 语义层新列覆盖 | 2339 行 **100%** 有 `observed_at` / `created_at` / `checklist_sales_90d` |
| 状态层行数 | 1230（去重键 1230，**无重复**） |
| 状态层 vs 独立基线（重度积压档） | **500 行 / ¥16,442.08** vs 基线 488 行 / ¥16,442.08 → **货值完全一致** |
| 状态层 vs 独立基线（活跃档） | **446 行 / ¥180,208.86** vs 基线 446 行 / ¥180,208.86 → **完全一致** |
| 状态层 vs `mart.inventory_snapshot_latest` 的库存 | 可用/总量/预占 **0 处不一致** → 增量模式下库存始终准 |
| 库存自洽性（总量 = 可用 + 预占） | 1230 行**全部成立** |
| 「零销量有库存」 | 139 行 / ¥36,418.48（基线 138 行 / ¥36,411.48） |

**新增测试**（21 + 2 项，全绿）：

- `backend/tests/data_pipeline/test_inventory_stall_service.py`（11 项）—— 纯函数：分档边界、
  不可算**不得回落「活跃」**、SKU 级聚合取各仓最长、只算有库存的仓
- `backend/tests/data_pipeline/test_inventory_state_refresh_service.py`（10 项）—— 双闸：
  首次观测 / 库存变了推进 / **库存没变保留旧值（批量戳不刷新停滞时长）** /
  预占变化也算数量变化 / 按采集时间取最新
- `backend/tests/data_pipeline/test_inventory_snapshot_views_behavior.py`（2 项，`pg_only`）——
  真实 PostgreSQL 容器执行**仓库里的真实 SQL 资产**，守住「同日多批不重复累加」

---

## 6. 水位线与断档补采

### 6.1 水位线存储

新增 `ops.inventory_collection_watermark`（或复用 `ops.pipeline_run_log`）：

| 列 | 含义 |
|---|---|
| platform_code | `miaoshou` |
| account_id | `miaoshou_real_001` |
| observed_at_watermark | 上次成功采集的 `max(observed_at)` |
| last_run_id | 对应的 `core.collection_config_runs.id` |
| last_full_run_at | 上次全量采集时间 |
| updated_at | |

### 6.2 采集窗口计算

```
默认窗口 = [observed_at_watermark, 本次采集时刻]
```

**但用户配置里的日期区间优先级更高**——因为用户的意图是「我就是要采这一段」。
两者冲突时的规则：

| 情形 | 窗口 | 理由 |
|---|---|---|
| 配置了 custom_date_range | 用配置的区间 | 用户显式指定 |
| 未配置 / 用默认 | `[水位线, now]` | 自动推进 |
| 请求区间起点 < 水位线 | 取 `max(请求起点, 水位线)` | 避免重复采集已采过的行 |

### 6.3 全量回退规则 → 2026-10-24 晚间修正：取消全量档，改用「长窗口补采」

**⚠️ 采集策略已定（Walter 拍板）：后面不再全量采集，只有「配置采集 + 增量更新」。**
因此本节原设计的「自动回退全量 / 周期性全量」两条规则**不再成立**，改为下表：

| 原规则 | 改为 |
|---|---|
| 首次采集（状态层为空）→ 强制全量 | **不需要**——现有 1113 行（file 3004）就是基线 |
| 断档 > 阈值（建议 7 天）→ 自动回退全量 | **长窗口补采**：把增量区间向前拉长到覆盖断档期。妙手本来就是按更新时间筛选，拉长区间即可，不存在「切全量」这个动作 |
| 上一批失败 → 下一批回退全量 | 下一批把窗口拉长到覆盖失败期 + 记日志 |
| 周期性全量（查删除/下架） | **⚠️ 取消** → 见下方「删除/下架怎么办」 |
| 导出结果行数异常 → 下次回退全量 | 记录告警 + 下一批窗口拉长 |

#### 删除/下架怎么办（不再全量后的真问题）

**风险**：妙手的「更新时间」筛选只能返回**还存在的行**。SKU 被删除或下架时，增量永远看不到它
→ 状态层会**残留幽灵行** → 它的库存价值会一直挂在总库存价值里，**虚高**。

在「不再全量」的前提下，三条可选对策：

| 方案 | 做法 | 代价 / 前提 |
|---|---|---|
| **A. 零库存宽限期** | 某 SKU×仓 连续 N 天（建议 14 天）**未被采集到**、且最后一次已知库存为 0 → 标记「疑似已下架」，从活跃库存汇总中摘出，**保留行不硬删** | 覆盖「库存清零 + 长期不再出现」这一大类；**SKU 是被删而非库存清零的话识别不了** |
| **B. 商品档案的上下架状态** | 从妙手商品档案 / 商品列表侧拿上下架标记，与库存清单交叉 | **需要先确认妙手有没有这个可取的口子**——本轮未取证 |
| **C. 极低频核对批次** | 保留一个远低于日常频率的核对（例如每季度一次） | 与「不再全量」的字面要求冲突，但这是**唯一能发现「被删除」的手段** |

**建议**：**A 立刻做**（成本低、覆盖一大类）；**B 需要一次真实页面取证**才能定；
**C 建议保留但拉长到季度**——理由不是「DOS 需要刷新」（DOS 已降级为参考），
而是**没有它，虚高的库存价值会无限期挂着**，而「总库存价值」是业务概览顶部第一张卡。

#### 变更判定必须双闸（仍然必须做，且更重要）

它现在承担两件事：① 决定哪些行进观测层；② 维护 `stock_changed_at`（**停滞时长的分子来源**）。

| 闸 | 判定 | 作用 |
|---|---|---|
| 闸 1（妙手侧，筛选） | 用「更新时间」维度 + 区间**缩小候选集** | 只决定「这次导出哪些行」，**不决定「这行算不算变了」** |
| 闸 2（我方侧，行内容 diff） | 与上一批同 SKU×仓 比对：**可用库存 / 库存总量 / 预占库存** 是否真的变了 | **决定是否推进 `stock_changed_at`、是否写入观测层**（`observed_at` 才落这一行） |

→ 批量戳时间戳的行，闸 2 会判定「业务内容没变」→ **不写观测层、不推进 `stock_changed_at`**
（避免观测层被批量操作污染，也避免水位线被假变更推着走，更避免污染停滞时长）。
→ 闸 2 **不比较销量**：销量在增量下本就不更新，拿它做 diff 会把 93 行「库存没变但销量变了」
的行误判成业务变更。

#### 双闸的实测依据

| 发现 | 数据 |
|---|---|
| **误报**：一次批量操作把大量行一起戳了 | file 2764 有 **535 行（43.7%）**的更新时间被批量写成 `2026-05-08 10:36:36~39`（4 秒窗口，一次 bulk UPDATE）。同样这些行在 file 3004 里各自是真实更新时间（136 行 = 创建时间 = 从未修改） |
| **不完整**：库存数量没变，行却仍被写了 | 两批 1109 共同行中 **93 行（8.4%，货值 ¥13,560）库存数量完全没变、销量却变了** → 妙手在非库存变动（批量编辑/改价/盘点）时也会刷新行的销量列 |
| **可靠**：行状态本身稳定 | 同一筛选条件连查两次（间隔 40 秒、不做业务操作）→ 20 行的更新时间/创建时间/库存/销量**逐字相同** → 「更新时间」是稳定的行级存储字段，不是查询时生成的 |

### 6.4 采集配置的改造

`core.collection_configs` 已有 `date_range_type` / `custom_date_start` / `custom_date_end`，
增量模式下需要新增「自动推进」语义。建议新增：

- `date_range_type = 'auto'`（新增枚举值）→ 用水位线自动算窗口
- 沿用 `custom` → 用户指定固定区间

### 6.5 落盘层的具体要求

1. 观测层写入条件：`闸1 命中` **且** `闸2 内容有变`；两者都满足才产生行级 `observed_at`。
2. 状态层（每 SKU×仓 upsert）**每批都更新**（保证状态完整），但要**分别记录**：
   - `stock_changed_at` —— **库存数量最后一次真实变动的时间（停滞时长的分子，必须由闸 2 维护）**
   - `row_seen_at` —— 本行最近一次被采集看到的时间
   - `row_written_at` —— 妙手给的时间戳（仅留档，不参与判定）
3. `ops.inventory_collection_watermark` 的 `observed_at_watermark` 只在**闸 2 判定为真变更**的行上推进，
   **不能**被「只是被批量戳了」的行推进。
4. **不再产出 `dos_as_of`** —— DOS 已降级为参考值，不需要口径时点管控（DOS 设计稿 §6.6）。
5. 断档补采只拉长区间，**不做全量切换**；导出结果行数异常要记日志并在下一批拉长窗口。

---

## 7. 派生层联动（本次一并解决）

这三个改动与增量模型强相关，一次做完可以避免二次返工。

### 7.1 库龄锚点修正

`mart.inventory_age_current` / `mart.inventory_age_history` 的 `age_anchor_date` / `age_days`
当前由 `inventory_age_refresh_service.replay_snapshot_rows` 按 `snapshot_date` 差计算。

改为：**优先用行级 `created_at`**（妙手「创建时间」= 该 SKU 在该仓的库存记录创建时间 ≈ 首次入库时间）。

实测收益（file 3004，1113 行）：

| 口径 | 分桶分布 |
|---|---|
| 现状（snapshot_date 锚） | 0-30: 495，>30: **0** |
| 改用创建时间锚 | 0-30: 4，61-90: 8，91-180: 5，**180+: 1096** |

商品中心 56% SKU 的 `fallback_no_age_data` 兜底档可随之消除。

> 注意：`created_at` 是**商品在该仓的记录创建时间**，不是「这批货的入库时间」。
> 跨 SKU 不可比性需要业务确认。若业务上要求 FIFO 口径，需另取入库流水数据（当前没有）。

> **⚠️ 2026-10-24 晚间补充：修好锚点后，库龄也不再用于选定价档。**
> 业务说的「库龄」=「这批货压了多久」，数据上对应的是**库存停滞时长**
> （`inventory_stall_days`），不是妙手的「创建时间」（那是首次铺货时间）。
> 实测：用 `created_at` 直接选档 → **1060/1076 个 SKU（99%）落最深档**，平均折扣 0.2979（等于全场清仓）；
> 而「库龄≥180 天且近90天还在卖」的老品有 **430 行 / ¥187,980**，是真滞销（136 行 / ¥32,569）的 5.8 倍。
> → 商品中心选档改用**库存停滞时长**（DOS 设计稿 §6.7）；
> 库龄修好后**保留为「商品生命周期视角」**，不再参与定价分档。

### 7.2 9999 哨兵值拆分

`mart.inventory_backlog_base` 的 30 天销量取自 `semantic.fact_orders_atomic`（无 miaoshou 数据）。

**改用库存表自带的销量列**（已入库，100% 覆盖）：
`近30天销量数据` / `近60天销量数据` / `近90天销量数据`（raw_data 键，text 类型需 cast numeric）。

实测收益（file 3004，513 个有货行）：

| 口径 | 结果 |
|---|---|
| 现状 | 499 行 `estimated_turnover_days = 9999`，risk_level 全 high，30/60/90 天金额全等 ¥217,787.41 |
| 改用库存自带销量 | **298 行（58.1%）可算出真实周转天数**（均值约 203 天），215 行是真零销量 |
| 三档区分度 | 290 行 30≠60，264 行 60≠90 → 三档金额可拆开 |

**设计要点**：9999 应改为独立的「无销量」标识，不参与 `risk_level` 判定，也不参与
`clearance_priority_score` 评分（当前 `estimated_turnover_days * 2` 让哨兵值主导全部排序）。

> ⚠️ 口径差异需业务确认：库存表的「近30天销量」是**妙手平台口径**（按 SKU 在该仓），
> 而 `fact_orders_atomic` 是 ERP 订单域口径（跨平台、按商品）。
> 两者不完全等价，但前者在当前 miaoshou 订单域缺失的情况下，是**唯一可用的真实销量信号**。

### 7.3 `api.clearance_ranking_module` 重写

超时根因是 O(N×M²)：`order_months`(31012) JOIN LATERAL(扫 backlog_base 1230) 每行再 EXISTS(又扫 1230)，
约 470 亿次；外加 `to_jsonb(o.*)->>'col'` 取字段废索引、JSON 文本正则、布尔排序、join 键被函数包裹。

重写要点：
1. 去掉 `to_jsonb(o.*)`，直接用物理列。
2. 去掉 LATERAL + 相关 EXISTS，改为预聚合 JOIN。
3. join 键去 `::text` / `COALESCE(NULLIF(btrim()))` 包裹，或补上函数索引。
4. 布尔排序改为显式 CASE。
5. 用库存自带销量替代订单域 join 后，join 基数从 31012 降到 1230，本身就是数量级下降。

> 该视图目前即使不超时也返回空（无 miaoshou 订单）。7.2 落地后才有数据可返回。

---

## 8. 实施顺序

| 批次 | 内容 | 依赖 | 风险 |
|---|---|---|---|
| **B1** | 采集组件：`inventory_date_filter` 新组件 + 编排改造 + 行为测试 | 需真实页面复验 | 低（只加筛选，不改落盘） |
| **B2** | 语义层暴露 `observed_at` / `created_at`；`latest` / `current` 改排序键 | 无 | 低（视图改动，可回滚） |
| **B3** | 水位线表 + 自动推进 + 全量回退规则 | B1 B2 | 中 |
| **B4** | 库龄锚点修正 + 9999 拆分 + `clearance_ranking_module` 重写 | B2 | 中 |
| **B5** | 周期全量档 + 增量/全量差异对账报表 | B3 | 低 |

> B1 可以独立上线（只采集不改下游），但**单独上线会让「增量批次进不了 latest」的问题更严重**
> （旧批次 metric_date 09-14 依然压过新批次）。因此 B1 与 B2 应当**同批发布**。

---

## 9. 验收标准

### 9.1 采集层（B1）

- [ ] 维度下拉切到「更新时间」后，`modelvaluegroup` 以 `gmtModified` 开头（断言，非日志）
- [ ] 填完区间点「确定」后，`modelvaluegroup` 含目标起止时间（断言）
- [ ] 点搜索后「SKU 总数」文本发生变化，且新值 > 0
- [ ] 导出文件行数 = 页面筛选后的 SKU 数（用户已实测「导出搜索的商品」= 筛选结果）
- [ ] 导出文件含「更新时间」「创建时间」两列
- [ ] 组件行为测试覆盖：维度未切 / 未点确定 / 搜索无刷新 三条失败路径（断言行为，不做源码字符串断言）

### 9.2 落盘层（B2）

- [ ] `semantic.fact_inventory_snapshot` 新增 `observed_at`、`created_at`
- [ ] 用现有两批数据重算：`mart.inventory_snapshot_latest` 中最新批次贡献 ≥ 400 行（当前 4 行）
- [ ] `mart.inventory_current` 行数 = 去重 SKU×仓数（1113），无重复
- [ ] shopee / tiktok 的 `observed_at` 落到 `metric_date` 兜底，行为不变

### 9.3 派生层（B4）

- [ ] `mart.inventory_age_current` 的 `age_days > 30` 的行数 > 0（当前 0）
- [ ] `mart.inventory_backlog_base` 的 `estimated_turnover_days = 9999` 行数 < 250（当前 499）
- [ ] `api.clearance_ranking_module` 在 5 秒内返回且行数 > 0
- [ ] `mart.inventory_backlog_base` 的 30/60/90 天金额三档不再全部相等

### 9.4 全局

- [ ] 采集测试面全绿（当前基线 149 项）
- [ ] `black --line-length 88` / `ruff` 全过
- [ ] 函数 ≤ 50 行、类 ≤ 500 行（`TESTING_AND_QUALITY.md` 硬门禁）
- [ ] lint 基线不劣化（当前全仓库 385 条 / 656 处）

---

## 10. 风险与未决

| 项 | 说明 |
|---|---|
| **导出文件是否含筛选结果** | ✅ 用户 2026-10-24 实测确认 |
| **快捷项能否替代手填日期** | 待定。「近7天/近30天」相对今天，与「水位线推进」语义不同。若采用，可省掉日期输入，稳定性更高，但窗口由平台决定而非配置决定 |
| **创建时间 ≠ 入库时间** | 库龄改用 `created_at` 是「商品在该仓的记录创建时间」。若业务要求 FIFO 口径，当前数据源不支持 |
| **库存销量 ≠ ERP 订单销量** | 平台口径 vs ERP 口径。订单域修复后可校准 |
| **增量查不出删除** | ⚠️ **不再全量后没有兜底**。三条对策：① 零库存宽限期（连续 N 天未被采集到且库存为 0 → 标「疑似下架」）② 商品档案的上下架状态（**待取证**）③ 保留一个季度级核对批次（唯一能发现「被删除」的手段） |
| **★ DOS 降级为参考，不做判定** | 实测增量只覆盖 13.6% SKU，分母是行级存储快照。**DOS 不作判据**，滞销判据改用**库存停滞时长**（DOS 设计稿 §4.8 / §6.6） |
| **★ 妙手的「更新时间」不能当变更信号** | 实测 43.7% 的行被一次 bulk UPDATE 批量戳过；另有 8.4% 的行库存没变却被写入。变更判定必须双闸（筛选 + 行内容 diff，§6.3） |
| **页面改版风险** | 选择器全部基于 2026-10-24 实测，但妙手前端改版会使其失效。沿用现有做法：在 `inventory_config.py` 注明取证日期与来源 |

---

## 11. 参考

- 概念对齐页：`output/inventory-incremental-concept.html`
- 取证结论页：`output/inventory-updated-filter-evidence.html`
- 录制产物：`output/playwright/work/miaoshou/inventory_date_filter/`
- 取证探针：`scripts/probe_miaoshou_warehouse_scope.py`（同类，本次为只读 CDP 临时脚本）
- 落盘模型依据：`sql/semantic/inventory_snapshot.sql`、`sql/mart/inventory_snapshot_latest.sql`、
  `sql/mart/inventory_current.sql`、`sql/mart/inventory_backlog_base.sql`
- 采集组件：`modules/platforms/miaoshou/components/inventory_export.py`、
  `modules/platforms/miaoshou/components/inventory_config.py`、
  `modules/platforms/miaoshou/components/date_picker.py`
