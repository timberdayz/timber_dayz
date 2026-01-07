# Change: 优化数据采集组件工作流

## Why

当前数据采集模块虽然架构完善（归档提案 `2025-12-19-refactor-collection-module`），但存在以下问题影响实际可用性：

### P0 阻塞性问题（2025-12-25 已修复）

1. **密码解密导入错误**：`launch_inspector_recorder.py` 的 `_decrypt_password` 方法从错误的模块导入函数，导致自动登录时填入加密密码而非明文密码
2. **登录错误检测不完善**：`miaoshou/login.yaml` 的 `error_handlers` 选择器不够准确，无法识别账号密码错误
3. **弹窗处理时机不当**：登录后弹窗遮挡页面，导致后续步骤无法执行
4. **架构规范缺失**：密码解密问题多次发生，`.cursorrules` 中缺乏相关规范

### P1 优化问题（待处理）

5. **自动登录检测不准确**：录制非 login 组件时，自动登录检测逻辑存在问题，导致即使持久化会话已登录也可能重新执行登录
6. **登录状态检测时机不当**：导航到 login_url 后等待时间不足，无法正确检测自动跳转
7. **缺乏 Cookie 检测**：未检查认证 Cookie 是否存在，仅依赖 URL 和元素检测
8. **平台检测规则不完善**：各平台的检测规则（URL 关键词、选择器等）可能不够准确

**根本原因**：

- 密码解密逻辑分散在多处，导入路径不统一
- 登录状态检测器（`LoginStatusDetector`）的检测逻辑需要优化
- 组件执行器的弹窗处理时机不够智能

## What Changes

### Phase 0: 紧急修复（P0）✅ 2025-12-25 已完成

#### 0.1 修复密码解密导入错误 ✅

- 修复 `tools/launch_inspector_recorder.py` 的 `_decrypt_password` 方法
- 使用 `backend.services.encryption_service.get_encryption_service().decrypt_password()`
- 增加空值检查和错误日志

#### 0.2 增强登录错误检测 ✅

- 优化 `config/collection_components/miaoshou/login.yaml` 的 `error_handlers`
- 增加 Element Plus 错误消息检测 (`.el-message--error`)
- 增加文本匹配检测 (`text=用户名或密码错误`, `text=登录失败`)
- 增加表单验证错误检测 (`.el-form-item__error`)

#### 0.3 增强弹窗处理时机 ✅

- 登录组件中添加 `close_popups` 动作
- 在 `_verify_success_criteria` 方法前处理弹窗
- 避免弹窗遮挡验证元素

#### 0.4 补充架构规范文档 ✅

- 在 `.cursorrules` 中添加"组件变量替换规范"章节
- 明确 `{{account.password}}` 必须自动解密
- 记录历史教训和禁止行为

### Phase 1: 优化登录状态检测器（P0）✅ 2025-12-25 已完成

- ✅ 增强检测方法：
  - 增加 Cookie 检测（检查平台特定的认证 Cookie）
  - 增加等待自动跳转逻辑（最多等待 5 秒检测 URL 变化）
  - 优化元素检测超时和重试机制
- ✅ 完善各平台检测规则：
  - 优化 URL 关键词匹配（处理`redirect=`等参数）
  - 补充缺失的选择器
  - 增加更多已登录状态的标识

### Phase 2: 优化自动登录流程（P0）✅ 2025-12-25 已完成

- ✅ 优化 `_auto_login` 方法：
  - 增加等待自动跳转逻辑
  - 优化检测时机（快速检测 + 完整检测）
  - 增强错误处理和降级策略
- ✅ 登录后验证：
  - 执行登录组件后再次检测登录状态
  - 处理登录组件不存在的情况

### Phase 3: 增强日志和调试（P1）✅ 2025-12-25 已完成

- ✅ 记录检测过程：URL 检测、元素检测、Cookie 检测结果
- ✅ 记录检测耗时和最终判断
- ✅ 支持调试模式（环境变量启用详细日志）
- ✅ 检测失败时自动截图

