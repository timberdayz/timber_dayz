# v4.14.0 动态列管理和核心字段去重实现总结

## 实现概述

v4.14.0版本实现了以下核心功能：
1. **动态列管理**：根据源文件表头动态添加列到PostgreSQL表
2. **核心字段去重**：基于核心字段计算data_hash，不受表头变化影响
3. **唯一约束优化**：唯一约束包含platform_code和shop_id

## 已完成的工作

### Phase 7: 动态列管理功能 ✅

#### 7.1 创建动态列管理服务 ✅
- ✅ 创建 `backend/services/dynamic_column_manager.py`
- ✅ 实现 `ensure_columns_exist()` 函数（根据header_columns动态添加列）
- ✅ 实现 `get_existing_columns()` 函数（查询表现有列）
- ✅ 实现列名冲突处理（PostgreSQL列名限制和冲突检测）
- ✅ 实现列数限制处理（PostgreSQL列数限制1600列）
- ✅ 添加错误处理和日志记录

#### 7.2 模板配置增强 ✅
- ✅ 修改 `FieldMappingTemplate` 表结构（添加 `deduplication_fields` JSONB字段）
- ✅ 创建数据库迁移脚本 `scripts/migrate_add_deduplication_fields.py`

#### 7.3 核心字段配置 ✅
- ✅ 创建 `backend/services/deduplication_fields_config.py`
- ✅ 定义各数据域+子类型的默认核心字段
- ✅ 实现 `get_default_deduplication_fields()` 函数

#### 7.4 修改表结构 ✅
- ✅ 保留 `raw_data` JSONB 列（用于 data_hash 计算和数据备份）
- ✅ 保留 `header_columns` JSONB 列
- ✅ 保留 `data_hash` 列
- ✅ 创建唯一约束迁移脚本 `scripts/migrate_unique_constraint_v4_14_0.py`

#### 7.5 修改 data_hash 计算逻辑 ✅
- ✅ 修改 `backend/services/deduplication_service.py`
- ✅ `calculate_data_hash()` 支持 `deduplication_fields` 参数
- ✅ `batch_calculate_data_hash()` 支持 `deduplication_fields` 参数

#### 7.6 修改数据入库逻辑 ✅
- ✅ 修改 `backend/services/raw_data_importer.py`
  - ✅ 调用 `dynamic_column_manager.ensure_columns_exist()` 确保列存在
  - ✅ 将源数据表头字段填充到列中（TEXT类型）
  - ✅ 修改 `ON CONFLICT` 逻辑（向后兼容，检查新索引是否存在）
- ✅ 修改 `backend/services/data_ingestion_service.py`
  - ✅ 从模板读取 `deduplication_fields` 配置
  - ✅ 使用默认核心字段配置（如果模板没有配置）
  - ✅ 传递 `deduplication_fields` 到 `batch_calculate_data_hash()`
- ✅ 修改 `backend/services/data_sync_service.py`
  - ✅ 从模板读取 `deduplication_fields` 配置
  - ✅ 传递 `deduplication_fields` 和 `sub_domain` 到 `ingest_data()`

### Phase 8: 核心字段去重功能 ✅

#### 8.1 模板配置增强
- ⚠️ 8.1.1 修改模板保存逻辑（前端部分，待实现）
  - ⚠️ 在保存模板时支持保存 `deduplication_fields`（可选）
  - ⚠️ 如果用户未指定，使用默认核心字段配置
  - ⚠️ 验证 `deduplication_fields` 格式（JSONB数组）

#### 8.2 默认核心字段配置 ✅
- ✅ 定义默认核心字段（根据数据域+子类型）
- ✅ 实现核心字段获取逻辑（优先级：模板配置 > 默认配置 > 所有字段）

#### 8.3 验证核心字段去重机制
- ⚠️ 需要实际测试验证

### Phase 9: 唯一约束优化 ✅

#### 9.1 修改唯一约束 ✅
- ✅ 创建迁移脚本 `scripts/migrate_unique_constraint_v4_14_0.py`
- ✅ 处理 shop_id 为 NULL 的情况（使用 COALESCE(shop_id, '')）

#### 9.2 验证唯一约束
- ⚠️ 需要实际测试验证

#### 9.3 数据库迁移
- ⚠️ 需要执行迁移脚本

