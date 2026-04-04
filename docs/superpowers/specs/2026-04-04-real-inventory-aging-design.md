# Real Inventory Aging Design

**日期:** 2026-04-04

**目标:** 在现有 `ledger-first` 库存真源基础上，为系统补齐“真实库龄”能力，使滞销库存管理不再依赖 `estimated_turnover_days` 这类周转推导口径，而是基于真实入库层、真实剩余量和真实在库天数进行分析、预警和清理排序。

## 1. 背景

当前系统已经完成库存域重构，具备以下真实库存基础设施：

- `OpeningBalance`
- `GRNHeader / GRNLine`
- `InventoryLedger`
- `InventoryAdjustmentHeader / InventoryAdjustmentLine`

它们已经能支撑：

- 期初余额
- GRN 过账
- 调整单过账
- 库存流水
- 当前结存

但是“真实库龄”仍然缺失。

当前系统中与滞销库存相关的主运行口径是：

- 当前库存快照
- 近 30 天销量
- `daily_avg_sales`
- `estimated_turnover_days`

这条链路来自：

- `mart.inventory_backlog_base`
- `api.clearance_ranking_module`
- `backend.services.postgresql_dashboard_service.rank_inventory_backlog_rows`

这意味着当前“滞销库存管理”本质上是“预计周转天数管理”，不是“真实库龄管理”。

同时，从妙手库存快照导入链路看，当前仓库并没有接入明确的库龄字段：

- 妙手仓库导出组件配置只负责仓库清单导出，不暴露库龄字段契约
- inventory 导入校验中仅识别库存、成本、日期等字段，不识别 `库龄 / age_days / stock_age`

因此，如果要做真正的滞销库存管理，必须在系统内部自行建立真实库龄模型。

## 2. 设计目标

本次设计要达成以下目标：

1. 让系统能够计算每个 SKU 当前剩余库存的真实在库天数。
2. 让系统能够回答“当前库存由哪些入库层组成”。
3. 让系统能够回答“某次出库消耗了哪几层库存”。
4. 在不破坏现有 `InventoryLedger` 真源地位的前提下，为库龄补充“库存层”模型。
5. 支持 30/60/90 天以及自定义库龄桶分析。
6. 为滞销库存管理提供真实库龄、库龄价值、老库存清理优先级。

## 3. 非目标

本次设计不做以下事情：

1. 不依赖妙手导出中的库龄字段作为系统唯一来源。
2. 不用快照中的单个“库龄天数”字段直接替代真实库龄模型。
3. 不在本轮同时实现 FIFO、LIFO、WAC 多套并行库存层逻辑。
4. 不在本轮重构现有 dashboard backlog / clearance 模块的全部 SQL。

## 4. 核心原则

### 4.1 InventoryLedger 仍然是库存数量变化真源

`InventoryLedger` 继续承担唯一库存流水真源职责。

真实库龄不是替代 `InventoryLedger`，而是在其上补充“库存层剩余量”的解释能力。

### 4.2 库龄必须建立在“剩余库存层”上

真实库龄不是“当前日期减去某个快照日期”。

真实库龄必须建立在下面这个事实之上：

- 每次入库形成一层库存
- 每次出库消耗这些库存层
- 当前剩余库存 = 若干未完全消耗的库存层之和
- 每层剩余库存都有自己的 `received_date`

### 4.3 默认采用 FIFO

第一版真实库龄按 FIFO 消耗库存层。

原因：

- 最符合“先处理老货”的库存运营目标
- 最容易解释
- 最适合滞销库存与清仓优先级分析
- 与库龄天然一致

## 5. 目标数据模型

### 5.1 `finance.inventory_layers`

用途：

- 记录每一批入库形成的库存层
- 跟踪该层当前剩余多少

建议字段：

- `layer_id`
- `source_type`
  - `opening_balance`
  - `grn`
  - `return`
  - `adjustment_in`
- `source_id`
- `source_line_id`
- `platform_code`
- `shop_id`
- `platform_sku`
- `warehouse`
- `received_date`
- `original_qty`
- `remaining_qty`
- `unit_cost`
- `base_unit_cost`
- `created_by`
- `created_at`

关键语义：

- 一次入库 = 新增一层
- `remaining_qty > 0` 才表示当前库存中仍保留该层

### 5.2 `finance.inventory_layer_consumptions`

用途：

- 记录某次出库消耗了哪些库存层

建议字段：

- `id`
- `outbound_ledger_id`
- `layer_id`
- `platform_code`
- `shop_id`
- `platform_sku`
- `consumed_qty`
- `consumed_at`
- `age_days_at_consumption`
- `created_at`

关键语义：

- 一次出库可能拆分消耗多个 layer
- 一个 layer 也可能被多次消耗

### 5.3 OpeningBalance 的增强要求

当前 `OpeningBalance` 仅记录：

- `period`
- `opening_qty`
- `opening_cost`
- `opening_value`

如果要支持真实库龄，必须补充以下二选一：

1. `received_date`
2. `opening_age_days`

推荐优先方案：

- 补 `received_date`

原因：

- 更接近真实世界
- 可直接用于后续 layer 构造

