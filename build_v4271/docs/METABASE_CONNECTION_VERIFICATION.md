# Metabase数据库连接验证报告

**验证日期**: 2025-12-02  
**验证结果**: ✅ 数据已入库，但Metabase需要手动配置数据库连接

---

## ✅ 验证结果总结

### 1. 数据入库状态

**数据确实已入库**：
- ✅ `public.fact_raw_data_inventory_snapshot`: **1218 行**
- ✅ 所有13个 `fact_raw_data_*` 表都在 `public` schema
- ✅ 表结构完整（11列）
- ✅ 数据无重复（data_hash唯一）

### 2. 数据库连接配置

**后端实际使用的数据库**：
```
数据库类型: PostgreSQL
主机: localhost
端口: 5432
数据库名: xihong_erp
用户名: erp_user
密码: erp_pass_2025
```

**连接字符串**：
```
postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp
```

### 3. 表位置确认

**所有表都在 `public` schema**：
- `public.fact_raw_data_inventory_snapshot` (1218行)
- `public.fact_raw_data_orders_daily`
- `public.fact_raw_data_orders_weekly`
- `public.fact_raw_data_orders_monthly`
- `public.fact_raw_data_products_daily`
- `public.fact_raw_data_products_weekly`
- `public.fact_raw_data_products_monthly`
- `public.fact_raw_data_traffic_daily`
- `public.fact_raw_data_traffic_weekly`
- `public.fact_raw_data_traffic_monthly`
- `public.fact_raw_data_services_daily`
- `public.fact_raw_data_services_weekly`
- `public.fact_raw_data_services_monthly`

**注意**：`b_class` schema 不存在，所有表都在 `public` schema。

---

## 🔧 Metabase配置步骤

### 步骤1：添加PostgreSQL数据库连接

1. **登录Metabase**：
   - 打开：`http://localhost:8080`
   - 使用管理员账号登录

2. **添加数据库**：
   - 点击：`Admin → Databases`
   - 点击：`Add database` 按钮
   - 选择：`PostgreSQL`

3. **填写连接信息**：
   ```
   Name: xihong_erp (或任意名称)
   Host: localhost (如果Metabase在Docker中，使用 postgres)
   Port: 5432
   Database name: xihong_erp
   Username: erp_user
   Password: erp_pass_2025
   ```

4. **配置高级选项**：
   - 点击：`Show advanced options`
   - **Schema filters**: 设置为 `public` 或 `public,b_class`
   - 其他选项：使用默认值

5. **保存连接**：
   - 点击：`Save` 按钮
   - 等待连接测试完成（应该显示绿色成功状态）

### 步骤2：同步数据库Schema

1. **同步Schema**：
   - 在 `Admin → Databases` 中找到 `xihong_erp` 数据库
   - 点击数据库右侧的 **"Sync database schema now"** 按钮
   - 等待同步完成（可能需要几秒钟）

2. **验证表可见**：
   - 同步完成后，点击数据库名称进入数据库详情
   - 应该能看到 `public` schema
   - 展开 `public` schema，应该能看到所有 `fact_raw_data_*` 表

### 步骤3：验证数据查询

1. **创建测试查询**：
   - 点击：`New → Question`
   - 选择：`Simple question`
   - 选择数据库：`xihong_erp`
   - 选择表：`public.fact_raw_data_inventory_snapshot`
   - 应该能看到1218行数据

---

## ⚠️ 常见问题排查

### 问题1：Metabase中看不到表

**可能原因**：
- Schema过滤器未包含 `public`
- 未同步数据库Schema
- 数据库连接失败

**解决方案**：
1. 检查数据库连接状态（应该是绿色）
2. 编辑数据库连接，确保Schema过滤器包含 `public`
3. 点击 "Sync database schema now"

### 问题2：连接失败

**可能原因**：
- 主机地址错误（Docker内部应使用 `postgres`，本地应使用 `localhost`）
- 端口错误
- 用户名或密码错误
- PostgreSQL服务未启动

**解决方案**：
1. 检查PostgreSQL服务是否运行：
   ```bash
   docker ps | grep postgres
   ```
2. 检查数据库连接配置是否正确
3. 测试连接：
   ```bash
   psql -h localhost -p 5432 -U erp_user -d xihong_erp
   ```

### 问题3：表在public schema但Metabase看不到

**可能原因**：
- Schema过滤器未设置或设置错误
- 未同步Schema

**解决方案**：
1. 编辑数据库连接
2. 显示高级选项
3. Schema过滤器设置为：`public`
4. 保存并重新同步Schema

---

## 📊 验证命令

### 验证数据库连接

```bash
python temp/development/diagnose_metabase_connection.py
```

### 验证数据入库

```bash
python temp/development/check_database_data.py
```

### 验证表位置

```sql
-- 在PostgreSQL中执行
SELECT table_schema, table_name, 
       (SELECT COUNT(*) FROM information_schema.columns 
        WHERE table_schema = t.table_schema 
        AND table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_name LIKE 'fact_raw_data_%'
ORDER BY table_schema, table_name;
```

---

## 🎯 下一步操作

1. ✅ **数据已入库**：1218行数据在 `public.fact_raw_data_inventory_snapshot`
2. ⏭️ **配置Metabase**：按照上述步骤添加数据库连接
3. ⏭️ **同步Schema**：点击 "Sync database schema now"
4. ⏭️ **验证查询**：创建测试查询验证数据可见性

---

## 📚 相关文档

- `docs/METABASE_DASHBOARD_SETUP.md` - Metabase配置指南
- `docs/DATA_SYNC_SCHEMA_ISSUE.md` - Schema问题诊断
- `docs/DATA_SYNC_TABLE_MAPPING.md` - 数据同步表映射关系

