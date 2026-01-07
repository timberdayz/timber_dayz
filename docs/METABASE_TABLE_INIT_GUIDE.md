# Metabase表/视图初始化指南

⚠️ **已过时**：本文档已过时。Metabase 会自动发现数据库中的所有表，不需要任何脚本。

**请参考**：`docs/METABASE_SIMPLE_SETUP_GUIDE.md` - 简单的配置指南

---

## 概述（已过时）

~~本文档说明如何使用自动化脚本初始化Metabase数据库连接和表/视图同步。~~

**新的方案**：在 Metabase UI 中手动配置连接，Metabase 会自动发现所有表。

## 前置条件

1. **Metabase已启动**
   ```bash
   docker-compose -f docker-compose.metabase.yml up -d
   ```

2. **首次运行需要手动完成设置向导**
   - 访问 http://localhost:3000
   - 完成初始设置（创建管理员账号）
   - 默认账号：admin@xihong.com / admin

3. **PostgreSQL数据库已运行**
   - 确保PostgreSQL容器正常运行
   - 确保数据库连接参数正确（见`.env`文件）

## 使用方法（已更新）

⚠️ **自动化脚本已归档**：`scripts/init_metabase_tables.py` 已归档，不再需要。

### 推荐方法：在 Metabase UI 中手动配置

**参见**：`docs/METABASE_SIMPLE_SETUP_GUIDE.md` - 简单的配置指南

**核心步骤**：
1. Admin → Databases → Add database → PostgreSQL
2. 填写连接信息
3. **重要**：Schema filters 设置为 `public,b_class,a_class,c_class,core,finance` 或选择 "全部"
4. 保存并等待自动同步

Metabase 会自动发现所有表，不需要任何脚本！

---

## 旧方法（已过时）

~~### 方法1：使用自动化脚本（推荐）~~

~~```bash
# 1. 设置环境变量（可选，使用.env文件中的默认值）
export METABASE_URL=http://localhost:3000
export METABASE_EMAIL=admin@xihong.com
export METABASE_PASSWORD=admin

# 2. 运行初始化脚本
python scripts/init_metabase_tables.py
```~~

~~### 方法2：手动配置（如果脚本失败）~~

1. **登录Metabase**
   - 访问 http://localhost:3000
   - 使用管理员账号登录

2. **添加数据库连接**
   - 点击左侧菜单 "Admin" → "Databases"
   - 点击 "Add database"
   - 选择 "PostgreSQL"
   - 填写连接信息：
     - **Display name**: 西虹ERP数据库
     - **Host**: postgres（Docker网络）或 localhost（本地）
     - **Port**: 5432
     - **Database name**: xihong_erp
     - **Username**: erp_user
     - **Password**: erp_pass_2025（或.env中的值）
   - 点击 "Save"

3. **同步表/视图**
   - 在数据库详情页面，点击 "Sync database schema now"
   - 等待同步完成（可能需要几分钟）

## 需要同步的表/视图列表

脚本会自动同步以下10个表/视图：

1. ✅ `view_orders_atomic` - 订单原子视图
2. ✅ `view_shop_performance_wide` - 店铺综合绩效宽表（核心！）
3. ✅ `view_product_performance_wide` - 产品全景视图
4. ✅ `mv_daily_sales_summary` - 每日销售汇总
5. ✅ `mv_monthly_shop_performance` - 月度店铺绩效
6. ✅ `mv_product_sales_ranking` - 产品销售排行榜
7. ✅ `mv_pnl_shop_month` - 店铺P&L报表（注意：可能需要重命名）
8. ✅ `mv_traffic_summary` - 流量分析（注意：可能需要重命名）
9. ✅ `mv_inventory_summary` - 库存分析（注意：可能需要重命名）
10. ✅ `view_targets_atomic` - 销售目标（A类数据）

## 验证同步结果

运行脚本后，检查输出日志：

```
表/视图同步状态：
======================================================================
  [OK] view_orders_atomic
  [OK] view_shop_performance_wide
  [OK] view_product_performance_wide
  ...
```

如果某个表显示 `[WARNING]`，说明该表未找到，可能需要：
1. 检查表名是否正确
2. 检查表是否在PostgreSQL中存在
3. 手动在Metabase UI中同步

## 常见问题

### Q1: 脚本提示"登录失败"

**原因**：
- Metabase未启动
- 账号密码错误
- 首次运行未完成设置向导

**解决方案**：
1. 检查Metabase容器状态：`docker ps | grep metabase`
2. 访问 http://localhost:3000 完成设置向导
3. 确认账号密码正确

### Q2: 表/视图未同步

**原因**：
- Schema同步未完成
- 表名不匹配
- 权限不足

**解决方案**：
1. 等待30秒后重新运行脚本
2. 在Metabase UI中手动同步：Admin → Databases → 选择数据库 → "Sync database schema now"
3. 检查PostgreSQL中表是否存在：`\dt` 或 `SELECT tablename FROM pg_tables WHERE schemaname = 'public'`

### Q3: 数据库连接失败

**原因**：
- PostgreSQL未运行
- 网络配置错误（Docker网络）
- 连接参数错误

**解决方案**：
1. 检查PostgreSQL容器状态：`docker ps | grep postgres`
2. 确认使用Docker网络时，Host填写 `postgres`（服务名）
3. 确认连接参数与`.env`文件一致

## 下一步

初始化完成后，下一步操作：

1. **创建自定义字段（Custom Fields）**
   - 参见 `docs/METABASE_CUSTOM_FIELDS_GUIDE.md`

2. **创建Dashboard和Question**
   - 参见 `docs/METABASE_DASHBOARD_MANUAL_SETUP.md`

3. **配置前端集成**
   - 参见 Phase 3 任务清单

## 脚本特性

- ✅ **幂等性**：可重复运行，不会重复创建
- ✅ **自动检测**：自动检测已存在的数据库连接
- ✅ **错误处理**：完善的错误提示和日志
- ✅ **异步同步**：Schema同步为异步执行，自动等待

## 技术支持

如遇到问题，请：
1. 查看脚本日志输出
2. 检查Metabase容器日志：`docker logs xihong_erp_metabase`
3. 查看PostgreSQL日志：`docker logs xihong_erp_postgres`

