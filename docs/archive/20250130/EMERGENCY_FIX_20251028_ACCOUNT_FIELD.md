# 紧急修复指南：catalog_files.account字段错误

**问题时间**: 2025-10-28 15:19  
**错误类型**: `psycopg2.errors.UndefinedColumn: 字段 catalog_files.account 不存在`  
**修复状态**: ✅ 数据库已修复，需重启后端

---

## 🔍 问题诊断

### 错误现象
1. 前端点击文件时报错："文件未找到"
2. 后端日志显示：`字段 catalog_files.account 不存在`
3. 文件扫描全部跳过（413个文件，注册0个，跳过413个）

### 根本原因
1. **Schema不同步**: PostgreSQL数据库已有`account`字段
2. **后端缓存**: 后端服务启动时缓存了旧schema
3. **事务失败**: 第一次查询失败后，整个session事务被终止

---

## ⚡ 立即修复（2步）

### 步骤1: 验证数据库（✅ 已完成）

```bash
python scripts/fix_pg_account_silent.py
```

**输出**: `[OK] account field exists`  
**结论**: 数据库正常，字段已存在

### 步骤2: 重启后端服务（**必须执行**）

#### 方法A: 使用run.py重启（推荐）

```bash
# 在run.py的窗口按Ctrl+C停止
# 然后重新执行：
python run.py
```

#### 方法B: 单独重启后端

```bash
# 1. 停止后端进程
taskkill /f /im python.exe /fi "WINDOWTITLE eq *uvicorn*"

# 2. 进入backend目录
cd backend

# 3. 重新启动
uvicorn main:app --reload --port 8001
```

---

## ✅ 验证修复

重启后端后，执行以下验证：

### 1. 检查后端日志

应该看到：
```
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8001
```

### 2. 前端测试

1. 刷新浏览器（F5）
2. 进入"字段映射审核"页面
3. 点击"扫描采集文件"按钮
4. 应看到成功提示："发现413个文件，新注册XXX个"
5. 选择文件查看详情
6. **不应再出现"文件未找到"或"字段不存在"错误**

### 3. API测试

```bash
curl http://localhost:8001/api/field-mapping/file-info?file_id=699
```

应返回200状态，包含账号和店铺信息：
```json
{
  "success": true,
  "file_name": "miaoshou_products_snapshot_20250925_110200.xlsx",
  "parsed_metadata": {
    "account": "N/A或实际账号",
    "shop": "shop_id",
    ...
  }
}
```

---

## 🎯 技术细节

### 为什么需要重启？

1. **SQLAlchemy Metadata缓存**:
   - 后端启动时，SQLAlchemy读取数据库schema并缓存到`MetaData`对象
   - 即使数据库schema更新，运行中的服务不会自动刷新
   - 查询时仍使用旧schema（不包含`account`字段）

2. **psycopg2连接池**:
   - 连接池中的连接可能缓存了prepared statements
   - 这些statements基于旧schema编译
   - 需要关闭连接池并重建

### 为什么扫描失败？

`catalog_scanner.py`的事务管理问题：
- 第一个文件扫描时，查询失败（字段不存在）
- PostgreSQL将整个事务标记为`InFailedSqlTransaction`
- 后续所有操作都被拒绝，直到rollback
- 413个文件全部跳过

---

## 🔧 后续优化建议（可选）

### 优化1: 改进catalog_scanner事务管理

```python
# modules/services/catalog_scanner.py
# 当前：使用单一session扫描所有文件
# 建议：每个文件独立事务，失败后rollback继续

for file_path in files:
    try:
        # 每个文件独立处理
        with Session() as session:
            process_file(session, file_path)
            session.commit()
    except Exception as e:
        session.rollback()  # ⭐ 关键：回滚后继续
        logger.warning(f"文件失败: {e}")
        continue
```

### 优化2: Schema验证中间件

```python
# backend/main.py
@app.on_event("startup")
async def verify_schema():
    """启动时验证数据库schema完整性"""
    required_columns = {'catalog_files': ['account', 'shop_id', ...]}
    # 验证所有必需字段存在
```

---

## 📋 完成检查清单

- [x] 数据库account字段已存在
- [x] 修复脚本已创建
- [ ] 后端服务已重启 ⬅️ **请执行**
- [ ] 前端测试通过
- [ ] 文件扫描成功

---

**现在请重启后端服务（按Ctrl+C，然后`python run.py`），问题即可解决！**

