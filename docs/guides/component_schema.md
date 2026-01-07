# 组件 YAML Schema 规范

## 概述

本文档定义数据采集组件的 YAML 配置格式规范。组件是可复用的采集操作单元，通过 YAML 配置描述浏览器自动化步骤。

## 组件类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `login` | 登录组件 | 账号登录流程 |
| `navigation` | 导航组件 | 页面导航和菜单点击 |
| `date_picker` | 日期选择组件 | 日期范围选择 |
| `export` | 导出组件 | 数据导出和文件下载 |
| `verification` | 验证组件 | 验证码处理 |

## 基础结构

```yaml
# 组件元数据
name: string                    # 组件名称（唯一标识）
platform: string                # 平台代码（shopee/tiktok/miaoshou）
type: string                    # 组件类型（login/navigation/date_picker/export/verification）
version: string                 # 组件版本（如 "1.0.0"）
description: string             # 组件描述
author: string                  # 作者
data_domain: string             # 数据域（仅export类型需要：orders/products/services/analytics/finance/inventory）

# 弹窗处理配置（可选）
popup_handling:
  enabled: boolean              # 是否启用弹窗处理（默认true）
  check_before_steps: boolean   # 步骤执行前检查弹窗（默认true）
  check_after_steps: boolean    # 步骤执行后检查弹窗（默认true）
  check_on_error: boolean       # 错误时检查弹窗（默认true）

# 执行步骤
steps:
  - action: string              # 动作类型
    # ... 动作特定参数
```

## 通用步骤参数

所有步骤都支持以下通用参数：

```yaml
- action: <action_type>
  optional: boolean             # 可选步骤（默认false）⭐ v4.7.0新增
  timeout: integer              # 超时时间（毫秒，默认5000）
  retry:                        # 重试配置（可选）⭐ v4.7.0新增
    max_attempts: integer       # 最大重试次数（默认3）
    delay: integer              # 重试延迟（毫秒，默认2000）
    on_retry: string            # 重试前操作：wait/close_popup（默认wait）
  fallback_methods:             # 降级方法列表（可选）⭐ Phase 2.5.5新增
    - selector: string          # 备用选择器
      description: string       # 方法描述（可选）
      timeout: integer          # 超时时间（可选，继承主步骤）
```

**optional参数说明**（⭐ 重要）：
- 当`optional: true`时，如果元素不存在，步骤会被跳过而不是失败
- 仅对需要定位元素的操作有效（click/fill/select/check_element/wait）
- 快速检测元素（1秒超时），不存在时记录日志并继续
- **最佳实践**：用于处理弹窗等不一定出现的元素

**retry参数说明**（⭐ 重要）：
- 步骤失败时自动重试
- `on_retry: close_popup` - 重试前自动关闭弹窗（推荐）
- `on_retry: wait` - 重试前等待指定延迟

**fallback_methods参数说明**（⭐ Phase 2.5.5）：
- primary方法失败后依次尝试fallback方法
- 适用于页面改版、多种UI变体、A/B测试场景
- 每个fallback可以有自己的selector和timeout
- 记录使用的方法，便于监控和优化

---

## 动作类型

### 1. navigate（页面导航）

```yaml
- action: navigate
  url: string                   # 目标URL（支持变量替换）
  wait_until: string            # 等待条件：load/domcontentloaded/networkidle（默认load）
  timeout: integer              # 超时时间（毫秒，默认30000）
```

### 2. click（点击元素）

```yaml
- action: click
  selector: string              # CSS选择器
  wait_for: string              # 点击前等待的选择器（可选）
  timeout: integer              # 超时时间（毫秒，默认5000）
  delay: integer                # 点击后延迟（毫秒，可选）
  optional: boolean             # 可选步骤（默认false）⭐
  retry:                        # 重试配置（可选）⭐
    max_attempts: 3
    delay: 2000
    on_retry: close_popup
```

### 3. fill（填充输入框）

```yaml
- action: fill
  selector: string              # CSS选择器
  value: string                 # 填充值（支持变量替换：{{account.username}}）
  clear: boolean                # 填充前是否清空（默认true）
  timeout: integer              # 超时时间（毫秒，默认5000）
  optional: boolean             # 可选步骤（默认false）⭐
```

### 4. wait（等待）

```yaml
- action: wait
  type: string                  # 等待类型：timeout/selector/navigation
  
  # type=timeout
  duration: integer             # 等待时长（毫秒）
  
  # type=selector
  selector: string              # 等待的选择器
  state: string                 # 等待状态：attached/detached/visible/hidden（默认visible）
  timeout: integer              # 超时时间（毫秒，默认30000）
  smart_wait: boolean           # 自适应等待（默认false）⭐ Phase 2.5.4.2新增
  
  # type=navigation
  wait_until: string            # 等待条件：load/domcontentloaded/networkidle
  timeout: integer              # 超时时间（毫秒，默认30000）
```

