# Change: 设计 Metabase 模型和 Question

## Why

当前系统已完成数据同步优化（v4.18.1），数据已正确同步到 `b_class.fact_raw_data_*` 表中，但：

1. **缺少统一的数据模型**：不同平台的相同字段名不同（如"销售额"vs"销售金额"），需要在Metabase Model中统一
2. **缺少跨粒度整合**：日度、周度、月度数据分散在不同表，需要整合到统一模型
3. **缺少业务概览Question**：前端业务概览页面需要多个Question提供数据，但尚未创建
4. **缺少字段标准化**：需要在Model SQL中统一不同平台的字段名
5. **缺少shop_id关联**：数据同步中的shop_id需要关联账号管理表获取店铺名称

**根本原因**：数据同步已完成，但Metabase层面的数据建模和Question创建尚未完成，导致前端无法获取标准化数据。

## What Changes

### 核心变更

1. **创建Metabase Models（数据模型）**
   - **Orders Model**：整合订单数据域（日度+周度+月度），统一字段名
   - **Products Model**：整合产品数据域（日度+周度+月度），统一字段名
   - **Traffic Model**：整合流量数据域（日度+周度+月度），统一字段名
   - **Services Model**：整合服务数据域（日度+周度+月度），统一字段名，区分子类型
   - **Inventory Model**：库存快照数据
   - **Analytics Model**：分析数据域

2. **字段标准化策略**
   - 在Model SQL中使用 `COALESCE` 或 `CASE WHEN` 统一不同平台的字段名
   - 示例：`COALESCE(raw_data->>'销售额', raw_data->>'销售金额') AS sales_amount`
   - 创建标准字段映射表（在Model注释中记录）
   - 支持多平台字段名映射（shopee, tiktok, miaoshou等）

3. **创建Metabase Questions（业务查询）**
   - **业务概览KPI Question**：GMV、订单数、买家数、转化率等核心指标
   - **业务概览数据对比 Question**：支持日/周/月度切换，同比、环比对比
   - **店铺赛马 Question**：店铺排名（支持店铺级/账号级切换）
   - **流量排名 Question**：流量指标排名
   - **库存积压 Question**：库存预警数据
   - **经营指标 Question**：门店经营表格数据
   - **清仓排名 Question**：清仓商品排名

4. **Question参数设计**
   - 所有Question支持动态筛选参数：
     - `{{platform}}` - 平台筛选（可选，默认全部）
     - `{{shop_id}}` - 店铺筛选（可选，默认全部）
     - `{{account_id}}` - 账号筛选（可选，默认全部）
     - `{{start_date}}` - 开始日期（必填）
     - `{{end_date}}` - 结束日期（必填）
     - `{{granularity}}` - 粒度筛选（daily/weekly/monthly，可选，默认全部）

5. **关联账号管理表**
   - 通过 `shop_id` 关联 `core.platform_accounts` 表
   - 获取 `store_name`（店铺名称）和 `account_alias`（账号别名）
   - 支持用户手动对齐的shop_id和店铺名称

### 技术细节

#### Model设计原则

1. **使用UNION ALL整合不同粒度**
   ```sql
   SELECT 
       platform_code, shop_id, data_domain, 'daily' as granularity,
       period_start_date, period_end_date, period_start_time, period_end_time,
       COALESCE(raw_data->>'销售额', raw_data->>'销售金额') AS sales_amount,
       raw_data->>'订单号' AS order_id,
       ...
   FROM b_class.fact_shopee_orders_daily
   UNION ALL
   SELECT 
       platform_code, shop_id, data_domain, 'weekly' as granularity,
       period_start_date, period_end_date, period_start_time, period_end_time,
       COALESCE(raw_data->>'销售额', raw_data->>'销售金额') AS sales_amount,
       raw_data->>'订单号' AS order_id,
       ...
   FROM b_class.fact_shopee_orders_weekly
   UNION ALL
   SELECT 
       platform_code, shop_id, data_domain, 'monthly' as granularity,
       period_start_date, period_end_date, period_start_time, period_end_time,
       COALESCE(raw_data->>'销售额', raw_data->>'销售金额') AS sales_amount,
       raw_data->>'订单号' AS order_id,
       ...
   FROM b_class.fact_shopee_orders_monthly
   ```

2. **字段标准化映射**
   - 销售额：`COALESCE(raw_data->>'销售额', raw_data->>'销售金额', raw_data->>'GMV')`
   - 订单号：`COALESCE(raw_data->>'订单号', raw_data->>'订单ID', raw_data->>'order_id')`
   - 产品ID：`COALESCE(raw_data->>'产品ID', raw_data->>'商品ID', raw_data->>'product_id')`
   - 订单状态：`COALESCE(raw_data->>'订单状态', raw_data->>'状态', raw_data->>'order_status')`

3. **关联账号管理表**
   ```sql
   LEFT JOIN core.platform_accounts pa 
       ON orders.shop_id = pa.shop_id 
       AND orders.platform_code = pa.platform
   ```

4. **支持多平台整合**
   - 每个Model需要整合所有平台的数据（shopee, tiktok, miaoshou等）
   - 使用UNION ALL合并不同平台的表
   - 统一字段名和数据类型

#### Question设计原则

1. **使用Native SQL模式**
   - 所有Question使用Native SQL（而非可视化构建器）
   - 原因：需要UNION ALL、复杂字段标准化、动态参数、多表关联

2. **参数化查询**
   - 使用 `{{variable}}` 语法定义参数
   - 支持默认值和可选参数
   - 参数类型：Text, Number, Date, Field Filter

3. **返回格式标准化**
   - 所有Question返回表格格式
   - 列名使用中文（便于前端显示）
   - 包含必要的维度字段（platform_code, shop_id, store_name, period_start_date等）

4. **性能优化**
   - 使用period_start_date和period_end_date进行日期范围查询
   - 创建必要的索引（已在表级别创建）
   - 避免全表扫描，使用WHERE子句过滤

## Impact

- Affected specs: dashboard, data-sync
- Affected code:
  - Metabase配置（Models和Questions）
  - `backend/services/metabase_question_service.py` - 可能需要调整参数映射
  - `env.example` - 需要配置Question ID
  - `frontend/src/api/dashboard.js` - 可能需要调整数据格式

## Risk Assessment

- **低风险**：Metabase Model和Question创建不影响现有数据
- **中风险**：字段标准化映射需要验证所有平台的数据格式
- **低风险**：Question创建可以逐步迭代，不影响现有功能

## Completion Status

- Models设计：待开始
- Questions设计：待开始
- 字段标准化映射：待开始
- Question ID配置：待开始

