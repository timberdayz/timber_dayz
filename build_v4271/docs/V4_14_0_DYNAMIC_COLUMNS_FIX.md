# v4.14.0 动态列插入错误修复报告

## 🐛 问题描述

**错误信息**: `sqlalchemy.exc.CompileError: Unconsumed column names:`

**错误原因**: 
- SQLAlchemy ORM模型不包含动态添加的列
- 在 `insert_record` 中添加动态列字段后，使用 `pg_insert(target_table).values(insert_data)` 时，SQLAlchemy会检查 `insert_data` 中的键是否对应模型的列
- 由于动态列不在ORM模型中，SQLAlchemy报错 "Unconsumed column names"

**错误位置**: `backend/services/raw_data_importer.py` 的 `batch_insert_raw_data` 方法

## ✅ 修复方案

### 修复策略

**两步插入法**:
1. **第一步**: 使用ORM插入系统字段（不包含动态列）
2. **第二步**: 使用原始SQL更新动态列（从原始数据获取值）

### 修复内容

#### 1. 移除动态列填充逻辑（第234-237行）

**修复前**:
```python
# 将源数据表头字段填充到列中（动态列）
column_mapping = {}
for original_col in header_columns:
    normalized_col = dynamic_column_manager.normalize_column_name(original_col)
    column_mapping[original_col] = normalized_col

# 更新insert_data，将源数据字段填充到列中
for i, insert_record in enumerate(insert_data):
    row = rows[i]
    for original_col, normalized_col in column_mapping.items():
        if original_col in row:
            insert_record[normalized_col] = str(row[original_col]) if row[original_col] is not None else None
```

**修复后**:
```python
# ⭐ v4.14.0修复：不要在这里填充动态列
# 原因：SQLAlchemy ORM模型不包含动态列，会导致"Unconsumed column names"错误
# 解决方案：先使用ORM插入系统字段，然后使用原始SQL更新动态列
# 动态列的填充将在后面的UPDATE语句中完成
```

#### 2. 分离系统字段和动态列（第282-308行）

**修复后**:
```python
# 分离系统字段和动态列
system_fields = {
    'platform_code', 'shop_id', 'data_domain', 'granularity',
    'metric_date', 'file_id', 'raw_data', 'header_columns',
    'data_hash', 'ingest_timestamp'
}

# 准备ORM插入数据（只包含系统字段）
insert_data_orm = []
for record in insert_data:
    orm_record = {k: v for k, v in record.items() if k in system_fields}
    insert_data_orm.append(orm_record)

# 使用ORM插入系统字段
stmt = pg_insert(target_table).values(insert_data_orm)
# ... ON CONFLICT处理
self.db.execute(stmt)
```

#### 3. 使用原始SQL更新动态列（第290-359行）

