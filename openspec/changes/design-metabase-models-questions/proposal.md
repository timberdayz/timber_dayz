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

1. **创建Metabase Models（B类数据模型）** ✅ **已完成**
   - ✅ **Analytics Model**：整合分析数据域（日度+周度+月度），统一字段名，CTE分层架构
   - ✅ **Products Model**：整合产品数据域（日度+周度+月度），统一字段名，CTE分层架构
   - ✅ **Orders Model**：整合订单数据域（日度+周度+月度），统一字段名，CTE分层架构，优化日期/时间字段处理
   - ✅ **Inventory Model**：库存快照数据，CTE分层架构，仅snapshot粒度
   - ✅ **Services Model**：整合服务数据域（日度+周度+月度），统一字段名，区分子类型（ai_assistant/agent），CTE分层架构，直接使用数据库已清洗的日期字段

   **技术特点**：
   - 使用CTE分层架构（字段映射 → 数据清洗 → 去重 → 最终输出）
   - 统一数值清洗函数（处理破折号、逗号、空格等特殊字符）
   - 百分比字段自动除以100.0
   - 时间格式字段转换为秒数
   - 基于data_hash去重，优先级 daily > weekly > monthly

2. **A类数据处理决策** ✅ **已确定**
   - ✅ **决策**：A类数据直接使用表，不创建Metabase模型
   - ✅ **原因**：表结构简单，字段已标准化，无需字段映射和数据清洗，性能更好
   - ✅ **使用方式**：在Metabase Question中直接引用 `a_class.sales_targets_a` 等表

3. **字段标准化策略**
   - 在Model SQL中使用 `COALESCE` 或 `CASE WHEN` 统一不同平台的字段名
   - 示例：`COALESCE(raw_data->>'销售额', raw_data->>'销售金额') AS sales_amount`
   - 创建标准字段映射表（在Model注释中记录）
   - 支持多平台字段名映射（shopee, tiktok, miaoshou等）

4. **创建Metabase Questions（C类数据实时计算）** ⏳ **进行中**
   - ✅ **business_overview_kpi**：核心KPI指标（GMV、订单数、买家数、转化率等）— **已可用**
   - ✅ **business_overview_comparison**：数据对比（支持日/周/月度切换，当期/上期/平均/环比）— **已优化完成 v4.21.0**
   - ✅ **business_overview_shop_racing**：店铺赛马（店铺排名，支持店铺级/账号级切换，含目标、完成率）— **已可用**
   - ✅ **business_overview_traffic_ranking**：流量排名（访客数/浏览量排名，日/周/月，按店铺/账号维度，含本期/上期与环比）— **已可用**
   - ⏳ **business_overview_inventory_backlog**：库存积压（库存预警数据）
   - ✅ **business_overview_operational_metrics**：经营指标（月目标、达成率、今日销售、今日销售单数、经营结果等，JOIN A类数据）— **已可用**
   - ⏳ **clearance_ranking**：清仓排名（清仓商品排名）

   **设计原则**：
   - 使用Native SQL模式
   - 参数化查询（`{{variable}}`语法）
   - JOIN A类表（目标）和B类模型（实际）计算C类数据（达成率、对比等）
   - 返回格式标准化（表格格式，中文列名）

5. **Question参数设计**
   - 所有Question支持动态筛选参数：
     - `{{platform}}` - 平台筛选（可选，默认全部）
     - `{{shop_id}}` - 店铺筛选（可选，默认全部）
     - `{{account_id}}` - 账号筛选（可选，默认全部）
     - `{{start_date}}` - 开始日期（必填）
     - `{{end_date}}` - 结束日期（必填）
     - `{{granularity}}` - 粒度筛选（daily/weekly/monthly，可选，默认全部）

6. **三类数据处理方式总结**
   - **A类数据**：直接使用表（`a_class.sales_targets_a`等），无需模型
   - **B类数据**：使用Metabase模型（`Orders Model`等），已创建5个模型
   - **C类数据**：通过Metabase Question实时计算（达成率、对比、排名等），需要创建7个Question

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
   LEFT JOIN   core.platform_accounts pa
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