### Phase 4: 单元测试（P1）✅ 2025-12-25 已完成

- ✅ 测试 `LoginStatusDetector` 各检测方法（34 tests passed）
- ✅ 测试 `_auto_login` 不同场景
- ✅ 测试完整录制流程

### Phase 5: 前端组件录制界面改进（P0）- 2025-12-25 新增

#### 5.1 组件类型扩展

- 在组件类型下拉框中添加 `filters`（筛选器）选项
- 确保组件名称生成逻辑支持 `filters`

#### 5.2 数据域选择功能

- 添加数据域选择器（仅当组件类型为 `export` 时显示）
- 数据域选项：orders, products, analytics, finance, services, inventory
- 添加服务子域选择器（仅当 `export` + `services` 时显示）
- 子域选项：ai_assistant, agent
- 添加示例数据域选择器（仅当组件类型为 `navigation` 时显示，可选）

#### 5.3 组件名称生成逻辑

- 导出组件：`{platform}_{dataDomain}_export` 或 `{platform}_{dataDomain}_{subDomain}_export`
- 其他组件：`{platform}_{componentType}`

#### 5.4 YAML 生成逻辑

- 导出组件自动添加 `data_domain` 字段
- 导出组件有子域时自动添加 `sub_domain` 字段
- Navigation 组件添加 `data_domain_urls` 映射表（基于示例数据域）

#### 5.5 验证逻辑

- 更新 `canStartRecording`，导出组件必须选择数据域
- 其他组件类型不受数据域限制

### Phase 6: 前端快速采集界面改进（P0）- 2025-12-25 新增

#### 6.1 数据域选项完善

- 在快速采集面板中添加 `finance`（财务）选项
- 在快速采集面板中添加 `services`（服务）选项
- 在快速采集面板中添加 `inventory`（库存）选项

#### 6.2 子域选择功能

- 添加 `sub_domains` 字段到 `quickForm`
- 条件显示子域选择器（仅当选择 `services` 时）
- 在 `createQuickTask` 中添加 `sub_domains` 参数

### Phase 7: 组件录制指导文档（P1）✅ 2025-12-25 已完成

- ✅ 创建 `docs/guides/COMPONENT_RECORDING_GUIDE.md`
- ✅ 固定组件（login）的录制方法
- ✅ 灵活组件（navigation, date_picker, filters）的参数化设计
- ✅ 导出组件的录制方法（包含数据域选择）
- ✅ 组件粒度划分原则和参数化组件设计模式

### Phase 8: 组件模板库和协作文档（P1）✅ 2025-12-25 已完成

- ✅ 创建缺失的组件模板（navigation, date_picker, filters）
- ✅ 创建 `docs/guides/COMPONENT_COLLABORATION.md`
- ✅ 两层架构说明（执行器层面 + 组件内部）
- ✅ 参数传递机制和依赖关系说明

### Phase 9: 执行器架构简化 - 方案 B（P0）- 2025-12-25 新增

#### 问题分析

当前执行器存在导航逻辑重复问题：

- 执行器层面执行 `navigation` 组件（负责从登录后跳转到数据域页面）
- 导出组件内部也需要处理导航（因为需要知道在哪个页面进行筛选和导出）
- Shopee 平台有特殊执行顺序（Login → Navigation → Shop Switch → Export）

#### 方案 B：导出组件自包含（已批准）

**核心思想**：将所有导航、筛选、日期选择逻辑集中到导出组件内部

**执行器简化为**：

```
Login → Export（循环各数据域）
```

**导出组件职责**：

1. 导航到目标页面（URL 或点击菜单）
2. 切换店铺（如需要）
3. 选择日期范围
4. 设置筛选条件
5. 触发导出并下载文件

**子组件复用**：

- `date_picker` - 被导出组件通过 `component_call` 调用
- `shop_switch` - 被导出组件通过 `component_call` 调用
- `filters` - 被导出组件通过 `component_call` 调用

