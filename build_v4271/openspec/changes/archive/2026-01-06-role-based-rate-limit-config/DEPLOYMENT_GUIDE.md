# 限流配置系统部署指南

**创建日期**: 2026-01-05  
**版本**: v4.19.4  
**状态**: ✅ 已完成

## 概述

本文档说明如何部署和初始化基于角色的限流配置系统（Phase 3）。

## 部署步骤

### 1. 运行数据库迁移

创建限流配置表和审计表：

```bash
# 方法1：使用 alembic 命令
alembic upgrade head

# 方法2：使用 Python 模块
python -m alembic upgrade head
```

**迁移脚本**: `migrations/versions/20260105_v4_19_4_add_rate_limit_config_tables.py`

**创建的表**:
- `dim_rate_limit_config` - 限流配置维度表
- `fact_rate_limit_config_audit` - 限流配置审计日志表

### 2. 初始化配置数据（可选）

将默认限流配置写入数据库：

```bash
python scripts/init_rate_limit_config.py
```

**说明**:
- 如果数据库中已有配置，脚本会跳过初始化
- 默认配置来自 `backend/middleware/rate_limiter.py` 中的 `RATE_LIMIT_TIERS`
- 初始化后，系统会优先使用数据库配置，如果数据库没有配置则使用默认配置

### 3. 验证部署

运行测试脚本验证配置管理功能：

```bash
python scripts/test_rate_limit_config_api.py
```

**测试内容**:
- 查询配置列表
- 查询指定角色的配置
- 创建配置
- 更新配置
- 删除配置
- 验证审计日志

### 4. 重启应用

重启 FastAPI 应用以加载新的路由和功能：

```bash
# 如果使用 run.py
python run.py

# 如果使用 uvicorn
uvicorn backend.main:app --reload
```

## API 使用说明

### 查询配置列表

```bash
GET /api/rate-limit/config/roles?role_code=admin&endpoint_type=default&is_active=true
```

**权限**: 仅管理员

**响应示例**:
```json
{
  "total": 18,
  "configs": [
    {
      "config_id": 1,
      "role_code": "admin",
      "endpoint_type": "default",
      "limit_value": "200/minute",
      "is_active": true,
      "description": "admin 角色的 default 端点默认限流配置",
      "created_by": "system",
      "created_at": "2026-01-05T10:00:00",
      "updated_at": "2026-01-05T10:00:00",
      "updated_by": null
    }
  ]
}
```

### 查询指定角色的配置

```bash
GET /api/rate-limit/config/roles/admin
```

**权限**: 仅管理员

### 创建配置

```bash
POST /api/rate-limit/config/roles
Content-Type: application/json

{
  "role_code": "admin",
  "endpoint_type": "default",
  "limit_value": "200/minute",
  "description": "管理员默认限流",
  "is_active": true
}
```

**权限**: 仅管理员

### 更新配置

```bash
PUT /api/rate-limit/config/roles/admin/default
Content-Type: application/json

{
  "limit_value": "250/minute",
  "is_active": true,
  "description": "更新后的管理员限流"
}
```

**权限**: 仅管理员

**注意**: 配置更新后会自动刷新缓存

### 删除配置

```bash
DELETE /api/rate-limit/config/roles/admin/default
```

**权限**: 仅管理员

**注意**: 删除配置后，系统会使用默认配置（`RATE_LIMIT_TIERS`）

### 刷新缓存

```bash
POST /api/rate-limit/config/refresh-cache
```

**权限**: 仅管理员

**说明**: 手动刷新配置缓存（配置更新后会自动刷新）

## 配置优先级

系统按以下优先级使用限流配置：

1. **数据库配置**（如果存在且启用）
   - 从 `dim_rate_limit_config` 表读取
   - 缓存5分钟（TTL）
   - 配置更新后立即刷新缓存

2. **默认配置**（降级方案）
   - 从 `backend/middleware/rate_limiter.py` 中的 `RATE_LIMIT_TIERS` 读取
   - 如果数据库没有配置或配置被禁用，使用默认配置

## 审计日志

所有配置变更都会记录到 `fact_rate_limit_config_audit` 表：

- **操作类型**: create/update/delete
- **操作人**: 操作人ID和用户名
- **变更详情**: 变更前后的值
- **IP和设备**: IP地址和User-Agent
- **时间戳**: 操作时间

**查询审计日志**:
```sql
SELECT * FROM fact_rate_limit_config_audit 
WHERE role_code = 'admin' 
ORDER BY created_at DESC 
LIMIT 10;
```

## 故障排查

### 问题1: 迁移失败

**症状**: `alembic upgrade head` 失败

**解决方案**:
1. 检查数据库连接配置
2. 检查迁移脚本语法
3. 查看错误日志

### 问题2: 配置不生效

**症状**: 更新配置后限流值没有变化

**解决方案**:
1. 检查配置是否启用（`is_active = true`）
2. 手动刷新缓存：`POST /api/rate-limit/config/refresh-cache`
3. 检查数据库配置是否正确

### 问题3: API 返回 403

**症状**: 访问配置管理 API 返回 403 Forbidden

**解决方案**:
1. 确认用户具有管理员权限
2. 检查 JWT Token 是否有效
3. 确认用户角色为 `admin` 或 `is_superuser = true`

## 相关文档

- [配额设计文档](QUOTA_DESIGN.md) - 配额设计原则和配置说明
- [提案文档](proposal.md) - 完整提案说明
- [任务清单](tasks.md) - 实施任务清单
- [漏洞修复报告](VULNERABILITY_FIXES.md) - 漏洞修复详情

## 支持

如有问题，请查看：
- 日志文件：`logs/`
- 数据库表：`dim_rate_limit_config` 和 `fact_rate_limit_config_audit`
- API 文档：`http://localhost:8001/docs`

