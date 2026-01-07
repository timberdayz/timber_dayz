# Change: 重构后端为DSS（决策支持系统）架构

## Why（为什么）

当前系统在开发过程中遇到以下核心问题：

1. **字段映射系统过于复杂**：多层数据转换导致前后端数据流转混乱，维护成本高
2. **数据流不清晰**：A类（用户配置）、B类（业务数据）、C类（计算数据）的处理流程缺乏统一规划
3. **计算逻辑分散**：KPI计算逻辑硬编码在后端，难以维护和扩展
4. **扩展性差**：新增数据域或KPI需要大量代码修改
5. **缺乏BI工具**：用户无法自助进行数据分析和探索

**根本原因**：系统从数据采集工具演变为ERP决策支持系统，但架构未能及时调整以匹配新的业务定位。

## What Changes（变更内容）

### 核心架构转型

将系统从"**数据采集+字段映射**"架构转型为"**DSS（决策支持系统）+ BI层**"架构：

```
【现有架构】
Excel文件 → 字段映射（标准字段） → 数据清洗 → 入库 → 后端计算KPI → 前端展示

【新架构】
Excel文件 → 表头识别（中文表头） → 模板匹配/创建 → Staging层（原始数据JSONB）
→ 数据去重（多层策略） → Fact层（按data_domain+granularity分表，JSONB格式，中文表头）
→ Metabase直接查询 → Metabase计算和关联 → 前端展示
```

### 主要变更

#### 1. 后端简化（Backend Simplification）
- **移除复杂的KPI计算引擎**：不再在Python中硬编码计算逻辑
- **专注数据ETL**：后端只负责数据采集、清洗、验证、入库
- **字段映射系统重构**：不再映射到标准字段，直接保存原始中文表头，利用Metabase支持中文表头的优势
- **多层数据去重策略**：文件级、行内、跨文件、业务语义四层去重，确保数据准确性
- **按数据域+粒度分表**：B类数据按`data_domain + granularity`分表存储，避免不同粒度使用相同表头名称导致的数据混乱
- **数据同步功能重设计** ⭐ **新增（2025-01-31）**：
  - **用户手动选择表头行**：大多数文件表头行不在第一行，自动检测效果不佳，必须由用户手动选择
  - **模板驱动同步**：用户选择表头行 → 预览验证 → 保存模板 → 自动同步时严格执行模板表头行
  - **完全独立系统**：新数据同步功能完全独立于字段映射审核系统，在"数据采集与管理"下新增"数据同步"二级菜单
  - **保留现有UI设计**：文件详情、数据预览、原始表头字段列表设计保留，确保用户能够判断系统识别是否正常

#### 2. PostgreSQL表结构简化（Database Layer Simplification）
- **删除三层视图架构**：不再需要Layer 1/2/3视图，Metabase直接查询原始表
- **B类数据分表存储**：按`data_domain + granularity`分表（最多16张表）
  - 标准数据域：4个数据域（orders/products/traffic/services）× 3个粒度（daily/weekly/monthly）= 12张表
  - 特殊粒度：inventory_snapshot（1张）+ 未来inventory_daily/weekly/monthly（3张）= 4张
  - **总计：最多16张表**
- **表名英文，表头中文**：数据库表名使用英文（符合规范），JSONB中的字段名使用中文（用户友好）
- **删除维度表和复杂事实表**：所有`dim_*`表和复杂`fact_*`表全部删除
- **表分区支持**：按`data_domain`分区（可选，数据量大时启用）
- **索引优化**：联合索引、部分索引、GIN索引（针对JSONB字段）

#### 3. BI层引入（BI Layer Integration）
- **Metabase集成**：作为核心计算和可视化引擎
- **配置驱动的KPI**：KPI在Metabase中声明式定义，无需代码修改
- **交互式分析**：用户可自助筛选、钻取、探索数据
- **类似Excel的编辑体验**：拖拽式查询构建器，非技术人员友好
- **外键关联**：在Metabase中灵活创建表间关联，处理不同粒度的数据关联
- **定时计算任务**：每20分钟自动更新C类数据（绩效、提成等）

#### 4. 前端集成（Frontend Integration）
- **API调用模式**：Vue.js前端通过Metabase REST API获取Question查询结果，使用ECharts/Chart.js自己渲染图表
- **原生布局保留**：现有页面布局和交互逻辑保持不变
- **完全控制UI**：前端完全控制图表样式和交互，避免使用Metabase收费的Embedding功能
- **数据来源**：在Metabase中创建所有需要的Question（查询），前端通过API获取JSON数据后自己渲染

