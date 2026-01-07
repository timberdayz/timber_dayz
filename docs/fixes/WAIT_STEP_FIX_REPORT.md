# Wait步骤修复报告

**日期**: 2025-12-20  
**提案**: verify-collection-and-sync-e2e  
**优先级**: P0（阻塞性）

## 问题描述

在验证数据采集录制模块时，发现wait步骤无法复现，到达该步骤时报错。

### 根本原因

1. **字段不一致**：
   - `executor_v2.py`使用`type`字段区分等待类型（timeout/selector/navigation）
   - `test_component.py`直接检查`duration`或`selector`存在，未使用`type`字段
   
2. **TODO占位符未检测**：
   - 录制工具生成的模板包含`selector: 'TODO: 填写等待的选择器'`
   - 验证逻辑未检测占位符，导致执行时Playwright找不到元素超时

3. **API不完整**：
   - test_component.py缺少`type='navigation'`支持（等待页面加载完成）

## 修复内容

### 1. 统一wait实现（tools/test_component.py）

**修复前**：
```python
elif action == 'wait':
    duration = step.get('duration')
    if duration:
        page.wait_for_timeout(duration)
    elif selector:
        page.wait_for_selector(selector, timeout=timeout)
```

**修复后**：
```python
elif action == 'wait':
    wait_type = step.get('type', 'timeout')
    
    if wait_type == 'timeout':
        duration = step.get('duration', 1000)
        page.wait_for_timeout(duration)
    
    elif wait_type == 'selector':
        selector = step.get('selector')
        state = step.get('state', 'visible')
        page.wait_for_selector(selector, state=state, timeout=timeout)
    
    elif wait_type == 'navigation':
        wait_until = step.get('wait_until', 'load')
        page.wait_for_load_state(wait_until, timeout=timeout)
```

### 2. 修复validation逻辑（tools/test_component.py）

**新增验证**：
- 检查`type`字段的有效性（timeout/selector/navigation）
- 检查必需字段（timeout需要duration，selector需要selector）
- 检测TODO占位符并报错

```python
if action == 'wait':
    wait_type = step.get('type', 'timeout')
    
    if wait_type == 'timeout':
        if 'duration' not in step:
            logger.error("wait步骤type='timeout'时必须提供'duration'字段")
            return False
    
    elif wait_type == 'selector':
        if 'selector' not in step:
            logger.error("wait步骤type='selector'时必须提供'selector'字段")
            return False
        
        # 检测TODO占位符
        selector_val = step.get('selector', '')
        if 'TODO' in str(selector_val).upper():
            logger.error("wait步骤包含TODO占位符，请手动完善或标记为optional")
            return False
```

### 3. 修复录制工具模板（tools/record_component.py）

**修复前**：
```python
{
    'action': 'wait',
    'selector': 'TODO: 填写等待的选择器',
    'state': 'visible',
    'timeout': 10000,
}
```

**修复后**：
```python
{
    'action': 'wait',
    'type': 'navigation',
    'wait_until': 'networkidle',
    'timeout': 30000,
    'comment': '等待页面加载完成（推荐：登录、导航场景）'
},
{
    'action': 'wait',
    'type': 'selector',
    'selector': 'TODO: 填写等待的选择器（如：.user-menu, .dashboard-header）',
    'state': 'visible',
    'timeout': 10000,
    'optional': True,  # 标记为可选
    'comment': '等待关键元素出现（请手动完善selector或删除此步骤）'
}
```

### 4. 修复miaoshou/login.yaml

**修复前**：
```yaml
- action: wait
  selector: 'TODO: 填写等待的选择器'
  state: visible
  timeout: 10000
```

**修复后**：
```yaml
- action: wait
  type: navigation
  wait_until: networkidle
  timeout: 30000
  comment: 等待页面加载完成

- action: wait
  type: selector
  selector: '.user-menu, .dashboard-header, [class*="nav"], [class*="menu"]'
  state: visible
  timeout: 10000
  optional: true
  comment: 等待登录成功后的关键元素出现（可选验证）
```

