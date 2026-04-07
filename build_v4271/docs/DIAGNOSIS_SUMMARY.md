# 后端连接诊断总结

## 问题诊断和修复记录

### 1. 前端API配置问题 ✅ 已修复
**问题**：前端硬编码了 `http://localhost:8001/api`，在Docker模式下无法连接后端

**修复**：
- 修改 `frontend/src/api/index.js`，使用相对路径 `/api` 或环境变量 `VITE_API_BASE_URL`
- Vite代理配置正常（`frontend/vite.config.js` 已配置代理到 `http://localhost:8001`）

### 2. 数据库表未创建问题 ⚠️ 部分解决
**问题**：登录端点返回500错误，原因是 `dim_users` 表不存在

**状态**：
- 数据库用户 `erp_dev` 和数据库 `xihong_erp_dev` 已创建 ✅
- 数据库表创建遇到索引冲突问题 ⚠️
- 需要手动清理残留索引后重新创建表

**解决方案**：
```bash
# 1. 清理残留索引
docker exec xihong_erp_postgres psql -U erp_dev -d xihong_erp_dev -c "DROP INDEX IF EXISTS ix_sales_campaigns_status, ix_sales_campaigns_type, ix_sales_campaigns_dates CASCADE;"

# 2. 重新创建表
docker exec xihong_erp_backend_dev python /tmp/init_tables.py

# 3. 或使用init_db函数（在容器中）
docker exec xihong_erp_backend_dev python -c "from backend.models.database import init_db; init_db()"
```

### 3. 后端服务状态 ✅ 正常
- 容器状态：healthy ✅
- 健康检查端点：正常 ✅
- 数据库连接：正常 ✅
- 环境变量配置：正确 ✅

### 4. 前端配置状态 ✅ 已修复
- API baseURL：已改为相对路径 `/api` ✅
- Vite代理：已配置 ✅

## 下一步操作

1. **清理残留索引并重新创建表**
2. **验证登录功能**：创建测试用户后测试登录
3. **测试前端连接**：确认前端可以正常访问后端API

## 诊断脚本

已创建诊断脚本：`scripts/diagnose_backend_connection.py`

使用方法：
```bash
python scripts/diagnose_backend_connection.py
```