#### 9.1 执行器简化

- 移除执行器层面的 `navigation` 组件执行
- 移除 Shopee 平台的特殊执行顺序逻辑
- 统一所有平台为：`Login → Export`

#### 9.2 文档更新

- 更新 `COMPONENT_COLLABORATION.md` 反映新架构
- 更新 `COMPONENT_RECORDING_GUIDE.md` 说明导出组件的完整录制流程

#### 9.3 组件结构规范

- 导出组件必须是自包含的（从导航到下载完成）
- 可以内嵌步骤或调用子组件
- 执行器只关心 `action` 字段，不理解业务含义

### Phase 10: 增强事件监听与多选择器策略（P0）- 2025-12-26 新增

#### 问题分析

当前录制工具存在以下问题：

1. **事件监听不完整**：只监听 `framenavigated`，不捕获 click、fill 等交互
2. **选择器覆盖率低**：单一选择器无法覆盖所有平台和场景
3. **日期选择器录制丢失**：Inspector 操作未被正确捕获

#### 10.1 增强事件监听（方案 A）

在录制脚本中注入 JavaScript 监听器，实时捕获用户交互：

- 监听 click 事件，生成 click 步骤
- 监听 input/change 事件，生成 fill 步骤
- 监听 select 事件，生成 select 步骤
- 与 Trace 录制并行工作，互不干扰

#### 10.2 多选择器降级策略

为每个步骤生成多重选择器，按优先级降级：

| 优先级 | 选择器类型  | 示例                          | 稳定性   |
| ------ | ----------- | ----------------------------- | -------- |
| 1      | role + name | `role=option[name="最近7天"]` | 最稳定   |
| 2      | 文本匹配    | `text="最近7天"`              | 较稳定   |
| 3      | 关键类名    | `.shortcut-7days`             | 较稳定   |
| 4      | 属性选择器  | `[data-range="7days"]`        | 可能变化 |
| 5      | 位置选择器  | `li:nth-child(2)`             | 易变化   |

#### 10.3 执行器多选择器支持

执行步骤时按优先级尝试多个选择器：

```yaml
- action: click
  selectors:
    - type: role
      value: 'option[name="最近7天"]'
    - type: text
      value: "最近7天"
    - type: css
      value: ".shortcut-7days"
```

### Phase 11: 发现模式（Discovery Mode）- 2025-12-26 新增

#### 问题分析

日期选择器和筛选器组件与登录、导出组件有本质区别：

| 组件类型             | 录制模式     | 执行逻辑                 |
| -------------------- | ------------ | ------------------------ |
| login, export        | 顺序步骤     | 按顺序执行所有步骤       |
| date_picker, filters | **选项发现** | 执行 open + 选择一个选项 |

**问题**：每个平台的日期选项不同（如 Miaoshou 有"最近 30 天"，TikTok 有"最近 28 天"），需要录制发现所有可用选项。

#### 11.1 发现模式设计

**录制流程**：

1. 用户点击日期控件（记录为 `open_action`）
2. 用户点击"今天"（添加到 `available_options`）
3. 用户再次点击日期控件（识别为重复 open）
4. 用户点击"昨天"（添加到 `available_options`）
5. ...以此类推

**组件结构**：

```yaml
name: date_picker
platform: miaoshou
type: date_picker

open_action:
  action: click
  selector: ".date-picker-trigger"

available_options:
  - key: today
    text: "今天"
    selectors: [...]
  - key: last_7_days
    text: "最近7天"
    selectors: [...]

params:
  date_range:
    type: enum
    values: [today, last_7_days, ...]
    default: last_7_days
```

#### 11.2 前端显示

发现模式组件不显示为步骤列表，而是显示为：

- 打开动作编辑区
- 已发现选项列表
- 默认选项选择器

#### 11.3 执行逻辑

执行器处理发现模式组件时：

