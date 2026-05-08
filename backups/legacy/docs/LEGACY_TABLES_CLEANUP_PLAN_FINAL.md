# 历史遗留表清理计划（最终确认）

**日期**: 2026-01-11  
**状态**: ✅ 清理计划已确认

---

## 一、清理计划总结

### 1.1 表分类

| 分类 | 数量 | 说明 |
|------|------|------|
| **需要清理的表** | 8 张 | public schema，全部为空，无业务代码引用 |
| **不能删除的表** | 2 张 | `user_roles`（在schema.py中定义），`dim_date`（有数据） |
| **需要确认的表** | 2 张 | `campaign_targets`（有业务代码），`fact_sales_orders`（主要脚本引用） |

---

## 二、清理执行计划

### 2.1 ✅ 可以安全清理的表（8张）

**public schema**:
1. `collection_tasks_backup` - 备份表（0行）
2. `key_value` - 键值对表（0行）
3. `keyvalue` - 键值对表（0行）
4. `raw_ingestions` - 原始数据表（0行）
5. `report_execution_log` - 报告执行日志（0行）
6. `report_recipient` - 报告接收者（0行）
7. `report_schedule` - 报告调度（0行）
8. `report_schedule_user` - 报告调度用户（0行）

**清理SQL**:
```sql
-- public schema（需要确认后执行）
DROP TABLE IF EXISTS collection_tasks_backup CASCADE;
DROP TABLE IF EXISTS key_value CASCADE;
DROP TABLE IF EXISTS keyvalue CASCADE;
DROP TABLE IF EXISTS raw_ingestions CASCADE;
DROP TABLE IF EXISTS report_execution_log CASCADE;
DROP TABLE IF EXISTS report_recipient CASCADE;
DROP TABLE IF EXISTS report_schedule CASCADE;
DROP TABLE IF EXISTS report_schedule_user CASCADE;
```

**清理理由**:
- ✅ 全部为空表（0行数据）
- ✅ 无业务代码引用（引用仅在本检查脚本中）
- ✅ 不在schema.py中定义
- ✅ 不在迁移文件中创建
- ✅ 不影响系统功能

---

### 2.2 ❌ 不能删除的表（2张）

#### 1. `user_roles` (public schema)

**状态**: 2行数据，40处代码引用

**不能删除的原因**:
- ✅ **在schema.py中定义为Table（关联表）** - `modules/core/db/schema.py:2796`
- ✅ 有实际业务代码引用（`backend/routers/auth.py`, `backend/routers/roles.py`, `backend/routers/notifications.py`）
- ✅ 有数据（2行）
- ✅ 是系统正常使用的表

**结论**: **必须保留**

---

#### 2. `dim_date` (core schema)

**状态**: 4,018行数据，27处代码引用

**不能删除的原因**:
- ⚠️ 有数据（4,018行 - 2020-2030年的日期数据）
- ⚠️ 有迁移文件创建（`migrations/versions/20251027_0009_create_dim_date.py`）
- ⚠️ 不在schema.py中定义（但可能在迁移文件中创建）
- ⚠️ 可能被系统使用

**建议**:
- 如果代码中使用，应该在schema.py中定义
- 如果未使用，需要确认后清理（但需要先备份数据）

**结论**: **暂时保留，需要进一步确认**

---

### 2.3 ⚠️ 需要确认的表（2张）

#### 1. `campaign_targets` (a_class schema)

**状态**: 0行数据，11处代码引用

**代码引用位置**:
- `backend/routers/config_management.py:618` - SELECT FROM
- `backend/routers/config_management.py:662` - INSERT INTO
- `backend/routers/config_management.py:684` - SELECT WHERE

**分析**:
- 表为空，但有实际业务代码引用
- 可能是业务功能需要的表，但当前无数据
- 不在schema.py中定义
- 不在迁移文件中创建

**建议**:
- 需要确认是否应该在schema.py中定义
- 如果在使用，应该在schema.py中定义并创建迁移文件
- 如果未使用，可以清理

**结论**: **暂时保留，需要进一步确认**

---

#### 2. `fact_sales_orders` (core schema)

**状态**: 0行数据，165处代码引用（主要在脚本文件）

