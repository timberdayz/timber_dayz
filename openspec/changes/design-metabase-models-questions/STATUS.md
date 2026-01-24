# Metabase Models 和 Questions 实施状态

**最后更新**: 2026-01-24  
**当前阶段**: **🚨 生产环境优化（紧急）** + Question创建阶段

---

## 🚨 紧急事项

**上线倒计时**: 一周后正式上线  
**并发需求**: 50-100 用户同时操作（查询、上传、下载）  
**关键决策**: Metabase 应用数据库从 H2 迁移到 PostgreSQL

**Metabase 官方警告**：
> "The embedded H2 database is for development and evaluation purposes only. For production deployments, use PostgreSQL or MySQL."

---

## 📊 总体进度

| 类别 | 状态 | 进度 | 说明 |
|------|------|------|------|
| **🚨 生产环境优化** | ⏳ 紧急 | 0% | H2 → PostgreSQL，一周内必须完成 |
| **B类数据模型** | ✅ 已完成 | 5/5 (100%) | 所有模型已创建并优化 |
| **A类数据处理** | ✅ 已确定 | 100% | 直接使用表，不创建模型 |
| **部署架构设计** | ✅ 已更新 | 100% | 通过名称动态查询 + **PostgreSQL** |
| **C类数据Question** | ⏳ 进行中 | 0/7 (0%) | 需要创建7个Question |
| **部署架构实现** | ⏳ 待开始 | 0% | 配置清单、初始化脚本等 |

---

## ✅ 已完成工作

### 1. B类数据模型（Metabase Models）

所有模型已创建，使用CTE分层架构，统一数值清洗函数。

#### ✅ Analytics Model
- **文件**: `sql/metabase_models/analytics_model.sql`
- **数据域**: analytics
- **粒度**: daily, weekly, monthly
- **平台**: shopee, tiktok, miaoshou
- **特点**: 
  - CTE分层架构
  - 统一数值清洗（破折号、逗号、空格）
  - 百分比字段自动除以100.0
  - 时间格式转换为秒数

#### ✅ Products Model
- **文件**: `sql/metabase_models/products_model.sql`
- **数据域**: products
- **粒度**: daily, weekly, monthly
- **平台**: shopee, tiktok, miaoshou
- **特点**: 同上

#### ✅ Orders Model
- **文件**: `sql/metabase_models/orders_model.sql`
- **数据域**: orders
- **粒度**: daily, weekly, monthly
- **平台**: shopee, tiktok, miaoshou
- **特点**: 
  - 优化日期/时间字段处理
  - 优先使用数据库已清洗字段（period_start_time, period_start_date）

#### ✅ Inventory Model
- **文件**: `sql/metabase_models/inventory_model.sql`
- **数据域**: inventory
- **粒度**: snapshot（仅快照）
- **平台**: shopee, tiktok, miaoshou
- **特点**: 去重逻辑基于ingest_timestamp DESC

#### ✅ Services Model
- **文件**: `sql/metabase_models/services_model.sql`
- **数据域**: services
- **子类型**: ai_assistant, agent
- **粒度**: daily, weekly, monthly
- **平台**: shopee, tiktok
- **特点**: 
  - 直接使用数据库已清洗的日期字段
  - 统一锚点日期（period_end_date）
  - 支持日期范围查询

### 2. A类数据处理决策

- ✅ **决策**: A类数据直接使用表，不创建Metabase模型
- ✅ **原因**: 
  - 表结构简单，字段已标准化
  - 无需字段映射和数据清洗
  - 性能更好（少一层CTE）
  - 维护成本更低
- ✅ **使用方式**: 在Metabase Question中直接引用 `a_class.sales_targets_a` 等表

### 3. C类数据处理方式

- ✅ **决策**: C类数据通过Metabase Question实时计算
- ✅ **原因**: 
  - C类数据是衍生数据（达成率、对比、排名等）
  - 需要实时计算，不存储结果
  - 需要JOIN A类数据（目标）和B类数据（实际）

### 4. 部署架构设计 ✅ 已更新（H2 → PostgreSQL）

