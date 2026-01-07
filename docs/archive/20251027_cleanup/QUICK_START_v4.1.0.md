# 快速开始指南 v4.1.0

> **最新更新**: 2025-10-25 - 后端性能全面优化完成

## 🎉 v4.1.0 重大更新

### ✅ 已修复的问题

1. **功能完整恢复** - 所有12个核心功能模块正常工作
   - ✅ 数据看板 (Dashboard)
   - ✅ 数据采集 (Collection)
   - ✅ 数据管理 (Management)
   - ✅ 账号管理 (Accounts)
   - ✅ 字段映射 (Field Mapping)
   - ✅ 库存管理 (Inventory)
   - ✅ 财务管理 (Finance)
   - ✅ 认证授权 (Auth/Users/Roles)
   - ✅ 性能监控 (Performance)
   - ✅ 测试诊断 (Test API)

2. **性能显著提升**
   - 启动时间: 8-12秒（稳定）
   - 并发支持: 50+用户
   - Dashboard加载: <3秒
   - 无timeout错误

3. **用户体验优化**
   - 智能超时配置（不同操作不同时长）
   - 自动重试机制（网络波动自动重试3次）
   - 详细的启动性能报告

---

## 🚀 5分钟快速启动

### 前置要求

- ✅ Python 3.9+
- ✅ Node.js 16+
- ✅ PostgreSQL 15+ (已安装并运行)
- ✅ Git

### Step 1: 启动PostgreSQL

**Windows用户**:
```powershell
# 检查PostgreSQL服务状态
services.msc
# 找到 "PostgreSQL 15" 服务，确保状态为"正在运行"

# 或使用命令
net start postgresql-x64-15
```

**Linux/Mac用户**:
```bash
# 启动PostgreSQL
sudo systemctl start postgresql
# 或
brew services start postgresql@15
```

### Step 2: 验证数据库连接

```bash
# 测试连接
psql -U erp_user -d xihong_erp -h localhost -p 5432
# 密码: erp_pass_2025

# 如果连接成功，输入 \q 退出
```

### Step 3: 一键启动系统

```bash
# 克隆项目（如果还没有）
git clone https://github.com/xihong-erp/xihong-erp.git
cd xihong-erp

# 安装Python依赖
pip install -r requirements.txt

# 启动完整系统（推荐）
python run.py

# 或分别启动
python run.py --backend-only   # 只启动后端
python run.py --frontend-only  # 只启动前端
```

### Step 4: 验证优化效果

```bash
# 运行快速验证脚本
python backend/verify_optimization.py
```

**预期输出**:
```
🚀 西虹ERP系统后端优化验证 v4.1.0

============================================================
  测试1: 后端服务状态
============================================================
✅ 后端服务运行正常
   版本: 4.1.0
   数据库: PostgreSQL
   路由数: 85
   连接池大小: 30
   活跃连接: 2

============================================================
  测试2: 路由恢复检查
============================================================
✅ API文档可访问

...

============================================================
  验证总结
============================================================

  总计: 5/5 项测试通过 (100%)

  ✅ 所有测试通过！后端优化成功！
```

---

## 📊 观察启动性能

启动后端时，会看到详细的性能报告：

```
🚀 西虹ERP系统后端服务启动中...
✓ PostgreSQL PATH配置完成 (0.12秒)
✓ 数据库连接验证成功 (1.45秒)
✓ 数据库表初始化完成 (2.31秒)
✓ 连接池预热完成 (1.76秒)

╔══════════════════════════════════════════════════════════╗
║          西虹ERP系统启动完成 - 性能报告                  ║
╠══════════════════════════════════════════════════════════╣
║  PostgreSQL PATH配置:   0.12秒                           ║
║  数据库连接验证:        1.45秒                           ║
║  数据库表初始化:        2.31秒                           ║
║  连接池预热:            1.76秒                           ║
╠══════════════════════════════════════════════════════════╣
║  总启动时间:            5.64秒                           ║
║  已注册路由:              85个                           ║
╚══════════════════════════════════════════════════════════╝
```

---

## 🌐 访问系统

### 后端服务

- **API文档**: http://localhost:8001/api/docs (Swagger UI)
- **健康检查**: http://localhost:8001/health
- **备用文档**: http://localhost:8001/api/redoc

### 前端界面

- **主界面**: http://localhost:5173
- **数据看板**: http://localhost:5173/#/dashboard
- **字段映射**: http://localhost:5173/#/field-mapping
- **数据采集**: http://localhost:5173/#/collection

---

## 🔧 配置说明

### 环境变量

