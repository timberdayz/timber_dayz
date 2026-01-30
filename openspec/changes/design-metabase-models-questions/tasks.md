# Tasks: 设计 Metabase 模型和 Question

## 0. Metabase 生产环境优化 [紧急 - 上线前必须完成] 🚨

**背景**：一周后系统正式上线，预期 50-100 并发用户。H2 不支持高并发，必须迁移到 PostgreSQL。

**Metabase 官方警告**：

> "The embedded H2 database is for development and evaluation purposes only. For production deployments, use PostgreSQL or MySQL."

### 0.1 创建 Metabase 应用数据库 ✅ 已完成

- [x] 0.1.1 修改 `docker/postgres/init.sql` ✅
  - ✅ 添加 `CREATE DATABASE metabase_app;`
  - ✅ 授权 `GRANT ALL PRIVILEGES ON DATABASE metabase_app TO erp_user;`
  - ✅ 添加详细注释说明数据库用途

### 0.2 修改 Docker Compose 配置 ✅ 已完成

- [x] 0.2.1 修改 `docker-compose.metabase.yml` ✅
  - ✅ 将 `MB_DB_TYPE: h2` 改为 `MB_DB_TYPE: postgres`
  - ✅ 添加 `MB_DB_HOST`, `MB_DB_PORT`, `MB_DB_DBNAME`, `MB_DB_USER`, `MB_DB_PASS`
  - ✅ 移除 `MB_DB_FILE` 配置
  - ✅ 添加详细的配置说明和架构图

- [ ] 0.2.2 修改 `docker-compose.prod.yml`（如有单独 Metabase 配置）
  - 确保生产环境使用 PostgreSQL 配置（需检查是否有单独配置）

### 0.3 更新环境变量 ✅ 已完成

- [x] 0.3.1 更新 `env.example` ✅
  - ✅ 添加 `METABASE_DB_HOST`, `METABASE_DB_PORT`, `METABASE_DB_DBNAME` 变量
  - ✅ 添加 `METABASE_DB_USER`, `METABASE_DB_PASS` 变量
  - ✅ 添加官方警告注释说明
  - ✅ 标记 Question ID 配置为"已废弃，保留用于向后兼容"

- [x] 0.3.2 更新 `env.production.example` ✅
  - ✅ 添加 Metabase PostgreSQL 环境变量
  - ✅ 添加密钥生成命令说明
  - ✅ 确保生产环境变量模板完整

### 0.4 验证和测试 ⏳ 待执行

- [ ] 0.4.1 本地测试
  - 重建 Docker 容器（需先删除旧的 metabase_data 卷）
  - 验证 Metabase 正常启动
  - 验证数据源连接正常
  - 验证 Models/Questions 能正常创建

- [ ] 0.4.2 性能验证
  - 模拟多用户并发操作
  - 验证无写入冲突

---

## 0.5 数据链路优化 ✅ 已完成（2025-01-27）

**背景**：发现A类/C类数据表的ORM定义未指定schema，导致表被创建在public而非a_class/c_class，造成经营指标SQL读取空表。

### 0.5.1 修复 Schema 配置 ✅

- [x] 修改 `modules/core/db/schema.py`
  - ✅ `SalesTargetA` 添加 `{"schema": "a_class"}`
  - ✅ `SalesCampaignA` 添加 `{"schema": "a_class"}`
  - ✅ `OperatingCost` 添加 `{"schema": "a_class"}`
  - ✅ `Employee` 添加 `{"schema": "a_class"}`
  - ✅ `EmployeeTarget` 添加 `{"schema": "a_class"}`
  - ✅ `AttendanceRecord` 添加 `{"schema": "a_class"}`
  - ✅ `PerformanceConfigA` 添加 `{"schema": "a_class"}`
  - ✅ `EmployeePerformance` 添加 `{"schema": "c_class"}`
  - ✅ `EmployeeCommission` 添加 `{"schema": "c_class"}`
  - ✅ `ShopCommission` 添加 `{"schema": "c_class"}`
  - ✅ `PerformanceScoreC` 添加 `{"schema": "c_class"}`
  - ✅ 重命名索引/约束名称避免冲突（添加 `_a` 或 `_c` 后缀）

### 0.5.2 创建迁移脚本 ✅

