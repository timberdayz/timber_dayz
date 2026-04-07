# Change: 完成数据同步管道，确保数据库有完整数据供 Metabase 查询

## Why

当前系统已完成 Metabase API 连接和 Question ID 配置验证，但由于数据库中缺少数据，无法进一步验证前端真实数据展示。需要完成完整的数据同步功能，确保：

1. **数据采集** → 文件下载并注册到 `catalog_files` 表
2. **文件扫描** → 自动发现并注册新文件
3. **模板管理** → 模板查找和配置（表头行和表头字段列表）
4. **数据入库** → 数据同步到B类数据表（fact_raw_data_*，动态列结构 + raw_data JSONB备份）
5. **去重处理** → 基于核心字段的data_hash去重（不受表头变化影响）
6. **Metabase验证** → 业务逻辑验证在Metabase中完成（DSS架构）

**根本原因**：数据同步管道虽然已实现，但可能缺少端到端的验证和完整性保证，导致数据库为空，Metabase 无法提供数据给前端。

**重要架构变更（v4.13.0 - 2025-02-01）**：
- **DSS架构重构**：数据同步流程已移除字段映射、数据标准化、业务逻辑验证和数据隔离
- **核心原则**：数据同步只做数据采集和存储，所有数据处理在Metabase中完成
- **模板作用**：模板只记录表头行（header_row）和表头字段列表（header_columns），不记录字段映射
- **新数据域处理**：需要先创建模板才能正常同步（only_with_template=True）
- **表头更新处理**：检测表头变化，提示用户更新模板（创建新版本）

**重要功能移除（v4.12.0 - 2025-02-01）**：
- **数据浏览器功能已完全移除**：数据浏览器功能修复多次仍无法正常使用，Metabase是更专业的BI工具
- **替代方案**：使用Metabase进行数据查询和分析（http://localhost:8080，端口从3000改为8080避免Windows端口权限问题）
- **已删除文件**：`frontend/src/views/DataBrowser.vue`、`frontend/src/views/DataBrowserSimple.vue`、`backend/routers/data_browser.py`
- **Metabase功能**：数据查询（SQL查询、可视化查询构建器）、数据可视化（多种图表类型、Dashboard）、数据导出（CSV、JSON、XLSX等格式）、数据质量分析（Question、Dashboard、告警）

**业务影响**：
- Metabase Dashboard 无法展示真实数据
- 前端迁移到 Metabase API 的工作无法继续
- 用户无法验证系统功能完整性

## What Changes

### 核心变更

0. **实现数据采集器自动注册文件**（新增 - 2025-02-01）
   - 在数据采集器下载文件完成后自动调用 `scan_and_register()` 注册文件
   - 确保采集器与文件注册服务集成
   - 验证采集后文件自动注册到 `catalog_files` 表
   - 保留手动扫描功能（数据同步模块中可手动扫描）

1. **验证文件扫描和注册流程**
   - 确保 `catalog_scanner` 服务正确扫描 `data/raw` 目录
   - 验证文件注册 API (`POST /api/field-mapping/scan`) 正常工作
   - 确保新文件自动注册到 `catalog_files` 表
   - 验证文件元数据完整性（platform_code, shop_id, data_domain, granularity, date_range）

2. **验证数据同步流程完整性（DSS架构）**
   - 确保单文件同步 API (`POST /api/data-sync/single`) 正常工作
   - 确保批量同步 API (`POST /api/data-sync/batch`) 正常工作
   - 验证模板查找和配置（表头行和表头字段列表）
   - 验证数据入库到B类数据表（fact_raw_data_*，动态列结构 + raw_data JSONB备份）
   - 验证去重处理（基于核心字段的data_hash）
   - 验证数据同步状态管理（pending → processing → ingested/failed）
   - **重要**：验证DSS架构下不再执行字段映射、数据标准化、业务逻辑验证和数据隔离

