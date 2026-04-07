# Change: 优化数据库表格结构 - 按平台-数据域-子类型-粒度分表

## Why

当前系统虽然代码已经支持按平台分表（v4.17.0新增`PlatformTableManager`），但数据库表结构设计存在以下问题：

1. **schema.py中仍有旧的固定表结构**：按`data_domain + granularity`分表（如`fact_raw_data_orders_daily`），没有区分平台
2. **用户查询困难**：用户无法通过"平台-数据域-子类型-粒度"直接检查数据，需要额外添加`WHERE platform_code = 'xxx'`条件
3. **架构不一致**：代码层面已支持动态表名（`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`），但schema.py中仍保留旧表结构，造成混淆
4. **代码中仍有使用旧表名的地方**：`config_management.py`和`inventory_management.py`中直接使用旧表名查询

**根本原因**：v4.17.0引入了按平台分表的动态表管理机制，但未完全清理旧的固定表结构，导致架构不统一。

## 架构定位

**PostgreSQL角色**：
- 只负责存储和提供干净完整的数据
- 表结构清晰，便于用户直接查看数据是否存在问题
- 一个模板一个表，便于管理维护
- 使用`b_class` schema组织B类数据表，便于Metabase中清晰区分

**Metabase角色**：
- 使用模型功能将所有表串联起来
- 所有运算和关联都在Metabase中进行处理
- 跨平台查询、复杂关联查询都在Metabase中完成
- 用户通过Metabase查看数据，表多不是问题，反而便于管理和查看

**表多的优势**：
- ✅ 便于用户查看数据是否存在问题（通过表名直接识别平台-数据域-子类型-粒度）
- ✅ 一个模板一个表，便于管理维护
- ✅ 表结构清晰，职责单一
- ✅ Metabase会处理所有复杂查询，表多不是问题

## What Changes

### 核心变更

1. **确保b_class schema存在并修改PlatformTableManager** ⭐⭐⭐
   - 检查`b_class` schema是否存在，如果不存在则创建
   - 修改`PlatformTableManager._create_base_table`方法，确保表创建在`b_class` schema中
   - 使用`CREATE TABLE IF NOT EXISTS b_class."{table_name}"`格式

2. **完全删除schema.py中的旧固定表类定义** ⭐⭐⭐
   - 删除所有旧的固定表类（`FactRawDataOrdersDaily`、`FactRawDataOrdersWeekly`等）
   - 从`modules/core/db/__init__.py`中删除导出
   - **原因**：旧表中无数据，开发环境无需备份，完全删除避免混淆

3. **修改查询逻辑使用动态表名** ⭐⭐
   - 修改`config_management.py`中的`calculate_achievement_rate`函数：
     - 从`sales_targets`表JOIN `dim_shops`表获取`platform_code`
     - 使用`PlatformTableManager.get_table_name()`生成表名
     - 查询时使用`b_class.{table_name}`格式
   - 修改`inventory_management.py`中的`get_products`函数：
     - 如果platform参数为空，从`dim_platforms`表查询所有平台
     - 使用UNION ALL合并所有平台表的查询结果
     - 查询时使用`b_class.{table_name}`格式
   - 修改`data_sync.py`中的`clean_all_b_class_data`函数：
     - 使用`inspector.get_table_names(schema='b_class')`查询所有表
     - 筛选出所有以`fact_`开头的表
     - 遍历所有表执行清理操作
   - **实现方式**：使用`PlatformTableManager.get_table_name()`生成表名，通过SQLAlchemy的`text()`函数执行原始SQL

4. **更新数据同步和数据库设计规范** ⭐
   - 更新`data-sync`规范，明确所有数据同步必须使用动态表名
   - 更新`database-design`规范，明确B类数据表必须按平台分表
   - 说明schema管理方式（`b_class` schema）
   - 更新相关文档

### 技术细节