#### 5. A类数据管理（A-Class Data Management）
- **CRUD界面**：为销售目标、战役目标、经营成本、员工目标提供可编辑表格界面
- **快速操作**：支持复制上月、批量填充、快速编辑
- **数据验证**：前端验证+后端验证双重保障
- **月份键值**：所有A类数据表包含`year_month`字段（格式：`2025-01`），用于Metabase关联
- **中文字段名**：A类数据表使用中文字段名（PostgreSQL支持，Metabase支持），用户友好

#### 6. 人力管理模块（HR Management Module）⭐ **新增**
- **员工档案管理**：`employees`表存储员工基本信息（中文字段名）
- **员工目标管理**：`employee_targets`表存储员工月度目标（中文字段名）
- **考勤管理**：`attendance_records`表存储考勤记录（中文字段名）
- **绩效计算**：`employee_performance`表存储Metabase计算的绩效结果（每20分钟更新）
- **提成计算**：`employee_commissions`和`shop_commissions`表存储Metabase计算的提成结果（每20分钟更新）
- **API设计**：先创建表结构，后续再实现API接口

#### 7. 统一对齐表（Entity Alignment Table）⭐ **新增**
- **entity_aliases表**：统一管理所有账号和店铺的别名映射
- **替代原有表**：替代`dim_shops`和`account_aliases`两张表
- **Metabase关联简化**：通过一张表即可对齐所有账号和店铺信息
- **支持多种类型**：支持账号别名、店铺别名、店铺名称等多种映射类型

#### 8. Metabase计算数据存储策略（Calculation Storage Strategy）⭐ **新增**
- **实时计算**：Dashboard展示使用实时计算（不存储），数据实时更新
- **物化存储**：提成、绩效等需要持久化的数据，由Metabase定时计算后存储在PostgreSQL中
- **定时刷新**：每20分钟执行一次计算任务，更新C类数据表（employee_performance, employee_commissions, shop_commissions）

### 技术栈更新

**新增技术栈**：
- Metabase (BI平台，开源免费)
- Docker Compose (Metabase容器化)

**保留技术栈**：
- PostgreSQL 15+ (主数据库，简化表结构，支持分区和中文字段名)
- FastAPI (简化后的API)
- Vue.js 3 + Element Plus (前端)

## Impact（影响范围）

### 受影响的规格（Affected Specs）

- **backend-architecture** (新增规格) ✅ - 后端架构从计算引擎转为ETL引擎
- **database-design** (重大修改规格) ✅ - PostgreSQL表结构大幅简化，删除三层视图架构，按data_domain+granularity分表，支持中文字段名
- **bi-layer** (新增规格) ✅ - Metabase集成 + JWT认证 + RLS详细配置 + 定时计算任务（每20分钟）
- **data-sync** (重大修改规格) ✅ - 简化数据同步流程，按data_domain+granularity分表，用户手动选择表头行，完全独立于字段映射审核系统 ⭐ **新增（2025-01-31）**
- **frontend-api-contracts** (新增规格) ✅ - API契约简化 + A类数据管理API + 人力管理API + Metabase代理API
- **dashboard** (新增规格) ✅ - 前端集成Metabase仪表盘 + MetabaseChart组件 + 降级策略
- **hr-management** (新增规格) ✅ - 人力管理模块（员工、目标、考勤、绩效、提成），先创建表结构，后续实现API

### 受影响的代码（Affected Code）

#### 需要重构的文件
- `backend/routers/field_mapping.py` - 重构字段映射API，直接保存原始中文表头
- `backend/services/data_importer.py` - 优化数据入库流程，支持JSONB存储，按data_domain+granularity分表
- `backend/services/deduplication_service.py` - **新增**多层数据去重服务
- `backend/services/excel_parser.py` - 增强合并单元格处理（关键列强制填充）
- `backend/services/kpi_calculator.py` - **删除**（功能迁移到Metabase）
- `modules/core/db/schema.py` - **重大修改**：删除所有dim_*表和复杂fact_*表，新增B类数据分表（最多16张），新增人力管理表（7张），新增统一对齐表（1张）
- `backend/routers/data_browser.py` - **修复**：支持多schema查询（public/b_class/a_class/c_class/core/finance），修复数据浏览器无法显示新表的问题
- `frontend/src/views/FieldMappingEnhanced.vue` - **修复**：完全移除标准字段映射UI元素，只显示原始表头字段列表
- `backend/services/data_sync_service.py` - **重构**：支持用户手动选择表头行，严格执行模板表头行设置，不进行自动检测 ⭐ **新增（2025-01-31）**
- `backend/routers/data_sync.py` - **重构**：新增文件预览API（支持表头行参数），优化模板保存API（保存表头行） ⭐ **新增（2025-01-31）**