3. **验证数据入库到B类数据表（DSS架构）**
   - 确保数据正确写入B类数据表（fact_raw_data_orders_daily, fact_raw_data_products_snapshot 等）
   - 验证数据以动态列格式存储（系统字段 + 源数据表头字段作为列）
   - 验证raw_data JSONB作为数据备份（用于data_hash计算和数据恢复）
   - 验证数据完整性（行数、字段完整性、data_hash唯一性）
   - 验证去重机制（唯一约束包含platform_code和shop_id）
   - **重要**：验证不再有数据隔离（DSS架构下quarantined_count始终为0）
   - **重要**：验证业务逻辑验证在Metabase中完成，不在数据同步流程中

12. **实现动态列管理功能**（新增 - 2025-02-01）
   - 根据源文件表头动态添加列到PostgreSQL表（TEXT类型，支持中文列名）
   - 保留raw_data JSONB作为数据备份（用于data_hash计算和数据恢复）
   - 确保Metabase可以查询所有列（源数据表头字段作为列）
   - 处理列名冲突和列数限制

13. **实现核心字段去重功能**（新增 - 2025-02-01）
   - 在模板中配置核心去重字段（deduplication_fields）
   - 修改data_hash计算逻辑（基于核心字段，不受表头变化影响）
   - 创建默认核心字段配置（根据数据域+子类型）
   - 验证核心字段去重机制（表头新增字段不影响去重）

14. **优化唯一约束**（新增 - 2025-02-01）
   - 修改所有fact_raw_data_*表的唯一约束（包含platform_code和shop_id）
   - 处理shop_id为NULL的情况（使用COALESCE）
   - 创建数据库迁移脚本

4. **端到端测试和验证**
   - 创建端到端测试脚本，验证完整数据流程
   - 验证 Metabase 可以查询B类数据表数据（fact_raw_data_*）
   - 确保前端可以通过 Metabase API 获取数据
   - 验证数据从采集到展示的完整链路

5. **路径配置管理优化**（与secrets_manager不冲突 - 2025-02-01）
   - **说明**：`secrets_manager.py` 主要处理环境变量和密钥管理，少量路径处理（数据库路径）
   - **新增**：`path_manager.py` 专注于统一项目路径管理（`data/raw`, `downloads`, `temp/outputs` 等）
   - **关系**：两者互补，`path_manager.py` 专注于路径管理，`secrets_manager.py` 专注于密钥和环境变量
   - 创建统一路径配置管理工具（`modules/core/path_manager.py`）
   - 替换所有硬编码路径为统一路径管理函数
   - 支持环境变量配置（PROJECT_ROOT、DATA_DIR等）
   - 确保项目迁移时路径配置正常工作

6. **⚠️ v4.12.0移除：数据浏览器功能已完全移除**（2025-02-01）
   - **移除原因**：数据浏览器功能修复多次仍无法正常使用，Metabase是更专业的BI工具
   - **替代方案**：使用Metabase进行数据查询和分析（http://localhost:8080，端口从3000改为8080避免Windows端口权限问题）
   - **已删除文件**：
     - `frontend/src/views/DataBrowser.vue` - 已删除
     - `frontend/src/views/DataBrowserSimple.vue` - 已删除
     - `backend/routers/data_browser.py` - 已删除
   - **Metabase功能**：
     - 数据查询（SQL查询、可视化查询构建器）
     - 数据可视化（多种图表类型、Dashboard）
     - 数据导出（CSV、JSON、XLSX等格式）
     - 数据质量分析（Question、Dashboard、告警）

7. **验证清理数据库功能**（已验证路由正确 - 2025-02-01）
   - **路由验证**：前端调用`/data-sync/cleanup-database`（baseURL已包含`/api`），实际请求为`/api/data-sync/cleanup-database`，与后端路由匹配 ✅
   - **无需修复路由**：清理数据库API路由正确，无需修复
   - 验证清理数据库功能正常工作（清理B类数据表，重置catalog_files状态）
   - 验证清理后的数据状态重置
   - 验证清理后的文件状态更新

