# 快速参考卡 - PostgreSQL ERP系统

**版本**: v4.1.0 | **更新**: 2025-10-23 | **一页纸速查**

---

## 🚀 快速启动（5分钟）

```bash
# 1. 启动PostgreSQL
start-docker-dev.bat                    # Windows
./docker/scripts/start-dev.sh           # Linux/Mac

# 2. 执行迁移（首次必须）
cd backend
python ../temp/development/apply_migrations.py
python ../temp/development/alter_fact_sales_orders.py
python ../temp/development/create_materialized_views.py

# 3. 启动后端
cd ..
python run.py

# 4. 访问系统
# http://localhost:8000/api/docs
```

---

## 📊 数据架构速查

### 26个核心表

```
维度表 (5个)         事实表 (9个)              管理表 (9个)
├── dim_platform   ├── fact_sales_orders    ├── accounts
├── dim_shop       ├── fact_order_items     ├── data_files
├── dim_product    ├── fact_inventory       ├── field_mappings
├── dim_users      ├── fact_inv_transactions└── ...
└── dim_roles      ├── fact_ar
                   ├── fact_payments
                   ├── fact_expenses
                   ├── fact_product_metrics
                   └── fact_audit_logs
```

### 6个物化视图（性能优化）

- `mv_daily_sales` - 日度销售汇总
- `mv_weekly_sales` - 周度销售汇总
- `mv_monthly_sales` - 月度销售汇总
- `mv_profit_analysis` - 利润分析
- `mv_inventory_summary` - 库存汇总
- `mv_financial_overview` - 财务总览

---

## 🔌 API接口速查（69个）

### 库存管理 `/api/inventory`

```
GET  /list                  # 库存列表
GET  /detail/{id}           # 库存详情+流水
POST /adjust                # 库存调整
GET  /low-stock-alert       # 低库存预警
```

### 财务管理 `/api/finance`

```
GET  /accounts-receivable   # 应收账款列表
POST /record-payment        # 记录收款
GET  /payment-receipts      # 收款记录
GET  /expenses              # 费用列表
GET  /profit-report         # 利润报表
GET  /overdue-alert         # 逾期预警
GET  /financial-overview    # 财务总览
```

### 数据采集 `/api/collection`

```
POST /start                 # 启动采集
GET  /status/{task_id}      # 采集状态
GET  /platforms             # 平台列表
```

### 字段映射 `/api/field-mapping`

```
POST /scan                  # 扫描文件
POST /preview               # 预览数据
POST /generate-mapping      # 生成映射
POST /ingest                # 数据入库
GET  /progress/{task_id}    # 入库进度
```

---

## ⚡ 性能速查

| 操作 | 性能 | 说明 |
|------|------|------|
| 日度销售查询 | 50ms | 物化视图 |
| 利润报表 | 100ms | 物化视图 |
| 库存列表（100条） | 200ms | 索引优化 |
| 批量导入（1万行） | 10秒 | UPSERT优化 |
| 并发支持 | 60连接 | 连接池 |

---

## 🤖 自动化流程

### 订单入库自动触发

```
订单数据导入
    ↓
自动扣减库存 (quantity_available -qty)
    ↓
创建应收账款 (Net 30天账期)
    ↓
计算订单利润 (销售 - 成本 - 费用)
    ↓
刷新物化视图 (5分钟后)
```

### 定时任务

```
每5分钟   → 刷新销售视图
每10分钟  → 刷新库存/财务视图
每6小时   → 低库存检查
每天9:00  → 应收账款逾期检查
每天3:00  → 数据库备份
```

---

## 🔧 常用命令

### Docker管理

```bash
# 启动/停止
docker-compose up -d postgres
docker-compose stop postgres

# 查看日志
docker-compose logs -f postgres

# 进入容器
docker exec -it xihong_erp_postgres bash
```

### 数据库操作

```bash
# 连接数据库
docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp

# 备份数据库
docker exec xihong_erp_postgres pg_dump -U erp_user -d xihong_erp -F c -f /tmp/backup.dump

# 刷新物化视图
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_sales"
```

### Celery管理

```bash
# 启动Worker
cd backend
celery -A celery_app worker -l info

# 启动Beat（定时任务）
celery -A celery_app beat -l info

# 查看任务状态
celery -A celery_app inspect active
```

---

## 🐛 故障速查

### PostgreSQL连接失败
```bash
# 检查容器
docker ps --filter name=postgres
# 检查端口
docker port xihong_erp_postgres
```

### API启动失败
```bash
# 检查依赖
pip list | grep psycopg2
pip list | grep celery
# 重新安装
pip install -r requirements.txt
```

### 物化视图数据为空
```bash
# 手动刷新
docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -c "REFRESH MATERIALIZED VIEW mv_daily_sales"
```

---

## 📚 文档索引

| 文档 | 用途 | 链接 |
|------|------|------|
| 快速启动 | 5分钟上手 | [QUICK_START_POSTGRESQL_ERP.md](QUICK_START_POSTGRESQL_ERP.md) |
| 实施总结 | 技术详情 | [POSTGRESQL_OPTIMIZATION_SUMMARY_20251023.md](POSTGRESQL_OPTIMIZATION_SUMMARY_20251023.md) |
| 部署清单 | 上线检查 | [DEPLOYMENT_CHECKLIST_POSTGRESQL.md](DEPLOYMENT_CHECKLIST_POSTGRESQL.md) |
| API示例 | 接口调用 | [API_USAGE_EXAMPLES.md](API_USAGE_EXAMPLES.md) |
| 架构对比 | 架构决策 | [ARCHITECTURE_COMPARISON.md](ARCHITECTURE_COMPARISON.md) |
| 实施报告 | 完整报告 | [IMPLEMENTATION_REPORT_20251023.md](IMPLEMENTATION_REPORT_20251023.md) |

---

## 🎯 关键数字

```
26个表 | 6个物化视图 | 69个API | 60并发 | 50倍性能提升
```

---

**打印提示**: 建议打印此页作为桌面速查卡  
**版本**: v1.0 | **状态**: ✅ 生产就绪