## 部署架构设计

### 部署策略选择

**选择方案**：通过名称动态查询 + **PostgreSQL 应用数据库**

**选择理由**：

1. **最小化用户工作量**：无需手动维护 Question ID 环境变量
2. **本地和云端代码一致**：通过名称查询，无需关心 ID 差异
3. **生产环境可靠性**：PostgreSQL 支持高并发（50-100用户同时操作）
4. **自动化部署**：初始化脚本自动创建/更新配置
5. **官方推荐**：Metabase 官方明确建议生产环境使用 PostgreSQL/MySQL

### 为什么不使用 H2？

| 问题       | H2 的限制              | PostgreSQL 的优势    |
| ---------- | ---------------------- | -------------------- |
| **并发**   | 不支持高并发写入       | 支持 50-100+ 并发    |
| **可靠性** | 文件损坏 = 配置全丢    | 事务保护，数据安全   |
| **备份**   | 需停止服务才能安全备份 | 支持热备份 (pg_dump) |
| **扩展**   | 不支持多实例/负载均衡  | 支持高可用部署       |
| **升级**   | 升级时文件可能损坏     | 升级风险低           |

**Metabase 官方警告**：

> "The embedded H2 database is for development and evaluation purposes only. For production deployments, use PostgreSQL or MySQL."

### Metabase 数据架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     Metabase 数据架构                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  PostgreSQL 容器                                                 │
│  ├── xihong_erp          # 业务数据库（ERP 数据）               │
│  │   ├── a_class schema  # A类数据（目标/配置）                 │
│  │   ├── b_class schema  # B类数据（采集数据）                  │
│  │   └── public schema   # 主业务表                             │
│  │                                                               │
│  └── metabase_app        # Metabase 应用数据库（新建）          │
│      └── public schema   # Metabase 内部表                      │
│          - Models、Questions、Dashboards                        │
│          - 用户设置、权限配置                                   │
│                                                                  │
│  Metabase 容器                                                   │
│  - MB_DB_TYPE=postgres                                          │
│  - MB_DB_HOST=postgres                                          │
│  - MB_DB_DBNAME=metabase_app                                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 环境一致性

**本地开发和云端生产使用完全相同的配置**：

| 环境 | Metabase 应用数据库         | 业务数据源                |
| ---- | --------------------------- | ------------------------- |
| 本地 | PostgreSQL (`metabase_app`) | PostgreSQL (`xihong_erp`) |
| 云端 | PostgreSQL (`metabase_app`) | PostgreSQL (`xihong_erp`) |

**优势**：本地测试通过 = 云端部署大概率成功

### 核心组件设计

#### 1. 配置文件（Git 版本控制）

```yaml
# config/metabase_config.yaml
database:
  name: "西虹ERP数据库"
  engine: postgres

models:
  - name: "Analytics Model" # 唯一标识（用于名称查询）
    sql_file: "sql/metabase_models/analytics_model.sql"
    description: "分析数据域模型"

  - name: "Orders Model"
    sql_file: "sql/metabase_models/orders_model.sql"
    description: "订单数据域模型"

  # ... 其他 Models

questions:
  - name: "business_overview_kpi" # 唯一标识（用于名称查询）
    display_name: "业务概览-核心KPI"
    sql_file: "sql/metabase_questions/business_overview_kpi.sql"
    parameters:
      - name: start_date
        type: date
        required: true
      - name: end_date
        type: date
        required: true

  # ... 其他 Questions
```

#### 2. 初始化脚本（scripts/init_metabase.py）

```python
class MetabaseInitializer:
    """Metabase 配置初始化器（幂等操作）"""

    def ensure_model_exists(self, model_config: dict) -> int:
        """确保 Model 存在，返回 Model ID"""
        existing = self.find_card_by_name(model_config['name'])

        if existing:
            # 存在 → 检查是否需要更新 SQL
            if self.should_update_sql(existing, model_config):
                self.update_card_sql(existing['id'], model_config)
            return existing['id']

        # 不存在 → 创建新 Model
        return self.create_model(model_config)

    def ensure_question_exists(self, question_config: dict) -> int:
        """确保 Question 存在，返回 Question ID"""
        # 类似逻辑
        pass
```