8. **修复刷新按钮功能**
   - 修复文件列表刷新按钮的API调用（前端调用`/collection/scan-files`，后端实际路由为`/api/field-mapping/scan`，路径完全不匹配）
   - 确保刷新功能正常工作（扫描文件目录并注册新文件）
   - 验证刷新后文件列表更新
   - 验证刷新后统计数据更新

9. **验证空文件处理逻辑**（已实现 - 2025-02-01）
   - **状态**：空文件处理逻辑已实现
   - **位置**：
     - `backend/routers/field_mapping.py` (第1046-1060行)
     - `backend/services/data_ingestion_service.py` (第185-198行)
   - **机制**：通过检查 `error_message` 字段中的 `[全0数据标识]` 来识别全0数据文件
   - **函数**：`check_if_all_zero_data()` (第1438行)
   - **验证**：验证空文件识别和处理机制正常工作
   - **验证**：确保空文件不会导致同步失败
   - **验证**：验证空文件不会被重复处理

10. **验证数据采集流程完整性**（最后验证，Phase 0已实现自动注册）
   - 确保数据采集器正确下载文件并自动注册到 `catalog_files` 表（Phase 0已实现）
   - 验证自动注册功能正常工作（文件元数据、路径、哈希等）
   - 验证文件元数据（platform_code, data_domain, granularity 等）正确提取
   - 确保文件哈希去重机制正常工作
   - 验证采集器与文件注册服务的集成
   - 验证自动注册与手动扫描不冲突

11. **验证模板管理与数据同步协同机制**（新增 - 2025-02-01）
   - **新数据域处理流程**：
     - 验证无模板时跳过同步（only_with_template=True）
     - 验证用户创建模板流程（选择表头行和保存表头字段列表）
     - 验证模板创建后可以正常同步
   - **表头更新处理流程**：
     - 验证表头匹配验证（匹配率<80%时检测变化）
     - 验证表头变化检测（新增字段、删除字段、重命名字段）
     - 验证模板版本管理（新版本自动归档旧版本）
   - **模板查找和配置**：
     - 验证三级智能降级匹配（精确匹配 → 忽略sub_domain → 已禁用）
     - 验证模板header_row和header_columns的使用
     - 验证表头匹配验证（仅日志，不阻止同步）

### 技术细节

- **数据采集验证**：
  - 测试 Playwright 采集器下载文件
  - 验证文件注册到 `catalog_files` 表
  - 验证文件元数据正确性（platform_code, shop_id, data_domain, granularity, date_range）
  - 验证文件哈希计算和去重机制

- **文件扫描验证**：
  - 测试 `catalog_scanner.scan_and_register()` 函数
  - 验证文件去重机制（file_hash）
  - 验证文件状态管理（pending/ingested/failed）
  - 验证文件元数据提取逻辑

- **数据同步验证（DSS架构）**：
  - 测试 `DataSyncService.sync_single_file()` 方法
  - 验证模板查找和配置（TemplateMatcher.find_best_template()）
  - 验证模板header_row和header_columns的使用
  - 验证数据入库到B类数据表（DataIngestionService，动态列结构 + raw_data JSONB备份）
  - 验证去重处理（基于核心字段的data_hash）
  - 验证进度跟踪（SyncProgressTracker）
  - **重要**：验证DSS架构（不再执行字段映射、数据标准化、业务逻辑验证和数据隔离）

- **数据完整性验证（DSS架构）**：
  - 验证B类数据表（fact_raw_data_*）数据行数
  - 验证动态列结构（源数据表头字段作为列）
  - 验证raw_data JSONB数据格式（数据备份）
  - 验证元数据字段完整性（platform_code, shop_id, data_hash）
  - 验证去重机制（唯一约束包含platform_code和shop_id，基于核心字段的data_hash）
  - **重要**：验证不再有数据隔离（quarantined_count始终为0）

- **动态列管理验证**：
  - 验证动态列管理服务（DynamicColumnManager）
  - 验证列自动添加（根据header_columns动态添加列）
  - 验证列类型处理（统一使用TEXT类型，支持中文列名）
  - 验证列名冲突处理
  - 验证列数限制处理（PostgreSQL列数限制）

