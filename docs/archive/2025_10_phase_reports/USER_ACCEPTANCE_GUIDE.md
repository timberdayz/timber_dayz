# 用户验收指南 - PostgreSQL优化版

**验收日期**: 2025-10-23  
**版本**: v4.1.0  
**预计验收时间**: 30分钟

---

## 🎯 验收目标

验证以下功能：
- ✅ 数据库架构正确（26个表 + 6个视图）
- ✅ API接口可用（69个路由）
- ✅ 性能达标（查询<1秒，并发60人）
- ✅ 自动化流程正常

---

## 📋 验收步骤

### 步骤1: 验证数据库（5分钟）

**1.1 访问pgAdmin**:
- 打开浏览器: http://localhost:5051
- 登录: `admin@xihong.com` / `admin`

**1.2 连接数据库**:
- 右键 "Servers" → "Register" → "Server"
- Name: `XihongERP`
- Host: `postgres` (Docker内) 或 `localhost` (本地)
- Port: `5432`
- Username: `erp_user`
- Password: `erp_pass_2025`

**1.3 检查表数量**:
- 展开: Servers → XihongERP → Databases → xihong_erp → Schemas → public → Tables
- **验收标准**: 应该看到 **26个表**

**1.4 检查物化视图**:
- 展开: Schemas → public → Materialized Views
- **验收标准**: 应该看到 **6个物化视图** (`mv_daily_sales`, `mv_weekly_sales`, etc.)

**1.5 检查fact_sales_orders新字段**:
- 右键 `fact_sales_orders` → Properties → Columns
- **验收标准**: 应该看到新字段：
  - `platform_commission`
  - `cost_amount_cny`
  - `gross_profit_cny`
  - `is_invoiced`
  - `inventory_deducted`

✅ **步骤1通过标准**: 26个表 + 6个视图 + fact_sales_orders有新字段

---

### 步骤2: 验证API接口（10分钟）

**2.1 访问Swagger文档**:
- 打开浏览器: http://localhost:8000/api/docs

**2.2 检查API分类**:
- **验收标准**: 应该看到以下分类：
  - 数据看板 (7个接口)
  - 数据采集 (8个接口)
  - 数据管理 (10个接口)
  - 账号管理 (7个接口)
  - 字段映射 (17个接口)
  - **库存管理 (4个接口)** ⭐ 新增
  - **财务管理 (7个接口)** ⭐ 新增

**2.3 测试库存管理API**:
- 找到 `GET /api/inventory/list`
- 点击 "Try it out"
- 点击 "Execute"
- **验收标准**: 返回 200 状态码，响应示例：
  ```json
  {
    "success": true,
    "total": 0,
    "items": [],
    "page": 1,
    "total_pages": 0
  }
  ```

**2.4 测试财务管理API**:
- 找到 `GET /api/finance/accounts-receivable`
- 点击 "Try it out" → "Execute"
- **验收标准**: 返回 200 状态码

**2.5 测试利润报表API**:
- 找到 `GET /api/finance/profit-report`
- 设置参数: `granularity=daily`, `start_date=2025-10-01`, `end_date=2025-10-23`
- 点击 "Execute"
- **验收标准**: 返回 200 状态码

✅ **步骤2通过标准**: 所有新API返回200，数据格式正确

---

### 步骤3: 验证物化视图性能（5分钟）

**3.1 在pgAdmin中执行查询**:

```sql
-- 查询日度销售（应该很快 <100ms）
SELECT * FROM mv_daily_sales 
WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
LIMIT 100;
```

**3.2 查看执行时间**:
- 看查询结果下方的 "Query returned successfully"
- **验收标准**: 执行时间 < 100ms（如果有数据）

**3.3 测试其他视图**:
```sql
SELECT * FROM mv_weekly_sales LIMIT 10;
SELECT * FROM mv_profit_analysis LIMIT 10;
SELECT * FROM mv_inventory_summary LIMIT 10;
```

**验收标准**: 所有查询都能快速返回（<200ms）

✅ **步骤3通过标准**: 物化视图查询快速（毫秒级）

---

### 步骤4: 验证业务自动化（10分钟）

**注意**: 此步骤需要有测试数据。如果当前数据库为空，可以跳过。

**4.1 导入测试订单**:
- 使用字段映射系统导入一个测试订单Excel
- 或使用API直接插入测试数据

**4.2 检查库存是否自动扣减**:
```sql
-- 查看库存流水
SELECT * FROM fact_inventory_transactions 
ORDER BY transaction_time DESC 
LIMIT 10;
```

**验收标准**: 
- 应该看到 `transaction_type = 'sale'` 的记录
- `quantity_change` 为负数（扣减）

**4.3 检查应收账款是否自动创建**:
```sql
-- 查看应收账款
SELECT * FROM fact_accounts_receivable 
ORDER BY created_at DESC 
LIMIT 10;
```

**验收标准**: 
- 应该看到新的应收账款记录
- `ar_status = 'pending'`
- `due_date` 约为30天后