#### 3. MetabaseQuestionService（运行时）

```python
class MetabaseQuestionService:
    """通过名称动态查询 Question"""

    def __init__(self):
        self._question_cache: dict[str, int] = {}  # 名称 → ID 缓存
        self._cache_loaded = False

    def get_question_id(self, question_name: str) -> int | None:
        """通过名称获取 Question ID（带缓存）"""
        if not self._cache_loaded:
            self._load_question_cache()
        return self._question_cache.get(question_name)

    async def execute_question(self, question_name: str, parameters: dict = None):
        """执行 Question 并返回结果"""
        question_id = self.get_question_id(question_name)
        if not question_id:
            raise ValueError(f"Question '{question_name}' 未找到")

        return await self._api_post(f"/api/card/{question_id}/query", ...)
```

### 部署流程

#### 首次部署

```
Phase 1: 基础设施启动 (PostgreSQL, Redis)
    ↓
Phase 2: 数据库迁移 (Alembic)
    ↓
Phase 2.5: Bootstrap 初始化 (角色、管理员)
    ↓
Phase 3: Metabase 启动
    ↓
Phase 3.5: Metabase 配置初始化 ← 新增
    │  - init_metabase.py 执行
    │  - 读取 config/metabase_config.yaml
    │  - 通过 API 创建 Models/Questions
    ↓
Phase 4: 应用层启动 (Backend, Celery)
    ↓
Phase 5: 网关启动 (Nginx)
```

#### 后续更新部署

```
开发者修改 SQL 文件
    ↓
Git commit & push
    ↓
GitHub Actions 触发
    ↓
Phase 3.5: init_metabase.py 检测变更
    │  - 已存在 + SQL 变化 → 更新
    │  - 不存在 → 创建
    │  - 无变化 → 跳过
    ↓
部署完成
```

### 运行时数据流

```
用户请求 → Frontend → GET /api/business-overview/kpi
                         ↓
              Backend (MetabaseQuestionService)
                         ↓
              通过名称查询 Question ID（带缓存）
              question_name = "business_overview_kpi" → ID = 15
                         ↓
              POST http://metabase:3000/api/card/15/query
                         ↓
              Metabase 执行 SQL → 查询 PostgreSQL
                         ↓
              返回结果 → Backend → Frontend → 用户
```

### 环境变量简化

**改进前（需维护多个 ID）**：

```bash
METABASE_QUESTION_BUSINESS_OVERVIEW_KPI=12
METABASE_QUESTION_BUSINESS_OVERVIEW_COMPARISON=13
# ... 每个 Question 一个 ID
```

**改进后（只需基础配置）**：

```bash
METABASE_URL=http://metabase:3000
METABASE_API_KEY=mb_xxxxxxxxxxxxx=
```

### 新增文件清单

| 文件                                     | 用途                              |
| ---------------------------------------- | --------------------------------- |
| `config/metabase_config.yaml`            | 配置清单（Models/Questions 定义） |
| `scripts/init_metabase.py`               | 初始化脚本（自动创建/更新配置）   |
| `sql/metabase_questions/*.sql`           | Question SQL 文件                 |
| `sql/metabase_models/FIELD_STANDARDS.md` | 字段标准文档（已创建）            |

## Impact

- Affected specs: dashboard, data-sync
- Affected code:
  - Metabase配置（Models和Questions）
  - `backend/services/metabase_question_service.py` - 改为通过名称动态查询
  - `config/metabase_config.yaml` - 新增配置清单
  - `scripts/init_metabase.py` - 新增初始化脚本
  - `scripts/deploy_remote_production.sh` - 添加 Phase 3.5
  - `env.example` - 简化，移除 Question ID，保留 API Key
  - `frontend/src/api/dashboard.js` - 可能需要调整数据格式
