# Metabase 显示旧表名 - 最终修复指南

**问题确认**：数据库检查通过，没有旧表。问题出在 Metabase 的配置。

---

## ✅ 数据库状态（已验证）

- ✅ **b_class schema** 中有 **26 个按平台分表的表**（正确）
  - `fact_shopee_*` (14个表)
  - `fact_tiktok_*` (10个表)
  - `fact_miaoshou_*` (1个表)
  - `fact_test_*` (1个表)
- ✅ **没有旧表**（`fact_raw_data_*` 不存在）
- ✅ **没有视图引用旧表**
- ✅ **没有跨 schema 的重复表名**

---

## 🔍 问题根源

Metabase 显示旧表名的原因可能是：

1. **Schema filters 配置错误**：Metabase 可能只同步了 `public` schema，没有同步 `b_class` schema
2. **Metabase 连接到了错误的 schema**：虽然重置了 H2 数据库，但重新连接时可能配置错误
3. **Metabase 的 H2 数据库仍有缓存**：虽然删除了数据卷，但可能还有其他缓存

---

## ✅ 解决方案

### 步骤1：检查 Metabase 数据库连接配置

1. **登录 Metabase**：`http://localhost:8080`
2. **进入数据库设置**：
   - Admin → Databases → XIHONG_ERP → **Edit**
3. **检查 Schema filters**：
   - 滚动到 **Advanced options**
   - 找到 **Schema filters** 字段
   - **必须包含**：`public,b_class,a_class,c_class,core,finance`
   - **或选择**：**"全部"** / **"All schemas"**
4. **如果配置不正确**：
   - 修改为：`public,b_class,a_class,c_class,core,finance`
   - 或选择 **"全部"** / **"All schemas"**
   - 点击 **Save**

### 步骤2：强制重新同步 Schema

1. **在数据库详情页**，点击 **"Sync database schema now"** 按钮
2. **等待同步完成**（60-90秒）
3. **刷新页面**（F5）

### 步骤3：验证结果

1. **查看表列表**：
   - 在数据库详情页，点击 **"Tables"** 标签
   - 展开 **`b_class`** schema
   - **应该看到**：26 个按平台分表的表
   - **不应该看到**：`fact_raw_data_*` 开头的旧表

2. **如果还是显示旧表**：
   - 检查是否在 **`public`** schema 中看到了旧表
   - 如果是，说明 Metabase 只同步了 `public` schema
   - 需要确保 Schema filters 包含 `b_class`

### 步骤4：如果 Schema filters 无法修改

如果 Metabase UI 中无法修改 Schema filters，可能需要通过 SQL 直接查询 Metabase 的 H2 数据库：

```bash
# 进入 Metabase 容器
docker exec -it xihong_erp_metabase bash

# 查看 H2 数据库文件位置
ls -la /metabase-data/

# 使用 H2 Console 连接（需要安装 Java）
# 或者直接修改 Metabase 的配置文件
```

**或者**，删除并重新创建数据库连接：

1. **删除现有连接**：
   - Admin → Databases → XIHONG_ERP → **Delete**
   - 确认删除

2. **重新创建连接**：
   - 点击 **Add database** → **PostgreSQL**
   - 填写连接信息
   - **重要**：在 **Advanced options** 中：
     - **Schema filters**: `public,b_class,a_class,c_class,core,finance`
     - 或选择 **"全部"** / **"All schemas"**
   - 保存并等待自动同步

---

## 🔧 验证脚本

运行以下脚本验证数据库状态：

```bash
# 检查所有 schema 中的旧表
python scripts/check_all_schemas_for_old_tables.py

# 检查 b_class schema 中的表
python scripts/check_b_class_tables.py

# 深度检查（包括视图、别名等）
python scripts/deep_check_metabase_issue.py
```

**预期输出**：
- ✅ 所有 schema 中都没有旧表
- ✅ b_class schema 中有 26 个按平台分表的表
- ✅ 没有视图引用旧表

---

## 📊 当前数据库状态

### b_class schema 中的表（26个）

**Shopee 平台（14个表）**：
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

**TikTok 平台（10个表）**：
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

**Miaoshou 平台（1个表）**：
- `fact_miaoshou_inventory_snapshot`

**Test 平台（1个表）**：
- `fact_test_platform_orders_daily`

---

## ⚠️ 关键检查点

1. **Schema filters 必须包含 `b_class`**
   - 如果只包含 `public`，Metabase 不会同步 `b_class` schema 中的表
   - 建议选择 **"全部"** / **"All schemas"**

2. **同步后等待足够时间**
   - Schema 同步是异步的，需要 60-90 秒
   - 同步完成后刷新页面

3. **如果还是显示旧表**
   - 检查是否在 `public` schema 中看到了旧表
   - 如果是，说明 Metabase 只同步了 `public` schema
   - 需要修改 Schema filters 配置

---

## 🎯 成功标志

修复成功后，在 Metabase 中应该看到：

1. ✅ `b_class` schema 下有 **26 个按平台分表的表**
2. ✅ 表名格式为 `fact_shopee_*`, `fact_tiktok_*`, `fact_miaoshou_*`
3. ✅ **不应该看到** `fact_raw_data_*` 开头的旧表
4. ✅ 可以正常查询这些表的数据

---

**创建时间**：2025-12-08  
**状态**：✅ 数据库检查通过，问题在 Metabase 配置