1. 执行 `open_action`（打开日期选择器）
2. 根据 `params.date_range` 找到对应选项
3. 使用该选项的 `selectors` 点击

### Phase 12: 发现模式组件测试配置（P0）- 2025-12-27 新增 ✅

#### 问题分析

发现模式组件（date_picker, filters）缺少测试页面导航机制：

- 测试工具不知道应该导航到哪个页面才能找到日期选择器
- 用户录制后无法独立测试组件

#### 12.1 test_config 配置

添加 `test_config` 字段，支持两种导航方式：

1. **test_url**: 直接使用 URL 导航
2. **test_data_domain**: 调用 navigation 组件导航

**组件结构**：

```yaml
test_config:
  test_url: "{{account.login_url}}/portal/sale/order"
  # 或者
  # test_data_domain: 'orders'
```

#### 12.2 前端配置界面

在发现模式编辑器中添加：

- 测试方式选择（URL / 数据域）
- URL 输入框（支持变量）
- 数据域选择器

#### 12.3 测试流程

1. 读取 `test_config`
2. 导航到测试页面
3. 执行 `open_action`
4. 循环测试每个 `available_option`
5. 汇总测试结果

### Phase 12.4: 导出组件步骤标记功能（P0）- 2025-12-27 新增 ✅

#### 问题分析

用户反馈导出组件录制流程复杂，需要明确标记日期和筛选器步骤：

- 自动识别增加开发复杂度
- 用户手动标记更加可控

#### 12.4.1 步骤标记功能

前端步骤编辑器增强：

1. **步骤标记下拉框**：普通步骤 / 日期组件 / 筛选器
2. **批量选择**：全选、单选复选框
3. **批量标记按钮**：标记为日期组件/筛选器/取消标记
4. **视觉标识**：日期=橙色边框，筛选=绿色边框

#### 12.4.2 YAML 生成转换

保存时自动将标记步骤转换为 `component_call`：

```yaml
# 标记前
steps:
  - action: click
    selector: '.date-picker'
  - action: click
    selector: '.today'

# 标记后（步骤标记为 date_picker）
steps:
  - action: component_call
    component: 'platform/date_picker'
    params:
      date_range: '{{params.date_range}}'
```

#### 12.4.3 测试参数选择

测试对话框增强：

- 检测到日期组件步骤时显示日期范围选择
- 检测到筛选器步骤时显示筛选值输入

## Impact

### 受影响的规格（Affected Specs）

- **data-collection** (MODIFIED) - 优化自动登录检测要求

### 受影响的代码（Affected Code）

**Phase 0 已修改的文件** ✅：

- `tools/launch_inspector_recorder.py` - 修复 `_decrypt_password` 导入路径
- `config/collection_components/miaoshou/login.yaml` - 增强错误检测和弹窗处理
- `modules/apps/collection_center/executor_v2.py` - 验证前处理弹窗
- `.cursorrules` - 添加组件变量替换规范

**Phase 1-4 已修改的文件** ✅：

- ✅ `modules/utils/login_status_detector.py` - 增强检测逻辑（v4.8.0）
- ✅ `tools/launch_inspector_recorder.py` - 优化自动登录流程
- ✅ `tools/record_component.py` - 同步优化自动登录逻辑
- ✅ `tests/unit/test_login_status_detector.py` - 34 个单元测试全部通过

**Phase 5-6 已修改的文件** ✅：

- `frontend/src/views/ComponentRecorder.vue` - 添加数据域选择器、更新组件名称生成逻辑、更新 YAML 生成逻辑
- `frontend/src/views/CollectionTasks.vue` - 添加完整数据域选项、添加子域选择器

**Phase 9 已修改的文件** ✅：

- `modules/apps/collection_center/executor_v2.py` - 移除导航组件执行，简化执行顺序
- `docs/guides/COMPONENT_COLLABORATION.md` - 更新为新架构
- `docs/guides/COMPONENT_RECORDING_GUIDE.md` - 更新导出组件录制说明