- **Metabase 生产环境优化（紧急）**:
  - `docker-compose.metabase.yml` - Metabase 应用数据库改为 PostgreSQL
  - `docker-compose.prod.yml` - 生产环境 Metabase PostgreSQL 配置
  - `docker/init/01-init.sql` - 添加 metabase_app 数据库创建
  - `env.example` / `env.production.example` - 添加 Metabase PostgreSQL 环境变量

## Risk Assessment

- **低风险**：Metabase Model和Question创建不影响现有数据
- **中风险**：字段标准化映射需要验证所有平台的数据格式
- **低风险**：Question创建可以逐步迭代，不影响现有功能

## Completion Status

### ✅ 已完成（2025-01-26）

#### B类数据模型（Metabase Models）

- ✅ **Analytics Model** - 分析数据域模型（CTE分层架构，统一数值清洗）
- ✅ **Products Model** - 产品数据域模型（CTE分层架构，统一数值清洗）
- ✅ **Orders Model** - 订单数据域模型（CTE分层架构，统一数值清洗，优化日期/时间字段处理）
- ✅ **Inventory Model** - 库存数据域模型（CTE分层架构，统一数值清洗，仅snapshot粒度）
- ✅ **Services Model** - 服务数据域模型（CTE分层架构，统一数值清洗，直接使用数据库已清洗的日期字段）

**技术特点**：

- 使用CTE分层架构（字段映射 → 数据清洗 → 去重 → 最终输出）
- 统一数值清洗函数（处理破折号、逗号、空格等特殊字符）
- 百分比字段自动除以100.0
- 时间格式字段转换为秒数
- 基于data_hash去重，优先级 daily > weekly > monthly

#### A类数据处理决策

- ✅ **决策**：A类数据直接使用表，不创建Metabase模型
- ✅ **原因**：
  - A类数据表结构简单，字段已标准化
  - 无需字段映射（字段名统一）
  - 无需数据清洗（用户输入数据已是标准格式）
  - 无需去重（数据库已有唯一约束）
  - 性能更好（少一层CTE）
  - 维护成本更低
- ✅ **使用方式**：在Metabase Question中直接引用 `a_class.sales_targets_a` 等表

#### C类数据处理方式

- ✅ **决策**：C类数据通过Metabase Question实时计算
- ✅ **原因**：
  - C类数据是衍生数据（达成率、对比、排名等）
  - 需要实时计算，不存储结果
  - 需要JOIN A类数据（目标）和B类数据（实际）
- ✅ **使用方式**：创建Metabase Question，在Question中JOIN A类表和B类模型

#### 数据链路优化（2025-01-27新增）

- ✅ **Schema配置修复** - 修复A类/C类表的ORM Schema配置
  - A类表添加 `{"schema": "a_class"}`（7张表）
  - C类表添加 `{"schema": "c_class"}`（4张表）
  - 修复索引/约束名称避免冲突
- ✅ **数据迁移脚本** - 创建 `migrate_a_c_class_to_schema` 迁移
  - 将 public schema 中的A类表迁移到 a_class
  - 将 public schema 中的C类表迁移到 c_class
  - 支持数据合并和清理重复表
- ✅ **目标管理数据同步** - 实现 `TargetSyncService`
  - 创建分解时自动同步到 `a_class.sales_targets_a`
  - 删除目标时自动清理 `a_class.sales_targets_a`
  - 确保前端目标管理和经营指标SQL使用同一数据源

### ✅ 已可用（核心KPI + 经营指标）

#### 业务概览 - 核心KPI指标（business_overview_kpi）

- ✅ 前端按月筛选、平台筛选，展示 GMV、订单数、客单价、转化率、客流量、销售单数
- ✅ 后端通过 Metabase Question API 查询，Question ID 已配置于 `.env`
- ✅ 环比数据由后端转换后返回

#### 业务概览 - 经营指标（business_overview_operational_metrics）

- ✅ 前端独立日期选择器（具体日期），两行布局：月目标/当月总达成/今日销售额/月达成率；时间GAP/预估毛利/预估费用/今日销售单数；经营结果竖状置于最右侧
- ✅ SQL 支持具体日期参数，today_sales / today_order_count 按所选日期查询
- ✅ 月目标、预估费用来自 A 类表，达成与订单来自 Orders Model
- ✅ Question ID 已配置，`init_metabase.py` 可同步 SQL 更新

