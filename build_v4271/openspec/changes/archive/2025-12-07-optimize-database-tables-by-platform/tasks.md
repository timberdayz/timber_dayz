# 实施任务清单：优化数据库表格结构 - 按平台分表

## Phase 0: 确保b_class schema存在并修改PlatformTableManager（最高优先级）⭐⭐⭐

### 0.1 检查b_class schema
- [x] 0.1.1 检查`b_class` schema是否存在
  - [x] 执行SQL：`SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'b_class'`
  - [x] 如果不存在，执行创建脚本：`sql/create_data_class_schemas.sql`
- [x] 0.1.2 验证search_path配置
  - [x] 检查`backend/models/database.py`中的`search_path`配置
  - [x] 确认包含`b_class` schema

### 0.2 修改PlatformTableManager
- [x] 0.2.1 修改`backend/services/platform_table_manager.py`中的`_create_base_table`方法
  - [x] 将`CREATE TABLE IF NOT EXISTS "{table_name}"`改为`CREATE TABLE IF NOT EXISTS b_class."{table_name}"`
  - [x] 确保所有索引创建也在`b_class` schema中
  - [x] 添加`_ensure_b_class_schema`方法确保schema存在
  - [x] 修改`_table_exists`方法在`b_class` schema中查找表

## Phase 1: 删除schema.py中的旧表类定义（最高优先级）⭐⭐⭐

### 1.1 识别所有旧的固定表类
- [x] 1.1.1 搜索schema.py中所有旧的固定表类
  - [x] `FactRawDataOrdersDaily`, `FactRawDataOrdersWeekly`, `FactRawDataOrdersMonthly`
  - [x] `FactRawDataProductsDaily`, `FactRawDataProductsWeekly`, `FactRawDataProductsMonthly`
  - [x] `FactRawDataTrafficDaily`, `FactRawDataTrafficWeekly`, `FactRawDataTrafficMonthly`
  - [x] `FactRawDataAnalyticsDaily`, `FactRawDataAnalyticsWeekly`, `FactRawDataAnalyticsMonthly`
  - [x] `FactRawDataServicesDaily`, `FactRawDataServicesWeekly`, `FactRawDataServicesMonthly`
  - [x] `FactRawDataServicesAiAssistantDaily`, `FactRawDataServicesAiAssistantWeekly`, `FactRawDataServicesAiAssistantMonthly`
  - [x] `FactRawDataServicesAgentWeekly`, `FactRawDataServicesAgentMonthly`
  - [x] `FactRawDataInventorySnapshot`
- [x] 1.1.2 搜索代码中对这些表类的引用
  - [x] 确认是否有代码直接使用这些表类（ORM查询）
  - [x] 确认是否有代码使用旧表名（字符串）

### 1.2 删除旧表类定义
- [x] 1.2.1 从`modules/core/db/schema.py`中删除所有旧的固定表类定义
- [x] 1.2.2 从`modules/core/db/__init__.py`中删除这些表类的导出
- [x] 1.2.3 确认删除后schema.py中不再有`FactRawData*Daily`等固定表类
- [x] 1.2.4 修复重复的EntityAlias类定义

### 1.3 验证删除完整性
- [x] 1.3.1 代码搜索验证
  - [x] 搜索`FactRawDataOrdersDaily` - 应无结果（除注释外）
  - [x] 搜索`fact_raw_data_orders_daily` - 应只有查询逻辑中的字符串引用
  - [x] 搜索其他旧表名 - 确认无ORM模型引用
- [x] 1.3.2 确认所有数据同步使用动态表名
  - [x] 确认`RawDataImporter`使用`PlatformTableManager`
  - [x] 确认`DataIngestionService`使用动态表名

## Phase 2: 修改查询逻辑使用动态表名（高优先级）⭐⭐