**Phase 10 已修改的文件** ✅：

- `tools/launch_inspector_recorder.py` - 增强事件监听，注入 JavaScript 捕获 click/fill/select
- `backend/utils/trace_parser.py` - 增强选择器生成策略，支持多选择器输出
- `modules/apps/collection_center/executor_v2.py` - 新增 `_get_locator_with_fallback()` 支持多选择器降级

**Phase 11 已修改的文件** ✅：

- `tools/launch_inspector_recorder.py` - 添加发现模式，识别重复 open 动作
- `backend/routers/component_recorder.py` - 返回不同数据结构（步骤 vs 选项）
- `modules/apps/collection_center/executor_v2.py` - 支持发现模式组件执行
- `modules/apps/collection_center/component_loader.py` - 验证发现模式结构（2025-12-27）
- `frontend/src/views/ComponentRecorder.vue` - 选项列表显示模式

**Phase 12 已修改的文件** ✅：

- `frontend/src/views/ComponentRecorder.vue` - 添加测试配置区域（test_config）
- `modules/apps/collection_center/component_loader.py` - 验证 test_config 字段
- `tools/test_component.py` - 支持发现模式组件测试（导航、open_action、选项测试）

**Phase 12.3 已修改的文件** ✅：

- `frontend/src/views/ComponentRecorder.vue` - 添加步骤标记功能（批量选择、日期组件/筛选器标记、YAML 生成 component_call、测试参数选择）

**新增文件** ✅：

- ✅ `docs/guides/COMPONENT_RECORDING_GUIDE.md` - 组件录制指南
- ✅ `docs/guides/COMPONENT_COLLABORATION.md` - 组件协作机制文档
- ✅ `config/collection_components/_templates/navigation.yaml` - Navigation 模板
- ✅ `config/collection_components/_templates/date_picker.yaml` - Date Picker 模板
- ✅ `config/collection_components/_templates/filters.yaml` - Filters 模板
- `tests/unit/test_login_status_detector.py` - 检测器单元测试（待 Phase 4）

### 破坏性变更（Breaking Changes）

**无破坏性变更** - 本 change 仅增强现有功能，不修改 API 契约或数据模型。

## Non-Goals

- **不添加新平台支持**：仅优化现有平台（妙手 ERP/Shopee/TikTok/Amazon）
- **不修改录制模式**：继续使用 Inspector 模式
- **不修改数据库 Schema**：使用现有表结构

## 验证指标

### 自动登录检测指标

| 指标                         | 目标值 | 验证方法                 |
| ---------------------------- | ------ | ------------------------ |
| 检测准确率                   | >= 95% | 100 次测试中正确判断次数 |
| 检测耗时                     | < 5 秒 | 包括等待自动跳转时间     |
| 误报率（已登录误判为未登录） | < 5%   | 持久化会话测试           |

### 测试场景

1. 持久化会话已登录 → 应跳过登录，直接开始录制
2. 持久化会话未登录 → 应执行登录组件，然后开始录制
3. 检测结果不确定 → 应执行登录组件作为保险

## 技术约束

### 遵循项目开发规范

- **SSOT**: 不重复定义 ORM 模型，从`modules/core/db`导入
- **async_playwright**: 在 FastAPI 异步框架中必须使用 async_playwright
- **禁止 Emoji**: 所有日志和输出使用 ASCII 符号

### 组件变量替换规范（v4.7.6 新增）

- **密码必须解密**：`{{account.password}}` 变量替换时必须自动解密
- **统一解密服务**：使用 `backend.services.encryption_service.get_encryption_service().decrypt_password()`
- **禁止错误导入**：不要从 `modules.core.secrets_manager` 导入 `decrypt_password`（该函数不存在）

### Playwright 使用规范

- 使用官方 API（`get_by_role`、`get_by_text`等）
- 避免硬编码选择器
- 使用适当的等待机制