- **表名格式**：
  - 无sub_domain：`fact_{platform}_{data_domain}_{granularity}`（如`fact_shopee_orders_daily`）
  - 有sub_domain：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`（如`fact_shopee_services_ai_assistant_monthly`）

- **Schema管理**：
  - 所有B类数据表存储在`b_class` schema中
  - 使用`b_class.{table_name}`格式创建和查询表
  - `search_path`已配置，支持直接使用表名（向后兼容）

- **动态表管理**：
  - 使用`PlatformTableManager`动态创建表（如果不存在）
  - 表创建在`b_class` schema中：`CREATE TABLE IF NOT EXISTS b_class."{table_name}"`
  - 表结构统一：系统字段（id, platform_code, shop_id等）+ 动态列（根据模板字段）
  - 唯一约束：基于`platform_code + shop_id + data_domain + granularity + data_hash`

- **PostgreSQL动态表名实现**：
  - 使用SQLAlchemy的`text()`函数执行原始SQL
  - 表名作为字符串参数传入（用双引号包裹，避免大小写问题）
  - 使用参数化查询（`:platform_code`），防止SQL注入
  - PostgreSQL完全支持这种动态表名查询

- **跨平台查询实现**：
  - 单平台查询：直接使用`PlatformTableManager.get_table_name()`生成表名
  - 跨平台查询：从`dim_platforms`表查询所有平台，使用UNION ALL合并查询结果
  - 复杂跨平台查询在Metabase中处理，后端查询逻辑保持简单

## Impact

### 受影响的规格（Affected Specs）

- **data-sync** (修改规格) - 明确数据同步必须使用动态表名
  - 更新表名生成规则
  - 明确表名格式：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`
  - 说明动态表管理的使用方式

- **database-design** (修改规格) - 更新数据库设计规范
  - 明确B类数据表必须按平台分表
  - 更新表名命名规范
  - 说明唯一约束设计规则

### 受影响的代码（Affected Code）

#### 需要修改的文件
- `backend/services/platform_table_manager.py` - 修改`_create_base_table`方法，确保表创建在`b_class` schema中
- `modules/core/db/schema.py` - 删除所有旧的固定表类定义
- `modules/core/db/__init__.py` - 删除旧表类的导出
- `backend/routers/config_management.py` - 修改`calculate_achievement_rate`函数，从`dim_shops`表JOIN获取platform_code，使用动态表名
- `backend/routers/inventory_management.py` - 修改`get_products`函数，从`dim_platforms`表查询所有平台，使用动态表名
- `backend/routers/data_sync.py` - 修改`clean_all_b_class_data`函数，使用`inspector.get_table_names`查询所有表
- `modules/services/catalog_scanner.py` - 增强文件扫描去重机制（基于`file_hash`和`file_path`双重去重，自动更新`file_hash`）
- `openspec/specs/data-sync/spec.md` - 更新数据同步规范，说明schema管理方式
- `openspec/specs/database-design/spec.md` - 更新数据库设计规范，说明schema管理规则
- `docs/DATA_SYNC_TABLE_MAPPING.md` - 更新表映射文档，说明schema管理方式

#### 不需要修改的文件（已支持动态表）
- `backend/services/raw_data_importer.py` - 已使用动态表名，无需修改
- `frontend/` - 前端不直接查询表，所有查询都通过后端API，无需修改

#### 补充修复文件（v4.17.3）
- `scripts/fix_duplicate_file_records.py` - 批量修复重复记录脚本
- `scripts/diagnose_inventory_duplicates.py` - 诊断重复记录问题脚本

### 破坏性变更（Breaking Changes）

**有破坏性变更** - 本change将完全删除旧的固定表类定义，但：
- ✅ 旧表中无数据，无需数据迁移
- ✅ 开发环境，无需备份
- ✅ 所有查询逻辑将改为使用动态表名

**迁移策略**：
1. 确保`b_class` schema存在
2. 修改`PlatformTableManager`确保表创建在`b_class` schema中
3. 删除旧表类定义
4. 修改查询逻辑使用动态表名
5. 更新规范和文档
6. 验证所有功能正常工作

## Non-Goals

- ❌ **不在本change中实现跨平台查询优化**：跨平台查询在Metabase中处理，后端查询逻辑保持简单
- ❌ **不在本change中修改前端代码**：前端不直接查询表，无需修改
- ❌ **不在本change中实现数据迁移**：旧表中无数据，无需迁移
- ❌ **不在本change中优化Metabase模型**：Metabase模型配置由单独change负责

## 成功标准

### Phase 0: 确保b_class schema存在
- ✅ `b_class` schema已存在或已创建
- ✅ `PlatformTableManager`已修改，确保表创建在`b_class` schema中

### Phase 1: 删除旧表类定义
- ✅ 所有旧的固定表类已从schema.py中删除
- ✅ 从`modules/core/db/__init__.py`中删除导出
- ✅ 代码搜索确认无代码直接使用旧表类

### Phase 2: 修改查询逻辑
- ✅ `config_management.py`使用动态表名查询，从`dim_shops`表JOIN获取platform_code
- ✅ `inventory_management.py`使用动态表名查询，从`dim_platforms`表查询所有平台
- ✅ `data_sync.py`清理数据API使用`inspector.get_table_names`查询所有表