#### 需要新增的文件
- `backend/services/metabase_client.py` - Metabase API客户端
- `backend/services/deduplication_service.py` - 多层数据去重服务（文件级/行内/跨文件/业务语义）
- `backend/routers/config_management.py` - A类数据管理API
- `backend/routers/hr_management.py` - **新增**人力管理API（Phase 3实现）
- `frontend/src/views/target/TargetManagement.vue` - 增强目标管理界面
- `frontend/src/views/finance/CostConfiguration.vue` - 新增成本配置界面
- `frontend/src/views/hr/EmployeeManagement.vue` - **新增**员工管理界面（Phase 3实现）
- `frontend/src/views/hr/CommissionManagement.vue` - **新增**提成管理界面（Phase 3实现）
- `docker-compose.metabase.yml` - Metabase容器配置
- `sql/partitions/` - **新增**表分区SQL脚本（可选）
- `frontend/src/views/DataSyncFiles.vue` - **新增**数据同步文件列表页面 ⭐ **新增（2025-01-31）**
- `frontend/src/views/DataSyncFileDetail.vue` - **新增**数据同步文件详情页面（包含文件详情、数据预览、原始表头字段列表） ⭐ **新增（2025-01-31）**
- `frontend/src/views/DataSyncTasks.vue` - **新增**数据同步任务管理页面 ⭐ **新增（2025-01-31）**
- `frontend/src/views/DataSyncHistory.vue` - **新增**数据同步历史记录页面 ⭐ **新增（2025-01-31）**
- `frontend/src/views/DataSyncTemplates.vue` - **新增**数据同步模板管理页面 ⭐ **新增（2025-01-31）**

#### 需要修复的漏洞（2025-01-31发现）⭐ **新增**
- **数据浏览器API多schema支持**：`backend/routers/data_browser.py`只查询`public` schema，无法显示`b_class`/`a_class`/`c_class`/`core`/`finance` schema中的表 ✅ **已修复**
- **数据浏览器查询API schema支持**：查询表数据时需要使用`schema.table`格式或配置`search_path` ✅ **已修复**
- **字段映射页面标准字段残留**：`frontend/src/views/FieldMappingEnhanced.vue`仍显示标准字段映射UI，需要完全移除 ✅ **已修复**
- **数据同步服务schema验证**：确认`backend/services/raw_data_importer.py`写入B类数据表时指定了正确的schema ✅ **已修复**（通过search_path配置）
- **HR管理API schema验证**：确认`backend/routers/hr_management.py`查询A类数据表时指定了正确的schema ✅ **已修复**（通过search_path配置）

#### 需要修复的架构漏洞（2025-11-27发现）⭐ **新增**
- **架构不一致：物化视图要求冲突**：`backend-architecture/spec.md`仍要求Materialized View Refresh Service，与新架构冲突 ✅ **已修复**
- **前端依赖旧API未迁移**：`frontend/src/views/Dashboard.vue`仍调用后端API获取KPI数据，需要迁移到Metabase ⏳ **待修复**（Phase 4）
- **前端组件依赖清单缺失**：没有完整的前端组件依赖清单，可能遗漏需要迁移的组件 ⏳ **待补充**（见下方清单）
- **数据迁移策略不明确**：生产环境数据迁移步骤不够详细 ⏳ **待补充**（见下方计划）
- **性能测试计划缺失**：没有明确的性能测试要求和基准 ⏳ **待补充**（见下方计划）
- **错误处理策略不充分**：Metabase不可用时的降级策略不够详细 ⏳ **待补充**（见下方策略）