### ✅ 数据对比模块已可用（v4.21.0，2025-01-30）

#### Metabase Questions（C类数据实时计算）

- ✅ **business_overview_comparison** - 数据对比（**已可用**，见下方「数据对比 Question 约定」）
- ✅ **business_overview_shop_racing** - 店铺赛马（已可用，2026-01-31：含目标、完成率，JOIN target_breakdown；前端 value-format 修复 UTC 偏差）
- ✅ **business_overview_traffic_ranking** - 流量排名（已可用：Analytics Model shop_id 兜底、本期/上期与环比、后端转英文 key、前端列映射与未关联店铺提示）
- ⏳ **business_overview_inventory_backlog** - 库存积压（待优化）
- ⏳ **clearance_ranking** - 清仓排名（待优化）

### ✅ 数据对比 Question 优化完成（v4.21.0，2025-01-30）

**约定（避免其他 Question 出现类似问题）：**

1. **时间定义**
   - **日度**：单日日期（`target_date` 即所选日期）。
   - **周度**：周一～周日；周期由 `date_trunc('week', target_date)` 得到当周周一，当周周日 = 周一 + 6；前端传参须为该周**周一**的 YYYY-MM-DD，避免同周不同日期导致数据跳变。
   - **月度**：整月 1 日～当月最后一天；参数可为 YYYY-MM 或 YYYY-MM-DD，后端规范为 YYYY-MM-01。

2. **平均定义**
   - **日度筛选时**：平均 = **本月平均** = 本月数据 / 本月天数（本月日度汇总 / 本月天数）。
   - **周度**：本周平均 = 本周数据 / 7。
   - **月度**：本月平均 = 本月数据 / 本月天数。
   - **转化率 / 连带率**：本期只算一个比率（本期订单/本期流量），不做「平均转化率」的额外定义；日度时「平均转化率」= 本月订单/本月流量。

3. **环比**
   - 当日 vs 昨天、本周 vs 上周、本月 vs 上月，直接计算（当期−上期）/上期×100%。

4. **引用的字段（Orders / Analytics Model）**
   - **`metric_date`**：在订单/分析模型中，无论粒度为 daily/weekly/monthly，存储的均为**单日日期**（订单日期或事件日期），**不是**周期起止。按周期汇总时须用「`metric_date` 落在计算出的周期范围内」匹配，例如 `metric_date >= current_period_start AND metric_date <= current_period_end`。
   - **`period_start_date` / `period_end_date`**：在 B 类模型中可能同样存单日，**勿**用其等于周期起止做过滤；周期边界由 SQL 内根据 `target_date` 与 `granularity` 计算。
   - **销售额**：订单模型若 `sales_amount` 常为 0，汇总时使用 **`paid_amount`**（实付金额）作为销售额指标。
   - **连带率**：= 商品件数 / 订单数；订单数 = `COUNT(DISTINCT order_id)`（与核心KPI、经营指标一致）。

5. **已实现功能**
   - 日/周/月切换、当期/上期/平均/环比、目标达成率、连带率（含 order_count 计算）。

### ⚠️ 后续调整（GMV/粒度口径）

- **GMV/月度销售额应只按日度粒度汇总**：Orders Model 中同一订单可能因 data_hash 不同而同时存在于 daily/weekly/monthly 表，若按全粒度汇总会重复计算。正确口径为**仅日度粒度的 paid_amount 总和**。核心 KPI、经营指标、数据对比的月度 GMV/销售额口径待统一调整（后续实施）。

### 📋 待完成

- [ ] 优化其余 2 个 Question（库存积压、清仓排名）
- [ ] GMV/月度销售额口径调整：核心 KPI、经营指标、数据对比统一为**仅日度粒度**汇总（避免跨粒度重复计算）
- [ ] 测试各 Question 查询性能与数据正确性
- [ ] 执行迁移脚本 `alembic upgrade head`（如未执行）
- [ ] 验证 A类/C类表已迁移到正确 schema
