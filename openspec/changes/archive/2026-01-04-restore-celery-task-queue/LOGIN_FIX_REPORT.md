# 登录功能修复报告

**日期**: 2026-01-03  
**问题**: 登录端点返回 500 错误  
**状态**: ✅ 已修复

---

## 问题描述

在测试 Celery 任务状态管理 API 时，发现登录端点返回 500 内部服务器错误。

### 错误信息

```
状态码: 500
响应: {"success":false,"error":{"code":1002,"type":"SystemError",...},"message":"内部服务器错误"}
```

---

## 问题分析

### 根本原因

在异步 SQLAlchemy 中，直接访问关系属性（如 `user.roles`）会导致 `MissingGreenlet` 错误或请求超时。这是因为：

1. **异步关系加载**：在异步 SQLAlchemy 中，关系属性不会自动加载
2. **懒加载问题**：直接访问 `user.roles` 会触发懒加载，但在异步上下文中会失败
3. **超时问题**：如果关系加载失败，请求可能会超时

### 问题代码

```python
# ❌ 错误：直接访问关系属性
result = await db.execute(select(DimUser).where(DimUser.username == credentials.username))
user = result.scalar_one_or_none()
user_roles = [role.role_name for role in user.roles]  # 这里会失败
```

---

## 修复方案

### 使用 `selectinload` 预加载关系

在查询用户时，使用 `selectinload` 预加载 `roles` 关系：

```python
# ✅ 正确：使用 selectinload 预加载关系
from sqlalchemy.orm import selectinload

result = await db.execute(
    select(DimUser)
    .where(DimUser.username == credentials.username)
    .options(selectinload(DimUser.roles))
)
user = result.scalar_one_or_none()
user_roles = [role.role_name for role in user.roles]  # 现在可以正常访问
```

### 修复位置

1. **`login()` 函数**（`backend/routers/auth.py` 第 105-111 行）

   - 查询用户时预加载 `roles` 关系

2. **`get_current_user()` 函数**（`backend/routers/auth.py` 第 70-77 行）

   - 查询用户时预加载 `roles` 关系

3. **导入优化**
   - 将 `selectinload` 导入移到文件顶部（第 7 行）

---

## 修复验证

### 测试结果

✅ **登录功能测试通过**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900,
  "user_info": {
    "id": 2,
    "username": "admin",
    "email": "admin@test.com",
    "full_name": "测试管理员",
    "roles": []
  }
}
```

**响应时间**: 251.12ms  
**状态码**: 200 ✅

### 测试脚本

- `scripts/test_login_debug.py` - 登录调试测试脚本
- `scripts/test_celery_task_status.py` - Celery 任务状态管理 API 测试脚本

---

## 注意事项

### 用户角色为空

测试中发现用户 `admin` 的 `roles` 为空数组 `[]`。这可能是因为：

1. **用户未分配角色**：创建用户时可能没有成功分配角色
2. **角色不存在**：数据库中可能没有 `admin` 角色

**建议**：

- 检查数据库中是否存在 `DimRole` 记录
- 确保创建用户时正确分配角色
- 如果需要，可以手动为用户分配角色

### 测试文件 ID 问题

在测试 Celery 任务状态管理 API 时，任务提交失败是因为测试文件 ID 不存在：

```
状态码: 404
响应: {"success":false,"error":{"code":1301,"type":"SystemError","detail":"文件ID: 1","recovery_suggestion":"请检查文件ID是否正确"},"message":"文件不存在"}
```

**这是测试数据问题，不是代码问题**。在实际使用中，需要提供存在的文件 ID。

---

## 相关文件

- `backend/routers/auth.py` - 认证路由（已修复）
- `scripts/test_login_debug.py` - 登录调试测试脚本
- `scripts/test_celery_task_status.py` - Celery 任务状态管理 API 测试脚本
- `scripts/create_test_user.py` - 创建测试用户脚本

---

## 总结

✅ **问题已解决**

1. ✅ 修复了异步关系加载问题
2. ✅ 登录功能正常工作
3. ✅ 响应时间正常（251ms）
4. ✅ 代码通过 lint 检查

**下一步**：

- 检查并修复用户角色分配问题
- 更新测试脚本使用存在的文件 ID
- 继续完成 Celery 任务状态管理 API 的完整测试