#### 需要删除的文件
- `backend/services/standard_field_mapper.py` - **删除**标准字段映射服务（如果存在，Phase 6删除）
- `sql/views/atomic_views.sql` - **删除**（不再需要三层视图架构，Phase 0删除）✅ **已归档**
- `sql/views/aggregate_mvs.sql` - **删除**（不再需要三层视图架构，Phase 0删除）✅ **已归档**
- `sql/views/wide_views.sql` - **删除**（不再需要三层视图架构，Phase 0删除）✅ **已归档**
- `FieldMappingTemplateItem`表 - **删除**（不再需要字段映射项表，Phase 6删除）
- 相关的标准字段映射表（如果存在，Phase 6删除）
- `backend/services/materialized_view_service.py` - **标记废弃**（Phase 6删除，保留3个月降级路径）
- `backend/routers/materialized_views.py` - **标记废弃**（Phase 6删除，保留3个月降级路径）
- `backend/routers/main_views.py` - **需要重构**（改为查询原始B类数据表，Phase 4完成）
- `backend/routers/metrics.py` - **需要重构**（改为Metabase代理，Phase 4完成）
- `backend/routers/store_analytics.py` - **需要重构**（改为Metabase代理，Phase 4完成）
- `backend/routers/dashboard_api.py` - **需要重构**（改为Metabase代理，Phase 4完成）

#### 前端组件依赖清单（需要迁移到Metabase Question API）⭐ **新增**
- **高优先级（核心功能）**：
  - `frontend/src/views/Dashboard.vue` - 业务概览页面，需要改为调用Metabase Question API获取数据，使用ECharts渲染
  - `frontend/src/stores/dashboard.js` - Dashboard状态管理，需要改为Metabase Question API调用
  - `frontend/src/api/dashboard.js` - Dashboard API调用，需要改为Metabase Question API代理
- **中优先级（分析功能）**：
  - `frontend/src/views/store/StoreAnalytics.vue` - 店铺分析页面，需要改为调用Metabase Question API，使用ECharts渲染
  - `frontend/src/views/sales/SalesDetailByProduct.vue` - 产品销售详情，需要改为调用Metabase Question API，使用ECharts渲染
  - `frontend/src/views/FinancialOverview.vue` - 财务概览，需要改为调用Metabase Question API，使用ECharts渲染
  - `frontend/src/views/ProductQualityDashboard.vue` - 产品质量看板，需要改为调用Metabase Question API，使用ECharts渲染
  - `frontend/src/views/InventoryHealthDashboard.vue` - 库存健康看板，需要改为调用Metabase Question API，使用ECharts渲染
- **低优先级（辅助功能）**：
  - `frontend/src/views/SalesTrendChart.vue` - 销售趋势图表，需要改为调用Metabase Question API，使用ECharts渲染
  - `frontend/src/views/TopProducts.vue` - Top产品排行，需要改为调用Metabase Question API，使用ECharts渲染

#### 数据迁移
- **开发阶段**：可以删除所有现有表（53张表），历史数据不需要迁移
- **生产环境**：如需保留历史数据，提供迁移脚本（从旧表迁移到新表）
- **创建新表结构**：按新架构创建约31-34张表
  - B类数据表：最多16张（按data_domain+granularity分表）
  - 统一对齐表：1张（entity_aliases）
  - A类数据表：7张（使用中文字段名）
  - C类数据表：4张（使用中文字段名）
  - 管理表：3张

#### 数据迁移详细计划（生产环境）⭐ **新增**
**迁移原则**：
1. **零数据丢失**：所有历史数据必须完整迁移
2. **并行运行**：新表结构创建后，旧表保留3个月（只读）
3. **数据验证**：迁移后必须验证数据完整性（行数、关键字段、数据范围）
4. **回滚方案**：如果新系统有问题，可以恢复旧表结构（3个月内）

**迁移步骤**：
1. **备份阶段**（1天）：
   - 完整备份现有数据库（pg_dump）
   - 备份到`backups/YYYYMMDD_production_backup/`
   - 验证备份完整性

2. **表结构创建阶段**（1天）：
   - 创建新Schema（b_class, a_class, c_class, core, finance）
   - 创建新表结构（31-34张表）
   - 创建索引和约束
   - 验证表结构正确性

3. **数据迁移阶段**（3-5天，取决于数据量）：
   - 迁移B类数据：从`fact_orders`等旧表迁移到`b_class.fact_raw_data_*`表
   - 迁移A类数据：从旧配置表迁移到`a_class.*`表（如需要）
   - 迁移对齐数据：从`dim_shops`和`account_aliases`迁移到`b_class.entity_aliases`
   - 数据转换：将标准字段映射转换为JSONB格式（中文字段名）