- **核心字段去重验证**：
  - 验证模板配置增强（deduplication_fields字段）
  - 验证data_hash计算逻辑（基于核心字段）
  - 验证默认核心字段配置（根据数据域+子类型）
  - 验证核心字段去重机制（表头变化不影响去重）

- **唯一约束优化验证**：
  - 验证唯一约束包含platform_code和shop_id
  - 验证shop_id为NULL的处理（COALESCE）
  - 验证数据库迁移脚本正确性

- **Metabase 集成验证（DSS架构）**：
  - 验证 Metabase 可以连接 PostgreSQL 数据库
  - 验证 Metabase Question 可以查询B类数据表（fact_raw_data_*）
  - 验证动态列结构符合Metabase要求（源数据表头字段作为列）
  - 验证Metabase可以对所有列进行筛选、排序、聚合
  - 验证Metabase字段映射配置正确（原始表头字段 → 标准字段）
  - 验证Metabase业务逻辑验证规则配置正确
  - 验证前端可以通过 Metabase API 获取数据

- **模板管理与数据同步协同机制验证**：
  - 验证新数据域处理流程（无模板跳过、创建模板、正常同步）
  - 验证表头更新处理流程（表头变化检测、模板版本管理）
  - 验证模板查找和配置（三级智能降级匹配、header_row和header_columns使用）
  - 验证表头匹配验证（仅日志，不阻止同步）

## Impact

### 受影响的规格（Affected Specs）

- **data-sync** (修改规格) - 补充DSS架构下的数据同步流程要求
  - 明确DSS架构下的数据同步流程（移除验证、字段映射、数据标准化）
  - 明确模板管理与数据同步的协同机制
  - 明确新数据域和表头更新的处理流程
  - 定义数据验证和测试场景（Metabase验证，非数据同步验证）
  - 说明与 Metabase 集成的数据要求
  - 补充数据完整性验证要求（去重、JSONB格式）

- **data-collection** (修改规格) - 补充文件注册和元数据验证要求
  - 明确文件注册到 `catalog_files` 表的要求
  - 定义文件元数据完整性要求
  - 说明文件去重机制
  - 补充采集后自动注册的要求

### 受影响的代码（Affected Code）

#### 需要验证/修改的文件
- `modules/apps/collection_center/handlers.py` - 添加采集后自动注册文件功能（新增）
- `modules/collectors/shopee_collector.py` - 验证文件下载和注册
- `modules/services/catalog_scanner.py` - 验证文件扫描和注册
- `backend/routers/data_sync.py` - 验证同步 API，验证清理数据库路由（已确认正确）
- `backend/services/data_sync_service.py` - 验证同步服务
- `backend/services/data_ingestion_service.py` - 验证DSS架构下的数据入库（已移除验证、字段映射、数据标准化），验证空文件处理，修改为传递deduplication_fields
- `backend/services/raw_data_importer.py` - 修改数据入库逻辑（动态列管理、raw_data JSONB备份、唯一约束优化）
- `backend/services/deduplication_service.py` - 修改data_hash计算逻辑（基于核心字段）
- `backend/services/dynamic_column_manager.py` - 创建动态列管理服务（新增）
- `backend/services/deduplication_fields_config.py` - 创建默认核心字段配置（新增）
- `modules/core/db/schema.py` - 修改表结构（添加deduplication_fields字段、修改唯一约束）
- `backend/routers/field_mapping.py` - 验证文件扫描 API，替换硬编码路径（注意：手动验证API保留验证逻辑）
- `backend/services/template_matcher.py` - 验证模板匹配（表头行和表头字段列表）
- `backend/services/data_sync_service.py` - 验证模板查找和配置，验证表头匹配验证
- `backend/services/sync_progress_tracker.py` - 验证进度跟踪
- ⚠️ **v4.12.0移除**：数据浏览器相关文件已完全删除，不再需要验证
  - `backend/routers/data_browser.py` - 已删除
  - `frontend/src/views/DataBrowser.vue` - 已删除
  - `frontend/src/views/DataBrowserSimple.vue` - 已删除
