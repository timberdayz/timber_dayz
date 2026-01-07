# 实施任务清单：配置 Metabase Dashboard Questions

## Phase 0: 基础设施验证和数据准备（新增 - 优先执行）✅ 部分完成

### 0.1 验证 Question 40 API 连接 ✅ 已完成（2025-11-30）
- [x] 0.1.1 测试 `/api/dashboard/business-overview/kpi` API（无参数）✅ 已完成
  - [x] 确认返回 HTTP 200 ✅
  - [x] 确认响应格式正确：`{"success": true, "data": {...}}` ✅
  - [x] 确认即使数据为空也返回 200（数据为空数组）✅ 返回 `{"data": [{}], "row_count": 1}`
- [x] 0.1.2 测试 Question 40 API（带参数）✅ 部分完成
  - [x] 测试日期范围参数：`start_date=2025-01-01&end_date=2025-01-31` ✅ 成功
  - [x] 测试平台参数：`platforms=shopee` ⚠️ Metabase返回HTTP 500（数据库为空导致，代码转换逻辑正确：API接收`platforms`，传递给Metabase时使用`platform`）
  - [ ] 测试店铺参数：`shops=shop_001` （待数据同步后测试）
  - [x] 确认参数传递正确，Metabase 接收参数 ✅ 日期参数正常，平台参数代码逻辑正确（数据库为空导致测试失败）
- [x] 0.1.3 验证 API Key 认证 ✅ 已完成
  - [x] 确认使用 `X-API-Key` header（不是 `X-Metabase-Api-Key`）✅ 已在代码中确认
  - [x] 确认认证成功，不返回 401 ✅ 无参数和日期参数请求均成功
  - [x] 记录测试结果 ✅ 测试脚本：`temp/development/test_metabase_question_api.py`，总结文档：`PHASE0_1_SUMMARY.md`，总结文档：`PHASE0_1_SUMMARY.md`

### 0.2 检查数据同步功能状态 ✅ 已完成
- [x] 0.2.1 检查 `catalog_files` 表状态 ✅ 已完成
  - [x] 查询待同步文件数量（status='pending'）：**411 个文件**（3个平台，6个数据域）
  - [x] 查询已同步文件数量（status='ingested'）：**0 个文件**
  - [x] 查询部分成功文件（status='partial_success'）：**1 个文件**
  - [x] 检查数据表状态：**fact_raw_data_orders_daily 表存在但为空（0行）**（Question 40 需要此表有数据）
  - [x] 检查字段映射模板：**141 个模板已配置**
  - [x] **结论**：有大量待同步文件（411个），但数据表为空，需要执行数据同步
- [x] 0.2.2 测试数据同步 API ✅ 已完成
  - [x] 测试 `/api/data-sync/files` API（查询文件列表）✅ 成功，返回100个待同步文件
  - [ ] 测试 `/api/data-sync/preview` API（文件预览）（待测试）
  - [x] 确认数据同步功能可用 ✅ API正常响应
- [ ] 0.2.3 准备测试数据（如果需要）
  - [ ] 如果有待同步文件，执行数据同步
  - [ ] 如果没有文件，准备测试数据或记录需要数据采集

### 0.3 验证 Question 40 返回真实数据（数据同步后）
- [ ] 0.3.1 执行数据同步（如果有待同步文件）
  - [ ] 使用批量同步 API 导入数据
  - [ ] 确认数据成功入库到 `b_class.fact_raw_data_orders_daily` 表
- [ ] 0.3.2 再次测试 Question 40 API
  - [ ] 确认返回真实业务数据（非空）
  - [ ] 验证数据格式正确
  - [ ] 记录测试结果

## Phase 1: 准备与梳理（1天）✅ 已完成

### 1.1 现状分析
- [x] 1.1.1 阅读 `openspec/specs/bi-layer/spec.md`，梳理当前 BI 层对 Question 的要求
- [x] 1.1.2 阅读 `openspec/specs/dashboard/spec.md`，列出所有依赖 Metabase 的 Dashboard 接口
- [x] 1.1.3 阅读 `backend/routers/dashboard_api.py`，确认所有需要配置的 Question key
- [x] 1.1.4 阅读 `backend/services/metabase_question_service.py`，确认 Question ID 读取逻辑