4. **数据验证阶段**（1天）：
   - 验证行数：`SELECT COUNT(*) FROM old_table` vs `SELECT COUNT(*) FROM new_table`
   - 验证关键字段：抽样验证关键字段数据正确性
   - 验证数据范围：验证日期范围、金额范围等
   - 验证关联关系：验证外键关联正确性

5. **并行运行阶段**（3个月）：
   - 新系统上线，旧表保留（只读）
   - 监控新系统运行情况
   - 收集用户反馈

6. **清理阶段**（3个月后）：
   - 确认新系统稳定后，删除旧表结构
   - 归档旧表数据（可选）

**迁移脚本位置**：
- `scripts/migrate_old_tables_to_dss.py` - 主迁移脚本
- `scripts/rollback_migration.py` - 回滚脚本
- `docs/PRODUCTION_MIGRATION_GUIDE.md` - 详细迁移指南

### 破坏性变更（Breaking Changes）

**Phase 0的破坏性变更**：
- ⚠️ **开发阶段暂不删除旧表**：避免破坏现有功能，旧表将在Phase 6清理阶段删除（3个月后）
- **创建B类数据分表**：按data_domain+granularity创建最多16张表
- **创建A类数据表**：使用中文字段名（7张表）
- **创建C类数据表**：使用中文字段名（4张表）
- **创建统一对齐表**：entity_aliases表（1张）
- **删除三层视图SQL文件**：`sql/views/atomic_views.sql`、`sql/views/aggregate_mvs.sql`、`sql/views/wide_views.sql`
- **Phase 6将删除**（3个月后，充分测试后）：
  - 删除所有dim_*表：不再需要维度表
  - 删除所有复杂fact_*表：不再需要复杂事实表（fact_orders, fact_order_items等）
  - 删除所有财务域表：不再需要po_*, grn_*, invoice_*等表
  - 删除FieldMappingTemplateItem表：不再需要字段映射项表
  - 删除dim_shops和account_aliases表：合并为统一的entity_aliases表
  - **影响**：生产环境需要数据迁移
  - **缓解措施**：
    1. 开发阶段：暂不删除旧表，创建新表结构并行运行
    2. 生产环境：提供数据迁移脚本（从旧表迁移到新表）
    3. 保留旧表数据3个月（只读，仅生产环境）
    4. Phase 6（3个月后）：确认新系统稳定后，删除旧表
  - **回滚方案**：如果新系统有问题，可以恢复旧表结构（3个月内，仅生产环境）

**其他阶段无破坏性变更** - 采用渐进式重构策略：
1. Phase 0: 表结构重构（开发阶段暂不删除旧表，避免破坏现有功能；生产环境提供迁移脚本）
2. Phase 1: Metabase集成和基础Dashboard（不影响现有功能）
3. Phase 2: Metabase Question创建和配置（不影响现有功能）
4. Phase 3: 人力管理模块和C类数据计算（先创建表结构，后续实现API）
5. Phase 4: 前端集成和A类数据管理（保留旧版降级）
6. Phase 5: 测试、优化、文档（1周）
7. Phase 6: 清理过时代码（可选，3个月后，充分测试后）⭐ **新增**

### 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Metabase学习曲线 | 低 | 提供详细文档和示例Question，类似Excel的拖拽式操作 |
| 前端开发复杂度 | 中 | 需要实现API调用和图表渲染，但完全控制UI设计 |
| 收费风险 | 低 | 使用免费的REST API，避免使用收费的Embedding功能 |
| 数据迁移复杂度 | 中 | 开发阶段可以删除历史数据，生产环境提供完整的数据迁移脚本（见上方详细计划） |
| 字段映射系统重构 | 中 | 保留旧模板数据3个月（只读，仅生产环境），提供迁移脚本自动转换 |
| 表结构大幅变更 | 高 | 开发阶段可以删除旧表，生产环境提供数据迁移脚本（如需要，见上方详细计划） |
| 全行哈希性能影响 | 低 | 使用批量处理和数据库唯一约束优化，预期1000行数据约0.05-0.2秒 |
| 数据对齐准确性 | 低 | pandas原生对齐保证+字典结构保证+入库前验证机制 |
| 合并单元格处理 | 低 | 增强版normalize_table，关键列强制填充，大文件优化处理 |
| 不同粒度表头混淆 | 低 | 按data_domain+granularity分表，避免混淆 |
| 定时计算任务性能 | 中 | 每20分钟更新一次，使用Metabase定时Question或后端API定时任务，优化计算逻辑 |
| 中文字段名兼容性 | 低 | PostgreSQL完全支持，SQLAlchemy支持，Metabase支持，只需在SQL中使用双引号 |
| **Metabase直接查询JSONB性能** | **中** | **添加GIN索引优化JSONB查询，设置性能基准（查询<2秒），大数据量时考虑分区** ⭐ **新增** |
| **前端迁移不完整** | **高** | **创建完整的前端依赖清单，分阶段迁移，提供降级策略** ⭐ **新增** |
| **Metabase服务不可用** | **中** | **前端降级策略：显示静态图表或错误提示，添加健康检查和告警** ⭐ **新增** |

