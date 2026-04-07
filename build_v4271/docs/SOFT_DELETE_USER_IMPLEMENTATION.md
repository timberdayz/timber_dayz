# 用户软删除功能实现说明

**版本**: v4.19.8  
**日期**: 2026-01-08  
**状态**: ✅ 已完成

## 概述

按照业界标准实现了用户软删除功能，替代原有的硬删除方式。软删除可以保留数据用于审计和合规，同时支持用户恢复。

## 实现的功能

### 1. 软删除用户 (`DELETE /users/{user_id}`)

**流程**：
1. ✅ 验证用户存在且未删除
2. ✅ 撤销所有活跃会话（安全要求）
3. ✅ 软删除用户（`status="deleted"`, `is_active=False`）
4. ✅ 记录删除操作（审计日志）
5. ✅ 保留数据用于合规和追溯

**特性**：
- 不能删除自己
- 不能重复删除已删除的用户
- 自动撤销所有活跃会话
- 完整的异常处理和错误提示
- 支持删除原因记录（可选参数 `reason`）

### 2. 恢复用户 (`POST /users/{user_id}/restore`)

**功能**：
- 恢复已删除的用户
- 将 `status` 设置为 `"active"`
- 将 `is_active` 设置为 `True`
- 记录恢复操作到审计日志

### 3. 查询过滤

**修改的API**：
- `GET /users` - 用户列表：自动过滤已删除用户
- `GET /users/{user_id}` - 用户详情：允许查看已删除用户（管理员可能需要查看）

### 4. 登录保护

**修改**：
- `POST /auth/login` - 登录接口：已删除用户无法登录
- `get_current_user` - Token验证：已删除用户无法使用现有Token访问系统

## 代码修改

### 修改的文件

1. **backend/routers/users.py**
   - 修改 `delete_user` 函数：实现软删除
   - 修改 `get_users` 函数：过滤已删除用户
   - 新增 `restore_user` 函数：恢复已删除用户
   - 添加必要的导入：`update`, `Optional`, `get_logger`

2. **backend/routers/auth.py**
   - 修改 `login` 函数：检查 `status == "deleted"`
   - 确保已删除用户无法登录

## 数据库设计

### 用户状态字段

```python
status = Column(
    String(20),
    default="pending",
    nullable=False,
    index=True,
    comment="用户状态: pending/active/rejected/suspended/deleted"
)
```

### 状态值说明

| 状态 | 说明 | is_active | 可登录 |
|------|------|-----------|--------|
| `pending` | 待审批（新注册） | `false` | ❌ |
| `active` | 已启用 | `true` | ✅ |
| `rejected` | 已拒绝 | `false` | ❌ |
| `suspended` | 已暂停（管理员手动） | `false` | ❌ |
| `deleted` | 已删除（软删除） | `false` | ❌ |

## API 使用示例

### 删除用户

```bash
# 删除用户（带原因）
DELETE /api/users/123
Content-Type: application/json

{
  "reason": "用户主动申请删除"
}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "user_id": 123
  },
  "message": "用户已删除（软删除，数据已保留用于审计）"
}
```

### 恢复用户

```bash
POST /api/users/123/restore
```

**响应**：
```json
{
  "success": true,
  "data": {
    "user_id": 123
  },
  "message": "用户已恢复"
}
```

## 安全特性

1. **会话撤销**：删除用户时自动撤销所有活跃会话
2. **登录保护**：已删除用户无法登录
3. **Token验证**：已删除用户无法使用现有Token
4. **审计日志**：所有删除和恢复操作都记录到审计日志

## 业界标准对比

| 特性 | 本实现 | GitHub | AWS | Salesforce |
|------|--------|--------|-----|------------|
| 软删除 | ✅ | ✅ | ✅ | ✅ |
| 会话撤销 | ✅ | ✅ | ✅ | ✅ |
| 恢复功能 | ✅ | ✅ (90天) | ✅ (30天) | ✅ (15天) |
| 审计日志 | ✅ | ✅ | ✅ | ✅ |
| 数据保留 | ✅ | ✅ | ✅ | ✅ |

## 后续优化建议

### 可选功能

1. **删除时间字段**：
   - 添加 `deleted_at` 字段记录删除时间
   - 添加 `deleted_by` 字段记录删除人

2. **恢复期限**：
   - 实现30天恢复期限
   - 超过期限需要特殊权限

3. **数据匿名化**：
   - 实现GDPR合规的数据匿名化
   - 匿名化邮箱、姓名等敏感信息

4. **延迟硬删除**：
   - 实现定时任务，30-90天后自动硬删除
   - 硬删除前再次确认

### 数据库迁移（可选）

如果需要添加 `deleted_at` 和 `deleted_by` 字段：

```python
# migrations/versions/xxxx_add_user_deletion_fields.py
def upgrade():
    op.add_column('dim_users', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column('dim_users', sa.Column('deleted_by', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_users_deleted_by', 'dim_users', 'dim_users', ['deleted_by'], ['user_id'], ondelete='SET NULL')
```

## 测试建议

1. **删除测试**：
   - 删除普通用户
   - 删除有活跃会话的用户
   - 尝试删除自己（应失败）
   - 尝试重复删除（应失败）

2. **恢复测试**：
   - 恢复已删除用户
   - 尝试恢复未删除用户（应失败）

3. **登录测试**：
   - 已删除用户尝试登录（应失败）
   - 已删除用户使用现有Token（应失败）

4. **查询测试**：
   - 用户列表不显示已删除用户
   - 用户详情可以查看已删除用户

## 相关文档

- [用户管理API文档](../API_CONTRACT.md)
- [用户状态设计](../openspec/changes/archive/2026-01-05-add-user-registration-approval/proposal.md)
- [审计日志规范](../DEVELOPMENT_RULES/ERROR_HANDLING_AND_LOGGING.md)

---

**实现完成时间**: 2026-01-08  
**测试状态**: 待测试  
**生产部署**: 待部署
