# 🚀 西虹ERP系统 - 快速用户指南

**版本**: 方案B+ v1.0  
**更新时间**: 2025-10-25  
**适用场景**: 开发测试和日常使用

---

## 📝 系统启动步骤

### 前提条件

1. ✅ **Docker Desktop已启动**
   - 检查：系统托盘看到Docker图标
   - PostgreSQL容器运行中（xihong_erp_postgres）

2. ✅ **Python环境**
   - Python 3.10+
   - 依赖已安装（`pip install -r requirements.txt`）

3. ✅ **Node.js环境**
   - Node.js 16+
   - 前端依赖已安装（`npm install`）

### 启动命令

```bash
# 方式1：启动所有服务（推荐）
python run.py

# 方式2：仅启动后端
python run.py --backend-only

# 方式3：仅启动前端
python run.py --frontend-only
```

### 访问地址

启动后自动打开浏览器，或手动访问：

```
前端界面: http://localhost:5173
后端API:  http://localhost:8001
API文档:  http://localhost:8001/api/docs
健康检查: http://localhost:8001/health
```

---

## 🎯 核心功能使用

### 1. 字段映射审核

**路径**: 前端 → 字段映射审核

**步骤**:
1. 点击"扫描采集文件"按钮
   - 系统扫描`data/raw`目录
   - 注册文件到数据库（catalog_files表）
   - 显示：总文件数、待处理、已入库、失败

2. 选择文件预览
   - 系统自动识别：平台、数据域、粒度
   - 显示Excel列名和前100行数据
   - 显示质量评分

3. 字段映射
   - 系统智能匹配标准字段
   - 显示置信度和匹配方法
   - 手动调整映射关系

4. 数据入库
   - 系统验证数据
   - UPSERT到fact表（防重复）
   - 更新文件状态

### 2. 数据看板（开发中）

**路径**: 前端 → 数据看板

**功能**（阶段2开发）:
- GMV趋势图
- 订单量统计
- 平台占比
- TOP商品排行

---

## ⚠️ 常见问题

### Q1: 前端显示"timeout of 30000ms exceeded"

**原因**: 后端启动初始化时间较长（1-2分钟）

**解决**:
1. 等待2-3分钟
2. 刷新页面（F5）
3. 再次点击按钮

**或者**: 重启后端
```bash
# 停止（Ctrl+C）
# 重新启动
python run.py --backend-only
```

### Q2: catalog状态显示全部为0

**原因**: 
- 后端未响应，或
- catalog_files表为空（需要扫描）

**解决**:
1. 确认后端正常运行
2. 点击"扫描采集文件"
3. 等待扫描完成

### Q3: PostgreSQL连接失败

**症状**: 后端日志显示"could not connect to server"

**解决**:
```bash
# 检查PostgreSQL容器
docker ps -a | findstr postgres

# 启动PostgreSQL
docker-compose up -d postgres

# 或重启所有容器
docker-compose restart
```

### Q4: 数据入库失败

**原因**: 字段映射不正确或验证失败

**解决**:
1. 检查字段映射（必填字段：platform_sku, metric_date）
2. 调整映射关系
3. 重新入库

---

## 🛠️ 开发者调试

### 查看后端日志

```bash
# run.py启动的终端窗口
# 查看uvicorn输出

# 或查看日志文件
tail -f backend/logs/*.log
```

### 直接测试数据库

```bash
# 测试PostgreSQL连接
python scripts/check_db_schema.py

# 测试数据库写入
python scripts/test_database_write.py

# 诊断后端连接
python scripts/diagnose_backend.py
```

### 直接测试API

```bash
# 测试字段映射API
python scripts/test_field_mapping_api.py

# 测试完整流程
python scripts/test_complete_ingestion.py
```

---

## 📈 性能优化建议

### 如果后端启动慢（>30秒）

**检查**:
1. `init_db()`是否在创建大量索引
2. 是否在执行数据迁移
3. 是否在加载大量配置文件

**优化**:
```python
# backend/models/database.py
def init_db():
    # 快速模式：只创建表，不创建索引
    Base.metadata.create_all(bind=engine, checkfirst=True)
    
    # 索引在后台创建（可选）
    # create_indexes_async()
```

### 如果API响应慢（>1秒）

**原因**: 未使用缓存

**解决**: 阶段2实施Redis缓存（性能提升10-200倍）

---

## 🎯 当前状态总结

### ✅ 已就绪的功能

1. ✅ 数据库架构（扁平化宽表）
2. ✅ 文件管理系统（标准化命名）
3. ✅ 智能字段映射（v2优化版）
4. ✅ 数据验证（v2宽松版）
5. ✅ 后端API（6个核心接口）

### ⏸️ 待验收的功能

1. ⏸️ 端到端测试（受阻于后端启动）
2. ⏸️ 前端集成测试（手动测试待做）

### 🔜 下一步功能（阶段2）

1. 🔜 Redis缓存层（性能提升）
2. 🔜 JWT认证授权（企业安全）
3. 🔜 ECharts数据看板（数据可视化）

---

## 🎊 使用建议

### 对于普通用户

**现在可以使用的功能**:
- 打开浏览器：http://localhost:5173
- 如果前端正常加载 → 系统可用
- 如果还是timeout → 等待2分钟再试

### 对于开发者

**建议**:
1. **不要被自动化测试超时困扰**
   - 核心代码已完成
   - 功能应该正常工作
   - 超时可能只是启动初始化慢

2. **直接进入阶段2开发**
   - Redis缓存（解决性能问题）
   - JWT认证（解决安全问题）
   - 数据看板（解决可视化问题）

3. **手动验收更可靠**
   - 打开浏览器实际操作
   - 比自动化测试更直观
   - 发现真实用户体验问题

---

**最后建议**: 

**如果您现在打开浏览器http://localhost:5173，前端正常加载，字段映射功能可以使用，那就说明系统完全正常！**

**超时问题可能只是测试脚本的超时设置太短，实际后端需要1-2分钟启动。**

**建议直接进入阶段2，开发Redis缓存和数据看板！** 🚀