### 预期收益

1. **开发效率提升**: 新增KPI无需修改代码，配置即可
2. **维护成本降低**: 减少70%+后端计算逻辑代码，表结构从53张简化到31-34张
3. **用户自助分析**: Metabase提供强大的交互式分析能力，非技术人员友好
4. **系统可扩展性**: 新增数据域和KPI成本降低80%
5. **表结构清晰**: 按data_domain+granularity分表，避免数据混淆，便于Metabase关联
6. **学习成本低**: Metabase拖拽式操作，类似Excel体验，30分钟即可上手
7. **中文表头支持**: 利用Metabase中文表头支持，用户体验更好
8. **实时数据更新**: 每20分钟自动更新计算数据，保证数据时效性
9. **统一对齐管理**: 通过entity_aliases表统一管理所有账号和店铺对齐信息

## 实施时间线

- **Phase 0**: 表结构重构和数据迁移（2周）⭐ **新增**
  - ⚠️ **开发阶段暂不删除旧表**，避免破坏现有功能
  - 创建新表结构（B类数据分表最多16张 + A类数据表7张 + C类数据表4张 + 人力管理表7张 + 统一对齐表1张）
  - 字段映射系统重构
  - 表分区配置（可选）
  - **删除三层视图SQL文件**：`sql/views/atomic_views.sql`、`sql/views/aggregate_mvs.sql`、`sql/views/wide_views.sql` ⭐ **新增**
  - **配置PostgreSQL search_path**：确保代码可以访问所有schema ⭐ **新增**
  - **生产环境**：提供数据迁移脚本（从旧表迁移到新表）
- **Phase 0.8**: 数据同步功能重设计（1周）⭐ **新增（2025-01-31）**
  - 用户手动选择表头行功能开发
  - 新数据同步系统开发（完全独立于字段映射审核系统）
  - 菜单结构更新（新增"数据同步"二级菜单）
  - 前端页面开发（文件列表、文件详情、任务管理、历史记录、模板管理）
  - 后端API开发（文件预览API、模板保存API、数据同步服务重构）
- **Phase 1**: Metabase集成和基础Dashboard（2周）
- **Phase 2**: Metabase Dashboard创建和配置（2周）⭐ **更新**
  - 创建业务概览Dashboard（包含5个Question）
  - 配置表关联、自定义字段、筛选器
- **Phase 3**: 人力管理模块和C类数据计算（2周）⭐ **新增**
  - 创建人力管理表结构（已在Phase 0完成）
  - 实现Metabase定时计算任务（每20分钟）
  - 实现人力管理API（已完成）
- **Phase 4**: 前端集成和A类数据管理（2周）⭐ **更新**
  - 前端调用Metabase Question API获取数据，使用ECharts渲染图表
  - A类数据管理界面开发
- **Phase 5**: 测试、优化、文档（1周）⭐ **更新**
- **Phase 6**: 清理过时代码（可选，3个月后）⭐ **新增**
  - 删除旧表结构（生产环境，3个月后）
  - 删除标准字段映射服务（`backend/services/standard_field_mapper.py`，如果存在）
  - 删除`FieldMappingTemplateItem`表和相关代码
  - 删除三层视图SQL文件（如果仍存在）
- **总计**: 12周（约3个月）+ Phase 6（可选，3个月后）
  - Phase 0: 2周（表结构重构）
  - Phase 0.8: 1周（数据同步功能重设计）⭐ **新增（2025-01-31）**
  - Phase 1-5: 9周（Metabase集成、Dashboard、HR管理、前端集成、测试优化）
  - Phase 6: 可选，3个月后（清理过时代码）

## 成功标准

