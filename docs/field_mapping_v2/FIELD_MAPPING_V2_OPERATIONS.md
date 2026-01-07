# 字段映射系统 v2 运维指南

**版本**: v2.3  
**更新日期**: 2025-10-27  
**目标用户**: 运维人员、系统管理员

---

## 部署前检查

### 数据库准备

1. **执行迁移脚本**:
```bash
# 升级到最新版本
cd migrations
python run_migration.py

# 或使用 Alembic
alembic upgrade head
```

2. **验证索引创建**:
```sql
-- 检查 catalog_files 索引
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'catalog_files';

-- 应包含：
-- ix_catalog_files_file_name (B-Tree)
-- ix_catalog_source_domain (复合)
-- ix_catalog_files_file_metadata_gin (GIN, 如果是 JSONB)
```

3. **验证约束**:
```sql
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'catalog_files'::regclass;

-- 应包含：
-- ck_catalog_files_date_range
-- ck_catalog_files_status
```

---

## 启动服务

### 后端启动

```bash
# 推荐：使用统一启动脚本
python run.py

# 或单独启动后端
cd backend
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

**健康检查**:
```bash
curl http://localhost:8001/health
```

### 前端启动

```bash
cd frontend
npm run dev
```

**访问地址**: `http://localhost:5173`

---

## 日常运维

### 文件扫描

**触发条件**:
- 采集模块下载新文件后
- 手动上传文件到 `data/raw/` 后
- 定期（建议每小时）

**执行方式**:
1. 前端界面：点击"扫描采集文件"按钮
2. API 调用：`POST /api/field-mapping/scan`
3. 脚本调用：
```python
from modules.services.catalog_scanner import scan_and_register
result = scan_and_register("data/raw")
print(f"发现 {result.seen} 个文件，注册 {result.registered} 个")
```

**注意事项**:
- 扫描基于 `file_hash` 去重，重复扫描不会创建重复记录
- 扫描时间与文件数量成正比（约 500 文件/秒）

---

### 清理孤儿记录

**触发条件**:
- 手动删除或移动文件后
- `catalog_files.status` 显示异常时
- 定期维护（建议每周）

**执行方式**:
1. 前端界面：点击"清理无效文件"按钮
2. API 调用：`POST /api/field-mapping/cleanup`

**安全机制**:
- 只删除文件不存在的记录
- 不会删除实际存在的文件
- 返回被删除的文件列表（最多 20 条）

---

### 入库状态监控

**关键指标**:
```sql
-- 各状态文件统计
SELECT status, COUNT(*) 
FROM catalog_files 
GROUP BY status;

-- 今日入库统计
SELECT COUNT(*) AS today_ingested
FROM catalog_files 
WHERE status IN ('ingested', 'partial_success')
  AND DATE(last_processed_at) = CURRENT_DATE;

-- 失败文件列表
SELECT file_name, error_message, last_processed_at
FROM catalog_files 
WHERE status = 'failed'
ORDER BY last_processed_at DESC 
LIMIT 20;
```

**告警阈值**:
- 待处理文件 > 1000：需加快处理速度
- 失败率 > 5%：检查数据质量或映射配置
- 隔离行数 > 10%：数据源可能存在问题

---

### 隔离区管理

**查看隔离数据**:
```sql
SELECT source_file, error_type, COUNT(*) 
FROM data_quarantine 
WHERE is_resolved = FALSE
GROUP BY source_file, error_type
ORDER BY COUNT(*) DESC;
```

**处理隔离数据**:
1. 导出隔离数据进行人工审核
2. 修正源文件后重新入库
3. 标记为已解决：
```sql
UPDATE data_quarantine 
SET is_resolved = TRUE, 
    resolved_at = NOW(), 
    resolution_note = '已修正并重新入库'
WHERE id = ?;
```

---

## 性能优化

### 连接池配置

**backend/models/database.py**:
```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,           # 基础连接数
    max_overflow=10,        # 最大溢出连接
    pool_recycle=3600,      # 1小时回收连接
    pool_pre_ping=True,     # 连接前检查
    echo=False,             # 生产环境关闭SQL日志
)
```

