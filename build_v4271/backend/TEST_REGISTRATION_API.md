# 用户注册和审批API测试指南

## 前置条件

1. 后端服务正在运行（默认端口：8000）
2. 数据库已连接并运行迁移
3. 至少有一个管理员用户（用于测试审批功能）

## 测试步骤

### 1. 测试用户注册API

**端点**: `POST /api/auth/register`

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_user_001",
    "email": "test_user_001@test.com",
    "password": "test123456",
    "full_name": "测试用户001",
    "phone": "13800138001",
    "department": "测试部门"
  }'
```

**预期响应**:
```json
{
  "success": true,
  "data": {
    "user_id": 1,
    "username": "test_user_001",
    "email": "test_user_001@test.com",
    "status": "pending",
    "message": "注册成功，请等待管理员审批"
  }
}
```

### 2. 测试Pending用户无法登录

**端点**: `POST /api/auth/login`

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_user_001",
    "password": "test123456"
  }'
```

**预期响应** (状态码: 403):
```json
{
  "success": false,
  "code": 4005,
  "message": "账号待审批，请联系管理员",
  "error_type": "UserError",
  "recovery_suggestion": "请等待管理员审批"
}
```

### 3. 获取待审批用户列表

**端点**: `GET /api/users/pending`

```bash
# 先获取管理员token
ADMIN_TOKEN="your_admin_token_here"

curl -X GET "http://localhost:8000/api/users/pending?page=1&page_size=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**预期响应**:
```json
[
  {
    "user_id": 1,
    "username": "test_user_001",
    "email": "test_user_001@test.com",
    "full_name": "测试用户001",
    "department": "测试部门",
    "created_at": "2026-01-04T10:00:00Z"
  }
]
```

### 4. 审批用户

**端点**: `POST /api/users/{user_id}/approve`

```bash
USER_ID=1  # 替换为实际用户ID

curl -X POST "http://localhost:8000/api/users/$USER_ID/approve" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "notes": "审批通过"
  }'
```

**预期响应**:
```json
{
  "success": true,
  "data": {
    "user_id": 1,
    "username": "test_user_001",
    "status": "active"
  },
  "message": "用户审批成功"
}
```

### 5. 拒绝用户（可选测试）

**端点**: `POST /api/users/{user_id}/reject`

```bash
USER_ID=1  # 替换为实际用户ID

curl -X POST "http://localhost:8000/api/users/$USER_ID/reject" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "不符合要求"
  }'
```

### 6. 测试审批后用户登录

审批后，用户应该可以正常登录：

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_user_001",
    "password": "test123456"
  }'
```

**预期响应** (状态码: 200):
```json
{
  "success": true,
  "data": {
    "access_token": "...",
    "refresh_token": "...",
    "token_type": "bearer",
    "expires_in": 1800,
    "user_info": {
      "id": 1,
      "username": "test_user_001",
      "email": "test_user_001@test.com",
      "full_name": "测试用户001",
      "roles": ["operator"]
    }
  }
}
```

## 使用Python脚本测试

也可以使用提供的Python测试脚本：

```bash
# 简化测试脚本（仅测试注册和登录）
python backend/test_registration_api_simple.py

# 完整测试脚本（需要管理员账号）
python backend/test_registration_api_manual.py
```

## 验证脚本

验证代码结构（不需要服务运行）：

```bash
python backend/verify_registration_api.py
```

## 测试检查清单

- [ ] 用户注册API正常工作
- [ ] Pending状态用户无法登录（返回403，错误码4005）
- [ ] 管理员可以查看待审批用户列表
- [ ] 管理员可以审批用户（状态变为active）
- [ ] 管理员可以拒绝用户（状态变为rejected）
- [ ] 审批后的用户可以正常登录
- [ ] 拒绝后的用户无法登录（返回403，错误码4006）
- [ ] 重复用户名/邮箱注册返回统一错误消息
- [ ] 注册API有速率限制（5次/分钟）

## 注意事项

1. 确保数据库迁移已运行（status字段等）
2. 确保operator角色存在（默认角色）
3. 测试前确保有管理员用户
4. 测试速率限制时注意不要超过5次/分钟