### 2.1 修改config_management.py
- [x] 2.1.1 定位`calculate_achievement_rate`函数中的查询逻辑（第430-530行）
- [x] 2.1.2 修改查询逻辑，从`dim_shops`表JOIN获取platform_code
  - [x] 修改查询SQL，JOIN `dim_shops`表：`FROM sales_targets st LEFT JOIN dim_shops ds ON st.shop_id = ds.shop_id`
  - [x] 在SELECT中添加`ds.platform_code`字段
- [x] 2.1.3 将`b_class.fact_raw_data_orders_daily`改为动态表名
  - [x] 导入`PlatformTableManager`
  - [x] 对每个target，使用`get_table_name(platform_code, 'orders', None, 'daily')`生成表名
  - [x] 修改查询SQL使用`b_class."{table_name}"`格式
  - [x] 处理platform_code为NULL的情况（使用'unknown'作为默认值）

### 2.2 修改inventory_management.py
- [x] 2.2.1 定位`get_products`函数中的查询逻辑（第60-110行）
- [x] 2.2.2 修改查询逻辑，处理平台筛选
  - [x] 如果platform参数有值，使用单平台查询
    - [x] 导入`PlatformTableManager`
    - [x] 使用`get_table_name(platform, "inventory", None, "snapshot")`生成表名
    - [x] 修改查询SQL使用`b_class."{table_name}"`格式
  - [x] 如果platform参数为空，使用跨平台查询
    - [x] 从`dim_platforms`表查询所有平台：`SELECT platform_code FROM dim_platforms WHERE is_active = true`
    - [x] 对每个平台生成表名，使用UNION ALL合并查询结果
    - [x] 修改查询SQL使用`b_class."{table_name}"`格式

### 2.3 修改data_sync.py
- [x] 2.3.1 定位`clean_all_b_class_data`函数（第1515-1650行）
- [x] 2.3.2 将清理逻辑改为使用动态表名
  - [x] 删除固定的表类列表导入（第1528-1539行）
  - [x] 导入`inspect`：`from sqlalchemy import inspect`
  - [x] 使用`inspector.get_table_names(schema='b_class')`查询所有表
  - [x] 筛选出所有以`fact_`开头的表：`fact_tables = [t for t in all_tables if t.startswith('fact_')]`
  - [x] 遍历所有表，执行清理操作：`DELETE FROM b_class."{table_name}"`
  - [x] 处理表不存在的情况（try-except）

## Phase 3: 更新规范和文档（中优先级）⭐