### Phase 0 成功标准
0. ⏳ **表结构重构完成** - **进行中**
   - ✅ B类数据分表创建成功（最多16张表）
   - ✅ 统一对齐表创建成功（entity_aliases表，1张）
   - ✅ A类数据表创建成功（7张表，使用中文字段名）
   - ✅ C类数据表创建成功（4张表，使用中文字段名）
   - ✅ 人力管理表创建成功（7张表，使用中文字段名）
   - ✅ 数据库Schema分离完成（a_class/b_class/c_class/core/finance）
   - ⏳ 表分区配置完成（可选）
   - ✅ 数据对齐准确性测试通过（订单号字段下的数据确实是订单号码）
   - ✅ 合并单元格处理测试通过（订单号跨2-5行正确填充）
   - ✅ 数据去重性能测试通过（1000行数据 < 0.2秒）
   - ✅ 不同粒度表头不混淆测试通过（日度和周度的"日期"字段不混淆）
   - ✅ 中文字段名兼容性测试通过（PostgreSQL和Metabase正常查询）
  - ⏳ **数据浏览器多schema支持完成** ⭐ **新增** - 数据浏览器可以显示所有schema中的表
  - ⏳ **字段映射页面标准字段完全移除** ⭐ **新增** - 字段映射页面只显示原始表头字段列表
  - ⏳ **数据同步服务schema配置验证通过** ⭐ **新增** - 数据同步可以正常写入B类数据表
  - ⏳ **HR管理API schema配置验证通过** ⭐ **新增** - HR管理API可以正常查询A类数据表

### Phase 0.8 成功标准 ⭐ **新增（2025-01-31）**
0. ⏳ **数据同步功能重设计完成** - **待开始**
   - ⏳ 用户手动选择表头行功能正常
   - ⏳ 模板保存表头行功能正常（`header_row`字段正确保存）
   - ⏳ 自动同步严格执行模板表头行（不自动检测）
   - ⏳ 新数据同步系统完全独立于字段映射审核系统
   - ⏳ 菜单结构更新完成（新增"数据同步"二级菜单）
   - ⏳ 前端页面开发完成（文件列表、文件详情、任务管理、历史记录、模板管理）
   - ⏳ 后端API开发完成（文件预览API、文件列表API、模板保存API、数据同步服务重构）

### Phase 1-4 成功标准
1. ⏳ **Metabase成功部署并可访问** - **待开始**
   - Metabase容器运行正常，Web界面可访问 (http://localhost:3000)
   - 默认管理员账号：admin/admin
   - 健康检查通过，数据库连接配置完成
   - 所有B类数据表在Metabase中可见（最多16张表）
   - 所有A类和C类数据表在Metabase中可见（中文字段名正常显示）
2. ⏳ 业务概览相关Question创建完成（至少5个Question） - **待开始** (Phase 2)
3. ⏳ 人力管理表结构创建完成 - **已完成** (Phase 0已完成，Phase 3实现API)
4. ⏳ Metabase定时计算任务正常运行（每20分钟更新一次） - **待开始** (Phase 3)
5. ⏳ C类数据表正常更新（employee_performance, employee_commissions, shop_commissions） - **待开始** (Phase 3)
6. ⏳ 统一对齐表正常工作（entity_aliases表，Metabase可以正确关联账号和店铺信息） - **待开始** (Phase 1)
7. ⏳ A类数据管理界面上线（目标/战役/成本/员工目标） - **待开始** (Phase 4)
8. ⏳ 业务概览页面集成Metabase仪表盘 - **待开始** (Phase 4)
9. ✅ 所有现有功能保持正常运行（零破坏） - **保持中**
10. ⏳ 新增KPI配置时间从2天降低到2小时 - **待验证** (Phase 1完成后)
11. ⏳ **PostgreSQL search_path配置完成** ⭐ **新增** - 代码可以访问所有schema中的表
12. ⏳ **三层视图SQL文件已删除** ⭐ **新增** - atomic_views.sql、aggregate_mvs.sql、wide_views.sql已删除或归档

### Phase 6 成功标准（可选，3个月后）⭐ **新增**
1. ⏳ **旧表结构已删除** - 所有dim_*表和复杂fact_*表已删除（生产环境）
2. ⏳ **标准字段映射代码已删除** - standard_field_mapper.py和FieldMappingTemplateItem相关代码已删除
3. ⏳ **代码库清理完成** - 无冗余代码，架构100%合规
4. ⏳ **文档更新完成** - 移除所有旧架构说明