- ✅ **选择方案**: 通过名称动态查询 + **PostgreSQL 应用数据库**
- ✅ **选择理由**:
  - 最小化用户工作量（无需手动维护 Question ID）
  - 本地和云端代码一致（通过名称查询）
  - **生产环境可靠性**：PostgreSQL 支持 50-100 并发用户
  - 自动化部署（初始化脚本处理创建/更新）
  - **官方推荐**：Metabase 明确建议生产环境使用 PostgreSQL/MySQL

#### 为什么从 H2 迁移到 PostgreSQL？

| H2 的问题 | PostgreSQL 的优势 |
|----------|------------------|
| 不支持高并发写入 | 支持 50-100+ 并发 |
| 文件损坏 = 配置全丢 | 事务保护，数据安全 |
| 需停止服务才能备份 | 支持热备份 (pg_dump) |
| 不支持多实例/负载均衡 | 支持高可用部署 |

#### Metabase 数据架构说明（更新）

```
┌─────────────────────────────────────────────────────────────┐
│                   PostgreSQL 容器                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ├── xihong_erp          # 业务数据库（ERP 数据）           │
│  │   ├── a_class schema  # A类数据（目标/配置）             │
│  │   ├── b_class schema  # B类数据（采集数据）              │
│  │   └── public schema   # 主业务表                         │
│  │                                                           │
│  └── metabase_app        # Metabase 应用数据库（新建）      │
│      └── public schema   # Metabase 内部表                  │
│          - Models、Questions、Dashboards                    │
│          - 用户设置、权限配置                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘

环境一致性（本地 = 云端）：
| 环境 | Metabase 应用数据库 | 业务数据源 |
|------|---------------------|-----------|
| 本地 | PostgreSQL (metabase_app) | PostgreSQL (xihong_erp) |
| 云端 | PostgreSQL (metabase_app) | PostgreSQL (xihong_erp) |
```

#### 核心设计

| 组件 | 说明 |
|------|------|
| `config/metabase_config.yaml` | 配置清单（Models/Questions 定义） |
| `scripts/init_metabase.py` | 初始化脚本（幂等创建/更新） |
| `MetabaseQuestionService` | 通过名称动态查询 Question ID（带缓存） |

#### 部署流程

```
Phase 3: Metabase 启动
    ↓
Phase 3.5: init_metabase.py 执行 ← 新增
    │  - 读取 config/metabase_config.yaml
    │  - 通过名称查找 Model/Question
    │  - 不存在 → 创建
    │  - 存在但 SQL 变化 → 更新
    ↓
Phase 4: Backend 启动
    │  - MetabaseQuestionService 通过名称查询 ID
    │  - 缓存 名称→ID 映射
```

#### 运行时流程

```
用户请求 → Frontend → GET /api/business-overview/kpi
                         ↓
              MetabaseQuestionService.execute_question(
                  question_name="business_overview_kpi",
                  parameters={...}
              )
                         ↓
              通过名称查询 ID（带缓存）
              "business_overview_kpi" → ID = 15
                         ↓
              POST http://metabase:3000/api/card/15/query
                         ↓
              Metabase 执行 SQL → 查询 PostgreSQL
                         ↓
              返回结果 → Frontend → 用户
```

#### 环境变量简化

**改进前**:
```bash
METABASE_QUESTION_BUSINESS_OVERVIEW_KPI=12
METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON=13
# ... 每个 Question 一个 ID
```

**改进后**:
```bash
METABASE_URL=http://metabase:3000
METABASE_API_KEY=mb_xxxxxxxxxxxxx=
```

---

## ⏳ 进行中工作

### Metabase Questions（C类数据实时计算）

需要创建7个Question，用于业务概览页面和其他功能。

#### P0 - 业务概览页面必需（6个）

1. ⏳ **business_overview_kpi** - 核心KPI指标
   - 数据源: Orders Model
   - 指标: GMV、订单数、买家数、转化率、平均订单价值
   - 参数: `start_date`, `end_date`, `platforms`, `shops`
   - 后端API: `GET /api/dashboard/business-overview/kpi`

2. ⏳ **business_overview_comparison** - 数据对比
   - 数据源: Orders Model / Analytics Model
   - 指标: 同比、环比对比
   - 参数: `granularity`, `date`, `platforms`, `shops`
   - 后端API: `GET /api/dashboard/business-overview/comparison`