- [x] 创建 `migrations/versions/20260127_migrate_a_c_class_tables_to_schema.py`
  - ✅ 将 public 中的 A 类表迁移到 a_class schema
  - ✅ 将 public 中的 C 类表迁移到 c_class schema
  - ✅ 支持数据合并（如果目标 schema 已有表）
  - ✅ 自动清理 public 中的重复表
  - ✅ 幂等设计，可重复执行

### 0.5.3 实现目标管理数据同步 ✅

- [x] 创建 `backend/services/target_sync_service.py`
  - ✅ `TargetSyncService` 类实现同步逻辑
  - ✅ `sync_target_to_a_class()` - 同步单个目标到 a_class.sales_targets_a
  - ✅ `sync_all_active_targets()` - 批量同步所有活跃目标
  - ✅ `delete_target_from_a_class()` - 删除目标时清理 a_class
  - ✅ 使用原生SQL执行upsert（支持跨schema）

- [x] 修改 `backend/routers/target_management.py`
  - ✅ 创建分解时自动调用 `sync_target_after_create()`
  - ✅ 删除目标时自动调用 `sync_target_after_delete()`
  - ✅ 同步失败不影响主流程（仅记录警告日志）

### 0.5.4 待执行

- [ ] 执行迁移脚本：`alembic upgrade head`
- [ ] 验证 a_class/c_class schema 中的表已正确创建
- [ ] 验证 public schema 中的重复表已清理
- [ ] 测试目标管理同步功能

---

## 1. 创建 Metabase Models（B类数据）✅ 已完成

- [x] 1.1 Analytics Model ✅
  - ✅ 整合所有平台的分析数据（shopee, tiktok, miaoshou）
  - ✅ 整合所有粒度（daily, weekly, monthly）
  - ✅ 统一字段名（访客数、浏览量、转化率等）
  - ✅ CTE分层架构（字段映射 → 数据清洗 → 去重 → 最终输出）
  - ✅ 统一数值清洗函数（处理破折号、逗号、空格等特殊字符）
  - ✅ 文件：`sql/metabase_models/analytics_model.sql`

- [x] 1.2 Products Model ✅
  - ✅ 整合所有平台的产品数据
  - ✅ 整合所有粒度（daily, weekly, monthly）
  - ✅ 统一字段名（产品ID、SKU、产品名称等）
  - ✅ CTE分层架构，统一数值清洗
  - ✅ 文件：`sql/metabase_models/products_model.sql`

- [x] 1.3 Orders Model ✅
  - ✅ 整合所有平台的订单数据（shopee, tiktok, miaoshou等）
  - ✅ 整合所有粒度（daily, weekly, monthly）
  - ✅ 统一字段名（销售额、订单号、订单状态等）
  - ✅ CTE分层架构，统一数值清洗
  - ✅ 优化日期/时间字段处理（优先使用数据库已清洗字段）
  - ✅ 文件：`sql/metabase_models/orders_model.sql`

- [x] 1.4 Services Model ✅
  - ✅ 整合所有平台的服务数据
  - ✅ 整合所有粒度（daily, weekly, monthly）
  - ✅ 区分子类型（agent, ai_assistant）
  - ✅ 统一字段名
  - ✅ CTE分层架构，统一数值清洗
  - ✅ 直接使用数据库已清洗的日期字段（period_start_date, period_end_date, metric_date）
  - ✅ 文件：`sql/metabase_models/services_model.sql`

- [x] 1.5 Inventory Model ✅
  - ✅ 库存快照数据（仅snapshot粒度）
  - ✅ 统一字段名（库存数量、仓库ID等）
  - ✅ CTE分层架构，统一数值清洗
  - ✅ 文件：`sql/metabase_models/inventory_model.sql`

- [x] 1.6 A类数据处理决策 ✅
  - ✅ **决策**：A类数据直接使用表，不创建Metabase模型
  - ✅ **原因**：表结构简单，字段已标准化，无需字段映射和数据清洗，性能更好
  - ✅ **使用方式**：在Metabase Question中直接引用 `a_class.sales_targets_a` 等表

## 2. 字段标准化映射 ✅ 已完成（集成在Models中）

**说明**：字段标准化映射已集成在B类数据模型中，使用CTE分层架构统一处理。

