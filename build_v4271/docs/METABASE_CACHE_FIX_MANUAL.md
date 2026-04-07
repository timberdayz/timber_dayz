# Metabase 缓存修复 - 手动操作指南

## 问题描述

Metabase 显示旧的表名（`fact_raw_data_*`），但数据库中已经是新表名（`fact_shopee_*`, `fact_tiktok_*` 等）。

## 手动修复步骤（方案2：API 强制更新）

### 步骤1：登录 Metabase

1. 访问：`http://localhost:8080`
2. 使用管理员账号登录

### 步骤2：进入数据库设置

1. 点击左侧菜单：**Admin**（管理员）
2. 点击：**Databases**（数据库）
3. 找到：**XIHONG_ERP** 或 **xihong_erp** 数据库
4. 点击数据库名称进入详情页

### 步骤3：清除字段值缓存（如果存在）

1. 在数据库详情页，查找 **"Discard field values"** 或 **"丢弃字段值"** 按钮
2. 如果存在，点击该按钮
3. 确认操作

**注意**：这个按钮可能不存在（取决于 Metabase 版本），如果不存在，跳过此步骤。

### 步骤4：强制重新同步 Schema

1. 在数据库详情页，找到右上角的 **"Sync database schema now"** 按钮
   - 中文界面可能显示为：**"立即同步数据库架构"** 或 **"同步数据库架构"**
2. 点击该按钮
3. **等待同步完成**（通常需要 30-60 秒）
   - 同步过程中会显示进度提示
   - 同步完成后会显示成功消息

### 步骤5：重新扫描字段值（如果存在）

1. 在数据库详情页，查找 **"Rescan field values now"** 或 **"重新扫描字段值"** 按钮
2. 如果存在，点击该按钮
3. 等待扫描完成

**注意**：这个按钮可能不存在（取决于 Metabase 版本），如果不存在，跳过此步骤。

### 步骤6：验证结果

1. 等待 1-2 分钟让 Metabase 完成内部处理
2. 刷新 Metabase 页面（F5 或 Ctrl+R）
3. 在数据库详情页，点击 **"Tables"**（表）标签
4. 展开 **`b_class`** schema
5. 应该能看到以下新表（按平台分组）：
   - **Shopee**: `fact_shopee_orders_daily`, `fact_shopee_products_daily` 等（14个表）
   - **TikTok**: `fact_tiktok_orders_daily`, `fact_tiktok_products_daily` 等（10个表）
   - **Miaoshou**: `fact_miaoshou_inventory_snapshot`（1个表）
   - **Test**: `fact_test_platform_orders_daily`（1个表）
6. **不应该看到**旧的表名（`fact_raw_data_orders_daily` 等）

---

## 如果手动操作后还是显示旧表

### 方案A：等待更长时间

Metabase 的 Schema 同步是异步的，可能需要更长时间：

1. 等待 5-10 分钟
2. 刷新页面
3. 再次检查

### 方案B：重启 Metabase 容器

```bash
# 重启 Metabase 容器
docker restart xihong_erp_metabase

# 等待容器完全启动（约 30-60 秒）
# 然后重新登录 Metabase，再次同步 Schema
```

### 方案C：清除 Metabase H2 数据库（最后手段）

**警告**：这会清除所有 Metabase 配置，需要重新设置！

```bash
# 1. 停止 Metabase 容器
docker stop xihong_erp_metabase

# 2. 删除 Metabase 数据卷
docker volume rm xihong_erp_metabase_data

# 3. 重新启动 Metabase
docker-compose -f docker-compose.metabase.yml up -d

# 4. 等待 Metabase 完全启动（约 30-60 秒）
# 5. 访问 http://localhost:8080 重新完成初始设置
# 6. 重新添加数据库连接
# 7. 同步 Schema
```

---

## 验证脚本

修复后，运行以下脚本验证数据库中的实际表结构：

```bash
python scripts/check_b_class_tables.py
```

**预期输出**：
- 应该看到 26 个按平台分表的表
- 不应该看到 `fact_raw_data_*` 开头的旧表

---

## 当前数据库状态

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

**创建时间**：2025-12-08  
**状态**：✅ 手动操作指南已提供

