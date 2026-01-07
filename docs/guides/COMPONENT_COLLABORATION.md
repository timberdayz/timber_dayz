# 组件协作机制

本文档说明数据采集组件之间如何协作工作。

## 目录

1. [两层架构](#两层架构)
2. [执行顺序](#执行顺序)
3. [参数传递](#参数传递)
4. [子组件调用](#子组件调用)
5. [错误处理与恢复](#错误处理与恢复)
6. [网络延迟处理](#网络延迟处理)

---

## 两层架构

### 第一层：执行器层面（简化架构 - Phase 9）

执行器（`executor_v2.py`）控制组件的全局执行顺序：

```
Login → Export（循环各数据域）
```

**执行顺序**：

| 顺序 | 组件类型 | 必需 | 说明 |
|-----|---------|------|------|
| 1 | `login` | 是 | 登录到平台 |
| 2 | `export` | 是 | 导出数据文件（自包含完整流程） |

**导出组件自包含原则**：

导出组件包含完整的数据采集流程：
- 导航到目标页面（URL 或点击菜单）
- 切换店铺（如需要）
- 选择日期范围
- 设置筛选条件
- 触发导出并下载文件

### 第二层：组件内部（component_call）

导出组件内部可以通过 `component_call` 调用可复用的子组件：

```yaml
# shopee/orders_export.yaml
steps:
  # 1. 导航到订单页面
  - action: navigate
    url: '{{account.login_url}}/portal/sale/order'
      
  # 2. 调用店铺切换组件（可选）
  - action: component_call
    component: 'shopee/shop_switch'
    optional: true
      
  # 3. 调用日期选择组件
  - action: component_call
    component: 'shopee/date_picker'
    params:
      date_from: '{{params.date_from}}'
      date_to: '{{params.date_to}}'
      
  # 4. 点击导出按钮
  - action: click
    selector: 'button:has-text("导出")'
    
  # 5. 等待下载
  - action: wait_for_download
    timeout: 60000
```

### 两层架构的优势

1. **简洁性**：执行器只关心 Login → Export，逻辑清晰
2. **自包含**：每个导出组件是完整独立的流程
3. **复用性**：date_picker、shop_switch、filters 作为子组件被复用
4. **无特殊逻辑**：所有平台执行顺序统一，无平台特殊分支

---

## 执行顺序

### 统一执行顺序（Phase 9）

所有平台使用统一的执行顺序：

```python
# executor_v2.py
# Phase 9 架构简化：所有平台统一执行顺序
COMPONENT_ORDER = ['login', 'export']
```

**为什么简化？**

1. **消除重复**：导航逻辑不再在执行器和导出组件中重复
2. **消除特殊分支**：不再需要 `if platform == 'shopee'` 特殊逻辑
3. **职责清晰**：执行器负责调度，导出组件负责完整流程

### 数据域循环

执行器会循环执行各数据域的导出组件：

```python
for domain in data_domains:
    component_name = f"{platform}/{domain}_export"
    export_component = load_component(component_name)
    await execute_component(export_component)
```

### 子组件复用

以下组件作为子组件被导出组件调用，不再由执行器直接执行：

| 子组件 | 用途 | 调用方式 |
|-------|------|---------|
| `navigation` | 导航到数据页面 | 或直接使用 `navigate` action |
| `shop_switch` | 切换店铺 | `component_call` |
| `date_picker` | 选择日期范围 | `component_call` |
| `filters` | 设置筛选条件 | `component_call` |

---

## 参数传递

### 统一参数结构

所有组件接收统一的参数结构：

```python
params = {
    # 账号信息
    'account': {
        'account_id': 'acc_123',
        'platform': 'shopee',
        'username': 'user@example.com',
        'password': '******',  # 已解密
        'shop_name': 'My Shop',
        'login_url': 'https://seller.shopee.com/login'
    },
    
    # 任务参数
    'params': {
        'data_domain': 'orders',
        'date_from': '2025-12-01',
        'date_to': '2025-12-25',
        'order_status': 'completed'
    },
    
    # 任务信息
    'task': {
        'task_id': 'task_abc123',
        'created_at': '2025-12-25T10:00:00'
    },
    
    # 平台信息
    'platform': 'shopee'
}
```

### 变量替换

组件 YAML 中的变量会在执行前被替换：

```yaml
# 原始
- action: fill
  value: '{{account.username}}'

# 替换后
- action: fill
  value: 'user@example.com'
```

### 密码自动解密

`{{account.password}}` 变量会自动解密：

```python
# ComponentLoader._replace_variables()
if var_path == "account.password":
    decrypted = encryption_service.decrypt_password(value)
    return decrypted
```

### 参数合并

子组件调用时，参数会合并：

```yaml
- action: component_call
  component: 'shopee/date_picker'
  params:
    date_from: '2025-12-01'  # 覆盖原有参数
    date_to: '2025-12-25'
```

```python
# 合并逻辑
merged_params = {**parent_params, **call_params}
```

---

## 子组件调用

### 基本语法

```yaml
- action: component_call
  component: '{platform}/{component_type}'
  params:
    key: value
```

### 完整示例

```yaml
# shopee_orders_export.yaml
name: shopee_orders_export
platform: shopee
type: export
data_domain: orders

steps:
  # 1. 调用导航组件
  - action: component_call
    component: 'shopee/navigation'
    params:
      data_domain: 'orders'
    comment: '导航到订单页面'
    
  # 2. 调用日期选择组件
  - action: component_call
    component: 'shopee/date_picker'
    params:
      date_from: '{{params.date_from}}'
      date_to: '{{params.date_to}}'
    comment: '选择日期范围'
    
  # 3. 调用筛选组件（可选）
  - action: component_call
    component: 'shopee/filters'
    params:
      order_status: '{{params.order_status}}'
    optional: true
    comment: '设置筛选条件'
    
  # 4. 执行导出
  - action: click
    selector: 'button:has-text("导出")'
    comment: '点击导出按钮'
    
  - action: wait_for_download
    timeout: 60000
    comment: '等待文件下载'
```

### 组件依赖声明

可以在组件中声明依赖（用于验证和文档）：

```yaml
dependencies:
  - component: 'shopee/navigation'
    required: true
  - component: 'shopee/date_picker'
    required: true
  - component: 'shopee/filters'
    required: false
```

---

## 错误处理与恢复

### 三层错误处理

1. **步骤级别**：`error_handlers` 在组件内处理
2. **组件级别**：`optional` 组件失败可跳过
3. **执行器级别**：全局错误处理和重试

### 步骤级别错误处理

```yaml
steps:
  - action: click
    selector: '.export-btn'
    error_handlers:
      - condition: 'element_not_found'
        action: retry
        max_attempts: 3
        delay: 1000
      - condition: 'timeout'
        action: screenshot
        then: fail
```

### 组件级别可选

```yaml
steps:
  - action: component_call
    component: 'shopee/filters'
    optional: true  # 失败时继续执行
```

### 执行器级别重试

```python
# executor_v2.py
MAX_COMPONENT_RETRIES = 3
RETRY_DELAY_MS = 2000

async def _execute_component_with_retry(self, component, params):
    for attempt in range(MAX_COMPONENT_RETRIES):
        try:
            return await self._execute_component(component, params)
        except RetryableError as e:
            if attempt < MAX_COMPONENT_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_MS / 1000)
            else:
                raise
```

---

## 网络延迟处理

### 多级等待策略

```python
async def _smart_wait_for_element(self, page, selector, timeout=30000):
    """
    智能等待策略：
    1. 快速检测（500ms）
    2. 关闭弹窗 + 重试
    3. 等待网络空闲
    4. 长等待
    """
    # 1. 快速检测
    try:
        await page.wait_for_selector(selector, timeout=500)
        return True
    except:
        pass
    
    # 2. 关闭弹窗 + 重试
    await self.popup_handler.close_popups(page)
    try:
        await page.wait_for_selector(selector, timeout=2000)
        return True
    except:
        pass
    
    # 3. 等待网络空闲
    try:
        await page.wait_for_load_state('networkidle', timeout=5000)
    except:
        pass
    
    # 4. 长等待
    await page.wait_for_selector(selector, timeout=timeout)
    return True
```

### 弹窗处理机制

三层弹窗处理：

1. **组件级别**：组件 YAML 中定义的 `popup_handling`
2. **平台级别**：平台特定的弹窗选择器
3. **通用级别**：ESC 键 + 通用关闭按钮

```python
# popup_handler.py
UNIVERSAL_POPUP_SELECTORS = [
    '.el-dialog__close',
    '.ant-modal-close',
    '[aria-label="Close"]',
    'button:has-text("关闭")',
    'button:has-text("取消")'
]

PLATFORM_POPUP_SELECTORS = {
    'shopee': [
        '.shopee-popup-close',
        '[data-dismiss="popup"]'
    ],
    'miaoshou': [
        '.el-message-box__close',
        '.el-notification__closeBtn'
    ]
}
```

### 超时配置

```yaml
# 组件级超时
timeout: 60000

# 步骤级超时
steps:
  - action: click
    selector: '.export-btn'
    timeout: 10000
    
  - action: wait_for_download
    timeout: 120000  # 下载可能需要更长时间
```

### 页面加载等待

```yaml
steps:
  - action: navigate
    url: '{{account.login_url}}'
    wait_until: 'networkidle'  # domcontentloaded | load | networkidle
    
  - action: wait
    duration: 1000
    comment: '等待渲染完成'
```

---

## 执行流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                    执行器 (Executor) - Phase 9                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 初始化浏览器                                                  │
│     └─> 持久化上下文 / 设备指纹                                    │
│                                                                  │
│  2. 检测登录状态                                                  │
│     ├─> 已登录: 跳过 login 组件                                   │
│     └─> 未登录: 执行 login 组件                                   │
│                                                                  │
│  3. 执行登录组件 (Login)                                         │
│     └─> [login] ─────────────────────────────────> 执行器层面    │
│                                                                  │
│  4. 循环执行各数据域导出                                          │
│     │                                                            │
│     │  for domain in [orders, products, services, ...]:          │
│     │                                                            │
│     └─> [export]  ───────────────────────────────> 执行器层面    │
│           │                                                      │
│           │  ┌────────────────────────────────────────────────┐  │
│           │  │          导出组件（自包含流程）                   │  │
│           │  ├────────────────────────────────────────────────┤  │
│           │  │                                                │  │
│           │  │  1. navigate: 导航到目标页面                    │  │
│           │  │                                                │  │
│           │  │  2. component_call: shop_switch (可选)         │  │
│           │  │                                                │  │
│           │  │  3. component_call: date_picker                │  │
│           │  │                                                │  │
│           │  │  4. component_call: filters (可选)             │  │
│           │  │                                                │  │
│           │  │  5. click: 导出按钮                             │  │
│           │  │                                                │  │
│           │  │  6. wait_for_download                          │  │
│           │  │                                                │  │
│           │  └────────────────────────────────────────────────┘  │
│           │                                                      │
│           └─> 返回下载的文件路径                                  │
│                                                                  │
│  5. 注册文件                                                      │
│     └─> 移动到 data/files/{platform}/{domain}/...                │
│                                                                  │
│  6. 更新任务状态                                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 相关文档

- [组件录制指南](./COMPONENT_RECORDING_GUIDE.md) - 如何录制组件
- [快速启动指南](./QUICK_START_ALL_FEATURES.md) - 系统快速上手
- [V4.6.0 架构指南](../architecture/V4_6_0_ARCHITECTURE_GUIDE.md) - 系统架构说明

