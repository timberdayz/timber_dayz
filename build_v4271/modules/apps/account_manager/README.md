# 📋 账号管理模块

## 📖 模块简介

账号管理模块是跨境电商ERP系统的核心组件之一，提供多平台电商账号的统一管理、验证和监控功能。

## ✨ 功能特性

### 🔐 账号管理
- ✅ **多平台支持**: 支持Amazon、eBay、Shopee、Lazada等主流电商平台
- ✅ **统一管理**: 集中管理所有平台账号信息
- ✅ **安全存储**: 敏感信息加密存储，支持备份机制
- ✅ **批量操作**: 支持账号的批量导入、导出和编辑

### 🛡️ 安全验证
- ✅ **实时验证**: 定期检查账号状态和有效性
- ✅ **风险监控**: 识别异常登录和风险操作
- ✅ **权限控制**: 基于角色的账号访问权限管理
- ✅ **审计日志**: 完整的账号操作记录和追踪

### 📊 统计分析
- ✅ **状态统计**: 账号健康度、活跃度统计
- ✅ **平台分布**: 各平台账号数量和状态分布
- ✅ **趋势分析**: 账号状态变化趋势图表
- ✅ **异常预警**: 智能识别潜在风险账号

## 🚀 快速开始

### 安装要求
```bash
# 核心依赖
pip install cryptography
pip install pydantic
pip install loguru
```

### 基本使用
```python
from modules.apps.account_manager.app import AccountManagerApp

# 初始化应用
app = AccountManagerApp()

# 运行应用
app.run()
```

## 📋 功能菜单

### 主要功能
1. **📝 查看所有账号** - 显示所有已配置的账号列表
2. **➕ 添加新账号** - 添加新的电商平台账号
3. **✏️ 编辑账号** - 修改现有账号信息
4. **🗑️ 删除账号** - 安全删除不需要的账号
5. **✅ 验证账号状态** - 检查账号的可用性和健康状态
6. **📊 账号统计** - 查看账号统计信息和分析报告
7. **🔄 同步账号配置** - 同步和更新账号配置信息
8. **📁 导入账号** - 从文件批量导入账号信息
9. **📤 导出账号** - 导出账号配置到文件

### 管理功能
- **🔍 健康检查** - 系统健康状态检查
- **📈 性能监控** - 模块性能指标监控
- **🔧 配置管理** - 模块配置参数管理

## 🏗️ 架构设计

### 核心组件
```
account_manager/
├── app.py              # 主应用入口
├── handlers.py         # 业务逻辑处理
├── validators.py       # 数据验证器
└── README.md          # 模块文档
```

### 类图关系
```
AccountManagerApp (继承 BaseApplication)
    ├── AccountHandler (业务处理)
    ├── AccountValidator (数据验证)
    └── ConfigManager (配置管理)
```

## 📊 数据模型

### 账号数据结构
```json
{
  "platform": "amazon",
  "username": "seller@example.com",
  "password": "encrypted_password",
  "login_url": "https://sellercentral.amazon.com",
  "status": "active",
  "created_at": "2025-01-01T00:00:00Z",
  "last_verified": "2025-01-15T12:00:00Z",
  "metadata": {
    "region": "US",
    "marketplace_id": "ATVPDKIKX0DER",
    "seller_id": "A1234567890123"
  }
}
```

### 状态定义
- `active`: 账号正常可用
- `error`: 账号异常或无法访问
- `pending`: 账号待验证
- `disabled`: 账号已禁用

## 🔧 配置说明

### 配置文件位置
- **主配置**: `local_accounts.json`
- **备份目录**: `temp/backups/`
- **日志文件**: `logs/account_manager.log`

### 配置示例
```json
{
  "accounts": [
    {
      "platform": "amazon",
      "username": "seller@example.com",
      "login_url": "https://sellercentral.amazon.com",
      "status": "active"
    }
  ],
  "settings": {
    "auto_verify": true,
    "verify_interval": 3600,
    "backup_enabled": true
  }
}
```

## 🧪 测试说明

### 单元测试
```bash
# 运行测试
python -m pytest modules/apps/account_manager/tests/

# 生成覆盖率报告
python -m pytest --cov=modules.apps.account_manager
```

### 功能测试
```python
# 测试账号添加
def test_add_account():
    handler = AccountHandler()
    result = handler.add_account({
        "platform": "test",
        "username": "test@example.com"
    })
    assert result == True
```

## 🔒 安全考虑

### 数据安全
- ✅ **密码加密**: 使用AES-256加密存储密码
- ✅ **访问控制**: 基于权限的数据访问控制
- ✅ **审计日志**: 完整的操作记录和追踪
- ✅ **备份机制**: 自动备份重要配置文件

### 网络安全
- ✅ **HTTPS通信**: 所有网络请求使用HTTPS
- ✅ **请求限制**: 防止暴力破解和频繁请求
- ✅ **异常检测**: 识别异常登录模式

## 📈 性能优化

### 缓存策略
- ✅ **配置缓存**: 配置文件内存缓存
- ✅ **状态缓存**: 账号状态定期缓存
- ✅ **智能更新**: 仅在必要时更新缓存

### 并发处理
- ✅ **异步验证**: 异步批量账号验证
- ✅ **连接池**: 复用网络连接提升性能
- ✅ **队列处理**: 大批量操作队列化处理

## 🚨 故障排除

### 常见问题

#### 1. 配置文件不存在
```
错误: 配置文件不存在: local_accounts.json
解决: 首次运行会自动创建，或手动创建空配置文件
```

#### 2. 账号验证失败
```
错误: 账号验证失败
解决: 检查账号信息、网络连接和平台状态
```

#### 3. 权限不足
```
错误: 权限不足，无法访问配置文件
解决: 检查文件权限，确保有读写权限
```

### 日志分析
```bash
# 查看错误日志
grep "ERROR" logs/account_manager.log

# 查看账号操作日志
grep "账号" logs/account_manager.log
```

## 🔄 版本历史

### v1.0.0 (2025-01-27)
- ✅ 初始版本发布
- ✅ 基础账号管理功能
- ✅ 配置文件管理
- ✅ 健康检查机制

### 🛣️ 后续规划
- 🔮 v1.1.0: 添加批量验证功能
- 🔮 v1.2.0: 集成API自动化验证
- 🔮 v1.3.0: 智能风险预警系统
- 🔮 v2.0.0: Web界面集成

## 🤝 贡献指南

### 开发流程
1. **Fork项目** - 创建项目分支
2. **开发功能** - 按照代码规范开发
3. **编写测试** - 确保测试覆盖率
4. **提交PR** - 详细描述改动内容

### 代码规范
- ✅ 遵循PEP 8代码风格
- ✅ 添加完整的类型注解
- ✅ 编写详细的文档字符串
- ✅ 包含完整的错误处理

## 📞 支持与联系

### 技术支持
- 📧 **邮件**: support@example.com
- 📝 **文档**: 查看完整的API文档
- 🐛 **Bug报告**: 通过GitHub Issues报告

### 相关资源
- 📚 [模块维护指南](../../MODULE_MAINTENANCE_GUIDE.md)
- 🏗️ [架构重构计划](../../ARCHITECTURE_REFACTORING_PLAN.md)
- 🎯 [项目开发规范](../../repo_specific_rule.md)

---

**📋 账号管理模块 - 让多平台账号管理变得简单高效！** 