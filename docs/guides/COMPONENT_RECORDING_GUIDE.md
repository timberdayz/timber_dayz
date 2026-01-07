# 组件录制指南

本指南说明如何使用组件录制工具录制和创建数据采集组件。

## 目录

1. [组件类型概述](#组件类型概述)
2. [录制前准备](#录制前准备)
3. [固定组件录制](#固定组件录制)
4. [灵活组件录制](#灵活组件录制)
5. [导出组件录制](#导出组件录制)
6. [参数化设计模式](#参数化设计模式)
7. [最佳实践](#最佳实践)

---

## 组件类型概述

| 组件类型 | 说明 | 特点 | 需要数据域 |
|---------|------|------|-----------|
| `login` | 登录组件 | 固定流程，每个平台一个 | 否 |
| `shop_switch` | 店铺切换 | 相对固定，选择店铺 | 否 |
| `navigation` | 页面导航 | 灵活，根据数据域导航 | 否（运行时传入） |
| `date_picker` | 日期选择 | 灵活，处理日期控件 | 否 |
| `filters` | 筛选器 | 灵活，处理状态/条件筛选 | 否 |
| `export` | 数据导出 | 核心组件，按数据域区分 | **是**（必选） |

### 组件类型选择决策树

```
需要录制什么功能？
├─ 登录到平台？ → login
├─ 切换店铺？ → shop_switch  
├─ 导航到某个页面？ → navigation
├─ 选择日期范围？ → date_picker
├─ 筛选订单状态/条件？ → filters
└─ 导出数据？ → export（必须选择数据域）
```

---

## 录制前准备

### 1. 准备测试账号

确保在**账号管理**中已添加要录制的平台账号：
- 账号已启用
- 登录URL正确
- 密码已加密存储

### 2. 选择录制模式

**Inspector 模式（推荐）**：
- 持久化会话，复用登录状态
- 自动处理弹窗
- 支持 Trace 录制回放

**Codegen 模式（备选）**：
- 简单快速
- 适合一次性录制

### 3. 了解目标平台

在录制前，建议手动操作一遍目标流程，了解：
- 页面加载顺序
- 可能出现的弹窗
- 元素定位方式

---

## 固定组件录制

### Login 组件

**特点**：每个平台只需一个登录组件，流程相对固定。

**录制步骤**：
1. 选择平台和 `login` 组件类型
2. 选择测试账号
3. 点击"开始录制"
4. 在浏览器中执行登录操作：
   - 输入用户名（使用变量 `{{account.username}}`）
   - 输入密码（使用变量 `{{account.password}}`，系统自动解密）
   - 点击登录按钮
5. 等待登录成功
6. 点击"停止录制"

**示例 YAML**：

```yaml
name: miaoshou_login
platform: miaoshou
type: login
version: 1.0.0

steps:
  - action: navigate
    url: '{{account.login_url}}'
    
  - action: fill
    selector: 'input[placeholder*="手机号"]'
    value: '{{account.username}}'
    
  - action: fill
    selector: 'input[placeholder*="密码"]'
    value: '{{account.password}}'  # 自动解密
    
  - action: click
    selector: 'button:has-text("登录")'
    
  - action: wait
    duration: 3000
    
success_criteria:
  - type: url_not_contains
    value: '/login'
```

### Shop Switch 组件

**特点**：切换到指定店铺，流程相对固定。

**录制步骤**：
1. 选择 `shop_switch` 组件类型
2. 录制点击店铺选择器、选择店铺的操作
3. 使用变量 `{{account.shop_name}}` 替代硬编码店铺名

---

## 灵活组件录制

### Navigation 组件

**设计原则**：Navigation 组件是**通用的**，不绑定特定数据域。运行时通过 `params.data_domain` 参数决定导航目标。

**录制方法**：
1. 选择 `navigation` 组件类型
2. 选择一个**示例数据域**（仅用于录制演示）
3. 录制导航到该数据域页面的操作
4. 完成后，组件会自动生成 `data_domain_urls` 映射表

**示例 YAML**：

```yaml
name: shopee_navigation
platform: shopee
type: navigation
version: 1.0.0

# 数据域URL映射（运行时根据 params.data_domain 参数动态选择）
data_domain_urls:
  orders: '/portal/sale/order'
  products: '/portal/product/list'
  analytics: '/portal/datacenter/traffic'
  finance: '/portal/income/bill'
  services: '/portal/chat'
  inventory: '/portal/stock'

steps:
  - action: navigate
    url: '{{account.login_url}}{{data_domain_urls[params.data_domain]}}'
    comment: '根据数据域导航到对应页面'
    
  - action: wait
    selector: '.page-content'
    comment: '等待页面加载'
```

**运行时调用**：

```yaml
# 在执行器中传入 params.data_domain = 'orders'
# 组件会导航到 /portal/sale/order
```

### Date Picker 组件

**设计原则**：Date Picker 组件是**通用的**，处理平台的日期选择控件。

**录制方法**：
1. 选择 `date_picker` 组件类型
2. 录制日期选择操作（建议录制"自定义日期"路径）
3. 使用变量 `{{params.date_from}}` 和 `{{params.date_to}}`

**示例 YAML**：

```yaml
name: shopee_date_picker
platform: shopee
type: date_picker
version: 1.0.0

steps:
  - action: click
    selector: '.date-picker-trigger'
    comment: '打开日期选择器'
    
  - action: click
    selector: '[data-range="custom"]'
    comment: '选择自定义日期'
    
  - action: fill
    selector: 'input[placeholder*="开始"]'
    value: '{{params.date_from}}'
    
  - action: fill
    selector: 'input[placeholder*="结束"]'
    value: '{{params.date_to}}'
    
  - action: click
    selector: 'button:has-text("确定")'
```

### Filters 组件

**设计原则**：Filters 组件处理订单状态、店铺选择等筛选条件。

**录制方法**：
1. 选择 `filters` 组件类型
2. 录制筛选操作
3. 使用变量 `{{params.order_status}}`、`{{params.shop_id}}` 等

**示例 YAML**：

```yaml
name: shopee_filters
platform: shopee
type: filters
version: 1.0.0

steps:
  - action: click
    selector: '.order-status-dropdown'
    comment: '打开订单状态下拉框'
    optional: true
    
  - action: click
    selector: '[data-status="{{params.order_status}}"]'
    comment: '选择订单状态'
    optional: true
```

---

## 导出组件录制

### 核心原则（Phase 9 架构）

导出组件是数据采集的**核心组件**，必须按数据域区分，并且是**自包含的完整流程**：

**自包含原则**：导出组件必须包含从登录后到下载完成的完整流程：
1. 导航到目标页面（URL 或点击菜单）
2. 切换店铺（如需要）
3. 选择日期范围
4. 设置筛选条件（可选）
5. 触发导出并下载文件

| 数据域 | 组件名称 | 说明 |
|-------|---------|------|
| orders | `{platform}_orders_export` | 订单导出 |
| products | `{platform}_products_export` | 产品导出 |
| analytics | `{platform}_analytics_export` | 流量分析导出 |
| finance | `{platform}_finance_export` | 财务导出 |
| services | `{platform}_services_export` | 服务数据导出 |
| inventory | `{platform}_inventory_export` | 库存导出 |

### 服务数据域的子域

当选择 `services` 数据域时，可以进一步选择子域：

| 子域 | 组件名称 | 说明 |
|-----|---------|------|
| ai_assistant | `{platform}_services_ai_assistant_export` | 智能客服数据 |
| agent | `{platform}_services_agent_export` | 人工客服数据 |

### 录制步骤

1. 选择 `export` 组件类型
2. **必须选择数据域**（如 `orders`）
3. 如果是 `services`，可选择子域
4. 录制**完整的导出流程**：
   - 导航到目标页面（直接 URL 或点击菜单）
   - 切换店铺（如需要）
   - 选择日期范围（调用 `date_picker` 子组件或直接录制）
   - 设置筛选条件（可选）
   - 点击导出按钮
   - 处理导出配置弹窗（如有）
   - 等待下载完成

**示例 YAML（订单导出 - 自包含流程）**：

```yaml
name: shopee_orders_export
platform: shopee
type: export
version: 1.0.0
data_domain: orders

steps:
  # 1. 导航到订单页面（直接URL或调用子组件）
  - action: navigate
    url: '{{account.login_url}}/portal/sale/order'
    comment: '导航到订单页面'
    
  # 2. 切换店铺（可选，调用子组件）
  - action: component_call
    component: 'shopee/shop_switch'
    optional: true
    comment: '切换到目标店铺'
      
  # 3. 选择日期范围（调用子组件）
  - action: component_call
    component: 'shopee/date_picker'
    params:
      date_from: '{{params.date_from}}'
      date_to: '{{params.date_to}}'
    comment: '选择日期范围'
    
  # 4. 设置筛选条件（可选）
  - action: component_call
    component: 'shopee/filters'
    params:
      order_status: '{{params.order_status}}'
    optional: true
    comment: '设置筛选条件'
      
  # 5. 点击导出按钮
  - action: click
    selector: 'button:has-text("导出")'
    comment: '点击导出按钮'
    
  # 6. 等待下载
  - action: wait_for_download
    timeout: 60000
    comment: '等待文件下载完成'
```

**说明**：导出组件是自包含的完整流程，从导航到下载一气呵成。执行器只需调用登录组件后，直接执行导出组件即可。

**示例 YAML（服务-智能客服导出）**：

```yaml
name: shopee_services_ai_assistant_export
platform: shopee
type: export
version: 1.0.0
data_domain: services
sub_domain: ai_assistant

steps:
  - action: component_call
    component: 'shopee/navigation'
    params:
      data_domain: 'services'
      
  # 切换到智能客服标签
  - action: click
    selector: '[data-tab="ai_assistant"]'
    
  # ... 后续导出步骤
```

---

## 参数化设计模式

### 变量类型

| 变量前缀 | 说明 | 示例 |
|---------|------|------|
| `{{account.xxx}}` | 账号信息 | `{{account.username}}`, `{{account.password}}` |
| `{{params.xxx}}` | 运行时参数 | `{{params.date_from}}`, `{{params.data_domain}}` |
| `{{task.xxx}}` | 任务信息 | `{{task.task_id}}` |

### 子组件调用

使用 `component_call` 动作调用其他组件：

```yaml
- action: component_call
  component: '{platform}/navigation'
  params:
    data_domain: 'orders'
```

### 条件执行

使用 `optional` 标记可选步骤：

```yaml
- action: click
  selector: '.popup-close'
  optional: true
  comment: '关闭可能出现的弹窗'
```

### 重试机制

为不稳定步骤配置重试：

```yaml
- action: click
  selector: '.export-btn'
  retry:
    max_attempts: 3
    delay: 1000
```

---

## 最佳实践

### 1. 组件粒度

- **细粒度**：将可复用的功能拆分为独立组件（navigation, date_picker）
- **粗粒度**：导出组件可以包含完整流程，但应调用子组件而非重复代码

### 2. 选择器规范

**推荐顺序**：
1. `get_by_role` - 语义化选择
2. `get_by_text` - 文本匹配
3. `get_by_placeholder` - 表单元素
4. CSS 选择器 - 降级方案

**避免**：
- 复杂的 XPath
- 依赖动态生成的 ID 或 class
- 过于具体的结构路径

### 3. 等待策略

```yaml
# 等待固定时间
- action: wait
  duration: 2000

# 等待元素出现
- action: wait
  selector: '.success-message'
  timeout: 10000
  
# 等待网络空闲
- action: wait
  wait_until: 'networkidle'
```

### 4. 错误处理

```yaml
error_handlers:
  # Element Plus 错误消息
  - selector: '.el-message--error'
    action: fail_task
    message: '操作失败'
    
  # 通用错误提示
  - selector: '[class*="error"]'
    action: retry
    max_attempts: 3
```

### 5. 成功标准

```yaml
success_criteria:
  # URL 包含特定路径
  - type: url_contains
    value: '/success'
    
  # 元素存在
  - type: element_exists
    selector: '.download-complete'
    
  # 文件已下载
  - type: file_downloaded
    pattern: '*.xlsx'
```

---

## 常见问题

### Q: Navigation 组件选择"示例数据域"有什么用？

A: 示例数据域仅用于录制演示，帮助你导航到一个具体页面进行录制。组件本身是通用的，运行时会根据 `params.data_domain` 参数动态导航。

### Q: 为什么导出组件必须选择数据域？

A: 因为不同数据域的导出流程和页面结构可能不同。系统根据数据域加载对应的导出组件，确保正确执行。

### Q: 如何处理复杂的日期选择器？

A: 建议录制"自定义日期"路径，使用 `{{params.date_from}}` 和 `{{params.date_to}}` 变量。避免录制"今天"、"最近7天"等快捷选项，因为这些值会随时间变化。

### Q: 组件录制完成后如何测试？

A: 
1. 在录制工具中点击"测试组件"
2. 选择测试账号
3. 观察浏览器执行过程
4. 查看测试结果和失败截图

---

## 相关文档

- [组件协作机制](./COMPONENT_COLLABORATION.md) - 组件间如何协作
- [快速启动指南](./QUICK_START_ALL_FEATURES.md) - 系统快速上手
- [V4.6.0 架构指南](../architecture/V4_6_0_ARCHITECTURE_GUIDE.md) - 系统架构说明

