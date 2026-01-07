# 组件测试调试指南

**版本**: v4.7.3  
**更新日期**: 2025-12-22

---

## 📋 概述

本指南帮助您理解组件测试的执行过程，以及如何快速定位和解决测试失败的问题。

---

## 🔍 如何查看测试执行详情

### 1. 测试过程中

当您点击"开始测试"后：

1. **浏览器窗口会自动打开**（非 headless 模式）
   - ✅ 您可以**实时观看**浏览器执行每个步骤
   - ✅ 看到页面导航、点击、输入等操作
   - ✅ 看到弹窗出现和关闭

2. **控制台输出**（如果从命令行运行）
   ```
   [OK] Step 1: goto
   [OK] Step 2: click
   [OK] Step 3: fill
   [FAIL] Step 4: click - TimeoutError: Element not found
   ```

### 2. 测试完成后

前端会显示**完整的步骤执行详情**：

#### ✅ 测试概览卡片
- **总步骤数**: 10
- **成功步骤**: 7
- **失败步骤**: 3
- **总耗时**: 18,165ms
- **成功率**: 70%

#### 📋 步骤执行列表（Timeline 视图）

每个步骤显示：
- ✅ **步骤序号和动作**: "步骤 1: goto"
- ✅ **执行状态**: 成功（绿色）/ 失败（红色）/ 跳过（灰色）
- ✅ **耗时**: "7059.84ms"
- ✅ **错误信息**（如果失败）: "TimeoutError: Locator.click: Timeout 5000ms exceeded"
- ✅ **失败截图**（如果启用）: 点击查看大图

---

## 🐛 常见问题排查

### 问题 1: 步骤执行成功，但测试显示失败

**症状**:
```
✅ 步骤 1-10: 全部成功
❌ 测试结果: 失败
错误: Success criteria verification failed
```

**原因**: `success_criteria` 验证失败

**解决方法**:

1. **检查 URL 验证**
   ```yaml
   success_criteria:
     - type: url_contains
       value: '/welcome'  # 确保登录后 URL 包含这个路径
   ```
   
   **调试**: 在浏览器地址栏查看实际 URL，确认是否匹配

2. **检查元素存在性验证**
   ```yaml
   success_criteria:
     - type: element_exists
       selector: 'role=navigation'  # 确保元素存在
   ```
   
   **调试**: 使用 Playwright Inspector 检查元素是否存在

3. **临时解决**: 设置为 `optional: true`
   ```yaml
   success_criteria:
     - type: url_contains
       value: '/welcome'
       optional: true  # 失败不影响测试结果
   ```

---

### 问题 2: 步骤失败 - TimeoutError

**症状**:
```
❌ 步骤 3: click - TimeoutError: Locator.click: Timeout 5000ms exceeded
```

**可能原因**:

#### 原因 1: 元素未加载完成

**解决方法**: 在操作前添加等待步骤

```yaml
steps:
  - action: click
    selector: 'role=button[name=登录]'
  
  # ⭐ 添加等待，确保页面加载完成
  - action: wait
    type: navigation
    wait_until: networkidle
    timeout: 30000
  
  - action: click
    selector: 'role=button[name=下一步]'
```

#### 原因 2: 弹窗遮挡元素

**解决方法**: v4.7.2 已自动处理，但您可以手动添加

```yaml
steps:
  - action: click
    selector: 'role=button[name=登录]'
    max_retries: 3  # ⭐ 失败时自动关闭弹窗并重试
```

#### 原因 3: Selector 不正确

**解决方法**: 使用 Playwright Inspector 重新录制

```bash
# 启动 Playwright Inspector
playwright codegen https://erp.91miaoshou.com/login

# 悬停在元素上，复制推荐的 selector
# 优先使用 role-based selector:
#   role=button[name='登录']  ✅ 推荐
#   #login-btn                ❌ 易碎
```

---

### 问题 3: 无限循环登录

**症状**: 浏览器不断重复登录流程，没有停下来

**原因**: 登录后的 `success_criteria` 验证失败，导致重试

**解决方法**:

1. **检查登录组件的 success_criteria**
   ```yaml
   # config/collection_components/miaoshou/miaoshou_login.yaml
   success_criteria:
     - type: url_contains
       value: '/welcome'  # ⭐ 确保这个值正确
       optional: false
   ```

2. **确认登录后的实际 URL**
   - 手动登录一次
   - 查看浏览器地址栏
   - 更新 `success_criteria` 中的 `value`

3. **临时禁用验证**（调试用）
   ```yaml
   success_criteria:
     - type: url_contains
       value: '/welcome'
       optional: true  # ⭐ 临时设为可选
   ```

---

### 问题 4: 新弹窗出现后操作停滞

**症状**: 点击登录后，页面出现弹窗，后续操作无响应

**原因**: 弹窗遮挡了下一步要操作的元素

**解决方法**: v4.7.2 已自动处理

系统会：
1. 步骤失败时自动检测弹窗
2. 关闭弹窗
3. 等待页面稳定（networkidle + 0.5s）
4. 重试步骤（默认 2 次）