- [x] 2.1 订单字段标准化 ✅
  - ✅ 销售额：销售额/销售金额/GMV → `sales_amount`
  - ✅ 订单号：订单号/订单ID/order_id → `order_id`
  - ✅ 订单状态：订单状态/状态/order_status → `order_status`
  - ✅ 订单日期：订单日期/日期/order_date → `order_date`
  - ✅ 买家数：买家数/买家/buyer_count → `buyer_count`
  - ✅ 订单数：订单数/订单数量/order_count → `order_count`
  - ✅ 实现位置：`sql/metabase_models/orders_model.sql`

- [x] 2.2 产品字段标准化 ✅
  - ✅ 产品ID：产品ID/商品ID/product_id → `product_id`
  - ✅ SKU：SKU/平台SKU/platform_sku → `platform_sku`
  - ✅ 产品名称：产品名称/商品名称/product_name → `product_name`
  - ✅ 实现位置：`sql/metabase_models/products_model.sql`

- [x] 2.3 流量字段标准化 ✅
  - ✅ 访客数：访客数/访客/visitor_count → `visitor_count`
  - ✅ 浏览量：浏览量/浏览/pv → `page_views`
  - ✅ 转化率：转化率/转化/conversion_rate → `conversion_rate`
  - ✅ 点击率：点击率/点击/click_rate → `click_rate`
  - ✅ 实现位置：`sql/metabase_models/analytics_model.sql`

- [x] 2.4 服务字段标准化 ✅
  - ✅ 访客数：访客数/visitors → `visitor_count`
  - ✅ 聊天数：聊天询问/chats → `chat_count`
  - ✅ 订单数：订单/orders → `order_count`
  - ✅ 满意度：满意度/satisfaction → `satisfaction`
  - ✅ 实现位置：`sql/metabase_models/services_model.sql`

- [x] 2.5 库存字段标准化 ✅
  - ✅ 可用库存：可用库存/available_stock → `available_stock`
  - ✅ 在库库存：在库库存/on_hand_stock → `on_hand_stock`
  - ✅ 库存价值：库存价值/inventory_value → `inventory_value`
  - ✅ 实现位置：`sql/metabase_models/inventory_model.sql`

- [x] 2.6 数值清洗统一处理 ✅
  - ✅ 处理破折号（—、–、-）
  - ✅ 处理千分位逗号（,）
  - ✅ 处理空格（ ）
  - ✅ 处理百分比（%），自动除以100.0
  - ✅ 处理时间格式（HH:MM:SS），转换为秒数
  - ✅ 使用REGEXP_REPLACE移除所有非数字字符
  - ✅ 实现位置：所有B类数据模型的cleaned CTE层

- [ ] 2.1 订单字段标准化
  - 销售额：销售额/销售金额/GMV → `sales_amount`
  - 订单号：订单号/订单ID/order_id → `order_id`
  - 订单状态：订单状态/状态/order_status → `order_status`
  - 订单日期：订单日期/日期/order_date → `order_date`
  - 买家数：买家数/买家/buyer_count → `buyer_count`
  - 订单数：订单数/订单数量/order_count → `order_count`

- [ ] 2.2 产品字段标准化
  - 产品ID：产品ID/商品ID/product_id → `product_id`
  - SKU：SKU/平台SKU/platform_sku → `platform_sku`
  - 产品名称：产品名称/商品名称/product_name → `product_name`
  - 产品标题：产品标题/商品标题/product_title → `product_title`

- [ ] 2.3 流量字段标准化
  - 访客数：访客数/访客/visitor_count → `visitor_count`
  - 浏览量：浏览量/浏览/pv → `page_view`
  - 转化率：转化率/转化/conversion_rate → `conversion_rate`
  - 点击率：点击率/点击/click_rate → `click_rate`

- [ ] 2.4 服务字段标准化
  - 服务ID：服务ID/service_id → `service_id`
  - 服务类型：服务类型/service_type → `service_type`
  - 响应时间：响应时间/response_time → `response_time`

- [ ] 2.5 库存字段标准化
  - 库存数量：库存数量/库存/stock_quantity → `stock_quantity`
  - 仓库ID：仓库ID/仓库/warehouse_id → `warehouse_id`
  - 库存金额：库存金额/库存价值/stock_value → `stock_value`

## 3. 创建 Metabase Questions（C类数据实时计算）⏳ 进行中