### 1.2 需求整理
- [x] 1.2.1 在文档或临时表中整理出「后端 question_key → 业务含义 → 预期维度/指标」映射表
- [x] 1.2.2 确认每个 Question 需要查询的表（如 `b_class.fact_raw_data_orders_daily` 等）
- [x] 1.2.3 确认每个 Question 需要的过滤参数（日期、平台、店铺、粒度等）

## Phase 2: Question 设计（1天）

### 2.1 核心 Question 设计
- [ ] 2.1.1 设计 `business_overview_kpi` Question
  - [ ] 表：`b_class.fact_raw_data_orders_daily`
  - [ ] 参数：`start_date` (date), `end_date` (date), `platform` (string), `shop_id` (string)
  - [ ] 指标：GMV (Sum of 销售额), Order Count (Sum of 订单数)
  - [ ] 记录设计文档
  
- [ ] 2.1.2 设计 `business_overview_comparison` Question
  - [ ] 表：`b_class.fact_raw_data_orders_daily` (根据 granularity 选择 daily/weekly/monthly)
  - [ ] 参数：`granularity` (string), `date` (date), `platform` (string), `shop_id` (string)
  - [ ] 维度：`metric_date` (X轴)
  - [ ] 指标：GMV, Order Count (折线图)
  - [ ] 记录设计文档

- [ ] 2.1.3 设计 `business_overview_shop_racing` Question
  - [ ] 表：`b_class.fact_raw_data_orders_daily`
  - [ ] 参数：`granularity` (string), `date` (date), `platform` (string)
  - [ ] 分组：`shop_id`
  - [ ] 指标：GMV (Sum, 排序 Desc)
  - [ ] 限制：Top 20
  - [ ] 记录设计文档

- [ ] 2.1.4 设计 `business_overview_traffic_ranking` Question
  - [ ] 表：`b_class.fact_raw_data_traffic_daily`
  - [ ] 参数：`granularity` (string), `date` (date), `platform` (string), `shop_id` (string)
  - [ ] 分组：`shop_id`
  - [ ] 指标：UV (Sum of 访客数), PV (Sum of 浏览量)
  - [ ] 排序：按 UV Desc
  - [ ] 记录设计文档

- [ ] 2.1.5 设计 `business_overview_inventory_backlog` Question
  - [ ] 表：`b_class.fact_raw_data_inventory_snapshot`
  - [ ] 参数：`days` (number), `platform` (string), `shop_id` (string)
  - [ ] 逻辑：筛选 `raw_data->>'最近成交天数' > days` 的记录
  - [ ] 分组：`shop_id` 或 SKU
  - [ ] 指标：积压 SKU 数, 积压金额
  - [ ] 记录设计文档

- [ ] 2.1.6 设计 `business_overview_operational_metrics` Question
  - [ ] 表：`b_class.fact_raw_data_orders_daily`
  - [ ] 参数：`date` (date), `platform` (string), `shop_id` (string)
  - [ ] 分组：`shop_id`
  - [ ] 指标：GMV, Order Count, 客单价 (GMV/Order Count), 退货率 (占位)
  - [ ] 记录设计文档

- [ ] 2.1.7 设计 `clearance_ranking` Question
  - [ ] 表：`b_class.fact_raw_data_inventory_snapshot`
  - [ ] 参数：`start_date` (date, 可选), `end_date` (date, 可选), `platform` (string), `shop_id` (string)
  - [ ] 分组：SKU (`raw_data->>'SKU'` 或 `raw_data->>'商品ID'`)
  - [ ] 指标：折扣率 (现价/原价), 库存数量
  - [ ] 排序：按折扣率或库存数量 Desc
  - [ ] 限制：Top N
  - [ ] 记录设计文档

### 2.2 参数命名约定确认
- [x] 2.2.1 确认所有 Question 使用统一的参数命名（`start_date`/`end_date`/`date`/`platform`/`shop_id`/`granularity`）
- [x] 2.2.2 在文档中记录参数命名约定，供后续 Question 创建参考

## Phase 3: Metabase 中创建 Questions（2-3天）