**smart_wait参数说明**（⭐ Phase 2.5.4.2）：
- 当`smart_wait: true`时，使用多层次等待策略
- 自动处理网络延迟和弹窗遮挡
- 4层策略：快速检测(1s) → 关闭弹窗(10s) → 网络空闲(5s) → 长时间等待
- **推荐场景**：网络不稳定、页面加载慢、弹窗频繁出现

### 5. select（下拉选择）

```yaml
- action: select
  selector: string              # 下拉框选择器
  value: string                 # 选择值（支持变量替换）
  by: string                    # 选择方式：value/label/index（默认value）
  timeout: integer              # 超时时间（毫秒，默认5000）
```

### 6. wait_for_download（等待文件下载）

```yaml
- action: wait_for_download
  timeout: integer              # 超时时间（毫秒，默认120000）
  save_as: string               # 保存文件名（可选，支持变量替换）
```

### 7. screenshot（截图）

```yaml
- action: screenshot
  path: string                  # 保存路径（支持变量替换）
  full_page: boolean            # 是否全页截图（默认false）
```

### 8. component_call（调用其他组件）

```yaml
- action: component_call
  component: string             # 组件路径（如 "shopee/date_picker"）
  params:                       # 传递给组件的参数（可选）
    key: value
```

### 9. check_element（检查元素存在）

```yaml
- action: check_element
  selector: string              # 元素选择器
  expect: string                # 期望状态：exists/not_exists/visible/hidden
  timeout: integer              # 超时时间（毫秒，默认5000）
  on_fail: string               # 失败时动作：error/continue/skip（默认error）
  optional: boolean             # 可选步骤（默认false）⭐
```

### 10. close_popups（关闭弹窗）⭐ v4.7.0新增

```yaml
- action: close_popups
  # 无需额外参数，自动关闭当前平台的所有已知弹窗
```

## 变量替换

组件支持以下变量：

### 账号变量（来自 local_accounts.py）

```yaml
{{account.username}}          # 账号用户名
{{account.password}}          # 账号密码
{{account.store_name}}        # 店铺名称
{{account.platform}}          # 平台代码
```

### 参数变量（来自执行时传入）

```yaml
{{params.date_from}}          # 开始日期
{{params.date_to}}            # 结束日期
{{params.granularity}}        # 粒度（daily/weekly/monthly）
{{params.data_domain}}        # 数据域
{{params.sub_domain}}         # 子域（可选）
```

### 任务变量（来自任务上下文）

```yaml
{{task.id}}                   # 任务ID
{{task.download_dir}}         # 下载目录
{{task.screenshot_dir}}       # 截图目录
```

## 最佳实践：容错机制 ⭐ v4.7.0

### 1. 使用optional处理不确定的弹窗

```yaml
steps:
  # 主要操作
  - action: click
    selector: button.export-btn
    timeout: 5000
  
  # 可选：关闭可能出现的弹窗
  - action: click
    selector: div.popup-close
    optional: true              # ⭐ 弹窗不出现时跳过
    timeout: 1000               # 快速检测
  
  # 继续后续操作
  - action: wait
    type: selector
    selector: div.download-ready
```

### 2. 使用retry处理临时失败

```yaml
steps:
  # 关键操作：自动重试
  - action: click
    selector: button.submit
    retry:                      # ⭐ 失败时自动重试
      max_attempts: 3
      delay: 2000
      on_retry: close_popup     # 重试前关闭弹窗
```

### 3. 组合使用optional和retry

```yaml
steps:
  # 先尝试关闭弹窗（可选）
  - action: click
    selector: div.ad-close
    optional: true
    timeout: 1000
  
  # 执行主要操作（带重试）
  - action: click
    selector: button.export
    retry:
      max_attempts: 3
      delay: 2000
      on_retry: close_popup
```

### 4. 使用smart_wait处理网络延迟 ⭐ Phase 2.5.4.2

```yaml
steps:
  # 点击导出按钮
  - action: click
    selector: button.export-data
  
  # 等待导出对话框（使用自适应等待）
  - action: wait
    type: selector
    selector: div.export-dialog
    smart_wait: true          # ⭐ 自适应等待
    timeout: 30000            # 最大30秒
  
  # 继续后续操作
  - action: click
    selector: button.confirm-export
```