**代码引用位置**:
- `backend/alter_fact_sales_orders.py` - 修改表脚本
- `backend/analysis_current_schema.py` - 分析脚本
- `backend/apply_migrations.py` - 迁移脚本
- 大部分引用在脚本文件中，不是业务代码

**分析**:
- 表为空
- 大部分引用在脚本文件中（不是实际业务代码）
- 不在schema.py中定义
- 可能有旧的迁移文件创建过

**建议**:
- 确认是否有业务代码使用
- 如果没有业务代码使用，可以清理
- 如果有业务代码使用，应该在schema.py中定义并创建迁移文件

**结论**: **暂时保留，需要进一步确认**

---

## 三、清理执行步骤

### 3.1 清理前准备

1. ✅ **备份数据库**（重要！）
   ```bash
   # 备份数据库
   docker exec xihong_erp_postgres pg_dump -U erp_user -d xihong_erp > backup_before_cleanup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. ✅ **确认可以清理的表列表**（8张public schema表）

3. ✅ **验证表是否为空**（再次确认）

4. ✅ **验证无业务代码引用**（再次确认）

### 3.2 执行清理

**清理SQL脚本**: `sql/cleanup_legacy_tables.sql`

**执行方式**:
```bash
# 方式1: 使用psql执行
docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp < sql/cleanup_legacy_tables.sql

# 方式2: 使用Python脚本执行
python scripts/cleanup_legacy_tables.py
```

### 3.3 清理后验证

1. ✅ 验证表已删除
2. ✅ 验证系统功能正常
3. ✅ 验证无错误日志

---

## 四、清理时间表

### 阶段1: 准备阶段（已完成）

- [x] 创建检查脚本
- [x] 运行检查脚本
- [x] 分析检查结果
- [x] 制定清理计划
- [x] 确认清理计划

### 阶段2: 执行阶段（待执行）

- [ ] 备份数据库
- [ ] 创建清理SQL脚本
- [ ] 执行清理（测试环境）
- [ ] 验证清理结果
- [ ] 执行清理（生产环境）
- [ ] 验证系统功能

### 阶段3: 后续工作（待执行）

- [ ] 确认 `campaign_targets` 和 `fact_sales_orders` 的处理方式
- [ ] 如果需要，在schema.py中定义 `campaign_targets`
- [ ] 如果需要，创建 `campaign_targets` 的迁移文件
- [ ] 确认 `dim_date` 的处理方式
- [ ] 如果需要，在schema.py中定义 `dim_date`

---

## 五、风险评估

### 5.1 清理风险

**风险等级**: ⭐ 低风险

**风险点**:
- 清理表可能导致相关视图或函数失效（使用CASCADE可避免）
- 清理表可能导致数据丢失（但所有表都是空的，无数据）

**缓解措施**:
- ✅ 所有清理的表都是空表（0行数据）
- ✅ 所有清理的表都无业务代码引用
- ✅ 使用 `IF EXISTS` 和 `CASCADE` 确保安全
- ✅ 清理前备份数据库
- ✅ 先在测试环境执行清理

### 5.2 不清理的风险

**风险等级**: ⭐⭐ 中风险

**风险点**:
- 遗留表占用存储空间
- 遗留表增加系统复杂性
- 遗留表可能导致混淆

**缓解措施**:
- 定期清理遗留表
- 建立表管理规范

---

## 六、总结

### 6.1 清理计划确认

**可以安全清理的表**: 8张（全部为空，无业务代码引用）

**不能删除的表**: 2张（`user_roles`，`dim_date`）

**需要确认的表**: 2张（`campaign_targets`，`fact_sales_orders`）

### 6.2 清理执行

**清理时间**: 待定（需要用户确认）

**清理方式**: 使用SQL脚本或Python脚本执行

**清理范围**: 8张public schema的表

---

## 七、相关文档

- [遗留表使用情况检查总结](LEGACY_TABLES_USAGE_CHECK_SUMMARY.md) - 详细检查结果
- [表审计总结报告](TABLE_AUDIT_SUMMARY.md) - 完整审计报告
- [遗留表检查脚本](scripts/check_legacy_tables_usage.py) - 检查脚本
- [详细检查报告](temp/legacy_tables_usage_check.txt) - 详细报告