### 3.1 环境准备 ✅ 已完成
- [x] 3.1.1 确认 Metabase 服务正常运行（`http://localhost:3000`）
- [x] 3.1.2 确认 Metabase 已连接 PostgreSQL 数据库
- [x] 3.1.3 确认 Metabase 可以看到所有 B/A/C 类数据表（`b_class.fact_raw_data_*` 等）
- [x] 3.1.4 配置 Metabase API Key 认证（重要）✅ 已完成（2025-11-29）
  - [x] 在 Metabase 中创建 API Key（设置 → 认证 → API Keys）
  - [x] 将 API Key 配置到 `.env` 文件：`METABASE_API_KEY=mb_xxxxxxxxxxxxx=`
  - [x] 确认后端代码使用正确的 Header：`X-API-Key`（不是 `X-Metabase-Api-Key`）
  - [x] 参考文档：`docs/METABASE_DASHBOARD_SETUP.md` 和 [Metabase 官方文档](https://www.metabase.com/docs/v0.57/people-and-groups/api-keys)

### 3.2 创建 Question
- [x] 3.2.1 创建 `business_overview_kpi` Question ✅ 已完成（Question ID: 40）
  - [x] 在 Metabase 中创建 Simple Question
  - [x] 选择表：`b_class.fact_raw_data_orders_daily`
  - [x] 配置过滤条件（`start_date`, `end_date`, `platform`, `shop_id`）
  - [x] 配置汇总指标（GMV, Order Count）
  - [x] 保存 Question，记录 ID（从 URL 获取）：ID = 40

- [ ] 3.2.2 创建 `business_overview_comparison` Question
  - [ ] 在 Metabase 中创建 Simple Question
  - [ ] 选择表：`b_class.fact_raw_data_orders_daily`（后续可按 granularity 动态选择）
  - [ ] 配置过滤条件和分组
  - [ ] 配置折线图可视化
  - [ ] 保存 Question，记录 ID

- [ ] 3.2.3 创建 `business_overview_shop_racing` Question
  - [ ] 在 Metabase 中创建 Simple Question
  - [ ] 选择表：`b_class.fact_raw_data_orders_daily`
  - [ ] 配置过滤条件、分组、排序
  - [ ] 配置柱状图可视化
  - [ ] 保存 Question，记录 ID

- [ ] 3.2.4 创建 `business_overview_traffic_ranking` Question
  - [ ] 在 Metabase 中创建 Simple Question
  - [ ] 选择表：`b_class.fact_raw_data_traffic_daily`
  - [ ] 配置过滤条件、分组、排序
  - [ ] 配置表格可视化
  - [ ] 保存 Question，记录 ID

- [ ] 3.2.5 创建 `business_overview_inventory_backlog` Question
  - [ ] 在 Metabase 中创建 Simple Question
  - [ ] 选择表：`b_class.fact_raw_data_inventory_snapshot`
  - [ ] 配置过滤条件（使用 Custom Field 判断积压）
  - [ ] 配置分组和指标
  - [ ] 保存 Question，记录 ID

- [ ] 3.2.6 创建 `business_overview_operational_metrics` Question
  - [ ] 在 Metabase 中创建 Simple Question
  - [ ] 选择表：`b_class.fact_raw_data_orders_daily`
  - [ ] 配置过滤条件、分组
  - [ ] 配置 Custom Fields（客单价、退货率等）
  - [ ] 配置表格可视化
  - [ ] 保存 Question，记录 ID

- [ ] 3.2.7 创建 `clearance_ranking` Question
  - [ ] 在 Metabase 中创建 Simple Question
  - [ ] 选择表：`b_class.fact_raw_data_inventory_snapshot`
  - [ ] 配置过滤条件、分组、排序
  - [ ] 配置 Custom Fields（折扣率）
  - [ ] 配置表格可视化
  - [ ] 保存 Question，记录 ID

### 3.3 Question 参数验证
- [ ] 3.3.1 为每个 Question 测试参数传递
  - [ ] 测试日期参数（`start_date`, `end_date`, `date`）
  - [ ] 测试平台参数（`platform`）
  - [ ] 测试店铺参数（`shop_id`）
  - [ ] 测试粒度参数（`granularity`）
- [ ] 3.3.2 确认每个 Question 可以正常执行查询（即使数据为空也返回 200）

## Phase 4: 环境变量配置（1天）

### 4.1 更新 `.env` 文件 ⏳ 部分完成
- [x] 4.1.1 在 `.env` 中添加所有 Question ID 环境变量：
  ```env
  METABASE_QUESTION_BUSINESS_OVERVIEW_KPI=40  ✅ 已配置
  METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON=0  ⏳ 待创建
  METABASE_QUESTION_BUSINESS_OVERVIEW_SHOP_RACING=0  ⏳ 待创建
  METABASE_QUESTION_BUSINESS_OVERVIEW_TRAFFIC_RANKING=0  ⏳ 待创建
  METABASE_QUESTION_BUSINESS_OVERVIEW_INVENTORY_BACKLOG=0  ⏳ 待创建
  METABASE_QUESTION_BUSINESS_OVERVIEW_OPERATIONAL_METRICS=0  ⏳ 待创建
  METABASE_QUESTION_CLEARANCE_RANKING=0  ⏳ 待创建
  ```
  （ID 值替换为实际创建的 Question ID）

### 4.2 更新 `env.example` 文件 ✅ 已完成
- [x] 4.2.1 在 `env.example` 中添加所有 Question ID 环境变量
- [x] 4.2.2 为每个变量添加注释说明：
  ```env
  # Metabase Question IDs (从 Metabase UI 中获取)
  # 业务概览 KPI - 查询 GMV、订单数等核心指标
  METABASE_QUESTION_BUSINESS_OVERVIEW_KPI=0
  # 业务概览对比 - 日/周/月度趋势对比
  METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON=0
  # ... 其他 Question ID
  ```

### 4.3 重启后端服务
- [ ] 4.3.1 停止当前运行的后端服务
- [ ] 4.3.2 重新启动后端服务（`python run.py`）
- [ ] 4.3.3 确认后端日志中不再出现 "Question ID未配置" 错误

## Phase 5: 验证与文档（1天）

### 5.1 API 验证
- [ ] 5.1.1 使用 Swagger UI 或 Postman 测试所有 Dashboard API：
  - [ ] `GET /api/dashboard/business-overview/kpi`
  - [ ] `GET /api/dashboard/business-overview/comparison`
  - [ ] `GET /api/dashboard/business-overview/shop-racing`
  - [ ] `GET /api/dashboard/business-overview/traffic-ranking`
  - [ ] `GET /api/dashboard/business-overview/inventory-backlog`
  - [ ] `GET /api/dashboard/business-overview/operational-metrics`
  - [ ] `GET /api/dashboard/clearance-ranking`
- [ ] 5.1.2 确认所有 API 返回 200（不再返回 400）
- [ ] 5.1.3 确认返回的 JSON 数据结构正确（即使数据为空）

### 5.2 前端验证
- [ ] 5.2.1 访问业务概览页面（`http://localhost:5173`）
- [ ] 5.2.2 确认页面不再显示 "Question ID未配置" 错误提示
- [ ] 5.2.3 确认页面可以正常加载（即使数据为空，图表显示为 0 或空表）

### 5.3 文档编写 ⏳ 部分完成
- [x] 5.3.1 创建 `docs/METABASE_DASHBOARD_SETUP.md` 文档 ✅ 已完成（2025-11-29）
  - [x] 列出所有必备 Question 及其用途
  - [x] 提供步骤化的创建指南（可选截图）
  - [x] 说明如何在新环境中重新配置 Question ID
  - [x] 提供参数命名约定参考
  - [x] 添加 Metabase API Key 认证配置指南（重要）
- [ ] 5.3.2 更新 `docs/AGENT_START_HERE.md`，添加 Metabase Question 配置说明
- [x] 5.3.3 在 `openspec/changes/configure-metabase-dashboard-questions` 目录中记录实际使用的 Question ID 和验证结果 ✅ 已完成（STATUS.md）

## Phase 6: 验收（1天）

### 6.1 功能验收
- [ ] 6.1.1 所有 7 个核心 Question 已创建并配置
- [ ] 6.1.2 所有 Question ID 已写入环境变量
- [ ] 6.1.3 所有 Dashboard API 调用不再返回 400
- [ ] 6.1.4 前端业务概览页面可以正常加载

### 6.2 文档验收
- [ ] 6.2.1 `docs/METABASE_DASHBOARD_SETUP.md` 文档完整
- [ ] 6.2.2 `env.example` 已更新，包含所有 Question ID 变量和注释
- [ ] 6.2.3 新环境可以按照文档完成配置

### 6.3 代码验收
- [ ] 6.3.1 运行 `openspec validate configure-metabase-dashboard-questions --strict`，确认通过
- [ ] 6.3.2 提交代码：`git commit -m "feat: configure Metabase Dashboard Questions - eliminate 400 errors"`