**自适应等待策略**:
1. **快速检测（1秒）**: 元素已存在，立即返回
2. **关闭弹窗（10秒）**: 弹窗遮挡，关闭后重试
3. **网络空闲（5秒）**: 等待网络请求完成
4. **长时间等待（剩余时间）**: 页面加载慢，耐心等待

### 5. 使用fallback处理页面改版 ⭐ Phase 2.5.5

```yaml
steps:
  # 点击导出按钮（支持新旧版本）
  - action: click
    selector: button.export-v2        # Primary: 新版按钮
    fallback_methods:
      - selector: button.export-v1    # Fallback 1: 旧版按钮
        description: "旧版导出按钮"
      - selector: a.export-link       # Fallback 2: 链接形式
        description: "链接导出"
        timeout: 3000                 # 自定义超时
  
  # 继续后续操作
  - action: wait
    type: selector
    selector: div.export-dialog
```

**降级策略说明**:
- **Primary失败**: 尝试新版按钮 → 失败
- **Fallback 1**: 尝试旧版按钮 → 成功！
- **记录**: 日志记录使用了fallback方法，便于监控

**适用场景**:
- 页面改版过渡期（新旧版本并存）
- A/B测试（不同用户看到不同UI）
- 多种UI变体（不同区域/语言）
- 元素ID/类名变更

---

## 完整示例

### 示例1：登录组件

```yaml
name: shopee_login
platform: shopee
type: login
version: "1.0.0"
description: "Shopee平台登录组件"
author: "admin"

popup_handling:
  enabled: true
  check_before_steps: true
  check_after_steps: true

steps:
  - action: navigate
    url: "https://seller.shopee.cn/account/signin"
    wait_until: load
    
  - action: wait
    type: selector
    selector: "input[name='username']"
    state: visible
    timeout: 10000
    
  - action: fill
    selector: "input[name='username']"
    value: "{{account.username}}"
    
  - action: fill
    selector: "input[name='password']"
    value: "{{account.password}}"
    
  - action: click
    selector: "button[type='submit']"
    
  - action: wait
    type: navigation
    wait_until: networkidle
    timeout: 30000
    
  - action: check_element
    selector: ".seller-dashboard"
    expect: visible
    timeout: 10000
```

### 示例2：订单导出组件

```yaml
name: shopee_orders_export
platform: shopee
type: export
version: "1.0.0"
description: "Shopee订单数据导出组件"
author: "admin"
data_domain: orders

popup_handling:
  enabled: true
  check_on_error: true

steps:
  - action: click
    selector: "button:has-text('导出数据')"
    wait_for: ".export-dialog"
    
  - action: component_call
    component: "shopee/date_picker"
    params:
      date_from: "{{params.date_from}}"
      date_to: "{{params.date_to}}"
      
  - action: click
    selector: ".export-dialog button:has-text('确认导出')"
    
  - action: wait_for_download
    timeout: 120000
    save_as: "orders_{{params.date_from}}_{{params.date_to}}.xlsx"
```

### 示例3：日期选择组件

```yaml
name: shopee_date_picker
platform: shopee
type: date_picker
version: "1.0.0"
description: "Shopee日期范围选择组件"
author: "admin"

steps:
  - action: click
    selector: ".date-range-picker"
    
  - action: fill
    selector: "input[name='start_date']"
    value: "{{params.date_from}}"
    
  - action: fill
    selector: "input[name='end_date']"
    value: "{{params.date_to}}"
    
  - action: click
    selector: "button:has-text('确定')"
    delay: 500
```

## 验证规则

组件加载时会进行以下验证：

1. **必填字段**：name, platform, type, steps
2. **类型检查**：platform必须是shopee/tiktok/miaoshou之一
3. **步骤验证**：每个步骤必须有action字段
4. **选择器安全**：禁止javascript:、data:等危险模式
5. **变量格式**：变量必须是{{xxx.yyy}}格式

## 最佳实践

1. **组件粒度**：每个组件只做一件事，便于复用
2. **错误处理**：关键步骤使用check_element验证
3. **超时设置**：根据网络情况合理设置超时时间
4. **弹窗处理**：默认启用弹窗处理，特殊情况可禁用
5. **变量命名**：使用清晰的变量名，便于理解
6. **版本管理**：修改组件时更新version字段

## 常见问题

### Q: 如何处理动态选择器？

A: 使用更通用的选择器，如`:has-text()`、`:nth-child()`等

### Q: 如何处理验证码？

A: 创建verification类型组件，执行引擎会自动暂停并通知前端

### Q: 组件可以嵌套调用吗？

A: 可以，使用component_call动作调用其他组件

### Q: 如何调试组件？

A: 使用`tools/test_component.py`脚本单独测试组件

