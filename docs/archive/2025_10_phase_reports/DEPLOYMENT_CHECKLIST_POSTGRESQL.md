# PostgreSQL ERP系统 - 部署检查清单

> **版本**: v4.1.0  
> **更新时间**: 2025-10-23  
> **目标**: 确保系统正确部署并可用于生产环境

---

## 📋 部署前检查

### 环境要求

- [ ] Docker Desktop 已安装并运行
- [ ] Python 3.11+ 已安装
- [ ] Node.js 18+ 已安装  
- [ ] Git 已安装
- [ ] 至少8GB内存
- [ ] 至少20GB可用磁盘空间

### 配置文件

- [ ] `.env` 文件已创建（复制自 `env.production.example`）
- [ ] 数据库密码已修改（不使用默认密码）
- [ ] SECRET_KEY 已生成并配置
- [ ] CORS配置正确（ALLOWED_ORIGINS）

---

## 🚀 部署步骤

### 步骤1: 启动PostgreSQL

```bash
# Windows
start-docker-dev.bat

# Linux/Mac
./docker/scripts/start-dev.sh
```

**验证检查**:
- [ ] 容器健康状态：`docker ps --filter name=postgres`
- [ ] 应看到：`xihong_erp_postgres (healthy)`
- [ ] pgAdmin可访问：http://localhost:5051

### 步骤2: 应用数据库迁移

```bash
cd backend

# 1. 创建所有新表
python ../temp/development/apply_migrations.py

# 2. 添加新字段到现有表
python ../temp/development/alter_fact_sales_orders.py

# 3. 创建物化视图
python ../temp/development/create_materialized_views.py
```

**验证检查**:
- [ ] 打印信息显示："[OK] All tables created successfully"
- [ ] 打印信息显示："Fields added: 14"
- [ ] 打印信息显示："Total materialized views: 6"

### 步骤3: 验证数据库结构

**使用pgAdmin验证**:
1. 访问 http://localhost:5051
2. 登录（admin@xihong.com / admin）
3. 连接数据库（localhost / erp_user / erp_pass_2025）
4. 查看表列表

**应该看到的表**:
- [ ] 26个表（15个原有 + 11个新增）
- [ ] 重点检查：`fact_inventory`, `fact_accounts_receivable`, `dim_users`

**应该看到的视图**:
- [ ] 6个物化视图（mv_daily_sales, mv_weekly_sales, mv_monthly_sales, etc.）

### 步骤4: 安装Python依赖

```bash
# 更新依赖
pip install -r requirements.txt

# 验证关键包
python -c "import psycopg2; print('[OK] psycopg2 installed')"
python -c "import celery; print('[OK] celery installed')"
python -c "import redis; print('[OK] redis installed')"
```

**验证检查**:
- [ ] psycopg2安装成功
- [ ] celery安装成功
- [ ] redis安装成功

### 步骤5: 启动后端服务

```bash
# 方式1: 使用统一启动脚本
cd ..
python run.py

# 方式2: 直接启动
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**验证检查**:
- [ ] 服务启动无错误
- [ ] 控制台显示："Application startup complete"
- [ ] 访问 http://localhost:8000/health 返回 {"status": "healthy"}
- [ ] 访问 http://localhost:8000/api/docs 显示Swagger文档

### 步骤6: 验证新API接口

**在Swagger UI中测试**:

**库存管理**:
- [ ] `GET /api/inventory/list` - 返回200
- [ ] `GET /api/inventory/low-stock-alert` - 返回200

**财务管理**:
- [ ] `GET /api/finance/accounts-receivable` - 返回200
- [ ] `GET /api/finance/profit-report` - 返回200
- [ ] `GET /api/finance/financial-overview` - 返回200

### 步骤7: 启动Celery服务（可选但推荐）

**Terminal 1 - Worker**:
```bash
cd backend
celery -A celery_app worker -l info
```

**Terminal 2 - Beat**:
```bash
cd backend
celery -A celery_app beat -l info
```

**验证检查**:
- [ ] Worker启动显示："celery@hostname ready"
- [ ] Beat启动显示定时任务列表
- [ ] 应看到5个定时任务

### 步骤8: 验证自动化流程（可选）

**测试订单自动流程**:
```python
# 在Python控制台
from backend.models.database import SessionLocal
from backend.services.business_automation import OrderAutomation

