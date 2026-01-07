# Shopee自动登录模块使用指南

## 🎯 模块概述

Shopee自动登录模块是一个完整封装的自动化登录解决方案，专为跨境电商ERP系统设计。

### ✨ 核心特性

- 🎯 **智能状态检测** - 准确识别登录页面和后台页面
- 📝 **自动表单填写** - 自动填写用户名、密码
- 📱 **验证码处理** - 支持手机验证码自动化处理
- 🛡️ **持久化登录** - 浏览器Profile保存登录状态
- 🔄 **错误恢复** - 完善的异常处理和重试机制

## 🚀 快速开始

### 基本使用

```python
from modules.utils.shopee_auto_login import create_shopee_auto_login

# 创建自动登录实例
auto_login = create_shopee_auto_login(page, account)

# 执行自动登录
success = auto_login.execute_auto_login()

if success:
    print("🎉 登录成功！")
else:
    print("❌ 登录失败")
```

### 账号配置格式

```python
account = {
    'username': 'your_email@example.com',
    'password': 'your_password',
    'platform': 'shopee',
    'shop_name': '店铺名称'
}
```

## 📋 功能详解

### 1. 登录状态检测

模块会自动检测当前页面状态：

- **URL检测** - 检查是否在登录页面
- **DOM检测** - 检查页面元素类型
- **内容检测** - 分析页面文本内容

### 2. 自动表单填写

支持多种表单元素识别：

```python
# 用户名输入框识别
username_selectors = [
    'input[placeholder*="邮箱"]',
    'input[placeholder*="用户名"]',
    'input[type="email"]',
    'input[name="username"]',
    'input[name="email"]'
]

# 密码输入框识别
password_selectors = [
    'input[name="password"]',
    'input[type="password"]',
    'input[placeholder*="密码"]'
]
```

### 3. 验证码处理

#### 手机验证码流程

1. **自动检测** - 识别验证码弹窗
2. **用户输入** - 控制台提示输入验证码
3. **自动填写** - 自动填写到输入框
4. **自动提交** - 点击确认按钮

#### 验证码输入界面

```
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
📱 Shopee 手机验证码输入
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
🔔 请查看您的手机短信，获取 Shopee 发送的验证码
📞 验证码格式：4-6位数字（例如：123456）
⏰ 验证码有效期：5-10分钟
🚀 输入验证码后将自动完成登录并保存登录状态
🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥🔥
🎯 请输入手机验证码: 
```

## 🔧 高级配置

### 自定义选择器

如果页面结构发生变化，可以扩展选择器：

```python
class CustomShopeeAutoLogin(ShopeeAutoLogin):
    def _find_verification_input(self):
        # 添加自定义选择器
        custom_selectors = [
            'input[data-testid="otp-input"]',
            '.custom-otp-input'
        ]
        
        # 先尝试自定义选择器
        for selector in custom_selectors:
            try:
                element = self.page.wait_for_selector(selector, timeout=2000)
                if element and element.is_visible():
                    return element
            except:
                continue
        
        # 回退到默认实现
        return super()._find_verification_input()
```

### 错误处理

```python
try:
    auto_login = create_shopee_auto_login(page, account)
    success = auto_login.execute_auto_login()
    
    if not success:
        # 处理登录失败
        logger.error("自动登录失败，可能需要手动处理")
        
except Exception as e:
    logger.error(f"登录过程异常: {e}")
```

## 📊 状态码说明

| 返回值 | 说明 | 处理建议 |
|--------|------|----------|
| `True` | 登录成功 | 继续后续操作 |
| `False` | 登录失败 | 检查账号信息或手动登录 |

## 🛠️ 故障排除

### 常见问题

1. **找不到登录按钮**
   - 检查页面是否完全加载
   - 确认页面结构是否变化

2. **验证码输入失败**
   - 确认验证码格式正确
   - 检查验证码是否过期

3. **登录状态检测错误**
   - 检查URL是否正确
   - 确认页面内容是否加载完成

### 调试模式

启用详细日志：

```python
from modules.utils.logger import logger
logger.setLevel("DEBUG")
```

## 🔄 版本历史

### v2.0.0 (2025-08-29)
- ✅ 完整封装自动登录流程
- ✅ 修复登录状态误判问题
- ✅ 优化验证码处理逻辑
- ✅ 添加DOM元素检测
- ✅ 完善错误处理机制

### v1.0.0 (2025-08-28)
- ✅ 基础自动登录功能
- ✅ 手机验证码支持
- ✅ 持久化浏览器Profile

## 📞 技术支持

如遇到问题，请提供以下信息：

1. 错误日志
2. 页面截图
3. 账号配置（隐藏敏感信息）
4. 浏览器版本

## 🎯 下一步计划

- 📧 邮箱验证码自动化
- 🔐 二次验证支持
- 📱 移动端适配
- 🤖 AI验证码识别
