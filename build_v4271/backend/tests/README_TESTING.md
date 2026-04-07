# 用户注册和审批流程 - 测试指南

**创建日期**: 2026-01-05  
**测试范围**: Phase 1-7 所有功能

## 快速开始

### 1. 启动后端服务

```bash
# 方式1: 使用run.py
python run.py

# 方式2: 使用uvicorn
uvicorn backend.main:app --reload --port 8001
```

### 2. 运行测试

```bash
# 运行所有测试
python backend/tests/run_all_registration_tests.py

# 或运行单个测试
python backend/tests/test_user_registration_security.py
python backend/tests/test_user_registration_unit.py
python backend/tests/test_user_registration_integration.py
```

## 测试文件说明

### 1. 安全测试 (`test_user_registration_security.py`)

测试安全相关功能：
- ✅ 用户名/邮箱枚举攻击防护
- ✅ 权限绕过防护
- ✅ 状态一致性
- ✅ Open Redirect防护
- ✅ CSRF保护
- ⚠️ 注册API限流（需要后端服务运行）

### 2. 单元测试 (`test_user_registration_unit.py`)

测试单个API功能：
- ✅ 用户注册（正常流程、重复检查、密码强度）
- ✅ 用户审批（批准、拒绝）
- ✅ 用户登录（状态检查、账户锁定）

### 3. 集成测试 (`test_user_registration_integration.py`)

测试完整业务流程：
- ✅ 注册-审批-登录完整流程
- ✅ 管理员审批工作流
- ✅ 密码重置和账户解锁流程
- ✅ 会话管理流程

## 测试结果解读

### 通过率说明

- **92.3%** (安全测试): 12/13 通过
- **76.9%** (单元测试): 10/13 通过
- **44.4%** (集成测试): 4/9 通过

### 失败原因分析

大部分失败是因为：
1. **后端服务未运行**: 某些测试需要后端服务在 `http://localhost:8001` 运行
2. **API响应格式**: 部分API可能返回格式不一致
3. **数据库状态**: 某些测试依赖特定的数据库状态

### 建议

1. **启动后端服务后重新运行测试**
2. **检查API响应格式是否统一**
3. **确保测试数据库状态正确**

## 测试配置

### 测试环境变量

```bash
# 后端服务URL（默认: http://localhost:8001）
export TEST_BASE_URL=http://localhost:8001

# 管理员账号（默认: xihong / ~!Qq1`1`）
export TEST_ADMIN_USERNAME=xihong
export TEST_ADMIN_PASSWORD="~!Qq1`1`"
```

### 测试数据库

建议使用独立的测试数据库：
- 测试数据库: `xihong_erp_test`
- 避免污染生产数据
- 测试后自动清理

## 持续改进

### 待优化项

1. **使用pytest框架重构**
   - 更好的测试组织
   - 自动发现测试
   - 更好的断言

2. **添加测试数据库隔离**
   - 每个测试使用独立数据库
   - 测试后自动清理
   - 使用fixture管理测试数据

3. **添加性能测试**
   - 并发注册场景
   - 大量待审批用户场景
   - 会话管理性能

4. **添加E2E测试**
   - 使用Playwright测试前端
   - 完整的用户交互流程
   - 浏览器环境测试

## 故障排查

### 常见问题

1. **连接被拒绝**
   - 检查后端服务是否运行
   - 检查端口是否正确（默认8001）

2. **认证失败**
   - 检查管理员账号密码是否正确
   - 检查token是否有效

3. **数据库错误**
   - 检查数据库是否运行
   - 检查迁移是否已执行
   - 检查数据库连接配置

## 联系支持

如有问题，请查看：
- 测试总结: `backend/tests/TEST_SUMMARY.md`
- 测试日志: 查看控制台输出
- 后端日志: `backend/logs/backend_main.log`