创建 `.env` 文件：

```bash
# 数据库配置
DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:5432/xihong_erp
DATABASE_ECHO=false

# 连接池配置（v4.1.0优化）
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=70
DB_POOL_TIMEOUT=60
DB_POOL_RECYCLE=1800

# 服务配置
HOST=0.0.0.0
PORT=8001
DEBUG=false

# 安全配置
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-here
```

### 性能调优

根据并发需求调整连接池：

```bash
# 10-20并发用户（默认）
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=70

# 20-50并发用户
DB_POOL_SIZE=50
DB_MAX_OVERFLOW=100

# 50+并发用户
DB_POOL_SIZE=80
DB_MAX_OVERFLOW=150
```

---

## 🧪 性能测试

### 运行完整性能测试

```bash
cd backend
python tests/test_performance.py
```

**测试场景**:
1. ✅ 健康检查响应时间（目标: <500ms）
2. ✅ 并发20个请求（目标: <5秒）
3. ✅ Dashboard查询（目标: <3秒）
4. ✅ 连接池100个请求（目标: <10秒）

**预期结果**:
```
📊 总计: 4/4 测试通过 (100%)
```

---

## 📚 功能使用指南

### 1. 数据看板

访问 http://localhost:5173/#/dashboard

**功能**:
- GMV、订单量、利润等核心指标
- 销售趋势图表
- 平台占比分析
- 实时数据更新

**性能**: <3秒加载

### 2. 字段映射

访问 http://localhost:5173/#/field-mapping

**功能**:
- 扫描采集文件（120秒超时）
- 预览Excel数据（60秒超时）
- 智能字段映射
- 数据验证和入库（180秒超时）

**优化**: 大文件支持，不再timeout

### 3. 数据采集

访问 http://localhost:5173/#/collection

**功能**:
- 多平台数据采集（Shopee/TikTok/Amazon/妙手ERP）
- 实时采集状态监控
- 历史记录管理

**性能**: 300秒超时，支持长时间采集

---

## 🐛 故障排除

### 问题1: 启动超时

**症状**: 启动超过15秒  
**排查**:
```bash
# 1. 检查PostgreSQL服务
services.msc  # Windows
systemctl status postgresql  # Linux

# 2. 检查数据库连接
psql -U erp_user -d xihong_erp -h localhost

# 3. 查看启动日志
tail -f logs/backend.log
```

### 问题2: API超时

**症状**: 前端请求超时  
**排查**:
```bash
# 1. 检查健康状态
curl http://localhost:8001/health

# 2. 查看连接池状态
# health响应中的pool字段：
# {
#   "pool": {
#     "size": 30,
#     "checked_out": 25  # 如果接近30，说明连接池不足
#   }
# }

# 3. 增加连接池大小
# 修改.env: DB_POOL_SIZE=50
```

### 问题3: 功能不可用

**症状**: 某些页面或功能报错  
**排查**:
```bash
# 1. 验证所有路由已恢复
python backend/verify_optimization.py

# 2. 检查API文档
# 访问 http://localhost:8001/api/docs
# 确认所有12个标签都存在

# 3. 清除浏览器缓存
# Ctrl+Shift+Delete（Chrome）
```

---

## 📖 相关文档

- **[完整优化报告](BACKEND_OPTIMIZATION_v4.1.0.md)** - 技术实施细节
- **[性能测试指南](../backend/tests/test_performance.py)** - 性能验证方法
- **[API文档](http://localhost:8001/api/docs)** - 完整API参考
- **[开发规范](.cursorrules)** - 代码规范和架构标准

---

## 💡 提示和技巧

### 快速重启

```bash
# 后端修改后快速重启（支持热重载）
# FastAPI会自动检测文件变化并重载

# 前端修改后自动更新（Vite热重载）
# 保存文件后浏览器自动刷新
```

### 监控系统状态

```bash
# 实时查看健康状态
watch -n 1 'curl -s http://localhost:8001/health | jq'

# 监控日志
tail -f logs/backend.log
```

### 性能优化建议

1. **生产环境**: 关闭DEBUG模式
   ```bash
   DEBUG=false
   DATABASE_ECHO=false
   ```

2. **大数据量**: 启用Redis缓存
   ```bash
   REDIS_URL=redis://localhost:6379/0
   ```

3. **高并发**: 增加连接池
   ```bash
   DB_POOL_SIZE=80
   DB_MAX_OVERFLOW=150
   ```

---

**版本**: v4.1.0  
**更新日期**: 2025-10-25  
**维护者**: 西虹ERP开发团队

✅ **开始使用吧！**