- `frontend/src/views/DataSyncFiles.vue` - 修复刷新按钮和清理数据库按钮
- `frontend/src/api/index.js` - 修复API调用路径
- `backend/routers/collection.py` - 替换硬编码路径
- `modules/core/secrets_manager.py` - 替换硬编码路径

#### 需要创建的文件
- `scripts/test_data_sync_pipeline.py` - 端到端测试脚本
- `docs/DATA_SYNC_PIPELINE_VERIFICATION.md` - 验证文档
- `scripts/verify_database_data.py` - 数据库数据验证脚本
- `modules/core/path_manager.py` - 统一路径配置管理工具（新增）
- `docs/PATH_CONFIGURATION.md` - 路径配置文档（新增）
- `scripts/test_data_collection.py` - 数据采集验证脚本（新增）
- `backend/services/dynamic_column_manager.py` - 动态列管理服务（新增）
- `backend/services/deduplication_fields_config.py` - 默认核心字段配置（新增）
- `alembic/versions/xxxx_add_dynamic_columns.py` - 数据库迁移脚本（新增）

### 破坏性变更（Breaking Changes）

**表结构变更（v4.14.0 - 2025-02-01）**：
- **动态列管理**：所有 `fact_raw_data_*` 表将根据源文件表头动态添加列（TEXT类型）
- **唯一约束优化**：唯一约束从 `(data_domain, granularity, data_hash)` 改为 `(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)`
- **模板配置增强**：`FieldMappingTemplate` 表添加 `deduplication_fields` JSONB 字段
- **数据入库逻辑变更**：数据入库逻辑从"JSONB格式"改为"动态列 + raw_data JSONB备份"
- **data_hash计算变更**：data_hash计算从"所有业务字段"改为"核心字段（deduplication_fields）"

**数据迁移策略**：
- **开发阶段**：清理现有数据，重新同步（用户已确认）
- **生产环境**：需要数据迁移脚本（将现有JSONB数据转换为动态列格式）
- **回滚方案**：保留raw_data JSONB，可以回滚到JSONB格式

## Non-Goals

- ✅ **已修改数据同步实现（v4.13.0）**：已移除字段映射、数据标准化、业务逻辑验证和数据隔离，符合DSS架构原则
- ✅ **数据存储架构优化（v4.14.0）**：实现动态列管理、核心字段去重和唯一约束优化
- ❌ **不引入新的数据采集平台**：仅验证现有平台（Shopee/TikTok/妙手ERP）
- ❌ **不修改 Metabase Question 配置**：Question 配置由 `configure-metabase-dashboard-questions` change 负责
- ❌ **不进行大规模前端迁移**：前端迁移由 `migrate-frontend-dashboard-to-metabase-api` change 负责
- ⚠️ **v4.12.0移除**：数据浏览器功能已完全移除，不再需要修复（2025-02-01更新）
- ✅ **允许修复前端bug**：修复刷新按钮API调用等bug（2025-02-01更新）
- ✅ **允许修改数据库结构**：添加动态列、修改唯一约束、添加deduplication_fields字段（v4.14.0）
- ❌ **不优化性能**：性能优化不在本 change 范围内

## 成功标准

### Phase 0: 数据采集器自动注册实现完成（新增 - 2025-02-01）
- ✅ 数据采集器下载文件后自动调用 `scan_and_register()` 注册文件
- ✅ 文件自动注册到 `catalog_files` 表
- ✅ 文件元数据（platform_code, data_domain, granularity 等）正确提取
- ✅ 文件哈希去重机制正常工作
- ✅ 手动扫描功能保留（数据同步模块中可手动扫描）

### Phase 1: 文件扫描验证完成
- ✅ `catalog_scanner` 可以正确扫描 `data/raw` 目录
- ✅ 文件注册 API (`POST /api/field-mapping/scan`) 正常工作
- ✅ 文件去重机制（file_hash）正常工作
- ✅ 文件元数据完整性验证通过

