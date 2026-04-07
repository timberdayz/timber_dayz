# Miaoshou Inventory Snapshot And Backlog Design

**日期:** 2026-04-04

**目标:** 将当前库存运行主链明确收敛为“妙手库存快照全量更新 + 滞销看板分析”，确保系统围绕库存快照历史、快照变化和滞销风险分层稳定运行，而不把当前系统误当作实时库存事务系统。

## 1. 背景

当前系统已经具备两类库存能力：

1. `ledger-first` 真实库存域能力
   - `OpeningBalance`
   - `GRNHeader / GRNLine`
   - `InventoryLedger`
   - `InventoryAdjustment*`
   - `InventoryLayer / InventoryLayerConsumption`

2. 库存快照 + dashboard 分析链路
   - 妙手库存快照导出
   - inventory 数据导入
   - `mart.inventory_current`
   - `mart.inventory_backlog_base`
   - `api.clearance_ranking_module`

但根据当前业务定位，系统更接近：

- 采集、入库、存储、查询、看板系统

而不是：

- 实时交易执行系统
- 实时库存事务系统

同时，妙手库存快照目前存在两个关键事实：

1. 快照更像“当前总库存/全局库存”视图，不稳定提供每店铺单独可售库存
2. 快照更新频率可能是每周一次或每 3-4 天一次，而不是每日一次

因此，当前主链不适合做：

- 销售事实驱动实时库存扣减
- 精确店铺级实时可用库存
- 精确日级真实库龄承诺

本次设计的目标不是再扩展事务库存，而是把当前真正可用、可信的主链设计清楚并优化。

## 2. 设计目标

本次设计要达成以下目标：

1. 明确“妙手库存快照全量更新”是当前库存运行主链。
2. 保留每次库存快照历史，而不只保留最新值。
3. 用最新快照 + 快照历史 + 近 30 天销量计算滞销风险。
4. 以 `estimated_turnover_days` 作为主指标。
5. 以“连续积压快照次数 + 估算积压天数”作为辅助指标。
6. 在页面和 API 文案上避免把这些口径误称为“真实库龄”。

## 3. 非目标

本次设计不做以下事情：

1. 不把 B 类订单事实实时驱动为库存扣减命令。
2. 不承诺系统当前提供店铺级实时可售库存。
3. 不把当前滞销分析口径包装成“真实库龄”。
4. 不要求快照必须每日更新。
5. 不把真实库龄体系作为当前运行主链。

## 4. 运行主链定义

### 4.1 主数据来源

当前库存运行主链的数据来源定义为：

- 妙手仓库清单页导出的 inventory snapshot

系统角色：

- 采集 inventory snapshot
- 全量写入/刷新库存快照历史
- 派生最新快照读模型
- 派生滞销和清仓分析读模型

### 4.2 主链口径

系统当前提供的是：

- 当前库存快照展示
- 快照趋势与对比
- 滞销风险评估
- 清仓优先级排序

系统当前不提供的是：

- 实时交易后自动扣减库存
- 精确批次库存事务链
- 精确店铺级实时可售库存

## 5. 主指标设计

### 5.1 主指标: `estimated_turnover_days`

这是当前滞销分析的主指标。

定义：

- `estimated_turnover_days = current_available_stock / recent_daily_avg_sales`

实现来源：

- `mart.inventory_backlog_base`

特点：

- 只依赖最新库存快照 + 近 30 天销量
- 不要求每日快照
- 对当前系统最稳妥

### 5.2 辅助指标: `stagnant_snapshot_count`

定义：

- 连续多少次库存快照中，库存未明显下降

它不是自然日精确值，而是基于快照序列的观察指标。

### 5.3 辅助指标: `estimated_stagnant_days`

定义：

- 累计这些“连续未明显下降”的快照区间天数

计算方式：

- 使用相邻快照的 `snapshot_date` 差值累计

它是估算值，不是日级精确库龄。

## 6. 快照历史设计

### 6.1 保留每次全量快照