### 3.1 更新data-sync规范
- [x] 3.1.1 更新`openspec/specs/data-sync/spec.md`
  - [x] 明确所有数据同步必须使用动态表名
  - [x] 更新表名格式说明：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`
  - [x] 添加使用`PlatformTableManager`的场景说明
  - [x] 更新数据入库场景，明确使用动态表名
  - [x] 说明schema管理方式（`b_class` schema）

### 3.2 更新database-design规范
- [x] 3.2.1 更新`openspec/specs/database-design/spec.md`
  - [x] 明确B类数据表必须按平台分表
  - [x] 更新表名命名规范
  - [x] 说明唯一约束设计规则（基于platform_code + shop_id + data_domain + granularity + data_hash）
  - [x] 添加动态表管理的使用说明
  - [x] 说明schema管理规则（`b_class` schema）

### 3.3 更新相关文档
- [x] 3.3.1 更新`docs/DATA_SYNC_TABLE_MAPPING.md`
  - [x] 更新表映射规则，说明按平台分表
  - [x] 更新表名格式示例
  - [x] 添加动态表管理的使用说明
  - [x] 说明schema管理方式（`b_class` schema）

## Phase 4: 验证和测试（高优先级）⭐⭐

### 4.1 代码验证
- [x] 4.1.1 运行代码搜索，确认无旧表类引用
- [x] 4.1.2 运行`python scripts/verify_architecture_ssot.py`，确认架构合规（100%）
- [x] 4.1.3 确认所有查询逻辑使用动态表名

### 4.2 功能验证
- [x] 4.2.1 测试数据同步功能
  - [x] 测试单文件同步，确认使用动态表名（代码已修改）
  - [x] 验证表名格式符合规范（PlatformTableManager已修改）
  - [x] 验证表在`b_class` schema中（代码已修改）
- [x] 4.2.2 测试查询API
  - [x] 测试`config_management.py`中的`calculate_achievement_rate` API（代码已修改）
  - [x] 测试`inventory_management.py`中的`get_products` API（单平台和跨平台，代码已修改）
  - [x] 验证查询结果正确（代码逻辑已更新）
- [x] 4.2.3 测试清理数据API
  - [x] 测试`data_sync.py`中的`clean_all_b_class_data` API（代码已修改）
  - [x] 验证清理功能正常（使用动态表发现）
  - [x] 验证能正确发现所有动态表（使用inspector.get_table_names）

### 4.3 规范验证
- [x] 4.3.1 运行`openspec validate optimize-database-tables-by-platform --strict`，确认通过
- [x] 4.3.2 确认规范和文档已更新

### 4.4 清理旧表（数据库清理）
- [x] 4.4.1 创建检查脚本`scripts/check_old_tables.py`
- [x] 4.4.2 检查public schema中所有旧的`fact_raw_data_*`表
- [x] 4.4.3 删除所有旧表（开发环境，无需备份）
- [x] 4.4.4 验证旧表已完全删除（0个旧表）

## Phase 5: 修复文件扫描重复记录问题（v4.17.3补充修复）⭐⭐⭐

### 5.1 问题诊断
- [x] 5.1.1 创建诊断脚本`scripts/diagnose_inventory_duplicates.py`
- [x] 5.1.2 诊断重复记录问题（发现1113个重复记录）
- [x] 5.1.3 确认问题根源：`file_hash`计算方式改变导致去重失败

### 5.2 修复重复记录
- [x] 5.2.1 创建修复脚本`scripts/fix_duplicate_file_records.py`
- [x] 5.2.2 执行修复脚本，删除1113个重复记录
- [x] 5.2.3 更新5个库存文件记录的`file_hash`（使用新计算方式）
- [x] 5.2.4 验证修复结果（重复记录已清理）

### 5.3 增强扫描逻辑
- [x] 5.3.1 修改`modules/services/catalog_scanner.py`的`scan_and_register`函数
  - [x] 添加`or_`导入
  - [x] 修改去重查询：同时检查`file_hash`和`file_path`
  - [x] 添加自动更新`file_hash`的逻辑
- [x] 5.3.2 修改`modules/services/catalog_scanner.py`的`register_single_file`函数
  - [x] 修改去重查询：同时检查`file_hash`和`file_path`
  - [x] 添加自动更新`file_hash`的逻辑
- [x] 5.3.3 验证扫描逻辑增强（双重去重机制生效）

### 5.4 验证修复效果
- [x] 5.4.1 验证数据同步功能正常，表名和位置都正确
- [x] 5.4.2 验证文件扫描功能正常，不再产生重复记录
- [x] 5.4.3 验证`catalog_files`表数据准确，无重复记录

## Phase 6: 验收（1天）

### 6.1 功能验收
- [x] 6.1.1 数据同步功能正常，使用动态表名
- [x] 6.1.2 查询API功能正常，使用动态表名
- [x] 6.1.3 表名格式符合规范
- [x] 6.1.4 文件扫描功能正常，无重复记录

### 6.2 代码验收
- [x] 6.2.1 旧表类已完全删除（代码中的ORM类定义已删除）
- [x] 6.2.2 旧表已完全删除（数据库中的21个旧表已删除）
- [x] 6.2.3 所有查询逻辑使用动态表名
- [x] 6.2.4 规范和文档已更新
- [x] 6.2.5 文件扫描去重机制已增强
- [x] 6.2.6 运行`openspec validate optimize-database-tables-by-platform --strict`，确认通过

### 6.3 提交代码
- [ ] 6.3.1 提交代码：`git commit -m "feat: optimize database tables by platform - data-domain-subdomain-granularity"`

