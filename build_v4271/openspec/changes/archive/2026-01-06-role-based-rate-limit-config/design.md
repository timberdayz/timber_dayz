# 角色权限限流配置设计文档

## 1. 角色系统分析

### 1.1 系统角色定义

| 角色代码 | 角色名称 | 职责           | 典型使用场景                 |
| -------- | -------- | -------------- | ---------------------------- |
| admin    | 管理员   | 系统管理、配置 | 系统配置、用户管理、数据管理 |
| manager  | 主管     | 审批、查看     | 审批流程、数据查看、报表分析 |
| operator | 操作员   | 日常操作       | 数据录入、订单处理、库存管理 |
| finance  | 财务     | 财务分析       | 财务报表、数据分析、账务处理 |

### 1.2 角色权限映射

当前系统使用 `DimRole` 表存储角色信息：

- `role_code`: 角色代码（admin, manager, operator, finance）
- `role_name`: 角色名称（管理员, 主管, 操作员, 财务）
- `permissions`: 权限列表（JSON 格式）

## 2. 限流配额设计

### 2.1 配额分配原则

1. **职责导向**：根据角色职责分配配额
2. **安全优先**：认证接口限流更严格
3. **业务平衡**：数据同步配额适中，避免滥用
4. **可扩展性**：预留配置扩展空间

### 2.2 配额配置表

```python
RATE_LIMIT_TIERS = {
    "admin": {
        "default": "200/minute",
        "data_sync": "100/minute",
        "auth": "20/minute",
    },
    "manager": {
        "default": "150/minute",
        "data_sync": "80/minute",
        "auth": "15/minute",
    },
    "finance": {
        "default": "120/minute",
        "data_sync": "30/minute",
        "auth": "10/minute",
    },
    "operator": {
        "default": "100/minute",
        "data_sync": "50/minute",
        "auth": "10/minute",
    },
    "normal": {
        "default": "60/minute",
        "data_sync": "30/minute",
        "auth": "5/minute",
    },
    "anonymous": {
        "default": "30/minute",
        "data_sync": "10/minute",
        "auth": "3/minute",
    }
}
```

## 3. 角色映射逻辑设计

### 3.1 映射优先级

1. 检查 `role_code`（优先级最高）
2. 检查 `role_name`（降级方案）
3. 检查用户名（特殊处理，如 admin 用户）
4. 默认 `normal`（未匹配到角色）

### 3.2 实现逻辑

```python
def get_user_rate_limit_tier(user) -> str:
    """
    获取用户的限流等级

    角色映射优先级：
    1. role_code (admin, manager, operator, finance)
    2. role_name (管理员, 主管, 操作员, 财务)
    3. username (admin 用户特殊处理)
    4. normal (默认)
    """
    if not user:
        return "anonymous"

    # 检查用户角色
    roles = getattr(user, "roles", [])
    if roles:
        role_names = []
        role_codes = []
        for role in roles:
            if hasattr(role, "role_code"):
                role_codes.append(role.role_code.lower())
            if hasattr(role, "role_name"):
                role_names.append(role.role_name.lower())
            elif hasattr(role, "name"):
                role_names.append(role.name.lower())
            elif isinstance(role, str):
                role_names.append(role.lower())

        # 优先级：admin > manager > finance > operator
        if "admin" in role_codes or "admin" in role_names or "administrator" in role_names:
            return "admin"
        if "manager" in role_codes or "manager" in role_names or "supervisor" in role_names or "主管" in role_names:
            return "manager"
        if "finance" in role_codes or "finance" in role_names or "财务" in role_names:
            return "finance"
        if "operator" in role_codes or "operator" in role_names or "操作员" in role_names:
            return "operator"

    # 回退机制：检查用户名
    username = getattr(user, "username", None)
    if username and username.lower() == "admin":
        return "admin"

    return "normal"
```

## 4. 测试验证

### 4.1 测试场景

1. **角色映射测试**：验证各角色正确映射到限流等级
2. **配额验证测试**：验证各角色使用正确的限流配额
3. **降级测试**：验证未匹配到角色的用户使用 normal 配额
4. **匿名用户测试**：验证未认证用户使用 anonymous 配额

### 4.2 测试脚本

创建 `scripts/test_role_based_rate_limit.py` 测试脚本。

## 5. 后续扩展

### 5.1 数据库配置（Phase 3）

设计 `dim_rate_limit_config` 表：

```sql
CREATE TABLE dim_rate_limit_config (
    config_id BIGSERIAL PRIMARY KEY,
    role_code VARCHAR(50) NOT NULL,
    endpoint_type VARCHAR(50) NOT NULL,  -- default, data_sync, auth
    limit_value VARCHAR(50) NOT NULL,    -- "200/minute"
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 5.2 配置管理 API（Phase 3）

- `GET /api/rate-limit/config/roles` - 获取所有角色的限流配置
- `PUT /api/rate-limit/config/roles/{role_code}` - 更新角色限流配置
- `POST /api/rate-limit/config/roles/{role_code}/test` - 测试限流配置