**4.4 检查利润是否自动计算**:
```sql
-- 查看订单利润
SELECT 
    order_id,
    gmv_cny,
    cost_amount_cny,
    gross_profit_cny,
    net_profit_cny
FROM fact_sales_orders
WHERE cost_amount_cny IS NOT NULL
LIMIT 10;
```

**验收标准**: `cost_amount_cny` 和 `gross_profit_cny` 有值

✅ **步骤4通过标准**: 自动化流程正常工作（有测试数据时）

---

## 🎯 验收清单

### 必须验收项（Phase 0-2）

- [ ] **数据库架构**: 26个表全部存在
- [ ] **物化视图**: 6个视图全部创建
- [ ] **API接口**: 69个路由全部可用
- [ ] **新增库存API**: 4个接口返回200
- [ ] **新增财务API**: 7个接口返回200
- [ ] **查询性能**: 物化视图查询<200ms
- [ ] **文档完整**: 8个技术文档全部创建

### 可选验收项（需要测试数据）

- [ ] 订单入库自动扣减库存
- [ ] 订单入库自动创建应收账款
- [ ] 订单入库自动计算利润
- [ ] 低库存告警功能
- [ ] 应收账款逾期检查

---

## 📊 性能验收

### 查询性能测试

在pgAdmin中执行以下查询，记录执行时间：

```sql
-- 测试1: 日度销售查询
EXPLAIN ANALYZE 
SELECT * FROM mv_daily_sales 
WHERE order_date >= '2025-10-01';
```

**验收标准**: 执行时间 < 100ms

```sql
-- 测试2: 利润分析
EXPLAIN ANALYZE
SELECT * FROM mv_profit_analysis
WHERE order_date >= '2025-10-01';
```

**验收标准**: 执行时间 < 200ms

```sql
-- 测试3: 库存列表
EXPLAIN ANALYZE
SELECT * FROM fact_inventory
LIMIT 100;
```

**验收标准**: 执行时间 < 100ms

---

## ✅ 验收结果记录

### 验收表格（请填写）

| 验收项 | 预期结果 | 实际结果 | 状态 | 备注 |
|--------|---------|---------|------|------|
| 表数量 | 26个 | ___个 | ☐ | |
| 视图数量 | 6个 | ___个 | ☐ | |
| API路由 | 69个 | ___个 | ☐ | |
| 库存API | 4个 | ___个 | ☐ | |
| 财务API | 7个 | ___个 | ☐ | |
| 查询性能 | <200ms | ___ms | ☐ | |
| 文档完整 | 8个 | ___个 | ☐ | |

### 总体评价（请选择）

- [ ] ✅ **全部通过** - 可以继续Phase 3-8
- [ ] ⚠️ **部分通过** - 需要修复以下问题：_____________
- [ ] ❌ **未通过** - 需要重新实施：_____________

---

## 🚦 验收决策

### 如果全部通过 ✅

**建议行动**:
1. ✅ 批准Phase 0-2成果
2. ✅ 继续Phase 3: 字段映射适配（2天）
3. ✅ 继续Phase 4: 前端集成（3天）
4. ✅ 预计10天完成全部功能

### 如果部分通过 ⚠️

**建议行动**:
1. 列出需要修复的问题
2. 评估修复工作量（预计0.5-1天）
3. 修复后重新验收
4. 然后继续后续Phase

### 如果未通过 ❌

**建议行动**:
1. 详细记录问题
2. 回滚到数据库备份（如果需要）
3. 分析原因，调整方案
4. 重新实施

---

## 📞 技术支持

### 验收过程中遇到问题？

**问题类别**:
1. 数据库连接失败 → 查看 [部署检查清单](DEPLOYMENT_CHECKLIST_POSTGRESQL.md)
2. API无法访问 → 检查后端服务是否启动
3. 性能不达标 → 查看 [PostgreSQL优化总结](POSTGRESQL_OPTIMIZATION_SUMMARY_20251023.md)
4. 功能异常 → 查看 [实施完成报告](IMPLEMENTATION_REPORT_20251023.md)

### 联系方式

- **技术文档**: 查看 `docs/` 目录下的8个文档
- **API文档**: http://localhost:8000/api/docs
- **快速参考**: [QUICK_REFERENCE_CARD.md](QUICK_REFERENCE_CARD.md)

---

## 🎓 验收后的下一步

### 立即可用功能

即使不继续Phase 3-8，以下功能已可用：
- ✅ 通过API查询库存数据
- ✅ 通过API查询财务数据
- ✅ 查询物化视图获得高性能报表
- ✅ 使用pgAdmin管理数据库

### 完整功能（需要Phase 3-8）

- ⏳ 前端库存管理页面
- ⏳ 前端财务管理页面
- ⏳ 用户权限登录界面
- ⏳ 完整的业务流程测试

---

**验收版本**: v1.0  
**验收状态**: ☐ 待验收  
**建议**: 按步骤逐项验收，确保质量