### Phase 2: 数据同步验证完成（DSS架构）
- ✅ 单文件同步 API (`POST /api/data-sync/single`) 正常工作
- ✅ 批量同步 API (`POST /api/data-sync/batch`) 正常工作
- ✅ 模板查找和配置（表头行和表头字段列表）正常工作
- ✅ 数据入库到B类数据表（fact_raw_data_*，动态列结构 + raw_data JSONB备份）正常工作
- ✅ 去重处理（基于核心字段的data_hash）正常工作
- ✅ 数据同步状态管理正常（pending → processing → ingested/failed）
- ✅ **验证DSS架构**：不再执行字段映射、数据标准化、业务逻辑验证和数据隔离

### Phase 3: 数据入库验证完成（DSS架构）
- ✅ 数据正确写入B类数据表（fact_raw_data_orders_daily, fact_raw_data_products_snapshot 等）
- ✅ 数据以动态列格式存储（系统字段 + 源数据表头字段作为列）
- ✅ raw_data JSONB作为数据备份（用于data_hash计算和数据恢复）
- ✅ 数据完整性验证通过（行数、字段完整性、data_hash唯一性）
- ✅ 去重机制正常工作（唯一约束包含platform_code和shop_id）
- ✅ **验证DSS架构**：不再有数据隔离（quarantined_count始终为0）
- ✅ **验证DSS架构**：业务逻辑验证在Metabase中完成，不在数据同步流程中

### Phase 4: Metabase 集成验证完成
- ✅ Metabase 可以连接数据库
- ✅ Metabase Question 可以查询B类数据表（fact_raw_data_*）
- ✅ 数据格式符合 Metabase 要求
- ✅ 前端可以通过 Metabase API 获取数据

### Phase 5: 端到端验证完成（DSS架构）
- ✅ 端到端测试脚本可以成功运行
- ✅ 文件扫描 → 文件注册 → 模板查找和配置 → 数据入库到B类数据表 → Metabase验证的完整流程验证通过
- ✅ 数据库中有完整数据供 Metabase 查询
- ✅ DSS架构流程验证通过（跳过字段映射、数据标准化、业务逻辑验证和数据隔离）

### Phase 6: 路径配置管理优化完成
- ✅ 统一路径配置管理工具已创建（`modules/core/path_manager.py`）
- ✅ 所有硬编码路径已替换为统一路径管理函数
- ✅ 支持环境变量配置（PROJECT_ROOT、DATA_DIR等）
- ✅ 项目迁移时路径配置正常工作

### Phase 7: 动态列管理功能完成（新增 - 2025-02-01）
- ✅ 动态列管理服务已创建（DynamicColumnManager）
- ✅ 根据源文件表头动态添加列到PostgreSQL表（TEXT类型，支持中文列名）
- ✅ 保留raw_data JSONB作为数据备份（用于data_hash计算和数据恢复）
- ✅ 处理列名冲突和列数限制
- ✅ Metabase可以查询所有列（源数据表头字段作为列）

### Phase 8: 核心字段去重功能完成（新增 - 2025-02-01）
- ✅ 模板配置增强（添加deduplication_fields字段）
- ✅ data_hash计算逻辑修改（基于核心字段，不受表头变化影响）
- ✅ 默认核心字段配置已创建（根据数据域+子类型）
- ✅ 核心字段去重机制正常工作（表头新增字段不影响去重）

### Phase 9: 唯一约束优化完成（新增 - 2025-02-01）
- ✅ 所有fact_raw_data_*表的唯一约束已修改（包含platform_code和shop_id）
- ✅ shop_id为NULL的处理（使用COALESCE）
- ✅ 数据库迁移脚本已创建并执行

### Phase 10: 功能按钮修复完成（数据浏览器已移除 - v4.12.0）
- ⚠️ **v4.12.0移除**：数据浏览器功能已完全移除，使用Metabase替代（http://localhost:8080）
- ✅ 清理数据库功能正常工作（API路由已验证正确，清理B类数据表）
- ✅ 刷新按钮功能正常工作（API路由修复，扫描文件目录）
- ✅ 空文件处理逻辑验证通过（识别、跳过、状态管理，已实现）