### 查询超时设置

**PostgreSQL 配置**:
```sql
-- 设置语句超时（30秒）
ALTER DATABASE xihong_erp SET statement_timeout = '30s';

-- 设置空闲事务超时（5分钟）
ALTER DATABASE xihong_erp SET idle_in_transaction_session_timeout = '5min';
```

---

## 数据备份

### catalog_files 表备份

**每日备份**:
```bash
# 导出 catalog_files 表
pg_dump -h localhost -U postgres -t catalog_files xihong_erp > catalog_files_backup_$(date +%Y%m%d).sql

# 压缩备份
gzip catalog_files_backup_$(date +%Y%m%d).sql
```

**恢复**:
```bash
# 解压
gunzip catalog_files_backup_20251027.sql.gz

# 恢复
psql -h localhost -U postgres xihong_erp < catalog_files_backup_20251027.sql
```

---

## 监控指标

### 关键指标

| 指标 | SQL 查询 | 告警阈值 |
|------|---------|---------|
| 待处理文件数 | `SELECT COUNT(*) FROM catalog_files WHERE status='pending'` | > 1000 |
| 今日入库数 | `SELECT COUNT(*) FROM catalog_files WHERE DATE(last_processed_at)=CURRENT_DATE AND status='ingested'` | < 100/天 |
| 失败率 | `SELECT COUNT(CASE WHEN status='failed' THEN 1 END) * 100.0 / COUNT(*) FROM catalog_files` | > 5% |
| 隔离行数 | `SELECT COUNT(*) FROM data_quarantine WHERE is_resolved=FALSE` | > 10000 |

### Prometheus 导出器配置

**安装 postgres_exporter**:
```bash
docker run -d \
  --name postgres_exporter \
  -e DATA_SOURCE_NAME="postgresql://postgres:password@localhost:5432/xihong_erp?sslmode=disable" \
  -p 9187:9187 \
  prometheuscommunity/postgres-exporter
```

**Grafana 看板**: 导入 PostgreSQL 预置看板（ID: 9628）

---

## 故障恢复

### 场景1: 大量文件未找到

**诊断**:
```sql
SELECT COUNT(*) AS missing_files
FROM catalog_files 
WHERE file_path IS NOT NULL 
  AND NOT EXISTS (SELECT 1);  -- 需要自定义函数检查文件存在性
```

**解决方案**:
1. 运行"清理无效文件"
2. 检查文件是否被误删或移动
3. 从备份恢复文件
4. 重新扫描

### 场景2: 入库性能下降

**诊断**:
```sql
-- 检查慢查询
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 1000  -- 超过1秒
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**解决方案**:
1. 执行 `VACUUM ANALYZE catalog_files;`
2. 重建索引：`REINDEX TABLE catalog_files;`
3. 检查连接池是否耗尽
4. 考虑启用第二阶段优化（COPY 流水线）

### 场景3: 前端选择器无文件

**诊断**:
1. 检查 `catalog_files` 表是否有数据
2. 检查 `source_platform` 是否为 NULL
3. 检查前端控制台错误

**解决方案**:
1. 运行文件扫描
2. 检查 `data/raw/` 目录是否有文件
3. 检查后端日志是否有错误

---

## 维护计划

### 每日
- [ ] 监控入库成功率
- [ ] 检查隔离区数据量
- [ ] 查看错误日志

### 每周
- [ ] 清理无效文件记录
- [ ] 备份 catalog_files 表
- [ ] 清理过期日志文件

### 每月
- [ ] 执行 `VACUUM FULL ANALYZE`
- [ ] 审查慢查询并优化
- [ ] 归档旧数据（>90天）

---

## 联系支持

技术支持:
- 文档: `docs/` 目录
- 问题追踪: GitHub Issues
- 紧急联系: 系统管理员

---

**最后更新**: 2025-10-27  
**文档版本**: v2.3