如果历史数据无法提供精确入库日期，则允许临时使用：

- `opening_age_days`

再由系统推导：

- `received_date = period_start_date - opening_age_days`

## 6. 库龄核心流程

### 6.1 期初入层

当创建或导入 `OpeningBalance` 时：

- 为每条记录生成一条 `inventory_layer`
- `source_type = opening_balance`
- `original_qty = remaining_qty = opening_qty`

如果没有 `received_date` 或 `opening_age_days`，则该期初库存不能生成真实库龄。

### 6.2 GRN 入层

当 GRN 过账时：

- 继续照常写 `InventoryLedger(receipt)`
- 同时新增 `inventory_layer`
- `source_type = grn`
- `received_date = receipt_date`
- `original_qty = remaining_qty = qty_received`

### 6.3 退货入层

当退货入库发生时：

- 写 `InventoryLedger(return)`
- 同时新增 `inventory_layer`
- `source_type = return`

### 6.4 调整增加入层

当调整单增加库存时：

- 写 `InventoryLedger(adjustment)`
- 同时新增 `inventory_layer`
- `source_type = adjustment_in`

### 6.5 出库消层

当发生销售出库、报损、调整减少等操作时：

- 写 `InventoryLedger`
- 按 FIFO 查找 `remaining_qty > 0` 的 `inventory_layers`
- 依序扣减
- 为每次扣减写 `inventory_layer_consumptions`

举例：

- SKU 当前 layer:
  - L1: 10
  - L2: 8
- 本次出库 12
- 则：
  - L1.remaining_qty -> 0
  - L2.remaining_qty -> 6
- 生成两条 consumption：
  - consume L1 qty 10
  - consume L2 qty 2

## 7. 库龄计算口径

### 7.1 当前真实库龄

对每个 `remaining_qty > 0` 的 layer：

- `age_days = CURRENT_DATE - received_date`

这是最原始、最真实的库龄单位。

### 7.2 SKU 级聚合库龄

对某个 SKU，可以提供：

- `oldest_age_days`
- `youngest_age_days`
- `weighted_avg_age_days`
- `age_bucket_breakdown`

推荐主展示口径：

- `weighted_avg_age_days`

计算方式：

- `sum(remaining_qty * age_days) / sum(remaining_qty)`

### 7.3 库龄桶

默认提供以下库龄桶：

- `0-30`
- `31-60`
- `61-90`
- `91-180`
- `180+`

每个桶同时输出：

- `quantity`
- `inventory_value`
- `sku_count`

## 8. 读模型设计

### 8.1 `mart.inventory_age_base`

建议构建一个 SKU-layer 级基础视图：

- `platform_code`
- `shop_id`
- `platform_sku`
- `layer_id`
- `received_date`
- `remaining_qty`
- `unit_cost`
- `remaining_value`
- `age_days`
- `age_bucket`

### 8.2 `api.inventory_age_summary`

建议构建汇总视图，用于页面展示：

- SKU 级真实库龄汇总
- 店铺级库龄桶汇总
- 平台级库龄桶汇总

### 8.3 与现有 backlog / clearance 的关系

现有 backlog/clearance 可以先保留：

- `estimated_turnover_days`

后续升级成双指标：

1. 真实库龄
2. 预计周转天数

这样能区分两种风险：

- 货放太久但最近卖得快
- 货放不久但未来卖得慢

## 9. 页面与功能建议

### 9.1 库存管理域新增页面

建议新增：

- `库存库龄`
- `库龄分布`
- `老库存清理建议`

### 9.2 库存总览域增强

在总览中补充：

- `真实库龄`
- `加权平均库龄`
- `老货占比`

但总览页面只读，不承担库存层维护职责。

### 9.3 滞销管理主页面

建议同时显示两列：

- `真实库龄天数`
- `预计周转天数`

不要再只显示一个叫“滞销天数”的混合概念。

## 10. 风险与未知项

### 10.1 期初年龄数据缺失

这是最大风险。

如果历史期初库存没有 `received_date` 或 `opening_age_days`，则：

- 旧库存无法得到真实库龄
- 只能从新增入库开始逐步获得准确库龄

### 10.2 销售出库链路是否全部进入 InventoryLedger

如果实际销售出库没有稳定进入 `InventoryLedger`：

- 库存层不会被正确消耗
- 真实库龄会虚高

### 10.3 仓库维度是否需要进入 layer 主键

如果同一 SKU 存在多仓库存：

- `warehouse` 必须成为 layer 维度的一部分

否则库龄会在跨仓聚合时失真。

## 11. 结论

如果系统要做真正的滞销库存管理，就必须具备真实库龄能力。

正确做法不是依赖库存快照里是否有一个现成的“库龄”字段，而是：

1. 继续以 `InventoryLedger` 为库存变化真源
2. 补充 `inventory_layers` 和 `inventory_layer_consumptions`
3. 采用 FIFO 消耗剩余层
4. 由剩余层推导真实库龄

这样系统才真正知道：

- 当前库存从哪一天开始在库
- 当前库存由哪些批次构成
- 哪些货是真正的老库存
- 哪些 SKU 应该优先清理