系统必须保留每次 inventory snapshot 历史。

每条快照记录至少应包含：

- `snapshot_date`
- `platform_code`
- `shop_id`
- `platform_sku`
- `warehouse`
- `available_stock`
- `total_stock`
- `inventory_value`
- `source_file_id`
- `ingest_timestamp`

### 6.2 最新快照视图

为当前库存页面提供：

- 每个 SKU 的最新一条快照

该视图只用于“当前库存”展示，不承担历史分析职责。

### 6.3 快照变化视图

系统应构造一个快照变化视图，比较：

- 最新快照
- 上一次快照

并输出：

- `stock_delta`
- `inventory_value_delta`
- `is_stagnant`
- `stagnant_snapshot_count`
- `estimated_stagnant_days`

## 7. 滞销判断规则

### 7.1 “未明显下降”定义

建议默认规则：

- 如果 `available_stock` 变化绝对值 `<= threshold`
- 则视为“未明显下降”

默认阈值建议：

- `0`

后续允许配置为：

- `1`
- `2`
- `3`

以适应不同波动容忍度。

### 7.2 风险等级

推荐默认分层：

- `low`
  - `estimated_turnover_days < 30`
- `medium`
  - `30 <= estimated_turnover_days < 60`
  - 或 `stagnant_snapshot_count >= 2`
- `high`
  - `estimated_turnover_days >= 60`
  - 或 `stagnant_snapshot_count >= 3`
  - 若 `inventory_value` 较高，则排序优先级进一步上浮

### 7.3 排序分数

建议新增：

- `clearance_priority_score`

综合：

- `estimated_turnover_days`
- `estimated_stagnant_days`
- `inventory_value`

用途：

- 风险等级用于分类
- 优先级分数用于排序

## 8. 文案与概念约束

当前主链必须避免以下误导性命名：

- `真实库龄`
- `精确在库天数`
- `店铺可售库存(若数据并不具备店铺精度)`

推荐用语：

- `预计周转天数`
- `连续积压快照次数`
- `估算积压天数`
- `滞销风险等级`
- `清理优先级`

## 9. SQL / API / 页面目标

### 9.1 SQL 目标

建议新增或优化以下对象：

- `mart.inventory_snapshot_history`
- `mart.inventory_snapshot_latest`
- `mart.inventory_snapshot_change`
- `api.inventory_backlog_summary_module`
- `api.clearance_priority_module`

### 9.2 API 目标

建议主看板相关 API 返回结构包含：

- `summary`
  - 总库存价值
  - 风险桶数量
  - 30/60/90 口径金额
- `top_products`
  - `platform_sku`
  - `product_name`
  - `available_stock`
  - `inventory_value`
  - `estimated_turnover_days`
  - `stagnant_snapshot_count`
  - `estimated_stagnant_days`
  - `risk_level`
  - `clearance_priority_score`

### 9.3 页面目标

当前页面重点是：

- 当前库存总览
- 滞销产品列表
- 清仓优先级排序
- 平台分布
- 快照变化趋势

而不是：

- 实时库存事务处理
- 出库过账
- 批次追溯

## 10. 与真实库龄的关系

真实库龄能力仍然保留为未来增强方向：

- `InventoryLayer`
- `InventoryLayerConsumption`

但当前运行主链不依赖它。

未来如果满足以下条件：

1. 订单/出库事务源稳定
2. 店铺级库存口径稳定
3. 批次或入层数据完整

再将“真实库龄”并入滞销分析即可。

在那之前，系统应坚持：

- 当前主链 = 快照分析链
- 真实库龄 = 预留增强能力

## 11. 结论

当前最正确、最务实的库存主链是：

- 妙手库存快照全量更新
- 快照历史留存
- 基于销量的 `estimated_turnover_days`
- 基于快照变化的连续积压判断
- 滞销风险等级与清仓优先级排序

这条链最符合当前系统定位，也最不容易把“分析系统”误做成“事务库存系统”。