### Phase 11: 数据采集验证完成（Phase 0已实现自动注册）
- ✅ 数据采集器可以成功下载文件
- ✅ 文件自动注册到 `catalog_files` 表（Phase 0已实现自动注册功能）
- ✅ 验证自动注册功能正常工作（文件元数据、路径、哈希等）
- ✅ 文件元数据（platform_code, data_domain, granularity 等）正确提取
- ✅ 文件哈希去重机制正常工作
- ✅ 验证自动注册与手动扫描不冲突

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 数据采集失败 | 高 | 提供详细的错误日志和调试指南，支持手动文件上传 |
| 文件注册失败 | 中 | 验证文件元数据提取逻辑，提供手动注册选项 |
| 数据同步失败 | 高 | 提供详细的同步日志和错误处理，支持重试机制 |
| 数据入库失败 | 高 | 验证数据入库逻辑（DSS架构下不验证业务逻辑，不隔离数据） |
| 数据不完整 | 中 | 提供数据完整性检查工具，验证数据行数和字段完整性 |
| 动态列管理失败 | 高 | 验证动态列管理服务，处理列名冲突和列数限制 |
| 核心字段去重失败 | 高 | 验证核心字段配置和data_hash计算逻辑 |
| 唯一约束优化失败 | 高 | 验证数据库迁移脚本，处理shop_id为NULL的情况 |
| Metabase 查询失败 | 中 | 验证数据库连接和权限，提供查询测试工具 |
| ⚠️ v4.12.0移除：数据浏览器功能已完全移除 | N/A | 使用Metabase替代，不再需要验证数据浏览器 |
| 清理数据库功能失败 | 中 | 修复API路由不一致问题，验证清理逻辑 |
| 刷新按钮功能失败 | 中 | 修复API调用问题，验证刷新逻辑 |
| 空文件处理失败 | 低 | 验证空文件识别和处理机制 |
| 路径硬编码导致迁移失败 | 高 | 创建统一路径配置管理工具，支持环境变量配置 |
| 路径解析在不同工作目录下失败 | 中 | 统一路径解析逻辑，支持从任意目录运行 |

## 预期收益

1. **数据完整性保证**：确保数据同步管道完整工作，数据库有完整数据
2. **Metabase 集成支持（DSS架构）**：确保 Metabase 可以查询B类数据表数据（fact_raw_data_*），前端可以获取数据
3. **可维护性提升**：通过端到端测试和验证，提高系统可维护性
4. **问题定位能力**：通过详细的日志和错误处理，提高问题定位能力
5. **开发效率提升**：通过自动化测试脚本，提高开发和调试效率

## 依赖关系

- **前置依赖**：
  - `configure-metabase-dashboard-questions` - Metabase Question 配置已完成
  - 数据采集功能已实现（Playwright 采集器）
  - 字段映射功能已实现（TemplateMatcher, FieldMappingService）
  - 数据入库功能已实现（DataIngestionService）

- **后续依赖**：
  - `migrate-frontend-dashboard-to-metabase-api` - 前端迁移需要数据库有数据

## 验收标准

1. **功能验收**：
   - 文件扫描 → 文件注册 → 数据同步 → 数据入库的完整流程可以正常运行
   - 数据库中有完整的B类数据表数据（fact_raw_data_*，动态列结构）
   - Metabase 可以查询B类数据表数据（fact_raw_data_*，所有列可见）
   - 数据采集器可以成功下载文件并注册（Phase 11验证）
   - 动态列管理功能正常工作（源数据表头字段作为列）
   - 核心字段去重机制正常工作（表头变化不影响去重）
   - 唯一约束优化完成（包含platform_code和shop_id）

2. **测试验收**：
   - 端到端测试脚本可以成功运行
   - 所有验证场景通过测试

3. **文档验收**：
   - 验证文档完整，包含测试步骤和故障排查指南

