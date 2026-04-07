# 故障排查手册

**版本**: v1.0  
**更新日期**: 2025-10-16  

---

## 📋 目录

- [系统启动问题](#系统启动问题)
- [数据入库问题](#数据入库问题)
- [性能问题](#性能问题)
- [前端显示问题](#前端显示问题)
- [数据库问题](#数据库问题)
- [常见错误代码](#常见错误代码)

---

## 系统启动问题

### ❌ 问题：`ModuleNotFoundError: No module named 'modules'`

**原因**: Python路径配置问题

**解决方案**:

```bash
# 方式1：在项目根目录运行
cd F:\Vscode\python_programme\AI_code\xihong_erp
python scripts/your_script.py

# 方式2：设置PYTHONPATH
$env:PYTHONPATH="."; python scripts/your_script.py

# 方式3：使用-m方式
python -m scripts.your_script
```

---

### ❌ 问题：Streamlit启动失败

**症状**: `streamlit run frontend_streamlit/main.py` 报错

**检查步骤**:

1. 检查依赖是否安装：
   ```bash
   pip install -r requirements.txt
   ```

2. 检查文件是否存在：
   ```bash
   ls frontend_streamlit/main.py
   ```

3. 检查端口是否被占用：
   ```bash
   netstat -ano | findstr :8501
   ```

**解决方案**:

```bash
# 使用其他端口
streamlit run frontend_streamlit/main.py --server.port 8502

# 清除缓存重试
streamlit cache clear
streamlit run frontend_streamlit/main.py
```

---

## 数据入库问题

### ❌ 问题：文件扫描后找不到

**症状**: 运行`scan`命令后，`status`显示0个文件

**检查步骤**:

1. 文件是否在正确目录：
   ```bash
ls data/raw/**/*.xlsx
   ```

2. 文件格式是否支持：
   - 支持：.xlsx, .xls, .csv, .json, .jsonl
   - 不支持：.txt, .pdf, .doc

3. 文件是否被忽略：
   - 检查是否为consolidation_*.json等

**解决方案**:

```bash
# 检查扫描结果
python scripts/etl_cli.py scan data/raw

# 查看详细状态
python scripts/etl_cli.py status --detail
```

---

### ❌ 问题：入库全部失败

**症状**: `python scripts/etl_cli.py ingest` 后failed=100%

**常见原因**:

#### 1. 缺少shop_id

**错误信息**: `missing shop_id column`

**解决方案**:

方案A：在Excel中添加`shop_id`列

方案B：修改文件名包含shop_id：
```
shopee__account__123456__products__20241016.xlsx
                 ^^^^^^
                 shop_id
```

#### 2. 缺少SKU列

**错误信息**: `missing sku column`

**解决方案**:

检查Excel是否包含以下列名之一：
- SKU
- Seller SKU
- Item ID
- 商品SKU
- 商品编号

如果没有，添加`config/field_mappings.yaml`映射。

#### 3. Excel格式错误

**错误信息**: `empty or unreadable`

**解决方案**:

```bash
# 尝试手动读取
python -c "import pandas as pd; df = pd.read_excel('your_file.xlsx'); print(df.shape)"

# 转换为标准格式
# 1. 打开Excel
# 2. 另存为 → .xlsx格式
# 3. 确保第一行是表头
```

---

### ❌ 问题：部分字段未导入

**症状**: 入库成功，但某些字段为空

**原因**: 字段映射未识别

**解决**:

1. 查看字段映射审核页面
2. 确认字段名是否在配置中
3. 编辑`config/field_mappings.yaml`添加映射

---

## 性能问题

### ❌ 问题：扫描文件很慢

**症状**: 1000个文件扫描超过1分钟

**检查**:

```bash
# 检查文件数量
ls data/raw/**/*.xlsx | wc -l

# 检查缓存
python -c "from modules.services.cache_service import get_cache_stats; print(get_cache_stats())"
```

**优化**:

1. 使用缓存（自动，无需配置）
2. 减少扫描目录：
   ```bash
   # 只扫描特定平台
python scripts/etl_cli.py scan data/raw
   ```

---

### ❌ 问题：入库很慢

**症状**: 100个文件入库超过5分钟

**检查**:

1. 数据库是否有锁：
   ```bash
   sqlite3 data/unified_erp_system.db "PRAGMA wal_checkpoint;"
   ```

2. 文件是否很大：
   ```bash
ls -lh data/raw/**/*.xlsx | sort -k5 -hr | head
   ```

**优化**:

1. 减小批次：
   ```bash
   python scripts/etl_cli.py ingest --limit 10
   ```

2. 检查索引：
   ```bash
   python -m alembic current  # 应该显示20251016_0004
   ```

3. 清理临时文件：
   ```bash
   rm -rf temp/cache/*
   ```

---

### ❌ 问题：前端加载慢

**症状**: 打开数据看板超过10秒

**检查**:

1. 数据量是否过大：
   ```sql
   SELECT COUNT(*) FROM fact_product_metrics;
   ```

2. 缓存是否命中：
   - 第一次加载慢正常
   - 第二次应该<1秒

**优化**:

1. 减小时间范围（近7天 → 近30天）
2. 使用平台筛选
3. 清除过期缓存：
   ```python
   from modules.services.cache_service import get_cache_service
   get_cache_service().clear()
   ```

---

## 前端显示问题

### ❌ 问题：数据看板显示空白

**症状**: 打开页面后一片空白

**检查**:

1. 浏览器控制台是否有错误（F12）
2. Streamlit后台是否有报错
3. 数据库是否可访问

**解决**:

```bash
# 重启Streamlit
# Ctrl+C 停止
streamlit run frontend_streamlit/main.py --server.port 8502
```

---

### ❌ 问题：图表不显示

**症状**: 只显示表格，没有Plotly图表

**原因**: plotly库未安装或版本过旧

**解决**:

```bash
pip install plotly>=5.0.0
```

---

### ❌ 问题："数据来源"显示错误

**症状**: 提示"模拟数据"而不是"数据库数据"

**原因**: 查询返回空DataFrame

**检查**:

1. 数据是否已入库：
   ```bash
   python scripts/etl_cli.py status
   ```

2. 筛选条件是否正确

**解决**: 先执行数据入库

---

## 数据库问题

### ❌ 问题：`database is locked`

**原因**: SQLite被其他进程锁定

**解决**:

```bash
# 1. 检查是否有其他进程在使用
ps aux | grep python

# 2. 切换到WAL模式（已自动配置）
python -c "
from sqlalchemy import create_engine, text
from modules.core.secrets_manager import get_secrets_manager
sm = get_secrets_manager()
url = f'sqlite:///{sm.get_unified_database_path()}'
engine = create_engine(url)
with engine.begin() as conn:
    conn.exec_driver_sql('PRAGMA journal_mode=WAL;')
    print('已切换到WAL模式')
"

# 3. 减小并发
# 只运行一个入库进程
```

---

### ❌ 问题：Alembic迁移失败

**症状**: `alembic upgrade head` 报错

**检查**:

```bash
# 查看当前版本
python -m alembic current

# 查看历史
python -m alembic history
```

**解决**:

```bash
# 方案1：从头开始
python -m alembic downgrade base
python -m alembic upgrade head

# 方案2：手动修复
# 编辑 migrations/versions/xxx.py
# 修复SQL语法错误

# 方案3：跳过问题迁移
python -m alembic stamp 20251016_0003  # 标记为已执行
python -m alembic upgrade head         # 继续后续迁移
```

---

### ❌ 问题：查询超时

**症状**: `TimeoutError: database query timeout`

**原因**: 查询数据量过大或缺少索引

**解决**:

1. 添加WHERE条件减小范围：
   ```sql
   WHERE metric_date >= '2024-10-01'  -- 限定日期
   LIMIT 1000                         -- 限定数量
   ```

2. 检查索引：
   ```bash
   python -m alembic upgrade head
   ```

3. 优化查询：
   ```sql
   -- 避免：全表扫描
   SELECT * FROM fact_product_metrics WHERE product_title LIKE '%关键词%';
   
   -- 使用：索引字段
   SELECT * FROM fact_product_metrics WHERE platform_code = 'shopee';
   ```

---

## 常见错误代码

### ETL错误

| 错误代码 | 错误信息 | 原因 | 解决方案 |
|----------|----------|------|----------|
| `E001` | `missing sku column` | Excel缺少SKU列 | 添加SKU列或配置映射 |
| `E002` | `missing shop_id` | 无法推断shop_id | 文件名包含shop_id或添加列 |
| `E003` | `empty or unreadable` | 文件无法读取 | 检查文件格式，转换为标准xlsx |
| `E004` | `manifest skipped` | 元数据文件被跳过 | 正常，无需处理 |
| `E005` | `domain not implemented` | 数据域未实现 | 等待功能开发或手动处理 |

### 数据库错误

| 错误代码 | 错误信息 | 原因 | 解决方案 |
|----------|----------|------|----------|
| `D001` | `database is locked` | 数据库被锁定 | 关闭其他进程，切换WAL模式 |
| `D002` | `no such table` | 表不存在 | 运行Alembic迁移 |
| `D003` | `UNIQUE constraint failed` | 主键冲突 | 正常，系统会自动upsert |
| `D004` | `timeout` | 查询超时 | 添加索引，减小查询范围 |

---

## 🆘 紧急问题处理

### 数据库损坏

**症状**: 无法打开数据库，各种查询报错

**紧急恢复**:

```bash
# 1. 备份损坏的数据库
cp data/unified_erp_system.db data/unified_erp_system.db.broken

# 2. 从备份恢复
cp backups/latest_backup.db data/unified_erp_system.db

# 3. 如果没有备份，重建数据库
rm data/unified_erp_system.db
python -m alembic upgrade head

# 4. 重新入库数据
python scripts/etl_cli.py run data/raw
```

---

### 系统完全无法启动

**症状**: 所有操作都报错

**排查步骤**:

```bash
# 1. 检查Python版本
python --version  # 应该 >= 3.10

# 2. 检查依赖
pip list | grep -E "streamlit|pandas|sqlalchemy"

# 3. 重新安装依赖
pip install -r requirements.txt --force-reinstall

# 4. 检查数据库连接
python -c "
from modules.core.secrets_manager import get_secrets_manager
sm = get_secrets_manager()
print(sm.get_unified_database_path())
"

# 5. 测试基本功能
python scripts/etl_cli.py --help
```

---

## 📞 获取支持

### 自助排查

1. 查看日志文件：`logs/`
2. 查看错误信息完整堆栈
3. 搜索本文档关键词
4. 查看API文档

### 提交问题

如果无法自行解决，请提供以下信息：

```bash
# 生成诊断报告
python scripts/health_check.py > diagnostic_report.txt

# 包含：
# - Python版本
# - 依赖版本
# - 数据库状态
# - Alembic版本
# - 最近日志
```

---

## 🛠️ 维护工具

### 健康检查

```bash
python health_check.py
```

### 数据库维护

```bash
# VACUUM（压缩数据库）
sqlite3 data/unified_erp_system.db "VACUUM;"

# ANALYZE（更新统计信息）
sqlite3 data/unified_erp_system.db "ANALYZE;"

# 检查完整性
sqlite3 data/unified_erp_system.db "PRAGMA integrity_check;"
```

### 清理临时文件

```bash
# 清理缓存
rm -rf temp/cache/*

# 清理日志（保留最近7天）
find logs/ -name "*.log" -mtime +7 -delete

# 清理下载文件（30天前）
find downloads/ -mtime +30 -delete
```

---

## 💡 预防措施

### 1. 定期备份

**每天备份数据库**:
```bash
# 创建备份脚本
#!/bin/bash
DATE=$(date +%Y%m%d)
cp data/unified_erp_system.db backups/db_$DATE.db
```

### 2. 监控日志

**关注警告信息**:
- DeprecationWarning
- database locked
- query timeout

### 3. 测试新数据

**处理新平台数据前**:
1. 先用小文件测试
2. 检查字段映射
3. 确认无误后批量处理

### 4. 版本控制

**记录系统版本**:
```bash
# 查看Alembic版本
python -m alembic current

# 应该显示：20251016_0004 (head)
```

---

**文档维护**: 定期更新常见问题  
**最后更新**: 2025-10-16  
**反馈**: 发现新问题请更新本文档