db = SessionLocal()
result = OrderAutomation.on_order_created(db, order_id=1)
print(result)
```

**应该看到**:
- [ ] 库存自动扣减
- [ ] 应收账款自动创建
- [ ] 利润自动计算

---

## ✅ 功能验证清单

### 数据库功能

- [ ] 可以插入订单数据
- [ ] 可以插入库存数据
- [ ] 可以插入财务数据
- [ ] UPSERT正常工作（重复数据不报错）

### API功能

- [ ] 库存列表查询正常
- [ ] 财务报表查询正常
- [ ] 分页功能正常
- [ ] 筛选功能正常

### 自动化功能

- [ ] 物化视图能手动刷新
- [ ] Celery定时任务正常调度
- [ ] 低库存告警正常触发
- [ ] 应收账款逾期检查正常

---

## 🔧 故障排除

### 问题1: 数据库连接失败

**症状**: `sqlalchemy.exc.OperationalError: connection refused`

**检查**:
```bash
# 1. PostgreSQL容器是否运行
docker ps --filter name=postgres

# 2. 端口是否正确
docker port xihong_erp_postgres

# 3. 数据库URL配置
cat .env | grep DATABASE_URL
```

**解决**:
- 确保Docker容器健康
- 检查端口映射（5432:5432）
- 验证数据库凭据

### 问题2: 表不存在

**症状**: `relation "fact_inventory" does not exist`

**解决**:
```bash
# 重新执行迁移
cd backend
python ../temp/development/apply_migrations.py
```

### 问题3: 物化视图数据为空

**症状**: 查询视图返回空结果

**解决**:
```bash
# 手动刷新视图
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_weekly_sales;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_sales;
"
```

### 问题4: Celery无法启动

**症状**: `kombu.exceptions.OperationalError: Error 61 connecting to localhost:6379`

**原因**: Redis未启动

**解决**:
```bash
# 启动Redis（Docker）
docker run -d --name redis -p 6379:6379 redis:alpine

# 或安装本地Redis
```

---

## 📊 性能基准测试

### 查询性能测试

```sql
-- 测试1: 查询日度销售（物化视图）
EXPLAIN ANALYZE SELECT * FROM mv_daily_sales WHERE order_date >= '2025-10-01';
-- 预期: <100ms

-- 测试2: 查询周度销售
EXPLAIN ANALYZE SELECT * FROM mv_weekly_sales;
-- 预期: <100ms

-- 测试3: 复杂查询（多表JOIN）
EXPLAIN ANALYZE 
SELECT o.*, i.quantity_available, ar.outstanding_amount_cny
FROM fact_sales_orders o
LEFT JOIN fact_inventory i ON o.product_surrogate_id = i.product_id
LEFT JOIN fact_accounts_receivable ar ON o.id = ar.order_id
WHERE o.order_ts >= '2025-10-01'
LIMIT 100;
-- 预期: <500ms
```

### 批量处理测试

```python
# 测试批量UPSERT（1000行）
import time
from backend.services.data_importer import upsert_orders

start = time.time()
result = upsert_orders(db, test_data_1000_rows)
elapsed = time.time() - start

print(f"Processed {result} rows in {elapsed:.2f} seconds")
# 预期: <2秒（1000行）
```

### 并发测试（可选）

```bash
# 使用Apache Bench测试
ab -n 1000 -c 50 http://localhost:8000/api/dashboard/overview

# 预期结果
# - 成功率: >99%
# - 平均响应时间: <500ms
# - 无连接拒绝错误
```

---

## 📈 监控指标

### 关键指标

**数据库**:
- [ ] 连接数 < 50（峰值）
- [ ] 慢查询数 < 10/天（>1秒）
- [ ] 磁盘使用 < 80%

**API**:
- [ ] 响应时间 < 1秒（P95）
- [ ] 错误率 < 1%
- [ ] QPS > 100

**Celery**:
- [ ] 任务成功率 > 99%
- [ ] 队列堆积 < 100
- [ ] Worker CPU < 80%

---

## 🎯 上线前最终检查

### 功能完整性

- [ ] 数据采集正常（Shopee/TikTok/Amazon/妙手）
- [ ] 字段映射正常
- [ ] 数据入库正常
- [ ] 库存管理功能正常
- [ ] 财务管理功能正常
- [ ] 数据看板显示正常

### 性能达标

- [ ] 50人并发测试通过
- [ ] 1万行数据导入<10秒
- [ ] 查询响应时间<1秒
- [ ] 物化视图自动刷新正常

### 安全性

- [ ] 数据库密码已修改
- [ ] JWT Token认证正常
- [ ] 用户权限控制正常
- [ ] 审计日志记录正常

### 稳定性

- [ ] 24小时稳定性测试通过
- [ ] 自动备份正常执行
- [ ] 故障恢复流程测试通过

---

## 📞 技术支持

### 文档资源

- [PostgreSQL优化总结](POSTGRESQL_OPTIMIZATION_SUMMARY_20251023.md)
- [快速启动指南](QUICK_START_POSTGRESQL_ERP.md)
- [Docker部署指南](DOCKER_QUICK_START.md)

### 常见问题

- [FAQ](FAQ.md)
- [故障排除](TROUBLESHOOTING.md)

---

**检查清单版本**: v1.0  
**最后更新**: 2025-10-23  
**状态**: 生产就绪