## 下一步工作

### 1. 执行数据库迁移脚本

#### 1.1 添加deduplication_fields字段
```bash
python scripts/migrate_add_deduplication_fields.py
```

#### 1.2 更新唯一约束
```bash
python scripts/migrate_unique_constraint_v4_14_0.py
```

### 2. 清理已入库数据（开发阶段）

由于表结构变更（动态列），需要清理现有数据：
```bash
# 使用清理数据库API或直接执行SQL
# POST /api/data-sync/cleanup-database
```

### 3. 测试和验证

#### 3.1 单元测试
- [ ] 测试动态列管理服务（ensure_columns_exist, get_existing_columns）
- [ ] 测试核心字段去重逻辑（calculate_data_hash with deduplication_fields）
- [ ] 测试 data_hash 计算（基于核心字段）

#### 3.2 集成测试
- [ ] 测试完整数据同步流程（文件 → 动态列 → 入库）
- [ ] 测试核心字段去重（表头变化不影响去重）
- [ ] 测试唯一约束（包含 platform_code 和 shop_id）

#### 3.3 验证 Metabase 查询
- [ ] 验证 Metabase 可以看到所有列（源数据表头字段作为列）
- [ ] 验证 Metabase 可以对列进行筛选、排序、聚合

### 4. 前端模板保存逻辑（可选）

如果需要用户手动配置核心字段：
- [ ] 在模板保存界面添加 `deduplication_fields` 配置选项
- [ ] 如果用户未指定，使用默认核心字段配置

## 技术细节

### 动态列管理

**列名规范化规则**：
- 替换特殊字符为下划线
- 移除连续的下划线
- 截断到最大长度（63字符）
- 确保不以数字开头

**列数限制**：
- PostgreSQL最大列数：1600列
- 如果超过限制，只添加前N个列（N = 1600 - 现有列数）

### 核心字段去重

**优先级**：
1. 模板配置的 `deduplication_fields`
2. 默认核心字段配置（根据data_domain和sub_domain）
3. 所有业务字段（向后兼容）

**字段匹配**：
- 支持精确匹配
- 支持忽略大小写匹配
- 如果字段未找到，记录警告但不影响计算

### 唯一约束优化

**新的唯一索引**：
```sql
CREATE UNIQUE INDEX uq_{table_name}_hash_v2 
ON {table_name} 
(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)
```

**向后兼容**：
- 代码会检查新索引是否存在
- 如果不存在，使用旧的唯一约束（data_domain, granularity, data_hash）
- 迁移脚本运行后，自动使用新索引

## 文件清单

### 新增文件
- `backend/services/dynamic_column_manager.py` - 动态列管理服务
- `backend/services/deduplication_fields_config.py` - 默认核心字段配置
- `scripts/migrate_add_deduplication_fields.py` - 添加deduplication_fields字段迁移脚本
- `scripts/migrate_unique_constraint_v4_14_0.py` - 唯一约束迁移脚本
- `docs/V4_14_0_DYNAMIC_COLUMNS_IMPLEMENTATION.md` - 本文档

### 修改文件
- `modules/core/db/schema.py` - 添加deduplication_fields字段，更新唯一约束注释
- `backend/services/deduplication_service.py` - 支持核心字段去重
- `backend/services/raw_data_importer.py` - 集成动态列管理，修改ON CONFLICT逻辑
- `backend/services/data_ingestion_service.py` - 传递deduplication_fields
- `backend/services/data_sync_service.py` - 从模板读取deduplication_fields

## 注意事项

1. **数据库迁移**：必须先运行迁移脚本，才能使用新功能
2. **数据清理**：开发阶段需要清理现有数据（表结构变更）
3. **向后兼容**：代码支持向后兼容（检查新索引是否存在）
4. **列名冲突**：动态列管理会自动处理列名冲突（规范化列名）
5. **列数限制**：如果超过1600列限制，只添加前N个列

## 测试建议

1. **小规模测试**：先使用少量数据测试动态列管理功能
2. **核心字段测试**：测试核心字段去重机制（表头变化不影响去重）
3. **唯一约束测试**：测试唯一约束优化（不同platform_code和shop_id的数据可以共存）
4. **Metabase验证**：验证Metabase可以看到所有动态列