### 3.1 业务概览页面Question（P0 - 必须）

- [x] 3.1.1 business_overview_kpi - 核心KPI指标 ✅ **已可用**
  - **用途**：提供业务概览页面的6个核心KPI指标
  - **数据源**：Orders Model
  - **计算指标**：GMV、订单数、买家数、转化率、平均订单价值、销售单数等
  - **参数**：`{{month}}`（月初 YYYY-MM-01）, `{{platform}}`
  - **返回格式**：单行数据，包含所有KPI指标
  - **后端API**：`GET /api/dashboard/business-overview/kpi`
  - **前端**：按月、平台筛选，Question ID 已配置于 `.env`

- [x] 3.1.2 business_overview_comparison - 数据对比 ✅ **已优化完成 v4.21.0**
  - **用途**：提供日/周/月度数据对比（当期/上期/平均/环比）
  - **数据源**：Orders Model、Analytics Model、public.sales_targets、a_class.target_breakdown
  - **计算指标**：本期/上期/平均/环比；目标达成率
  - **参数**：`{{granularity}}`（daily/weekly/monthly）、`{{date}}`（YYYY-MM-DD，周度须传该周周一）、`{{platform}}`
  - **时间定义**：日度=单日；周度=周一～周日；月度=当月1～月末。详见 proposal 与 specs/metabase-questions.md
  - **平均定义**：日度=本月平均（本月数据/本月天数）；周度=本周数据/7；月度=本月数据/本月天数；转化率本期只算一个比率
  - **引用的字段**：按周期汇总时用 `metric_date` 落在周期范围内匹配，勿用 period_start_date/period_end_date 等于周期起止；销售额用 paid_amount
  - **返回格式**：单行多列（xxx_today/xxx_yesterday/xxx_average/xxx_change、target_xxx）
  - **后端API**：`GET /api/dashboard/business-overview/comparison`
  - **前端**：周度时传参规范为该周周一，避免同周跳变

- [ ] 3.1.3 business_overview_shop_racing - 店铺赛马
  - **用途**：店铺/平台排名对比
  - **数据源**：Orders Model
  - **计算指标**：按店铺/平台分组，GMV排序
  - **参数**：`{{granularity}}`, `{{date}}`, `{{group_by}}`, `{{platforms}}`
  - **返回格式**：多行数据，每行一个店铺/平台，包含排名
  - **后端API**：`GET /api/dashboard/business-overview/shop-racing`

- [ ] 3.1.4 business_overview_traffic_ranking - 流量排名
  - **用途**：流量相关指标排名
  - **数据源**：Analytics Model
  - **计算指标**：访客数、浏览量排名
  - **参数**：`{{granularity}}`, `{{dimension}}`, `{{date}}`, `{{platforms}}`, `{{shops}}`
  - **返回格式**：多行数据，每行一个店铺，包含排名
  - **后端API**：`GET /api/dashboard/business-overview/traffic-ranking`

- [ ] 3.1.5 business_overview_inventory_backlog - 库存积压
  - **用途**：库存积压分析
  - **数据源**：Inventory Model
  - **计算指标**：库存积压商品、积压天数
  - **参数**：`{{days}}`, `{{platforms}}`, `{{shops}}`
  - **返回格式**：多行数据，每行一个SKU，包含积压信息
  - **后端API**：`GET /api/dashboard/business-overview/inventory-backlog`

- [x] 3.1.6 business_overview_operational_metrics - 经营指标 ✅ **已可用** ⭐ **需要JOIN A类数据**
  - **用途**：门店经营表格数据（包含达成率、今日销售、今日销售单数、经营结果）
  - **数据源**：
    - A类数据：`a_class.sales_targets_a`（目标）
    - B类数据：Orders Model（实际）
    - A类数据：`a_class.operating_costs`（运营成本）
  - **计算指标**：
    - `monthly_target` - 月目标（来自A类 `sales_targets_a`）
    - `monthly_total_achieved` - 当月总达成（来自B类 Orders Model 聚合到所选日期）
    - `today_sales` / `today_order_count` - 所选日期的销售额与销售单数
    - `monthly_achievement_rate` - 月达成率
    - `time_gap` - 时间GAP
    - `estimated_expenses` - 预估费用（来自A类 `operating_costs`）
    - `operating_result` / `operating_result_text` - 经营结果（盈利/亏损）
  - **参数**：`{{month}}`（具体日期 YYYY-MM-DD）, `{{platform}}`
  - **返回格式**：单行数据，包含所有经营指标
  - **后端API**：`GET /api/dashboard/business-overview/operational-metrics`
  - **前端**：独立日期选择器、两行布局（今日销售单数、经营结果竖状最右侧），Question ID 已配置
  - **关键SQL**：JOIN `a_class.sales_targets_a` 和 Orders Model 计算达成率；SQL 更新后运行 `init_metabase.py` 同步

