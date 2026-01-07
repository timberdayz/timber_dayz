# 账号健康检测系统 - 使用指南

## 🎯 系统概述

账号健康检测系统是为跨境电商ERP系统设计的智能账号状态监控和异常处理机制，确保生产环境中只有健康的账号参与数据采集，提高系统稳定性和数据质量。

## 🔍 核心功能

### 1. 智能状态检测
- **多维度检测**：URL模式、页面内容、DOM元素综合分析
- **平台适配**：支持Shopee、Amazon、妙手ERP等多平台
- **实时监控**：登录后立即检测，采集前再次验证

### 2. 异常账号识别
- **权限不足**：检测"您没有权限查看这个页面"等提示
- **账号封禁**：识别账号被暂停或封禁状态
- **店铺不匹配**：发现账号与目标店铺不匹配
- **需要验证**：检测需要额外身份验证的情况

### 3. 自动处理机制
- **立即停止**：异常账号立即停止所有操作
- **资源释放**：关闭浏览器进程，释放系统资源
- **状态记录**：持久化存储异常账号信息
- **智能跳过**：后续操作自动跳过已知异常账号

## 📊 账号状态分类

| 状态 | 说明 | 处理策略 |
|------|------|----------|
| `HEALTHY` | 正常健康 | 继续数据采集 |
| `PERMISSION_DENIED` | 权限不足 | 停止操作，标记禁用 |
| `SHOP_MISMATCH` | 店铺不匹配 | 停止操作，标记禁用 |
| `ACCOUNT_SUSPENDED` | 账号被封 | 立即停止，永久禁用 |
| `ACCOUNT_LOCKED` | 账号锁定 | 立即停止，永久禁用 |
| `VERIFICATION_REQUIRED` | 需要验证 | 暂停操作，等待处理 |
| `UNKNOWN_ERROR` | 未知错误 | 暂停操作，人工检查 |

## 🚀 使用方法

### 1. 基础使用（录制向导中）

系统已自动集成到录制向导中，无需额外配置：

```python
# 自动集成在录制向导中
# 登录成功后自动进行健康检查
if self._check_if_already_in_backend(page):
    health_checker = AccountHealthChecker(platform)
    status, message, extra_data = health_checker.check_account_health(page, account)
    should_continue = health_checker.handle_unhealthy_account(status, message, account, page)
```

### 2. 在采集器中使用

```python
from modules.utils.collector_health_integration import quick_health_check

def collect_data(page, account, platform):
    # 采集前进行健康检查
    if not quick_health_check(page, account, platform, "商品数据采集"):
        logger.warning("账号健康检查失败，跳过采集")
        return False
    
    # 继续数据采集
    # ... 采集逻辑
```

### 3. 批量账号检查

```python
from modules.utils.collector_health_integration import create_health_integration

# 创建健康检查集成器
integration = create_health_integration("shopee")

# 批量检查账号
accounts = [...]  # 账号列表
results = integration.batch_check_accounts(accounts, "批量健康检查")

# 获取健康统计
stats = integration.get_health_statistics(days=7)
print(f"7天内健康率: {stats['health_rate']}%")
```

## 🔧 配置说明

### 1. 平台特定配置

系统支持多平台，每个平台有特定的检测规则：

#### Shopee平台
- **权限检测**：`"您访问的店铺不在当前账号下"`
- **正常标识**：`"我的商品"`, `"Product Settings"`, `"Mass Function"`
- **URL特征**：`seller.shopee.cn/portal`

#### Amazon平台
- **权限检测**：`"You don't have permission"`
- **正常标识**：`"Seller Central"`, `"Inventory"`
- **URL特征**：`sellercentral.amazon.com`

#### 妙手ERP平台
- **权限检测**：`"权限不足"`, `"无权访问"`
- **正常标识**：`"商品管理"`, `"订单管理"`

### 2. 数据存储

系统会在 `data/` 目录下创建以下文件：

- `account_health_logs.json` - 健康检查日志
- `disabled_accounts.json` - 禁用账号列表

## 📈 监控和统计

### 1. 实时监控

系统提供实时的账号状态监控：

```bash
🔍 开始健康检查 - 账号: shopee新加坡3C店, 操作: 数据采集
✅ 账号状态正常，可以进行数据采集
📊 健康率: 85.5% (最近7天)
```

### 2. 统计报告

```python
# 获取详细统计
stats = integration.get_health_statistics(days=30)
print(f"""
📊 30天健康统计报告
==================
总检查次数: {stats['total_checks']}
健康检查次数: {stats['healthy_checks']}
健康率: {stats['health_rate']}%
禁用账号数: {stats['disabled_accounts_count']}
""")
```

## ⚠️ 注意事项

### 1. 生产环境建议

- **定期检查**：建议每次采集前都进行健康检查
- **日志监控**：定期查看健康检查日志，及时发现问题
- **账号轮换**：对于频繁异常的账号，考虑更换或修复

### 2. 性能考虑

- **检查频率**：避免过于频繁的健康检查影响性能
- **超时设置**：合理设置检查超时时间
- **资源释放**：确保异常账号及时释放资源

### 3. 错误处理

- **网络异常**：检查过程中的网络问题会被记录但不影响其他账号
- **页面异常**：页面加载失败会标记为未知错误
- **配置错误**：账号配置错误会被记录并跳过

## 🔄 故障排除

### 1. 常见问题

**Q: 正常账号被误判为异常？**
A: 检查页面加载是否完整，可能需要增加等待时间

**Q: 异常账号没有被检测到？**
A: 检查平台特定的检测规则是否需要更新

**Q: 健康检查影响性能？**
A: 可以调整检查频率或优化检测逻辑

### 2. 调试方法

```python
# 启用详细日志
import logging
logging.getLogger('modules.utils.account_health_checker').setLevel(logging.DEBUG)

# 手动检查单个账号
checker = AccountHealthChecker("shopee")
status, message, data = checker.check_account_health(page, account)
print(f"状态: {status}, 信息: {message}")
```

## 📝 更新日志

- **v1.0.0** (2025-08-29)
  - 初始版本发布
  - 支持Shopee、Amazon、妙手ERP平台
  - 实现基础健康检查和异常处理
  - 集成到录制向导和采集器

## 🤝 贡献指南

如需添加新平台支持或改进检测逻辑，请：

1. 在 `AccountHealthChecker` 中添加平台特定方法
2. 更新检测规则和异常处理逻辑
3. 添加相应的测试用例
4. 更新文档说明

---

**系统设计目标**：确保生产环境中只有健康的账号参与数据采集，提高系统稳定性和数据质量。
