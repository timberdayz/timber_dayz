# Metabase Schema 同步问题修复指南

**问题描述**：Metabase 中显示的是旧的表结构（`fact_raw_data_*`），但实际数据库中已经更新到按平台分表架构（`fact_shopee_*`, `fact_tiktok_*`, `fact_miaoshou_*`）。

**诊断结果**：
- ✅ 数据库已更新：`b_class` schema 中有 **26 个按平台分表的表**
- ✅ 没有旧表：没有 `fact_raw_data_*` 开头的旧表
- ❌ Metabase 缓存：Metabase 还在显示旧的表结构

---

## 🔍 问题根源

Metabase 的 Schema 同步机制会缓存表结构。当数据库表结构发生变化时（如从 `fact_raw_data_orders_daily` 迁移到 `fact_shopee_orders_daily`），Metabase 需要手动触发重新同步才能看到新表。

---

## ✅ 解决方案

### 方案1：在 Metabase UI 中手动同步（推荐）

#### 步骤1：登录 Metabase

1. 访问：`http://localhost:8080`
2. 使用管理员账号登录

#### 步骤2：进入数据库设置

1. 点击左侧菜单：**Admin**（管理员）
2. 点击：**Databases**（数据库）
3. 找到：**XIHONG_ERP** 或 **xihong_erp** 数据库
4. 点击数据库名称进入详情页

#### 步骤3：检查 Schema 配置

1. 点击右上角的 **Edit**（编辑）按钮
2. 滚动到 **Advanced options**（高级选项）
3. 检查 **Schema filters**（Schema 过滤器）设置：
   - ✅ **应该包含**：`public,b_class,a_class,c_class,core,finance`
   - ✅ **或选择**：**"全部"** / **"All schemas"**
4. 如果设置不正确，修改后点击 **Save**（保存）

#### 步骤4：强制重新同步 Schema

1. 在数据库详情页，找到右上角的 **"Sync database schema now"** 按钮
   - 中文界面可能显示为：**"立即同步数据库架构"** 或 **"同步数据库架构"**
2. 点击该按钮
3. **等待同步完成**（通常需要 30-60 秒）
   - 同步过程中会显示进度提示
   - 同步完成后会显示成功消息

#### 步骤5：验证新表是否出现

1. 在数据库详情页，点击 **"Tables"**（表）标签
2. 展开 **`b_class`** schema
3. 应该能看到以下新表（按平台分组）：
   - **Shopee**: `fact_shopee_orders_daily`, `fact_shopee_products_daily`, `fact_shopee_analytics_daily` 等（14个表）
   - **TikTok**: `fact_tiktok_orders_daily`, `fact_tiktok_products_daily` 等（10个表）
   - **Miaoshou**: `fact_miaoshou_inventory_snapshot`（1个表）
   - **Test**: `fact_test_platform_orders_daily`（1个表）

4. **不应该看到**旧的表名（`fact_raw_data_orders_daily` 等）

---

### 方案2：重启 Metabase 容器（如果方案1无效）

如果手动同步后还是显示旧表，可能需要重启 Metabase 容器清除缓存：

```bash
# 停止 Metabase 容器
docker stop xihong_erp_metabase

# 启动 Metabase 容器
docker start xihong_erp_metabase

# 或使用 docker-compose
docker-compose -f docker-compose.metabase.yml restart metabase
```

重启后：
1. 等待 Metabase 完全启动（约 30 秒）
2. 登录 Metabase
3. 按照方案1的步骤重新同步 Schema

---

### 方案3：删除并重新创建数据库连接（最后手段）

如果以上方案都无效，可以删除并重新创建数据库连接：

#### 步骤1：删除现有连接

1. Admin → Databases → XIHONG_ERP
2. 点击右上角的 **Delete**（删除）按钮
3. 确认删除

#### 步骤2：重新创建连接

1. 点击 **Add database**（添加数据库）
2. 选择 **PostgreSQL**
3. 填写连接信息：
   ```
   Name: 西虹ERP数据库
   Host: postgres（如果 Metabase 在 Docker 中）或 localhost
   Port: 5432
   Database name: xihong_erp
   Username: erp_user
   Password: erp_pass_2025（或 .env 中的实际值）
   ```
4. **重要**：在 **Advanced options** 中：
   - **Schema filters**: 设置为 `public,b_class,a_class,c_class,core,finance`
   - 或选择 **"全部"** / **"All schemas"**
5. 点击 **Save**（保存）
6. 等待自动同步完成（或手动点击 "Sync database schema now"）

---

## 🔧 验证脚本

运行以下脚本检查数据库中的实际表结构：

```bash
python scripts/check_b_class_tables.py
```

**预期输出**：
- 应该看到 26 个按平台分表的表
- 不应该看到 `fact_raw_data_*` 开头的旧表

---

## 📊 当前数据库状态

根据最新检查，`b_class` schema 中有以下表：

### Shopee 平台（14个表）
- `fact_shopee_analytics_daily`
- `fact_shopee_analytics_monthly`
- `fact_shopee_analytics_weekly`
- `fact_shopee_orders_monthly`
- `fact_shopee_orders_weekly`
- `fact_shopee_products_daily`
- `fact_shopee_products_monthly`
- `fact_shopee_products_weekly`
- `fact_shopee_services_agent_daily`
- `fact_shopee_services_agent_monthly`
- `fact_shopee_services_agent_weekly`
- `fact_shopee_services_ai_assistant_daily`
- `fact_shopee_services_ai_assistant_monthly`
- `fact_shopee_services_ai_assistant_weekly`

### TikTok 平台（10个表）
- `fact_tiktok_analytics_daily`
- `fact_tiktok_analytics_monthly`
- `fact_tiktok_analytics_weekly`
- `fact_tiktok_orders_monthly`
- `fact_tiktok_orders_weekly`
- `fact_tiktok_products_daily`
- `fact_tiktok_products_monthly`
- `fact_tiktok_products_weekly`
- `fact_tiktok_services_daily`
- `fact_tiktok_services_monthly`

### Miaoshou 平台（1个表）
- `fact_miaoshou_inventory_snapshot`

### Test 平台（1个表）
- `fact_test_platform_orders_daily`

**总计**：26 个表

---

## ⚠️ 注意事项

1. **Schema 同步是异步的**：点击 "Sync database schema now" 后，需要等待 30-60 秒才能看到结果
2. **Schema filters 必须正确**：如果 Schema filters 只包含 `public`，Metabase 不会同步 `b_class` schema 中的表
3. **缓存问题**：如果同步后还是显示旧表，可能需要重启 Metabase 容器清除缓存
4. **表名变化**：从 `fact_raw_data_*` 迁移到 `fact_{platform}_*` 是架构升级（v4.17.0），旧的表名已经不存在

---

## 🎯 成功标志

修复成功后，在 Metabase 中应该看到：

1. ✅ `b_class` schema 下有 26 个按平台分表的表
2. ✅ 表名格式为 `fact_{platform}_{domain}_{granularity}`
3. ✅ **不应该看到** `fact_raw_data_*` 开头的旧表
4. ✅ 可以正常查询这些表的数据

---

## 📚 相关文档

- `docs/METABASE_POSTGRESQL_CONNECTION_GUIDE.md` - Metabase 连接配置指南
- `docs/METABASE_SCHEMA_SYNC_INSTRUCTIONS.md` - Schema 同步说明
- `scripts/check_b_class_tables.py` - 检查 b_class schema 中的表

---

**创建时间**：2025-12-08  
**最后更新**：2025-12-08  
**状态**：✅ 问题已诊断，修复方案已提供