3. ⏳ **business_overview_shop_racing** - 店铺赛马
   - 数据源: Orders Model
   - 指标: 按店铺/平台分组，GMV排序
   - 参数: `granularity`, `date`, `group_by`, `platforms`
   - 后端API: `GET /api/dashboard/business-overview/shop-racing`

4. ⏳ **business_overview_traffic_ranking** - 流量排名
   - 数据源: Analytics Model
   - 指标: 访客数、浏览量排名
   - 参数: `granularity`, `dimension`, `date`, `platforms`, `shops`
   - 后端API: `GET /api/dashboard/business-overview/traffic-ranking`

5. ⏳ **business_overview_inventory_backlog** - 库存积压
   - 数据源: Inventory Model
   - 指标: 库存积压商品、积压天数
   - 参数: `days`, `platforms`, `shops`
   - 后端API: `GET /api/dashboard/business-overview/inventory-backlog`

6. ⏳ **business_overview_operational_metrics** - 经营指标 ⭐ **需要JOIN A类数据**
   - 数据源: 
     - A类: `a_class.sales_targets_a`（目标）
     - B类: Orders Model（实际）
     - A类: `a_class.operating_costs`（运营成本）
   - 计算指标:
     - `monthly_target` - 月目标
     - `monthly_total_achieved` - 当月总达成
     - `monthly_achievement_rate` - 月达成率 = (实际 / 目标) × 100
     - `time_gap` - 时间GAP
     - `estimated_expenses` - 预估费用
   - 参数: `date`, `platforms`, `shops`
   - 后端API: `GET /api/dashboard/business-overview/operational-metrics`
   - **关键**: 需要JOIN A类表和B类模型计算达成率

#### P1 - 其他功能（1个）

7. ⏳ **clearance_ranking** - 清仓排名
   - 数据源: Products Model
   - 指标: 滞销商品排名
   - 参数: `start_date`, `end_date`, `platforms`, `shops`, `limit`
   - 后端API: `GET /api/dashboard/clearance-ranking`

---

## 📋 待完成工作

### 0. 🚨 生产环境优化（紧急 - 一周内必须完成）

**优先级**: P0 - 阻塞上线  
**原因**: H2 不支持 50-100 并发，官方明确警告生产环境必须使用 PostgreSQL/MySQL

| 任务 | 文件 | 状态 |
|------|------|------|
| 创建 metabase_app 数据库 | `docker/init/01-init.sql` | 🚨 待开始 |
| 修改 Metabase Docker 配置 | `docker-compose.metabase.yml` | 🚨 待开始 |
| 更新生产环境配置 | `docker-compose.prod.yml` | 🚨 待开始 |
| 添加环境变量 | `env.example`, `env.production.example` | 🚨 待开始 |
| 本地测试验证 | - | 🚨 待开始 |
| 并发性能验证 | - | 🚨 待开始 |

### 1. 部署架构实现（优先）

| 任务 | 文件 | 状态 |
|------|------|------|
| 创建配置清单 | `config/metabase_config.yaml` | ⏳ 待开始 |
| 创建初始化脚本 | `scripts/init_metabase.py` | ⏳ 待开始 |
| 修改 MetabaseQuestionService | `backend/services/metabase_question_service.py` | ⏳ 待开始 |
| 更新部署脚本 | `scripts/deploy_remote_production.sh` | ⏳ 待开始 |
| 简化环境变量 | `env.example` | ⏳ 待开始 |
| 创建 Question SQL 目录 | `sql/metabase_questions/` | ⏳ 待开始 |

### 2. 创建所有 Metabase Questions

| Question | SQL文件 | 状态 |
|----------|---------|------|
| business_overview_kpi | `sql/metabase_questions/business_overview_kpi.sql` | ⏳ 待开始 |
| business_overview_comparison | `sql/metabase_questions/business_overview_comparison.sql` | ⏳ 待开始 |
| business_overview_shop_racing | `sql/metabase_questions/business_overview_shop_racing.sql` | ⏳ 待开始 |
| business_overview_traffic_ranking | `sql/metabase_questions/business_overview_traffic_ranking.sql` | ⏳ 待开始 |
| business_overview_inventory_backlog | `sql/metabase_questions/business_overview_inventory_backlog.sql` | ⏳ 待开始 |
| business_overview_operational_metrics | `sql/metabase_questions/business_overview_operational_metrics.sql` | ⏳ 待开始 |
| clearance_ranking | `sql/metabase_questions/clearance_ranking.sql` | ⏳ 待开始 |

