# v4.4.0 快速部署指南（5分钟）

**目标**: 5分钟内完成财务域部署并开始使用

---

## 🚀 一键部署（推荐）

```bash
# 确保数据库运行中
docker ps | grep postgres

# 一键部署（自动完成全部步骤）
python scripts/deploy_v4_4_0_finance.py

# 验证部署
python scripts/verify_v4_4_0_deployment.py
```

**预期输出**：
```
[OK] 27/27 张表已创建
[OK] 辞典数据验证通过
[OK] 物化视图验证通过
[OK] API接口验证通过
[SUCCESS] 全部验证通过，v4.4.0部署成功
```

---

## 📋 手动部署（出问题时使用）

### 步骤1：运行数据库迁移（1分钟）

```bash
# 方式A：Alembic
cd migrations
alembic upgrade head

# 方式B：Python脚本
python migrations/run_migration.py
```

### 步骤2：初始化种子数据（2分钟）

```bash
# 基础辞典（如果未运行过）
python scripts/init_field_mapping_dictionary.py
python scripts/seed_services_dictionary.py
python scripts/seed_traffic_dictionary.py

# 财务域辞典（新增）
python scripts/seed_finance_dictionary.py
```

**预期输出**：
```
[OK] 已插入 16 个财务费用字段
[OK] 已插入 7 个采购管理字段
[OK] 已插入 6 个计算指标公式
[OK] 已插入 8 个货币
[OK] 已插入 12 个总账科目
[OK] 已插入 24 个会计期间
```

### 步骤3：创建物化视图（1分钟）

```bash
# PostgreSQL命令行
psql -U postgres -d xihong_erp -f sql/create_finance_materialized_views.sql

# 或Docker内执行
docker exec -i xihong_postgres psql -U postgres -d xihong_erp < sql/create_finance_materialized_views.sql
```

**预期输出**：
```
CREATE MATERIALIZED VIEW
CREATE INDEX
...
（共创建5个物化视图 + 索引）
```

### 步骤4：重启服务（1分钟）

```bash
# 停止现有服务
# Windows: Ctrl+C 停止run.py

# 重新启动
python run.py

# 等待启动完成（约10-15秒）
# 看到：[OK] 后端服务已启动 http://0.0.0.0:8001
#       [OK] 前端服务已启动 http://localhost:5173
```

---

## ✅ 验证部署成功

### 1. 访问API文档

打开浏览器：http://localhost:8001/docs

查找新增接口：
- `/api/field-mapping/dictionary/fields` (POST) - 创建标准字段
- `/api/procurement/po/create` (POST) - 创建采购订单
- `/api/finance/expenses/upload` (POST) - 上传费用
- `/api/finance/pnl/shop` (GET) - 查询P&L

### 2. 访问财务管理前端

打开浏览器：http://localhost:5173/#/financial-management

应该看到4个Tab：
- ✅ 费用导入
- ✅ P&L月报
- ✅ 汇率管理
- ✅ 会计期间

### 3. 测试费用导入

```
1. 点击"下载模板" → 获得Excel模板
2. 填写费用数据
3. 上传 → 应该成功导入
4. 执行分摊 → 应该显示分摊结果
5. 查看P&L → 应该显示数据
```

---

## 🔧 常见问题

### Q1: Alembic迁移失败

**错误**: `Target database is not up to date.`

**解决**:
```bash
# 检查当前版本
alembic current

# 查看历史
alembic history

# 强制升级到head
alembic upgrade head --sql  # 先看SQL
alembic upgrade head         # 确认后执行
```

### Q2: 种子脚本报错"表不存在"

**原因**: 未运行迁移

**解决**:
```bash
# 先运行迁移
alembic upgrade head

# 再运行种子
python scripts/seed_finance_dictionary.py
```

### Q3: 物化视图创建失败

**错误**: `relation "mv_sales_day_shop_sku" does not exist`

**原因**: 依赖的基表数据为空

**解决**:
```bash
# 检查基表数据
psql -U postgres -d xihong_erp -c "SELECT COUNT(*) FROM fact_order_items;"

# 如果为0，需要先导入销售数据
# 使用字段映射系统导入订单数据

# 再创建视图
psql -U postgres -d xihong_erp -f sql/create_finance_materialized_views.sql
```

### Q4: API返回500错误

**检查**:
```bash
# 查看后端日志
tail -f logs/backend.log

# 常见原因：
# - 表未创建 → 运行迁移
# - 导入语句错误 → 检查backend/routers/xxx.py的import
# - 数据库连接失败 → 检查.env配置
```

---

## 📊 部署后续步骤

### 1. 导入历史数据（可选）

```bash
# 创建迁移脚本（待实现）
python scripts/migrate_historical_data.py --period 2024-07 --to 2025-01

# 或手工导入
# 使用字段映射系统逐文件导入
```

### 2. 设置物化视图自动刷新

```python
# 在backend/tasks/scheduled_tasks.py添加

from celery import Celery
from sqlalchemy import text
from backend.models.database import engine

@celery_app.task
def refresh_materialized_views():
    """每小时刷新物化视图"""
    views = [
        'mv_sales_day_shop_sku',
        'mv_inventory_snapshot_day'
    ]
    
    with engine.connect() as conn:
        for view in views:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
            conn.commit()
```

### 3. 配置权限

```python
# 在backend/routers/auth.py添加财务角色

ROLE_PERMISSIONS = {
    'finance': [
        'finance.expenses.upload',
        'finance.pnl.view',
        'finance.periods.close'
    ],
    'procurement': [
        'procurement.po.create',
        'procurement.po.approve'
    ]
}
```

---

## 🎯 验收清单

- [ ] 27张表全部创建
- [ ] 财务域辞典≥16个字段
- [ ] 计算指标≥6个公式
- [ ] 5个物化视图全部创建
- [ ] API文档可访问
- [ ] 财务管理前端可访问
- [ ] 费用导入流程测试通过
- [ ] P&L月报查询返回数据

---

**部署耗时**: 5-10分钟  
**下一步**: [财务域完整指南](V4_4_0_FINANCE_DOMAIN_GUIDE.md)