**修复后**:
```python
# ⭐ v4.14.0新增：使用原始SQL更新动态列（如果存在）
# 从原始rows数据中获取动态列的值
if header_columns and rows:
    try:
        dynamic_column_manager = get_dynamic_column_manager(self.db)
        existing_columns = dynamic_column_manager.get_existing_columns(table_name)
        
        # 构建列名映射（原始列名 -> 规范化列名），只映射存在的列
        column_mapping = {}
        for original_col in header_columns:
            normalized_col = dynamic_column_manager.normalize_column_name(original_col)
            # 只映射那些确实存在于表中的列（排除系统字段）
            if normalized_col in existing_columns and normalized_col not in system_fields:
                column_mapping[original_col] = normalized_col
        
        if column_mapping:
            # 构建UPDATE语句更新动态列
            for i, row in enumerate(rows):
                orm_record = insert_data_orm[i]
                
                # 构建WHERE条件（使用唯一键）
                where_conditions = []
                where_params = {}
                
                if index_exists:
                    where_conditions.append('platform_code = :platform_code')
                    where_conditions.append('COALESCE(shop_id, \'\') = COALESCE(:shop_id, \'\')')
                    where_conditions.append('data_domain = :data_domain')
                    where_conditions.append('granularity = :granularity')
                    where_conditions.append('data_hash = :data_hash')
                else:
                    where_conditions.append('data_domain = :data_domain')
                    where_conditions.append('granularity = :granularity')
                    where_conditions.append('data_hash = :data_hash')
                
                where_params = {
                    'platform_code': orm_record['platform_code'],
                    'shop_id': orm_record.get('shop_id'),
                    'data_domain': orm_record['data_domain'],
                    'granularity': orm_record['granularity'],
                    'data_hash': orm_record['data_hash']
                }
                
                # 构建SET子句（从原始row数据获取值）
                set_clauses = []
                for original_col, normalized_col in column_mapping.items():
                    if original_col in row:
                        set_clauses.append(f'"{normalized_col}" = :{normalized_col}')
                        where_params[normalized_col] = str(row[original_col]) if row[original_col] is not None else None
                
                if set_clauses:
                    update_sql = text(f"""
                        UPDATE "{table_name}"
                        SET {', '.join(set_clauses)}
                        WHERE {' AND '.join(where_conditions)}
                    """)
                    self.db.execute(update_sql, where_params)
            
            logger.info(
                f"[RawDataImporter] [v4.14.0] 更新动态列: {len(column_mapping)}个列 "
                f"（表={table_name}）"
            )
    except Exception as e:
        logger.warning(
            f"[RawDataImporter] [v4.14.0] 更新动态列失败: {e}，"
            f"数据已通过raw_data JSONB存储",
            exc_info=True
        )
        # 更新失败不影响数据入库（数据已在raw_data JSONB中）
```

## 🔍 修复原理

### 问题根源

SQLAlchemy的ORM模型在定义时只包含固定的列。当我们动态添加列到数据库表时，ORM模型并不知道这些列的存在。因此，如果我们在 `insert_data` 中包含动态列，SQLAlchemy会报错。

### 解决方案

**两步插入法**:
1. **ORM插入**: 使用SQLAlchemy ORM插入系统字段（ORM模型已知的列）
2. **原始SQL更新**: 使用原始SQL UPDATE语句更新动态列（绕过ORM检查）

### 优势

1. **兼容性**: 完全兼容SQLAlchemy ORM
2. **灵活性**: 支持动态列，不受ORM模型限制
3. **容错性**: 如果动态列更新失败，数据仍在 `raw_data` JSONB中
4. **性能**: ORM插入系统字段（批量），然后UPDATE动态列（逐行，但列数少）

## 📝 注意事项

1. **数据完整性**: 
   - 系统字段通过ORM插入（保证数据完整性）
   - 动态列通过UPDATE更新（如果失败，数据仍在raw_data JSONB中）

2. **性能考虑**:
   - ORM插入是批量操作（高效）
   - UPDATE是逐行操作（如果动态列很多，可能影响性能）
   - 未来可以考虑批量UPDATE优化

3. **错误处理**:
   - 如果动态列更新失败，数据仍在 `raw_data` JSONB中
   - 不会影响数据入库（系统字段已成功插入）

## ✅ 验证步骤

1. **清理数据库**: 使用清理数据库API清理现有数据
2. **同步文件**: 点击单个文件同步按钮
3. **检查日志**: 查看是否有 "更新动态列" 的日志
4. **验证数据**: 在Metabase中查看表结构，确认动态列存在
5. **验证数据值**: 在Metabase中查看数据，确认动态列有值

## 🎯 预期结果

修复后，应该能够：
1. ✅ 成功插入系统字段（无错误）
2. ✅ 成功更新动态列（日志显示更新列数）
3. ✅ 在Metabase中可以看到所有动态列
4. ✅ 动态列有正确的数据值

---

**修复时间**: 2025-12-03  
**修复状态**: ✅ 完成  
**测试状态**: ⚠️ 待用户验证