### 3.2 其他功能Question（P1 - 重要）

- [ ] 3.2.1 clearance_ranking - 清仓排名
  - **用途**：清仓商品排名
  - **数据源**：Products Model
  - **计算指标**：滞销商品排名
  - **参数**：`{{start_date}}`, `{{end_date}}`, `{{platforms}}`, `{{shops}}`, `{{limit}}`
  - **返回格式**：多行数据，每行一个商品，包含排名
  - **后端API**：`GET /api/dashboard/clearance-ranking`

## 4. 部署架构实现 ✅ 部分完成

### 4.1 创建配置清单 ✅ 已完成

- [x] 4.1.1 创建 `config/metabase_config.yaml` ✅
  - ✅ 定义所有 Models 配置（名称、SQL文件路径、描述）
  - ✅ 定义所有 Questions 配置（名称、显示名、SQL文件路径、参数）
  - ✅ 定义数据库连接配置
  - ✅ 定义 Collection 组织结构

### 4.2 创建初始化脚本 ✅ 已完成

- [x] 4.2.1 创建 `scripts/init_metabase.py` ✅
  - ✅ 实现 MetabaseInitializer 类
  - ✅ 实现幂等操作（存在则更新，不存在则创建）
  - ✅ 通过名称查找 Model/Question
  - ✅ 支持 API Key 认证
  - ✅ 添加错误处理和日志
  - ✅ 支持 --dry-run 和 --verbose 参数

### 4.3 修改 MetabaseQuestionService

- [ ] 4.3.1 实现通过名称动态查询
  - 添加 `_question_cache: dict[str, int]` 缓存
  - 实现 `_load_question_cache()` 方法
  - 实现 `get_question_id(question_name: str)` 方法
  - 修改 `execute_question()` 接受名称参数

- [ ] 4.3.2 移除环境变量 ID 依赖
  - 移除 `METABASE_QUESTION_XXX` 环境变量
  - 改为通过名称调用

### 4.4 更新部署脚本

- [ ] 4.4.1 修改 `scripts/deploy_remote_production.sh`
  - 添加 Phase 3.5: Metabase 配置初始化
  - 等待 Metabase 健康检查通过后执行 init_metabase.py

### 4.5 更新环境变量配置

- [ ] 4.5.1 更新 `env.example`
  - 简化 Metabase 配置（只需 URL 和 API Key）
  - 移除 Question ID 环境变量
  - 添加注释说明

### 4.6 创建 Question SQL 文件目录 ✅ 已完成

- [x] 4.6.1 创建 `sql/metabase_questions/` 目录 ✅
- [x] 4.6.2 创建 Question SQL 模板文件 ✅
  - ✅ business_overview_kpi.sql
  - ✅ business_overview_comparison.sql
  - ✅ business_overview_shop_racing.sql
  - ✅ business_overview_traffic_ranking.sql
  - ✅ business_overview_inventory_backlog.sql
  - ✅ business_overview_operational_metrics.sql
  - ✅ clearance_ranking.sql

## 5. 测试和验证 [TODO]

- [ ] 5.1 测试Model数据完整性
  - 验证所有平台的数据都能正确整合
  - 验证字段标准化映射正确
  - 验证关联账号管理表正确

- [ ] 5.2 测试Question查询性能
  - 验证查询响应时间
  - 验证大数据量下的性能
  - 优化慢查询

- [ ] 5.3 测试Question参数
  - 验证所有参数正确传递
  - 验证参数默认值正确
  - 验证参数筛选正确

- [ ] 5.4 测试前端集成
  - 验证前端能正确调用Question API
  - 验证数据格式与前端期望一致
  - 验证错误处理正确