### 3. 测试和验证
- [ ] 本地测试初始化脚本
- [ ] 测试名称动态查询功能
- [ ] 测试所有 Question 能正常查询
- [ ] 验证业务概览页面数据呈现
- [ ] 验证达成率计算正确（JOIN A类数据）
- [ ] 云端部署验证

---

## 🎯 三类数据处理方式总结

| 数据类型 | 处理方式 | 说明 | 状态 |
|---------|---------|------|------|
| **A类数据** | 直接使用表 | `a_class.sales_targets_a` 等，无需模型 | ✅ 已确定 |
| **B类数据** | Metabase模型 | `Orders Model`, `Analytics Model` 等 | ✅ 已完成（5个） |
| **C类数据** | Metabase Question | 实时计算（达成率、对比、排名等） | ⏳ 进行中（0/7） |

---

## 📝 技术要点

### B类数据模型技术特点
- ✅ CTE分层架构（字段映射 → 数据清洗 → 去重 → 最终输出）
- ✅ 统一数值清洗函数（处理破折号、逗号、空格等特殊字符）
- ✅ 百分比字段自动除以100.0
- ✅ 时间格式字段转换为秒数
- ✅ 基于data_hash去重，优先级 daily > weekly > monthly

### 部署架构技术要点
- ✅ **配置存储**: Metabase 应用数据库改为 **PostgreSQL**（`metabase_app` 数据库）
- ✅ **名称查询**: 通过 Question/Model 名称动态查询 ID，无需硬编码
- ✅ **缓存机制**: MetabaseQuestionService 缓存 名称→ID 映射，避免频繁 API 调用
- ✅ **幂等初始化**: init_metabase.py 支持重复执行，存在则更新，不存在则创建
- ✅ **环境一致性**: 本地和云端统一使用 PostgreSQL，配置完全一致
- ✅ **并发支持**: PostgreSQL 支持 50-100+ 并发用户同时操作

### C类数据Question设计原则
- ⏳ 使用Native SQL模式
- ⏳ 参数化查询（`{{variable}}`语法）
- ⏳ JOIN A类表（目标）和B类模型（实际）计算C类数据
- ⏳ 返回格式标准化（表格格式，中文列名）

---

## 🔗 相关文档

- [SQL编写规范](docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md) - CTE分层架构规范
- [字段标准文档](sql/metabase_models/FIELD_STANDARDS.md) - 系统字段和标准字段定义
- [Metabase Dashboard设置指南](docs/METABASE_DASHBOARD_SETUP.md)
- [业务概览页面API](backend/routers/dashboard_api.py)

---

## 📁 文件结构

```
sql/
├── metabase_models/
│   ├── analytics_model.sql       # ✅ Analytics Model
│   ├── orders_model.sql          # ✅ Orders Model
│   ├── products_model.sql        # ✅ Products Model
│   ├── inventory_model.sql       # ✅ Inventory Model
│   ├── services_model.sql        # ✅ Services Model
│   ├── FIELD_STANDARDS.md        # ✅ 字段标准文档
│   └── FIX_GUIDE.md              # ✅ SQL修复指南
│
└── metabase_questions/           # ⏳ 待创建
    ├── business_overview_kpi.sql
    ├── business_overview_comparison.sql
    ├── business_overview_shop_racing.sql
    ├── business_overview_traffic_ranking.sql
    ├── business_overview_inventory_backlog.sql
    ├── business_overview_operational_metrics.sql
    └── clearance_ranking.sql

config/
└── metabase_config.yaml          # ⏳ 待创建 - 配置清单

scripts/
├── init_metabase.py              # ⏳ 待创建 - 初始化脚本
├── create_metabase_model_tables.py  # ✅ 表预创建脚本
└── verify_metabase_question_ids.py  # ✅ 配置验证脚本（将改为名称验证）
```
