# Metabase 重置和重新配置指南

**执行时间**：2025-12-08  
**操作**：已清除 Metabase H2 数据库（方案1）

---

## ✅ 已完成的操作

1. ✅ 停止 Metabase 容器：`docker stop xihong_erp_metabase`
2. ✅ 删除 Metabase 数据卷：`docker volume rm xihong_erp_metabase_data`
3. ✅ 重新启动 Metabase：`docker-compose -f docker-compose.metabase.yml up -d`

---

## 📋 下一步操作（必须完成）

### 步骤1：等待 Metabase 完全启动

Metabase 容器已重新启动，需要等待 30-60 秒让 Metabase 完全初始化。

**检查容器状态**：
```bash
docker ps --filter "name=metabase"
```

**查看日志**（确认启动完成）：
```bash
docker logs xihong_erp_metabase --tail 50
```

当看到类似以下日志时，说明启动完成：
```
Metabase initialization complete
```

---

### 步骤2：完成 Metabase 初始设置

1. **访问 Metabase**：
   - 打开浏览器访问：`http://localhost:8080`
   - 等待 Metabase 初始化完成（首次启动可能需要 1-2 分钟）

2. **创建管理员账号**：
   - 填写管理员邮箱（建议：`admin@xihong.com`）
   - 设置管理员密码（**请记住这个密码，后续需要用到**）
   - 填写姓名（可选）
   - 点击 **"让我们开始吧"** 或 **"Let's get started"**

3. **选择数据源**：
   - 选择 **"稍后添加"** 或 **"I'll add my data later"**
   - 点击 **"完成"** 或 **"Finish"**

---

### 步骤3：添加 PostgreSQL 数据库连接

1. **进入数据库设置**：
   - 点击左侧菜单：**Admin**（管理员）
   - 点击：**Databases**（数据库）
   - 点击：**Add database**（添加数据库）

2. **选择数据库类型**：
   - 选择：**PostgreSQL**

3. **填写连接信息**：
   ```
   Name: 西虹ERP数据库（或任意名称）
   Host: postgres（如果 Metabase 在 Docker 中）或 localhost
   Port: 5432
   Database name: xihong_erp
   Username: erp_user
   Password: erp_pass_2025（或 .env 中的实际值）
   ```

4. **配置高级选项**（重要）：
   - 点击：**Show advanced options**（显示高级选项）
   - **Schema filters**：设置为 `public,b_class,a_class,c_class,core,finance`
     - 或者选择 **"全部"** / **"All schemas"**
   - **使用安全连接 (SSL)**：❌ 关闭（本地 Docker 网络不需要 SSL）
   - **使用SSH-tunnel**：❌ 关闭

5. **测试连接**：
   - 点击：**Test connection**（测试连接）
   - 应该显示绿色成功状态

6. **保存连接**：
   - 点击：**Save**（保存）
   - Metabase 会自动开始同步数据库 Schema

---

### 步骤4：等待 Schema 同步完成

1. **查看同步状态**：
   - 在数据库详情页，可以看到同步进度
   - 同步过程可能需要 1-2 分钟

2. **手动触发同步**（如果需要）：
   - 点击：**"Sync database schema now"** 按钮
   - 等待同步完成

---

### 步骤5：验证表结构

1. **查看表列表**：
   - 在数据库详情页，点击 **"Tables"**（表）标签
   - 应该能看到按 Schema 分组的表

2. **验证 b_class schema**：
   - 展开 **`b_class`** schema
   - 应该能看到 **26 个按平台分表的表**：
     - **Shopee**: `fact_shopee_orders_daily`, `fact_shopee_products_daily` 等（14个表）
     - **TikTok**: `fact_tiktok_orders_daily`, `fact_tiktok_products_daily` 等（10个表）
     - **Miaoshou**: `fact_miaoshou_inventory_snapshot`（1个表）
     - **Test**: `fact_test_platform_orders_daily`（1个表）

3. **确认没有旧表**：
   - **不应该看到** `fact_raw_data_*` 开头的旧表
   - 如果看到旧表，说明同步不完整，需要再次点击 "Sync database schema now"

---

## 🔍 验证脚本

配置完成后，运行以下脚本验证数据库中的实际表结构：

```bash
python scripts/check_b_class_tables.py
```

**预期输出**：
- 应该看到 26 个按平台分表的表
- 不应该看到 `fact_raw_data_*` 开头的旧表

---

## ⚠️ 注意事项

1. **Schema filters 必须正确**：
   - 必须包含 `b_class` schema
   - 或选择 "全部" / "All schemas"

2. **同步是异步的**：
   - Schema 同步需要时间（1-2 分钟）
   - 请耐心等待同步完成

3. **如果还是显示旧表**：
   - 等待 5-10 分钟后再检查
   - 刷新 Metabase 页面
   - 再次点击 "Sync database schema now"

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

## 📚 相关文档

- `docs/METABASE_POSTGRESQL_CONNECTION_GUIDE.md` - Metabase 连接配置指南
- `docs/METABASE_SCHEMA_SYNC_INSTRUCTIONS.md` - Schema 同步说明
- `scripts/check_b_class_tables.py` - 检查 b_class schema 中的表

---

**创建时间**：2025-12-08  
**状态**：✅ Metabase 已重置，等待重新配置

