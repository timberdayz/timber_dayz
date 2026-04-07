# PostgreSQL企业级ERP系统 - 快速启动指南

> **版本**: v4.1.0  
> **更新时间**: 2025-10-23  
> **适用场景**: 20-50人团队使用

---

## 🚀 5分钟快速启动

### 步骤1: 启动Docker数据库

```bash
# Windows
start-docker-dev.bat

# Linux/Mac
./docker/scripts/start-dev.sh
```

**验证**: PostgreSQL容器健康
```bash
docker ps --filter name=postgres
# 应该看到: xihong_erp_postgres (healthy)
```

### 步骤2: 应用数据库迁移（首次启动必须）

```bash
cd backend

# 创建所有新表
python -c "import sys; sys.path.insert(0, '..'); from temp.development.apply_migrations import apply_migrations; import asyncio; asyncio.run(apply_migrations())"

# 添加新字段
python -c "import sys; sys.path.insert(0, '..'); from temp.development.alter_fact_sales_orders import alter_fact_sales_orders; alter_fact_sales_orders()"

# 创建物化视图
python -c "import sys; sys.path.insert(0, '..'); from temp.development.create_materialized_views import create_materialized_views; create_materialized_views()"
```

### 步骤3: 启动后端服务

```bash
# 方式1: 使用统一启动脚本（推荐）
cd ..
python run.py

# 方式2: 单独启动后端
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**验证**: 访问 http://localhost:8000/api/docs

### 步骤4: 启动Celery异步任务（可选）

```bash
# Terminal 1: 启动Worker（处理异步任务）
cd backend
celery -A celery_app worker -l info -Q data_processing

# Terminal 2: 启动Beat（定时任务调度）
cd backend
celery -A celery_app beat -l info
```

### 步骤5: 启动前端（可选）

```bash
cd frontend
npm install  # 首次
npm run dev
```

**访问**: http://localhost:5173

---

## 📊 新功能使用指南

### 库存管理

**API接口**:
```bash
# 获取库存列表（支持低库存筛选）
GET http://localhost:8000/api/inventory/list?low_stock_only=true

# 库存详情（含流水）
GET http://localhost:8000/api/inventory/detail/1

# 库存调整
POST http://localhost:8000/api/inventory/adjust
{
  "product_id": 1,
  "platform_code": "shopee",
  "shop_id": "123456",
  "quantity_change": 100,
  "operator_id": "admin",
  "notes": "盘点调整"
}

# 低库存告警
GET http://localhost:8000/api/inventory/low-stock-alert
```

### 财务管理

**API接口**:
```bash
# 应收账款列表
GET http://localhost:8000/api/finance/accounts-receivable?status=pending

# 记录收款
POST http://localhost:8000/api/finance/record-payment
{
  "ar_id": 1,
  "receipt_amount": 1000.00,
  "payment_method": "bank_transfer",
  "receipt_date": "2025-10-23"
}

# 利润报表
GET http://localhost:8000/api/finance/profit-report?granularity=daily&start_date=2025-10-01&end_date=2025-10-23

# 逾期预警
GET http://localhost:8000/api/finance/overdue-alert

# 财务总览
GET http://localhost:8000/api/finance/financial-overview?platform=shopee
```

### 数据看板（增强）

**查询物化视图** - 毫秒级响应:
```bash
# 日度销售趋势
SELECT * FROM mv_daily_sales WHERE order_date >= '2025-10-01'

# 周度销售对比
SELECT * FROM mv_weekly_sales

# 月度利润分析
SELECT * FROM mv_profit_analysis
```

---

## 🔄 自动化流程

### 订单入库自动流程

**触发时机**: 订单数据导入后

**自动执行**:
1. ✅ 扣减库存（`quantity_available` 减少）
2. ✅ 记录库存流水（追溯）
3. ✅ 创建应收账款（Net 30账期）
4. ✅ 计算订单利润（查询商品成本）
5. ✅ 刷新物化视图（下次刷新周期）

### 定时任务

**每5分钟**:
- 刷新销售物化视图（日/周/月、利润）

**每10分钟**:
- 刷新库存和财务物化视图

**每6小时**:
- 检查低库存，发送告警

**每天9:00**:
- 检查应收账款逾期，更新状态

**每天3:00**:
- 数据库全量备份

---

## 🎯 多粒度数据处理

### 数据采集策略

**日度采集**:
- 每天多次采集当天数据
- 自动UPSERT，覆盖旧数据

**周度采集**:
- 每周一采集上周整周数据
- 从日度数据聚合，不存储

**月度采集**:
- 每月初采集上月整月数据
- 从日度数据聚合，不存储

### 数据查询

**前端查询**:
```javascript
// 日度数据 - 查询物化视图
GET /api/finance/profit-report?granularity=daily

// 周度数据 - 自动从日度聚合
GET /api/finance/profit-report?granularity=weekly

// 月度数据 - 自动从日度聚合
GET /api/finance/profit-report?granularity=monthly
```

**优势**:
- ✅ 避免数据冲突（单一数据源）
- ✅ 节省存储空间（不重复存储）
- ✅ 查询性能高（物化视图预计算）
- ✅ 灵活分析（任意时间范围）

---

## 📚 技术文档

### 数据库文档
- [数据库架构设计](POSTGRESQL_OPTIMIZATION_SUMMARY_20251023.md)
- [物化视图说明](../sql/materialized_views/create_sales_views.sql)

### API文档
- [Swagger UI](http://localhost:8000/api/docs) - 交互式API文档
- [ReDoc](http://localhost:8000/api/redoc) - 详细API参考

### 开发文档
- [业务自动化](../backend/services/business_automation.py)
- [Celery任务](../backend/tasks/)

---

## 🐛 常见问题

### 1. 数据库连接失败

**问题**: Cannot connect to PostgreSQL

**解决**:
```bash
# 检查Docker容器状态
docker ps --filter name=postgres

# 检查端口占用
netstat -ano | findstr "5432"

# 重启容器
docker-compose restart postgres
```

### 2. 物化视图未刷新

**问题**: 数据看板显示旧数据

**解决**:
```bash
# 手动刷新所有视图
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales"
```

### 3. Celery任务未执行

**问题**: 定时任务没有运行

**解决**:
```bash
# 检查Celery Beat是否启动
ps aux | grep celery

# 查看Celery日志
celery -A backend.celery_app inspect stats
```

---

## 🎓 最佳实践

### 开发环境

1. ✅ 使用混合模式（Docker数据库 + 本地代码）
2. ✅ 启用数据库日志（DATABASE_ECHO=true）
3. ✅ 使用pgAdmin查看表结构

### 生产环境

1. ✅ 使用完全Docker模式
2. ✅ 配置自动备份（每日）
3. ✅ 监控慢查询（>1秒记录）
4. ✅ 定期执行VACUUM ANALYZE

### 数据导入

1. ✅ 大文件使用异步任务（Celery）
2. ✅ 批量导入（1000行/批次）
3. ✅ 验证后再入库（避免脏数据）

---

**祝您使用愉快！** 如有问题，请查看 [完整优化总结](POSTGRESQL_OPTIMIZATION_SUMMARY_20251023.md)