如果仍然失败，手动添加弹窗处理步骤：

```yaml
steps:
  - action: click
    selector: 'role=button[name=立即登录]'
  
  # ⭐ 显式处理弹窗
  - action: click
    selector: 'role=button[name=关闭此对话框]'
    optional: true  # 弹窗可能不出现
    timeout: 3000   # 缩短超时
  
  - action: click
    selector: 'role=button[name=我已知晓]'
    optional: true
    timeout: 3000
```

---

## 🛠️ 调试工具

### 1. Playwright Inspector（推荐）⭐⭐⭐

**启动方式**:
```bash
playwright codegen https://erp.91miaoshou.com/login
```

**功能**:
- ✅ 录制操作并生成代码
- ✅ 悬停在元素上查看推荐的 selector
- ✅ 实时测试 selector 是否有效
- ✅ 查看元素的 role、name、text 等属性

**使用技巧**:
1. 悬停在元素上
2. 查看 Inspector 底部的 selector
3. 优先使用 `role=xxx[name='yyy']` 格式
4. 复制到 YAML 配置中

### 2. Playwright Trace Viewer（失败分析）

**生成 trace**:
```yaml
# 在组件 YAML 中启用 trace
enable_trace: true
```

**查看 trace**:
```bash
playwright show-trace trace.zip
```

**功能**:
- ✅ 回放测试步骤
- ✅ 查看每个步骤的截图
- ✅ 查看网络请求
- ✅ 查看 DOM 快照
- ✅ 定位失败原因

### 3. 浏览器开发者工具

测试时浏览器会自动打开，您可以：
1. 打开开发者工具（F12）
2. 查看 Console 日志
3. 查看 Network 请求
4. 查看 Elements（DOM 结构）

---

## 📝 最佳实践

### 1. 使用官方推荐的 Selector

```yaml
# ✅ 推荐：role-based selector
selector: 'role=button[name=登录]'
selector: 'role=textbox[name=用户名]'
selector: 'text=欢迎'

# ❌ 不推荐：CSS selector（易碎）
selector: '#login-btn'
selector: '.user-input'
```

### 2. 为关键步骤添加等待

```yaml
steps:
  # 导航后等待
  - action: goto
    url: 'https://example.com'
    wait_until: domcontentloaded  # ⭐ 自动添加
  
  - action: wait
    type: navigation
    wait_until: networkidle  # ⭐ 自动添加
    timeout: 30000
  
  # 点击后等待（如果会触发页面跳转）
  - action: click
    selector: 'role=button[name=提交]'
  
  - action: wait
    type: navigation
    wait_until: networkidle
    timeout: 30000
```

### 3. 标记可选步骤

```yaml
steps:
  # 必需步骤
  - action: click
    selector: 'role=button[name=登录]'
  
  # 可选步骤（弹窗可能不出现）
  - action: click
    selector: 'role=button[name=关闭弹窗]'
    optional: true  # ⭐ 失败不影响测试
```

### 4. 设置合理的重试次数

```yaml
steps:
  # 容易失败的步骤，增加重试
  - action: click
    selector: 'role=button[name=加载更多]'
    max_retries: 5  # ⭐ 默认 2 次，可以增加
    timeout: 10000
```

---

## 🔄 测试失败后的处理流程

1. **查看测试结果详情**
   - 找到失败的步骤
   - 查看错误信息
   - 查看失败截图

2. **重现问题**
   - 点击"重新测试"
   - 观看浏览器执行过程
   - 确认问题是否稳定复现

3. **定位原因**
   - 使用本指南的"常见问题排查"
   - 使用 Playwright Inspector 检查元素
   - 检查 YAML 配置

4. **修复问题**
   - 更新 YAML 配置
   - 重新测试验证

5. **如果问题持续**
   - 重新录制组件（使用组件录制工具）
   - 检查账号是否有效
   - 检查网络连接

---

## 📞 获取帮助

如果以上方法都无法解决问题：

1. **查看日志**
   - 后端日志: `logs/app.log`
   - 前端控制台: F12 → Console

2. **提供详细信息**
   - 组件名称和版本
   - 失败的步骤序号
   - 完整的错误信息
   - 失败截图

3. **重新录制**
   - 使用组件录制工具重新录制
   - 系统会自动生成优化的配置

---

## 🎯 总结

**v4.7.3 改进后，您可以：**

1. ✅ **实时观看**浏览器执行每个步骤
2. ✅ **详细查看**每个步骤的执行结果和耗时
3. ✅ **快速定位**失败的步骤和原因
4. ✅ **查看截图**了解失败时的页面状态
5. ✅ **自动重试**失败的步骤（关闭弹窗后重试）

**不再"盲测"！每个操作都清晰可见！** 👀

---

**相关文档**:
- [v4.7.2 改进日志 - 智能重试与弹窗处理](../changelogs/v4.7.2_intelligent_retry_and_popup_handling.md)
- [Playwright 官方文档](https://playwright.dev/python/docs/intro)
- [组件录制工具指南](./COMPONENT_RECORDER_GUIDE.md)