### Phase 3: 更新规范和文档
- ✅ `data-sync`规范已更新，说明schema管理方式
- ✅ `database-design`规范已更新，说明schema管理规则
- ✅ 相关文档已更新

### Phase 4: 验证
- ✅ 运行`python scripts/verify_architecture_ssot.py`，确认架构合规
- ✅ 验证数据同步使用动态表名，表在`b_class` schema中
- ✅ 验证查询API使用动态表名，查询结果正确

### Phase 5: 修复文件扫描重复记录问题（v4.17.3补充修复）⭐⭐⭐
- ✅ 诊断并修复`file_hash`计算方式改变导致的重复记录问题
- ✅ 清理1113个重复的`catalog_files`记录
- ✅ 更新5个库存文件记录的`file_hash`（使用新计算方式）
- ✅ 增强扫描逻辑的去重机制（基于`file_hash`和`file_path`双重去重）
- ✅ 自动更新旧记录的`file_hash`（如果hash计算方式改变）
- ✅ 验证数据同步功能正常，表名和位置都正确

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 查询代码遗漏修改 | 中 | 代码搜索确认所有旧表名引用已修改 |
| 动态表名查询性能 | 低 | PostgreSQL完全支持动态表名，性能无影响 |
| Schema配置问题 | 低 | `b_class` schema已存在，`search_path`已配置 |
| 跨平台查询复杂度 | 低 | 跨平台查询在Metabase中处理，后端查询逻辑简单 |
| 表数量多 | 无 | 表多不是问题，Metabase会处理所有复杂查询，便于管理和查看 |

## 预期收益

1. **架构一致性**：代码和数据库表结构完全统一，都按平台分表 ⭐⭐⭐
2. **用户友好性**：用户可以通过"平台-数据域-子类型-粒度"直接检查数据，无需额外筛选条件
3. **代码清晰性**：删除旧的固定表结构，避免混淆，防止使用错误的表结构
4. **可维护性提升**：统一的表名格式，便于后续维护和扩展
5. **Metabase友好**：表结构清晰，便于Metabase模型配置和关联 ⭐⭐⭐
6. **管理便利性**：一个模板一个表，便于管理和维护 ⭐⭐
7. **Schema组织**：使用`b_class` schema组织表，便于Metabase中清晰区分 ⭐⭐
8. **数据质量保障**：增强的文件扫描去重机制，确保`catalog_files`表数据准确，避免重复记录 ⭐⭐⭐

## 补充修复：文件扫描重复记录问题（v4.17.3）

### 问题描述

在实施过程中发现，v4.17.3修复后`file_hash`计算方式改变（包含`shop_id`和`platform_code`），导致：
- 旧记录的`file_hash`不包含`shop_id`和`platform_code`
- 新记录的`file_hash`包含`shop_id`和`platform_code`
- 同一文件产生不同的`file_hash`，去重失败，被注册为多条记录

**具体表现**：
- 文件系统：5个库存文件
- 数据库：10个记录（每个文件2条记录）
- 重复记录总数：1113个（跨所有数据域）

### 修复措施

#### 方案1：重新计算并清理重复记录
- 创建并执行`scripts/fix_duplicate_file_records.py`
- 删除1113个重复记录（保留hash正确的记录）
- 更新5个库存文件记录的`file_hash`（使用新计算方式）

#### 方案3：增强扫描逻辑的去重机制
- 修改`modules/services/catalog_scanner.py`：
  - `scan_and_register`函数：基于`file_hash`和`file_path`双重去重
  - `register_single_file`函数：同样使用双重去重
  - 自动更新`file_hash`：如果发现旧记录的hash与新计算方式不同，自动更新

### 技术实现

**修改文件**：
- `modules/services/catalog_scanner.py`：
  - 添加`or_`导入
  - 修改去重查询：同时检查`file_hash`和`file_path`
  - 添加自动更新`file_hash`的逻辑

**修复脚本**：
- `scripts/fix_duplicate_file_records.py`：批量修复重复记录
- `scripts/diagnose_inventory_duplicates.py`：诊断重复记录问题

### 验证结果

- ✅ 重复记录已清理（1113个重复记录已删除）
- ✅ 扫描逻辑已增强，可防止未来出现类似问题
- ✅ 数据同步功能正常，表名和位置都正确
- ✅ 文件扫描功能正常，不再产生重复记录

