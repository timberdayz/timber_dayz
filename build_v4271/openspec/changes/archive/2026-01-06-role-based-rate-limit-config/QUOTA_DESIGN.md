# 限流配额设计文档

**创建日期**: 2026-01-05  
**版本**: v4.19.4  
**状态**: ✅ 已实施

## 概述

本文档详细说明了基于角色的限流配额设计原则、配置方案和使用指南。

## 配额配置

### 当前配额表

| 角色      | 默认限流 | 数据同步限流 | 认证限流 | 说明                 |
| --------- | -------- | ------------ | -------- | -------------------- |
| admin     | 200/分钟 | 100/分钟     | 20/分钟  | 系统管理，最高配额   |
| manager   | 150/分钟 | 80/分钟      | 15/分钟  | 审批、查看，较高配额 |
| finance   | 120/分钟 | 30/分钟      | 10/分钟  | 报表查询，中等配额   |
| operator  | 100/分钟 | 50/分钟      | 10/分钟  | 日常操作，标准配额   |
| normal    | 60/分钟  | 30/分钟      | 5/分钟   | 降级方案             |
| anonymous | 30/分钟  | 10/分钟      | 3/分钟   | 未认证用户           |

### 配置位置

配额配置在 `backend/middleware/rate_limiter.py` 中的 `RATE_LIMIT_TIERS` 字典：

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
    # ... 其他角色
}
```

## 设计原则

### 1. 职责导向

根据角色的业务职责分配配额：

- **admin（管理员）**：需要系统管理、配置调整等操作，配额最高
- **manager（主管）**：需要审批、查看报表等操作，配额较高
- **finance（财务）**：需要查询大量报表数据，配额中等
- **operator（操作员）**：日常操作，标准配额
- **normal（普通用户）**：降级方案，基础配额
- **anonymous（匿名用户）**：未认证用户，最低配额

### 2. 安全优先

认证接口限流更严格，防止暴力破解：

- admin: 20/分钟
- manager: 15/分钟
- finance/operator: 10/分钟
- normal: 5/分钟
- anonymous: 3/分钟

### 3. 业务平衡

数据同步配额适中，避免滥用但保证正常使用：

- admin: 100/分钟（系统管理需要）
- manager: 80/分钟（审批需要）
- finance: 30/分钟（报表查询需要）
- operator: 50/分钟（日常操作需要）
- normal: 30/分钟
- anonymous: 10/分钟

### 4. 可扩展性

- 预留配置扩展空间（支持未来添加新角色）
- 支持端点类型扩展（default/data_sync/auth）
- 支持未来数据库配置（Phase 3）

## 端点类型说明

### default（默认端点）

适用于大多数业务 API，如：
- 用户管理 API
- 账号管理 API
- 通知管理 API
- WebSocket 统计 API

### data_sync（数据同步端点）

适用于数据同步相关 API，如：
- 单文件同步
- 批量同步
- 全量同步

**特点**：配额通常低于 default，因为数据同步操作资源消耗较大。

### auth（认证端点）

适用于认证相关 API，如：
- 用户注册
- 用户登录
- Token 刷新

**特点**：配额最严格，防止暴力破解和滥用。

## 角色映射逻辑

### 优先级顺序

1. **role_code**（优先级最高）
   - admin, manager, finance, operator

2. **role_name**（降级方案）
   - 管理员, 主管, 财务, 操作员
   - Administrator, Manager, Finance, Operator

3. **is_superuser**（特殊处理）
   - 如果用户设置了 `is_superuser=True`，自动映射为 admin

4. **username**（最后回退）
   - 如果用户名为 "admin"，映射为 admin

5. **normal**（默认）
   - 其他情况映射为 normal

### 多角色处理

如果用户拥有多个角色，使用最高优先级角色：

```
优先级：admin > manager > finance > operator > normal
```

例如：
- 用户同时拥有 manager 和 operator 角色 → 使用 manager 配额
- 用户同时拥有 finance 和 operator 角色 → 使用 finance 配额

## 使用指南

### 在 API 端点中应用限流

```python
from backend.middleware.rate_limiter import role_based_rate_limit

# 默认端点
@router.get("/api/users")
@role_based_rate_limit(endpoint_type="default")
async def get_users(current_user = Depends(get_current_user), request: Request):
    ...

# 数据同步端点
@router.post("/api/data-sync/single")
@role_based_rate_limit(endpoint_type="data_sync")
async def sync_single_file(current_user = Depends(get_current_user), request: Request):
    ...

# 认证端点
@router.post("/api/auth/register")
@role_based_rate_limit(endpoint_type="auth")
async def register(request: Request):
    ...
```

### 注意事项

1. **必须提供 Request 参数**：装饰器需要从 Request 对象中获取用户信息
2. **降级机制**：如果限流器未启用，装饰器会直接返回原函数
3. **匿名用户**：如果用户未认证，会使用 anonymous 角色的配额

## 配额调整建议

### 调整时机

1. **生产环境数据收集**：运行 1-2 周后，收集实际使用数据
2. **监控限流触发频率**：如果某个角色频繁触发限流，考虑提高配额
3. **业务需求变化**：如果业务需求变化，相应调整配额

### 调整方法

1. **临时调整**：直接修改 `RATE_LIMIT_TIERS` 字典
2. **永久调整**：修改代码并重新部署
3. **未来支持**：Phase 3 将支持数据库配置，无需重新部署

### 调整原则

1. **渐进式调整**：每次调整不超过 20%
2. **监控影响**：调整后监控限流触发频率和系统负载
3. **文档更新**：调整后更新本文档

## 监控和统计

### 限流统计 API

使用 `/api/rate-limit/stats` API 查看限流统计：

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/rate-limit/stats
```

### 当前用户限流信息

使用 `/api/rate-limit/my-info` API 查看当前用户的限流信息：

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8001/api/rate-limit/my-info
```

### 监控指标

建议监控以下指标：

1. **限流触发频率**：各角色的限流触发次数
2. **配额使用率**：各角色的配额使用百分比
3. **异常模式**：单个用户/IP 频繁触发限流

## 测试验证

### 集成测试

运行集成测试验证配额配置：

```bash
python scripts/test_role_based_rate_limit_integration.py
```

### 测试覆盖

- ✅ 角色映射测试（9个测试用例）
- ✅ 配额配置测试（9个测试用例）
- ✅ 多角色优先级测试（3个测试用例）
- ✅ 边界情况测试（4个测试用例）
- ✅ 配置完整性测试（18个测试用例）

**总计**：43个测试用例，全部通过

## 未来优化

### Phase 2: 配额策略优化

- [ ] 根据生产环境实际使用情况调整配额
- [ ] 验证配额合理性（通过监控和统计）
- [ ] 优化配额分配策略

### Phase 3: 数据库配置支持（可选）

- [ ] 设计限流配置表结构
- [ ] 实现从数据库读取配置
- [ ] 创建配置管理 API
- [ ] 支持运行时动态调整

## 相关文档

- [提案文档](proposal.md) - 完整提案说明
- [任务清单](tasks.md) - 实施任务清单
- [漏洞修复报告](VULNERABILITY_FIXES.md) - 漏洞修复详情
- [漏洞审查报告](VULNERABILITY_REVIEW_2026-01-05.md) - 最新审查报告

