# Shopee 商家端数据采集器使用指南

> 文档索引（推荐入口）: docs/INDEX.md

## 📋 概述

Shopee 商家端数据采集器是基于 Playwright 技术栈开发的自动化数据采集工具，专门用于采集 Shopee 平台的运营数据，包括店铺客流量、用户画像、销售分析等关键业务指标。

## 🎯 主要特性

### 1. 智能登录系统

- **邮箱 OTP 验证**: 自动获取 163 邮箱验证码，避免手动输入
- **会话持久化**: 支持会话保存和恢复，减少重复登录
- **中国 IP 支持**: 针对中国商家端优化，支持中国 IP 代理

### 2. 数据采集功能

- **仪表板数据**: 访客数、浏览量、订单数、销售额、转化率
- **店铺分析**: 时间趋势分析、数据对比、图表数据

### 2.1 商品表现导出（周度）- 稳定性更新（2025-08-30）

- 指标勾选稳定性：规范化匹配 + 同义词 + 相似度 0.6，适配“矩形 选择指标”按钮
- 流程修复：标准导出中，先勾选指标并确认，再触发导出
- 诊断模式：生成 before/after 快照与网络快照，辅助定位导出失败
- 注意：导出列可能由平台默认决定，指标勾选主要影响页面展示（继续验证是否存在“列偏好保存”API）

- **用户画像**: 年龄分布、性别比例、地域分布、行为特征
- **数据导出**: 支持 Excel、CSV、JSON 等多种格式

### 3. 技术优势

- **反检测能力强**: 基于 Playwright，避免被平台检测
- **自动化程度高**: 全流程自动化，减少人工干预
- **错误处理完善**: 智能重试、异常恢复、详细日志

## 🚀 快速开始

### 1. 环境准备

确保已安装必要的依赖：

```bash
pip install playwright
playwright install chromium
```

### 2. 账号配置

在 `local_accounts.py` 中配置 Shopee 账号：

```python
"shopee": [
    {
        "account_id": "shopee商家端",
        "platform": "Shopee",
        "store_name": "MyStore_SG",
        "username": "your_username",
        "password": "your_password",
        "E-mail": "your_email@163.com",
        "Email password": "your_email_password",
        "Email License": "your_imap_license",
        "Email address": "https://mail.163.com/",
        "region": "CN",
        "currency": "SGD",
        "enabled": True,
        "proxy_required": False,
        "proxy_region": "china",
        "login_url": "https://seller.shopee.cn/account/signin",
        "notes": "新加坡Shopee卖家账号"
    }
]
```

### 3. 邮箱配置

确保 163 邮箱已开启 IMAP 服务：

1. 登录 163 邮箱
2. 进入设置 → POP3/SMTP/IMAP
3. 开启 IMAP 服务
4. 获取授权码（Email License 字段）

### 4. 运行采集

#### 方式一：通过主系统

```bash
python run.py
# 选择"数据采集" → "Shopee"
```

#### 方式二：直接调用

```python
from modules.collectors.shopee_collector import create_shopee_collector
from modules.utils.account_manager import AccountManager

# 获取账号配置
account_manager = AccountManager()
shopee_accounts = account_manager.get_accounts_by_platform("shopee")
account = shopee_accounts[0]

# 创建采集器
collector = create_shopee_collector(account)

# 运行采集
result = collector.run_full_collection()
print(result)
```

## 📊 数据采集流程

### 1. 登录流程

```
启动浏览器 → 访问登录页面 → 输入凭据 → 邮箱验证 → 登录成功
```

### 2. 数据采集流程

```
登录成功 → 采集仪表板数据 → 采集店铺分析 → 采集用户画像 → 导出数据报告
```

### 3. 邮箱验证流程

```
检测验证弹窗 → 连接163邮箱 → 搜索验证码邮件 → 提取OTP → 自动填写 → 确认验证
```

## ⚙️ 配置说明

### 配置文件位置

`config/collectors/shopee_config.yaml`

### 主要配置项

#### 连接配置

```yaml
connection:
  base_url: "https://seller.shopee.cn"
  login_url: "https://seller.shopee.cn/account/signin"
  timeout: 60
  retry_times: 3
```

#### 浏览器配置

```yaml
browser:
  headless: false # 开发阶段使用有头模式
  slow_mo: 1000 # 操作间隔1秒
  timeout: 30000 # 30秒超时
```

#### 数据采集配置