## Playwright官方API最佳实践

根据Playwright官方文档，wait步骤应该使用以下方式：

### 1. 等待页面加载（推荐⭐⭐⭐）

```yaml
- action: wait
  type: navigation
  wait_until: networkidle  # 或 'load', 'domcontentloaded'
  timeout: 30000
```

**适用场景**：
- 登录后等待页面跳转完成
- 导航到新页面
- 表单提交后等待响应

### 2. 等待元素出现（推荐⭐⭐）

```yaml
- action: wait
  type: selector
  selector: ".user-menu"
  state: visible  # 或 'attached', 'hidden', 'detached'
  timeout: 10000
```

**适用场景**：
- 等待关键元素出现（如用户菜单、导出按钮）
- 验证操作成功（如登录后的欢迎消息）

### 3. 固定延迟（不推荐⚠️）

```yaml
- action: wait
  type: timeout
  duration: 2000
```

**适用场景**：
- 仅在必要时使用（如已知的固定渲染延迟）
- 网络不稳定时不可靠

## 验证结果

运行验证脚本 `temp/verify_wait_fix.py`：

```
[TEST1] timeout缺少duration: PASS
[TEST2] selector缺少selector: PASS
[TEST3] selector包含TODO: PASS
[TEST4] 正确的timeout: PASS
[TEST5] 正确的selector: PASS
[TEST6] 正确的navigation: PASS

[OK] 所有验证测试通过！

[OK] 组件加载成功: miaoshou_login
[OK] 步骤数量: 3
[OK] 组件结构验证通过！
[OK] 找到 2 个wait步骤：
   1. type=navigation (wait_until=networkidle)
   2. type=selector (optional=True)

[SUCCESS] 所有测试通过！wait步骤修复成功
```

## 影响范围

### 修改的文件

1. ✅ `tools/test_component.py` - 统一wait实现和验证逻辑
2. ✅ `tools/record_component.py` - 修复生成的模板
3. ✅ `config/collection_components/miaoshou/login.yaml` - 修复现有配置

### 受益的场景

- ✅ 登录组件：等待页面跳转和登录成功验证
- ✅ 导航组件：等待页面加载完成
- ✅ 导出组件：等待导出按钮和下载开始
- ✅ 所有需要等待的组件步骤

## 后续建议

### 1. 录制新组件时

使用正确的wait格式：
```bash
python tools/record_component.py --platform miaoshou --component orders_export --account miaoshou_real_001
```

生成的YAML会自动包含正确的wait步骤。

### 2. 测试组件时

```bash
python tools/test_component.py --platform miaoshou --component login --account miaoshou_real_001
```

验证逻辑会自动检测：
- type字段是否正确
- 必需字段是否存在
- TODO占位符

### 3. 优先使用type='navigation'

对于需要等待页面加载的场景（登录、导航、表单提交），优先使用：
```yaml
- action: wait
  type: navigation
  wait_until: networkidle
```

而不是固定延迟：
```yaml
- action: wait
  type: timeout
  duration: 5000  # 不推荐
```

## 相关文档

- Playwright官方文档：https://playwright.dev/docs/api/class-page#page-wait-for-load-state
- 提案：`openspec/changes/verify-collection-and-sync-e2e/proposal.md`
- 任务清单：`openspec/changes/verify-collection-and-sync-e2e/tasks.md` (Phase 1.2)

## 总结

本次修复解决了wait步骤无法复现的问题，关键改进：

1. ✅ 统一了test_component.py和executor_v2.py的wait实现
2. ✅ 添加了type字段验证和TODO占位符检测
3. ✅ 修复了录制工具生成的模板，使用Playwright官方推荐的API
4. ✅ 所有验证测试通过

**现在可以继续进行提案的Phase 2（录制妙手ERP核心组件）。**

