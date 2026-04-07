# Metabase同步问题诊断

## 🔍 问题分析

从截图看，Metabase中**已经显示了很多新表**，包括：

### ✅ 已同步的表（从截图中可见）

**B类数据表**：
- Fact Raw Data Inventory Snapshot
- Fact Raw Data Orders Daily
- Fact Raw Data Orders Monthly
- Fact Raw Data Orders Weekly
- Fact Raw Data Products Daily
- Fact Raw Data Products Monthly
- Fact Raw Data Products Weekly
- Fact Raw Data Services Daily
- Fact Raw Data Services Monthly
- Fact Raw Data Services Weekly
- Fact Raw Data Traffic Daily
- Fact Raw Data Traffic Monthly
- Fact Raw Data Traffic Weekly

**其他表**：
- Entity Aliases
- Employee Commissions
- Employee Performance
- Employee Targets
- Employees
- Attendance Records

### ❓ 可能缺失的表

**A类数据表**（可能未显示或名称不同）：
- sales_targets_a
- sales_campaigns_a
- operating_costs
- performance_config_a

**C类数据表**（可能未显示）：
- shop_commissions
- performance_scores_c

**其他表**：
- staging_raw_data

## 🔧 可能的原因

### 1. 表名大小写问题

PostgreSQL表名是小写（`sales_targets_a`），但Metabase可能显示为不同的大小写格式。

### 2. 表过滤设置

Metabase可能配置了表过滤规则，某些表被排除在外。

### 3. Schema同步不完整

虽然点击了"Sync database schema now"，但可能只同步了部分表。

### 4. 缓存问题

Metabase可能缓存了旧的表列表，需要刷新。

## 🔍 诊断步骤

### 步骤1：检查PostgreSQL中的表

```bash
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND (
    table_name LIKE 'fact_raw_data%' 
    OR table_name IN (
        'sales_targets_a', 'sales_campaigns_a', 'operating_costs', 
        'employees', 'employee_targets', 'attendance_records', 
        'performance_config_a', 'employee_performance', 
        'employee_commissions', 'shop_commissions', 
        'performance_scores_c', 'entity_aliases', 'staging_raw_data'
    )
)
ORDER BY table_name;
"
```

### 步骤2：检查Metabase数据库连接配置

1. 登录Metabase：http://localhost:3000
2. Admin → Databases → XIHONG_ERP
3. 点击 "Edit" 按钮
4. 检查以下设置：
   - **Schema**: 应该包含 `public`
   - **Table inclusion patterns**: 确保没有过滤掉新表
   - **Table exclusion patterns**: 确保没有排除新表

### 步骤3：强制重新同步

1. 在数据库详情页，点击 "Sync database schema now"
2. 等待同步完成
3. 如果还是不行，尝试：
   - 点击 "Remove" 移除数据库连接
   - 重新添加数据库连接
   - 重新同步Schema

### 步骤4：检查表名显示

在Metabase中搜索以下表名（尝试不同的大小写）：
- `sales_targets_a` 或 `Sales Targets A`
- `sales_campaigns_a` 或 `Sales Campaigns A`
- `operating_costs` 或 `Operating Costs`
- `performance_config_a` 或 `Performance Config A`
- `shop_commissions` 或 `Shop Commissions`
- `performance_scores_c` 或 `Performance Scores C`
- `staging_raw_data` 或 `Staging Raw Data`

## 💡 解决方案

### 方案1：检查表过滤设置

1. Admin → Databases → XIHONG_ERP → Edit
2. 检查 "Table inclusion patterns" 和 "Table exclusion patterns"
3. 如果有限制，移除或修改规则

### 方案2：使用Metabase API强制同步

如果知道Metabase管理员密码，可以使用API强制同步：

```bash
# 需要Metabase管理员密码
python scripts/sync_dss_tables_to_metabase.py
```

### 方案3：重新添加数据库连接

如果以上方法都不行，可以：
1. 删除现有数据库连接
2. 重新添加PostgreSQL连接
3. 重新同步Schema

## 📊 验证清单

- [ ] PostgreSQL中所有26张表都存在
- [ ] Metabase数据库连接配置正确
- [ ] 表过滤规则没有排除新表
- [ ] Schema同步已执行
- [ ] 在Metabase中搜索表名（尝试不同大小写）

## ⚠️ 注意事项

1. **表名大小写**：PostgreSQL表名是小写，但Metabase可能显示为不同格式
2. **表过滤**：检查Metabase的表过滤设置
3. **缓存**：尝试刷新浏览器或清除Metabase缓存
4. **权限**：确保数据库用户有SELECT权限

---

**最后更新**: 2025-11-26 17:05

