# 组件录制指南

本文档介绍如何使用组件录制工具录制浏览器操作并生成YAML组件配置。

## 概述

组件录制工具 (`tools/record_component.py`) 是一个基于 Playwright 的录制工具，可以：

1. 启动浏览器并自动导航到目标页面
2. 记录用户的浏览器操作
3. 将录制结果转换为 YAML 组件格式

## 快速开始

### 前置要求

```bash
# 安装 Playwright
pip install playwright

# 安装浏览器
playwright install chromium
```

### 基本用法

```bash
# 录制 Shopee 登录组件
python tools/record_component.py --platform shopee --component login --account MyStore_SG

# 录制订单导出组件（跳过登录）
python tools/record_component.py --platform shopee --component orders_export --skip-login

# 查看帮助
python tools/record_component.py --help
```

## 命令行参数

| 参数 | 简写 | 说明 | 必填 |
|------|------|------|------|
| `--platform` | `-p` | 目标平台 (shopee/tiktok/miaoshou) | 是 |
| `--component` | `-c` | 组件名称 | 是 |
| `--account` | `-a` | 账号ID（用于自动登录） | 否 |
| `--skip-login` | - | 跳过自动登录 | 否 |
| `--output-dir` | `-o` | 输出目录 | 否 |
| `--convert` | - | 转换模式 | 否 |

## 录制流程

### 1. 准备工作

确保 `local_accounts.py` 中已配置目标账号：

```python
ACCOUNTS = {
    "MyStore_SG": {
        "platform": "shopee",
        "login_url": "https://seller.shopee.sg/",
        "username": "your_username",
        "password": "your_password",
        # ...
    }
}
```

### 2. 启动录制

```bash
python tools/record_component.py -p shopee -c login -a MyStore_SG
```

工具会显示：

```
============================================================
 组件录制工具 - Component Recorder
============================================================

平台: shopee
组件: login
账号: MyStore_SG
输出目录: config/collection_components/shopee

------------------------------------------------------------
 录制说明:
------------------------------------------------------------
1. 浏览器将自动打开并导航到目标页面
2. 在浏览器中执行您要录制的操作
3. 操作完成后，关闭浏览器
4. 工具将自动生成YAML组件文件
------------------------------------------------------------

按 Enter 键开始录制...
```

### 3. 执行操作

在打开的浏览器中执行需要录制的操作：
- 点击按钮
- 填写表单
- 选择选项
- 等待加载
- ...

### 4. 完成录制

关闭浏览器窗口后，工具会自动生成 YAML 文件：

```
============================================================
 录制完成!
============================================================

生成文件: config/collection_components/shopee/login.yaml
录制步骤数: 5

请检查并手动完善生成的YAML文件。
```

## 生成的 YAML 格式

录制工具会生成如下格式的 YAML 文件：

```yaml
# SHOPEE login 组件
# 生成时间: 2025-12-09 21:30:00
# 注意: 此文件由录制工具自动生成，请手动检查和完善

name: shopee_login
platform: shopee
type: login
version: 1.0.0
description: Shopee login 组件（自动生成，请手动完善）

steps:
  - action: navigate
    url: https://seller.shopee.sg/
    wait_until: domcontentloaded
    
  - action: fill
    selector: '#username'
    value: '{{account.username}}'
    
  - action: fill
    selector: '#password'
    value: '{{account.password}}'
    
  - action: click
    selector: 'button[type="submit"]'

success_criteria:
  - type: url_matches
    value: 'TODO: 填写成功URL特征'
    comment: 请填写成功判定条件

error_handlers:
  - selector: '.error-message'
    action: fail_task
    message: 'TODO: 填写错误处理'
```

## 手动完善组件

生成的 YAML 文件需要手动完善以下内容：

### 1. 变量替换

将硬编码的值替换为变量：

```yaml
# 之前
- action: fill
  selector: '#username'
  value: 'actual_username'

# 之后
- action: fill
  selector: '#username'
  value: '{{account.username}}'
```

### 2. 成功条件

填写正确的成功判定条件：

```yaml
success_criteria:
  - type: url_matches
    value: '/portal/home'
  - type: selector_exists
    selector: '.dashboard-container'
```

### 3. 错误处理

添加错误处理规则：

```yaml
error_handlers:
  - selector: '.login-error'
    action: fail_task
    message: '登录失败：用户名或密码错误'
  
  - selector: '.captcha-modal'
    action: pause_for_verification
    verification_type: image
```

### 4. 超时设置

为关键步骤设置超时：

```yaml
steps:
  - action: wait
    selector: '.loading-complete'
    timeout: 60000  # 60秒
```

### 5. 弹窗处理

配置弹窗处理策略：

```yaml
popup_handling:
  check_before_steps: true
  check_after_steps: true
  custom_popups:
    - selector: '.survey-popup-close'
      action: click
```

## 转换 Codegen 输出

如果您使用 `playwright codegen` 生成了 Python 代码，可以使用转换模式：

```bash
python tools/record_component.py --convert recorded.py output.yaml
```

## 组件测试

录制完成后，使用测试工具验证：

```bash
# 测试单个组件
python tools/test_component.py -p shopee -c login -a MyStore_SG

# 测试所有组件
python tools/test_component.py --all -p shopee
```

## 最佳实践

### 1. 组件粒度

- **单一职责**：每个组件只负责一个功能
- **可复用**：设计通用的组件，避免重复录制
- **可组合**：复杂流程通过组合多个组件实现

### 2. 选择器策略

优先级（从高到低）：
1. `data-testid` 属性
2. `id` 属性
3. `aria-label` 属性
4. CSS 类名（稳定的）
5. 文本内容（最后选择）

```yaml
# 推荐
selector: '[data-testid="submit-btn"]'
selector: '#login-form'
selector: '[aria-label="Close"]'

# 避免
selector: '.btn.btn-primary.mt-3'  # 可能变化
selector: 'div > div > button'     # 结构依赖
```

### 3. 等待策略

总是在关键操作后添加等待：

```yaml
steps:
  - action: click
    selector: '#submit'
  
  - action: wait
    selector: '.loading-indicator'
    state: hidden  # 等待加载完成
  
  - action: wait
    selector: '.success-message'
    state: visible
```

### 4. 错误恢复

为常见错误场景添加处理：

```yaml
error_handlers:
  # 网络错误重试
  - selector: '.network-error'
    action: retry_step
    max_retries: 3
    
  # 验证码暂停
  - selector: '.captcha-container'
    action: pause_for_verification
    
  # 会话过期重新登录
  - selector: '.session-expired'
    action: component_call
    component_name: login
```

## 常见问题

### Q: 录制的选择器不准确？

A: 使用 Playwright Inspector 的选择器建议功能，或手动编写更精确的选择器。

### Q: 如何处理动态内容？

A: 使用 `wait` 动作等待元素出现或消失：

```yaml
- action: wait
  selector: '[data-loaded="true"]'
  timeout: 30000
```

### Q: 如何处理 iframe？

A: 使用 `frame_selector` 指定 iframe：

```yaml
- action: click
  selector: '#button-in-iframe'
  frame_selector: 'iframe[name="content"]'
```

### Q: 如何调试组件？

A: 使用测试工具的可视模式（不加 `--headless`）：

```bash
python tools/test_component.py -p shopee -c login -a MyStore_SG
```

## 相关文档

- [组件 Schema 规范](component_schema.md)
- [组件测试指南](component_testing.md)
- [平台适配指南](platform_adaptation.md)

