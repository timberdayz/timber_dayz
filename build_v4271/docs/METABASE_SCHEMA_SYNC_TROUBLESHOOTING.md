# Metabase Schema同步问题排查指南

## 问题诊断结果

✅ **PostgreSQL检查结果**：
- 所有26张DSS架构新表都已存在于PostgreSQL中（100%完成率）
- Alembic迁移版本正确（20251126_132151）
- 表结构完整，索引已创建

❌ **Metabase检查结果**：
- Metabase中看不到新的DSS架构表
- 只显示旧表（如`Fact Sales Orders`、`Dim Shop`等）

## 问题原因

**Metabase没有同步数据库Schema**。PostgreSQL中的新表已经存在，但Metabase需要手动触发Schema同步才能发现这些新表。

## 解决方案

### 方法1：在Metabase UI中手动同步（推荐）

#### 步骤1：登录Metabase

1. 访问 http://localhost:3000
2. 使用管理员账号登录
   - 如果不知道密码，可以重置或使用默认密码

#### 步骤2：进入数据库管理页面

1. 点击左侧菜单 **"Admin"**（管理员）或 **"数据"** → **"数据库"**
2. 找到 **"XIHONG_ERP"** 数据库（或显示为 **"xihong_erp"**）
3. 点击数据库名称进入详情页

#### 步骤3：同步Schema

1. 在数据库详情页，找到右上角的 **"Sync database schema now"** 按钮
   - 中文界面可能显示为：**"立即同步数据库架构"** 或 **"同步数据库架构"**
2. 点击该按钮
3. 等待同步完成（通常需要10-30秒）
   - 同步过程中会显示进度提示
   - 同步完成后会显示成功消息

#### 步骤4：验证新表是否出现

1. 在数据库详情页，点击 **"Tables"** 标签（表）
2. 在表列表中查找以下新表：

**B类数据表（13张）**：
- `fact_raw_data_orders_daily`
- `fact_raw_data_orders_weekly`
- `fact_raw_data_orders_monthly`
- `fact_raw_data_products_daily`
- `fact_raw_data_products_weekly`
- `fact_raw_data_products_monthly`
- `fact_raw_data_traffic_daily`
- `fact_raw_data_traffic_weekly`
- `fact_raw_data_traffic_monthly`
- `fact_raw_data_services_daily`
- `fact_raw_data_services_weekly`
- `fact_raw_data_services_monthly`
- `fact_raw_data_inventory_snapshot`

**A类数据表（7张）**：
- `sales_targets_a`
- `sales_campaigns_a`
- `operating_costs`
- `employees`
- `employee_targets`
- `attendance_records`
- `performance_config_a`

**C类数据表（4张）**：
- `employee_performance`
- `employee_commissions`
- `shop_commissions`
- `performance_scores_c`

**其他表（2张）**：
- `entity_aliases`
- `staging_raw_data`

### 方法2：使用Metabase API同步（如果UI方法失败）

如果UI方法无法使用，可以通过API同步：

```bash
# 1. 获取Session Token（需要先登录Metabase获取）
# 2. 调用同步API
curl -X POST "http://localhost:3000/api/database/{database_id}/sync_schema" \
  -H "X-Metabase-Session: {session_token}"
```

**注意**：需要先登录Metabase获取Session Token。

### 方法3：检查Metabase数据库连接配置

如果同步后仍然看不到新表，检查数据库连接配置：

1. 进入数据库详情页
2. 点击 **"Edit"**（编辑）按钮
3. 检查以下配置：
   - **Schema**：应该包含 `public` schema
   - **Table inclusion patterns**：确保没有过滤掉新表
   - **Table exclusion patterns**：确保没有排除新表
4. 保存配置后，再次同步Schema

## 常见问题

### Q1: 点击"Sync database schema now"后没有反应

**可能原因**：
- Metabase正在处理其他任务
- 数据库连接有问题

**解决方案**：
1. 等待1-2分钟，查看是否有错误提示
2. 检查数据库连接状态（点击"Test connection"）
3. 刷新页面后重试

### Q2: 同步后只看到部分新表

**可能原因**：
- Schema过滤设置
- 表权限问题

**解决方案**：
1. 检查数据库连接配置中的Schema过滤
2. 确认数据库用户有SELECT权限
3. 尝试手动查询表：`SELECT * FROM fact_raw_data_orders_daily LIMIT 1;`

### Q3: 表名显示为小写或下划线格式

**这是正常的**。PostgreSQL表名在Metabase中会显示为小写，这是Metabase的默认行为。

### Q4: 中文字段名显示异常

**解决方案**：
1. 确认PostgreSQL数据库编码为UTF-8
2. 确认Metabase连接使用UTF-8编码
3. 重新同步Schema

## 验证清单

同步完成后，请验证：

- [ ] B类数据表（13张）全部出现在Metabase中
- [ ] A类数据表（7张）全部出现在Metabase中
- [ ] C类数据表（4张）全部出现在Metabase中
- [ ] `entity_aliases` 表出现在Metabase中
- [ ] `staging_raw_data` 表出现在Metabase中
- [ ] 可以点击表名查看表结构
- [ ] 中文字段名正常显示（对于A类和C类表）

## 下一步

同步完成后，可以：
1. 配置表关联（entity_aliases）
2. 创建自定义字段
3. 创建Dashboard

详见：
- `docs/METABASE_ENTITY_ALIASES_RELATIONSHIP_GUIDE.md` - 表关联配置
- `docs/METABASE_DSS_DASHBOARD_GUIDE.md` - Dashboard创建指南

