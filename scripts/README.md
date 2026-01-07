# 🧪 测试和工具脚本说明

**目录**: scripts/  
**用途**: 数据库管理、测试验证、诊断工具

---

## 📋 核心脚本（保留）

### 数据库管理

1. **`migrate_legacy_files.py`** - 历史文件迁移到方案B+结构
2. **`rebuild_database_schema.py`** - 数据库Schema重建
3. **`backup_existing_data.py`** - 数据备份工具
4. **`apply_b_plus_migration.py`** - 方案B+ Schema迁移

### 测试验证

5. **`check_db_schema.py`** - 检查数据库表结构
6. **`test_database_write.py`** - 测试数据库写入
7. **`test_complete_ingestion.py`** - 完整入库流程测试
8. **`test_e2e_complete.py`** - 端到端测试
9. **`diagnose_backend.py`** - 后端连接诊断
10. **`test_field_mapping_api.py`** - 字段映射API测试

### 其他工具

11. **`reset_catalog.py`** - 重置catalog_files表
12. **`verify_catalog.py`** - 验证catalog数据

---

## 🗑️ 已清理文件

以下文件已移至`temp/development/`归档：

- test_8002.py（临时端口测试）
- test_minimal_api.py（临时最小化测试）
- simple_api_test.py（临时简单测试）
- test_preview_direct.py（临时预览测试）
- test_single_preview.py（重复）
- quick_test.py（临时）
- test_scan.py（过时）
- test_data_query.py（过时）
- test_database_usage.py（过时）
- test_end_to_end.py（被test_e2e_complete.py替代）
- test_preview_api.py（过时）

---

## 🚀 使用方法

### 验证数据库

```bash
python scripts/check_db_schema.py
python scripts/test_database_write.py
```

### 完整测试

```bash
python scripts/test_complete_ingestion.py
python scripts/test_e2e_complete.py
```

### 诊断问题

```bash
python scripts/diagnose_backend.py
```

---

**所有核心脚本已保留，临时测试文件已清理归档。**