```yaml
data_collection:
  update_frequency: 3600 # 采集频率（秒）
  data_range_days: 7 # 数据范围（天）
  data_types:
    dashboard: true # 仪表板数据
    shop_analytics: true # 店铺分析
    user_profile: true # 用户画像
```

## 🔧 高级功能

### 1. 会话管理

- **自动保存**: 登录成功后自动保存会话状态
- **智能恢复**: 下次运行时自动恢复有效会话
- **过期检测**: 自动检测会话是否过期

### 2. 代理支持

- **中国 IP**: 支持中国地区代理配置
- **自动切换**: 支持代理自动切换和故障转移
- **连接测试**: 自动测试代理连接状态

### 3. 错误处理

- **智能重试**: 网络错误时自动重试
- **异常恢复**: 页面异常时自动恢复
- **详细日志**: 完整的操作日志和错误记录

## 📁 输出文件

### 1. 数据文件

- **位置**: `temp/outputs/shopee_data/`
- **格式**: Excel、CSV、JSON
- **内容**: 运营数据、分析报告、用户画像

### 2. 截图文件

- **位置**: `temp/media/screenshots/shopee/`
- **命名**: `shopee_功能_时间戳.png`
- **用途**: 操作记录、问题排查

### 3. 会话文件

- **位置**: `temp/sessions/shopee/`
- **格式**: JSON
- **用途**: 会话状态保存和恢复

## 🧪 测试验证

### 1. 邮箱连接测试

```python
from modules.utils.email_otp_service import create_email_otp_service

email_service = create_email_otp_service(account_config)
if email_service.test_connection():
    print("✅ 邮箱连接成功")
else:
    print("❌ 邮箱连接失败")
```

### 2. 采集器测试

```bash
python test_shopee_collector.py
```

### 3. 功能测试

- 登录功能测试
- 数据采集测试
- 邮箱验证测试
- 数据导出测试

## ⚠️ 注意事项

### 1. 安全注意事项

- **账号安全**: 不要在代码中硬编码敏感信息
- **代理使用**: 使用可靠的代理服务，避免 IP 被封
- **访问频率**: 控制采集频率，避免触发平台限制

### 2. 技术注意事项

- **浏览器版本**: 确保 Playwright 版本兼容
- **网络环境**: 确保网络连接稳定
- **系统资源**: 监控内存和 CPU 使用情况

### 3. 平台注意事项

- **验证码策略**: 优先使用邮箱验证，避免电话验证
- **登录限制**: 注意平台的登录频率限制
- **数据范围**: 遵守平台的数据使用条款

## 🐛 故障排除

### 1. 常见问题

#### 邮箱连接失败

- 检查 IMAP 服务是否开启
- 验证授权码是否正确
- 确认网络连接正常

#### 登录失败

- 检查账号密码是否正确
- 确认登录 URL 是否有效
- 查看是否有验证码要求

#### 数据采集失败

- 检查页面元素选择器
- 确认登录状态是否正常
- 查看网络连接状态

### 2. 日志分析

- **位置**: `logs/shopee_collector.log`
- **级别**: DEBUG、INFO、WARNING、ERROR
- **内容**: 详细的操作记录和错误信息

### 3. 调试模式

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 使用有头模式
collector = create_shopee_collector(account, {'headless': False})
```

## 📈 性能优化

### 1. 并发优化

- 支持多账号并发采集
- 优化网络请求频率
- 减少不必要的页面刷新

### 2. 资源优化

- 及时释放浏览器资源
- 优化内存使用
- 控制并发数量

### 3. 网络优化

- 使用连接池
- 优化请求超时设置
- 支持断点续传

## 🔮 未来规划

### 1. 功能扩展

- 支持更多数据源
- 增加数据可视化
- 集成机器学习分析

### 2. 技术升级

- 支持更多浏览器
- 优化反检测能力
- 提升采集效率

### 3. 平台支持

- 支持更多电商平台
- 跨平台数据对比
- 统一数据标准

## 📞 技术支持

### 1. 问题反馈

- 提交 Issue 到项目仓库
- 提供详细的错误信息和日志
- 包含复现步骤和环境信息

### 2. 功能建议

- 描述具体的使用场景
- 说明期望的功能特性
- 提供相关的技术参考

### 3. 贡献代码

- Fork 项目仓库
- 创建功能分支
- 提交 Pull Request

---

**版本**: 1.0.0
**更新日期**: 2025-08-24
**维护者**: 开发团队
