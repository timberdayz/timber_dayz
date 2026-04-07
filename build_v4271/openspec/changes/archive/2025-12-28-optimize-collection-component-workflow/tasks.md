# Tasks: 优化数据采集组件工作流

## 概述

优化数据采集模块的组件录制和自动登录功能，解决以下核心问题：

1. 密码解密导入错误导致自动登录失败
2. 登录错误检测不完善，无法识别账号密码错误
3. 弹窗处理时机不当，导致后续步骤被遮挡
4. 架构规范缺失，导致密码解密问题反复发生

**总预估时间**: 2-3 天  
**优先级说明**: P0 = 阻塞性, P1 = 高优先级, P2 = 中优先级

---

## Phase 0: 紧急修复（P0）- 2025-12-25 已完成

### 0.1 修复密码解密导入错误 ✅

- [x] 0.1.1 修复 `launch_inspector_recorder.py` 的 `_decrypt_password` 方法

  - **问题**: 从 `modules.core.secrets_manager` 导入不存在的 `decrypt_password` 函数
  - **影响**: 自动登录时填入加密密码而非明文密码，导致登录失败
  - **修复**: 使用 `backend.services.encryption_service.get_encryption_service().decrypt_password()`

- [x] 0.1.2 增加空值检查和错误日志
  - 检查 `encrypted_password` 是否为空
  - 解密失败时记录警告日志
  - 失败时降级返回原值（可能是明文）

### 0.2 增强登录错误检测 ✅

- [x] 0.2.1 优化 `miaoshou/login.yaml` 的 `error_handlers`

  - 增加 Element Plus 错误消息检测 (`.el-message--error`)
  - 增加通用错误消息类名检测 (`[class*='error-message']`)
  - 增加文本匹配检测 (`text=用户名或密码错误`, `text=登录失败`)
  - 增加表单验证错误检测 (`.el-form-item__error`)

- [x] 0.2.2 优化登录组件步骤顺序
  - 登录按钮点击后立即处理弹窗 (`close_popups` action)
  - 分段等待：先等待登录响应(3s)，再等待页面稳定(2s)

### 0.3 增强弹窗处理时机 ✅

- [x] 0.3.1 在 `_verify_success_criteria` 方法前处理弹窗
  - 验证前调用 `popup_handler.close_popups()`
  - 等待弹窗关闭动画 (500ms)
  - 避免弹窗遮挡验证元素

### 0.4 补充架构规范文档 ✅

- [x] 0.4.1 在 `.cursorrules` 中添加"组件变量替换规范"章节
  - 明确 `{{account.password}}` 必须自动解密
  - 说明正确的导入方式 (`get_encryption_service().decrypt_password()`)
  - 记录历史教训（导入错误的函数导致登录失败）
  - 列出禁止行为

---

## Phase 1: 优化登录状态检测器（P0）✅ 2025-12-25 已完成

### 1.1 增强检测方法

- [x] 1.1.1 增加 Cookie 检测方法

  - 检查平台特定的认证 Cookie 是否存在
  - 支持 Cookie 过期检测（如果可能）
  - 将 Cookie 检测结果纳入综合判断

- [x] 1.1.2 增加等待自动跳转逻辑

  - 导航后等待最多 5 秒检测 URL 是否自动跳转
  - 如果 URL 从登录页跳转到已登录页，判断为已登录
  - 记录跳转前后的 URL 变化

- [x] 1.1.3 优化元素检测逻辑
  - 增加检测超时时间（可配置，默认 10 秒）
  - 增加重试机制（检测失败后等待 1 秒重试）
  - 优化选择器匹配

### 1.2 完善各平台检测规则

- [x] 1.2.1 优化妙手 ERP 检测规则

  - 处理 `redirect=` 参数（跳转后不带该参数表示已登录）
  - 增加更多已登录页面 URL 关键词
  - 完善认证 Cookie 列表

- [x] 1.2.2 优化 Shopee 检测规则

  - 检查现有 URL 关键词和选择器
  - 补充缺失的检测规则
  - 更新认证 Cookie 列表

- [x] 1.2.3 优化 TikTok 检测规则

  - 检查现有 URL 关键词和选择器
  - 补充缺失的检测规则
  - 更新认证 Cookie 列表

- [x] 1.2.4 优化 Amazon 检测规则
  - 检查现有 URL 关键词和选择器
  - 补充缺失的检测规则
  - 更新认证 Cookie 列表

### 1.3 增强综合判断逻辑

- [x] 1.3.1 优化结果合并算法

  - 综合 URL、元素、Cookie 三方检测结果
  - 优化置信度计算
  - 处理检测结果不一致的情况

- [x] 1.3.2 增加检测结果缓存
  - 在同一页面上下文中缓存检测结果
  - 缓存有效期 30 秒
  - URL 变化时清除缓存

---

## Phase 2: 优化自动登录流程（P0）✅ 2025-12-25 已完成

### 2.1 优化 `_auto_login` 方法

- [x] 2.1.1 增加等待自动跳转逻辑

  - 导航到 `login_url` 后等待页面稳定
  - 检测 URL 是否自动跳转（最多 5 秒）
  - 如果已跳转到已登录页，跳过登录组件执行

- [x] 2.1.2 优化检测时机

  - 快速检测（导航后立即检测）
  - 完整检测（等待 2 秒后再次检测）
  - 记录每次检测结果和耗时

- [x] 2.1.3 增强错误处理
  - 检测失败时降级为执行登录组件
  - 记录检测失败原因
  - 提供详细日志输出

### 2.2 增强登录后验证

- [x] 2.2.1 登录组件执行后再次检测

  - 执行登录组件后等待 3 秒
  - 使用检测器验证登录状态
  - 记录验证结果

- [x] 2.2.2 处理登录组件不存在
  - 如果登录组件不存在，记录错误
  - 提示用户手动登录
  - 返回明确错误信息

---

## Phase 3: 增强日志和调试（P1）✅ 2025-12-25 已完成

### 3.1 增强日志输出

- [x] 3.1.1 记录检测过程

  - 记录导航 URL
  - 记录各检测方法结果（URL、元素、Cookie）
  - 记录检测耗时

- [x] 3.1.2 记录跳过登录原因
  - 记录最终判断结果和置信度
  - 记录跳过登录的具体原因
  - 记录登录组件执行步骤（如果执行）

### 3.2 增加调试模式

- [x] 3.2.1 支持详细调试输出

  - 环境变量 `DEBUG_LOGIN_DETECTION=true` 启用
  - 输出所有检测步骤详细信息
  - 输出 JSON 格式检测结果

- [x] 3.2.2 支持截图功能
  - 检测失败时自动截图
  - 保存到 `temp/debug/login_detection/`
  - 记录截图路径

---

## Phase 4: 单元测试（P1）✅ 2025-12-25 已完成

### 4.1 测试登录状态检测器

- [x] 4.1.1 测试 URL 检测逻辑

  - 测试各平台 URL 匹配
  - 测试 `redirect=` 参数处理
  - 测试未知 URL 处理

- [x] 4.1.2 测试 Cookie 检测逻辑

  - 测试 Cookie 存在场景
  - 测试 Cookie 不存在场景
  - 测试 Cookie 过期场景

- [x] 4.1.3 测试综合判断逻辑
  - 测试各检测方法结果一致
  - 测试结果不一致时的处理
  - 测试置信度计算

### 4.2 测试自动登录流程

- [x] 4.2.1 测试已登录场景

  - 持久化会话已登录
  - 应跳过登录组件

- [x] 4.2.2 测试未登录场景

  - 持久化会话未登录
  - 应执行登录组件

- [x] 4.2.3 测试检测失败场景
  - 检测抛出异常
  - 应降级执行登录组件

---

## Phase 5: 前端组件录制界面改进（P0）- 2025-12-25 已完成

### 5.1 组件类型扩展

- [x] 5.1.1 在组件类型下拉框中添加 `filters`（筛选器）选项
- [x] 5.1.2 确保组件名称生成逻辑支持 `filters`

### 5.2 数据域选择功能

- [x] 5.2.1 添加 `dataDomain` 字段到 `recorderForm`
- [x] 5.2.2 添加数据域选择器（仅当组件类型为 `export` 时显示）
  - 数据域选项：orders, products, analytics, finance, services, inventory
- [x] 5.2.3 添加 `subDomain` 字段到 `recorderForm`
- [x] 5.2.4 添加服务子域选择器（仅当 `export` + `services` 时显示）
  - 子域选项：ai_assistant, agent
- [x] 5.2.5 添加 `exampleDataDomain` 字段到 `recorderForm`
- [x] 5.2.6 添加示例数据域选择器（仅当组件类型为 `navigation` 时显示）
  - 添加工具提示说明用途

### 5.3 组件名称生成逻辑

- [x] 5.3.1 更新 `watch` 监听器，包含 `dataDomain`、`subDomain`、`exampleDataDomain`
- [x] 5.3.2 导出组件名称生成：`{platform}_{dataDomain}_export` 或 `{platform}_{dataDomain}_{subDomain}_export`
- [x] 5.3.3 其他组件名称生成：`{platform}_{componentType}`

### 5.4 YAML 生成逻辑

- [x] 5.4.1 导出组件自动添加 `data_domain` 字段
- [x] 5.4.2 导出组件有子域时自动添加 `sub_domain` 字段
- [x] 5.4.3 Navigation 组件添加 `data_domain_urls` 映射表注释（基于示例数据域）

### 5.5 验证逻辑

- [x] 5.5.1 更新 `canStartRecording`，导出组件必须选择数据域
- [x] 5.5.2 其他组件类型不受数据域限制

### 5.6 用户体验

- [x] 5.6.1 添加数据域说明（工具提示）
- [x] 5.6.2 添加子域说明（何时需要选择）
- [x] 5.6.3 添加示例数据域说明（navigation 组件用途）

---

## Phase 6: 前端快速采集界面改进（P0）- 2025-12-25 已完成

### 6.1 数据域选项完善

- [x] 6.1.1 在快速采集面板中添加 `finance`（财务）选项
- [x] 6.1.2 在快速采集面板中添加 `services`（服务）选项
- [x] 6.1.3 在快速采集面板中添加 `inventory`（库存）选项

### 6.2 子域选择功能

- [x] 6.2.1 添加 `sub_domains` 字段到 `quickForm`
- [x] 6.2.2 条件显示子域选择器（仅当选择 `services` 时）
- [x] 6.2.3 支持多选子域
- [x] 6.2.4 添加子域说明提示

### 6.3 任务创建逻辑

- [x] 6.3.1 在 `createQuickTask` 中添加 `sub_domains` 参数

---

## Phase 7: 组件录制指导文档（P1）✅ 2025-12-25 已完成

### 7.1 创建组件录制指南

- [x] 7.1.1 创建 `docs/guides/COMPONENT_RECORDING_GUIDE.md`
- [x] 7.1.2 固定组件（login）的录制方法
- [x] 7.1.3 灵活组件（navigation, date_picker, filters）的参数化设计
- [x] 7.1.4 导出组件的录制方法（包含数据域选择）
- [x] 7.1.5 组件粒度划分原则（细粒度 vs 粗粒度）
- [x] 7.1.6 参数化组件设计模式（使用 `{{params.xxx}}` 变量）
- [x] 7.1.7 子组件调用模式（使用 `component_call`）

### 7.2 组件类型选择指南

- [x] 7.2.1 说明各组件类型的用途和使用场景
- [x] 7.2.2 何时使用 `filters` vs `date_picker` vs `navigation`
- [x] 7.2.3 提供组件类型选择决策树
- [x] 7.2.4 数据域选择说明（仅导出组件需要）

---

## Phase 8: 组件模板库和协作文档（P1）✅ 2025-12-25 已完成

### 8.1 创建缺失的组件模板

- [x] 8.1.1 创建 `config/collection_components/_templates/navigation.yaml`
- [x] 8.1.2 创建 `config/collection_components/_templates/date_picker.yaml`
- [x] 8.1.3 创建 `config/collection_components/_templates/filters.yaml`

### 8.2 组件协作机制文档

- [x] 8.2.1 创建 `docs/guides/COMPONENT_COLLABORATION.md`
- [x] 8.2.2 两层架构说明（执行器层面 + 组件内部）
- [x] 8.2.3 参数传递机制（统一参数结构、变量替换、参数合并）
- [x] 8.2.4 执行顺序说明（全局固定顺序 + 局部可配置顺序）
- [x] 8.2.5 依赖关系说明（声明式依赖 vs 实际调用）

---

## Phase 9: 执行器架构简化 - 方案 B（P0）✅ 2025-12-25 已完成

### 9.1 执行器简化

- [x] 9.1.1 分析 `executor_v2.py` 中的导航组件执行逻辑
  - 定位 Shopee 特殊执行顺序代码（约第 500-520 行）
  - 定位其他平台导航组件执行代码（约第 590-610 行）
- [x] 9.1.2 移除执行器层面的导航组件执行

  - 删除 Shopee 特殊执行顺序中的 navigation 和 shop_switch 部分
  - 删除其他平台的 navigation 和 shop_switch 组件执行
  - 保留 Login → Export 的核心流程

- [x] 9.1.3 移除 Shopee 特殊执行顺序逻辑

  - 删除平台判断分支（`if platform == 'shopee'`）
  - 统一所有平台执行顺序

- [x] 9.1.4 更新注释和文档字符串
  - 更新执行器顶部的执行顺序说明
  - 更新相关方法的 docstring

### 9.2 文档更新

- [x] 9.2.1 更新 `COMPONENT_COLLABORATION.md`

  - 修改执行顺序说明为：Login → Export
  - 删除 Shopee 特殊顺序说明
  - 强调导出组件自包含原则
  - 更新执行流程图

- [x] 9.2.2 更新 `COMPONENT_RECORDING_GUIDE.md`
  - 更新导出组件录制说明
  - 强调导出组件必须包含完整流程（导航 → 筛选 → 导出）
  - 添加子组件调用示例

### 9.3 验证

- [x] 9.3.1 验证执行器代码无语法错误
- [x] 9.3.2 验证现有单元测试仍然通过（34 tests passed）
- [x] 9.3.3 文档更新完成后复查一致性

---

## Phase 10: 增强事件监听与多选择器策略（P0）- 2025-12-26 新增

### 10.1 增强事件监听

- [x] 10.1.1 在 `launch_inspector_recorder.py` 中注入 JavaScript 监听器

  - 监听 click 事件，记录元素和选择器
  - 监听 input/change 事件，记录输入值
  - 监听 select 事件，记录选项
  - 生成多重选择器（role, text, css）

- [x] 10.1.2 更新 `_setup_event_listeners` 方法

  - 添加 `page.add_init_script()` 注入监听脚本
  - 通过 console.log 捕获事件（[RecorderEvent] 前缀）
  - 转换事件为 `recorded_steps` 格式

- [x] 10.1.3 与 Trace 录制互不干扰
  - Trace 继续捕获所有浏览器事件
  - 事件监听作为补充机制

### 10.2 多选择器生成

- [x] 10.2.1 更新 `TraceParser` 增强选择器生成

  - 从 Trace 事件中提取元素信息（text_content, element_role）
  - 生成 role、text、css 多种选择器
  - 按优先级排序

- [x] 10.2.2 选择器生成策略（内置于 JavaScript 和 TraceParser）
  - 支持从元素生成多重选择器
  - 优先级：role+name > text > css > position
  - 自动排除无意义的选择器（hash 类名等）

### 10.3 执行器多选择器支持

- [x] 10.3.1 更新 `executor_v2.py` 支持 `selectors` 字段

  - 新增 `_get_locator_with_fallback()` 方法
  - 解析步骤中的 `selectors` 数组
  - 按优先级尝试每个选择器，第一个成功则使用

- [x] 10.3.2 更新 click、fill、select 动作
  - 使用 `_get_locator_with_fallback()` 获取定位器
  - 支持超时和 legacy selector 降级
  - 记录成功的选择器类型

### 10.4 验证

- [ ] 10.4.1 验证事件监听捕获日期选择器操作
- [ ] 10.4.2 验证多选择器降级正常工作
- [ ] 10.4.3 验证不影响现有 Trace 功能

---

## Phase 11: 发现模式（Discovery Mode）- 2025-12-26 新增

### 11.1 后端录制工具发现模式

- [x] 11.1.1 在 `launch_inspector_recorder.py` 中添加发现模式

  - 根据 `component_type` 判断使用发现模式（date_picker, filters）
  - 识别重复的 open 动作（同一选择器的多次点击）
  - 将后续点击识别为选项发现

- [x] 11.1.2 实现选项去重和分类

  - 根据文本内容去重选项
  - 为每个选项生成 key（如 today, last_7_days）
  - 保存多重选择器

- [x] 11.1.3 输出发现模式的 JSON 结构
  - `open_action`: 打开动作配置
  - `available_options`: 发现的选项列表
  - `default_option`: 默认选项 key

### 11.2 后端 API 适配

- [x] 11.2.1 更新 `component_recorder.py` 返回结构

  - 步骤模式：返回 `steps` 数组
  - 发现模式：返回 `open_action` + `available_options`

- [x] 11.2.2 更新保存组件逻辑
  - 支持保存发现模式的 YAML 结构

### 11.3 执行器支持发现模式

- [x] 11.3.1 在 `executor_v2.py` 中添加发现模式执行

  - 检测组件类型（`type: date_picker` 或 `type: filters`）
  - 执行 `open_action`
  - 根据参数选择并点击对应选项

- [x] 11.3.2 更新 `component_loader.py` 验证逻辑（2025-12-27 已完成）
  - 添加 `filters` 到 `SUPPORTED_TYPES`
  - 添加 `DISCOVERY_MODE_TYPES` 定义
  - 支持验证 `open_action` + `available_options` 结构
  - 添加 `_validate_discovery_mode()` 方法
  - 添加 `_validate_steps()` 方法

### 11.4 前端发现模式显示

- [x] 11.4.1 在 `ComponentRecorder.vue` 中添加模式切换

  - 根据 `componentType` 判断显示模式
  - 步骤模式：当前的拖拽步骤列表
  - 发现模式：选项列表视图

- [x] 11.4.2 实现发现模式 UI

  - 打开动作编辑区（显示/编辑 open_action）
  - 已发现选项列表（显示/编辑/删除选项）
  - 添加选项按钮
  - 默认选项选择器

- [x] 11.4.3 更新 YAML 生成逻辑
  - 发现模式生成不同的 YAML 结构

### 11.5 验证

- [ ] 11.5.1 验证录制日期选择器时正确识别发现模式
- [ ] 11.5.2 验证选项正确去重和分类
- [ ] 11.5.3 验证前端正确显示选项列表
- [ ] 11.5.4 验证执行器正确执行发现模式组件

---

## 验证清单

### 紧急修复验证 (Phase 0) ✅

- [x] V0.1: 密码正确解密并填入登录表单
- [x] V0.2: 登录错误能被检测并报告
- [x] V0.3: 弹窗不再遮挡后续操作
- [x] V0.4: 架构规范文档已更新

### 自动登录检测验证 (Phase 1-2) ✅

- [x] V1: 妙手 ERP 持久化会话已登录时，正确跳过登录
- [x] V2: Shopee 持久化会话已登录时，正确跳过登录
- [x] V3: TikTok 持久化会话已登录时，正确跳过登录
- [x] V4: Cookie 检测正常工作
- [x] V5: 等待自动跳转逻辑正常工作
- [x] V6: 日志输出清晰，便于调试

### 录制流程验证 ✅

- [x] V7: 录制非 login 组件时，自动登录正常工作
- [x] V8: 录制 login 组件时，不执行自动登录
- [x] V9: 检测失败时，降级执行登录组件

### 前端组件录制界面验证 (Phase 5) ✅

- [x] V10: 组件类型下拉框包含 `filters` 选项
- [x] V11: 选择 `export` 时显示数据域选择器
- [x] V12: 选择 `export` + `services` 时显示子域选择器
- [x] V13: 选择 `navigation` 时显示示例数据域选择器（可选）
- [x] V14: 导出组件名称生成正确（包含数据域和子域）
- [x] V15: 导出组件 YAML 包含 `data_domain` 字段
- [x] V16: 导出组件必须选择数据域才能开始录制

### 前端快速采集界面验证 (Phase 6) ✅

- [x] V17: 快速采集面板包含所有 6 种数据域
- [x] V18: 选择 `services` 时显示子域选择器
- [x] V19: 创建任务时正确传递 `sub_domains` 参数

### 执行器架构简化验证 (Phase 9) ✅

- [x] V20: 执行器代码无语法错误
- [x] V21: 执行顺序统一为 Login → Export
- [x] V22: 移除 Shopee 特殊执行顺序逻辑
- [x] V23: 文档更新反映新架构

### 增强事件监听验证 (Phase 10)

- [ ] V24: 事件监听能捕获日期选择器操作
- [ ] V25: 多重选择器正确生成
- [ ] V26: 执行器多选择器降级正常工作
- [ ] V27: Trace 功能不受影响

### 发现模式验证 (Phase 11)

- [ ] V28: 录制 date_picker 组件时自动进入发现模式
- [ ] V29: 选项正确去重（相同文本不重复添加）
- [ ] V30: 前端正确显示选项列表（非步骤列表）
- [ ] V31: 执行器正确执行发现模式组件
- [ ] V32: YAML 生成正确的发现模式结构

---

## 依赖关系

```
Phase 0 (紧急修复) ✅ 已完成
    │
    ├──▶ Phase 1 (登录状态检测器优化) ✅ 已完成
    │       │
    │       └──▶ Phase 2 (自动登录流程优化) ✅ 已完成
    │               │
    │               ├──▶ Phase 3 (日志和调试) ✅ 已完成
    │               │
    │               └──▶ Phase 4 (单元测试) ✅ 已完成 (34 tests passed)
    │
    └──▶ Phase 5 (前端组件录制界面改进) ✅ 已完成
            │
            ├──▶ Phase 6 (前端快速采集界面改进) ✅ 已完成
            │
            └──▶ Phase 7 (组件录制指导文档) ✅ 已完成
                    │
                    └──▶ Phase 8 (组件模板库和协作文档) ✅ 已完成
                            │
                            └──▶ Phase 9 (执行器架构简化 - 方案B) ✅ 已完成
                                    │
                                    └──▶ Phase 10 (增强事件监听与多选择器) ✅ 已完成
                                            │
                                            └──▶ Phase 11 (发现模式) ✅ 已完成
```

---

## 注意事项

1. **通用性**：优化针对所有平台，不仅限于妙手 ERP
2. **向后兼容**：不破坏现有功能
3. **禁止 Emoji**：所有日志使用`[OK]`, `[ERROR]`等 ASCII 符号
4. **async_playwright**：在异步环境中使用 async_playwright
5. **统一解密服务**：使用 `backend.services.encryption_service.get_encryption_service()` 解密密码

---

## 修复记录

### 2025-12-25 Phase 0 紧急修复

**修复内容**：

1. `tools/launch_inspector_recorder.py`：修复 `_decrypt_password` 方法的导入路径
2. `config/collection_components/miaoshou/login.yaml`：增强错误检测和弹窗处理
3. `modules/apps/collection_center/executor_v2.py`：在成功标准验证前处理弹窗
4. `.cursorrules`：添加"组件变量替换规范"章节

**验证结果**：

- 密码解密：✅ 使用正确的 EncryptionService
- 登录错误检测：✅ 增加多种错误选择器
- 弹窗处理：✅ 验证前主动处理弹窗
- 架构规范：✅ 文档已更新

### 2025-12-25 Phase 5-8 前端和文档完善

**完成内容**：

1. `frontend/src/views/ComponentRecorder.vue`：

   - 添加 `filters` 组件类型选项
   - 添加数据域选择器（仅 export 组件）
   - 添加服务子域选择器（仅 services 数据域）
   - 添加示例数据域选择器（仅 navigation 组件）
   - 更新组件名称生成逻辑（支持数据域和子域）
   - 更新 YAML 生成逻辑

2. `frontend/src/views/CollectionTasks.vue`：

   - 添加 finance、services、inventory 数据域选项
   - 添加子域选择器

3. 文档创建：

   - `docs/guides/COMPONENT_RECORDING_GUIDE.md` - 组件录制指南
   - `docs/guides/COMPONENT_COLLABORATION.md` - 组件协作机制

4. 组件模板创建：
   - `config/collection_components/_templates/navigation.yaml`
   - `config/collection_components/_templates/date_picker.yaml`
   - `config/collection_components/_templates/filters.yaml`

**验证结果**：

- 前端组件录制界面：✅ 支持数据域选择
- 前端快速采集界面：✅ 支持完整数据域
- 组件录制指南：✅ 文档已创建
- 组件协作机制：✅ 文档已创建
- 组件模板库：✅ 模板已创建

### 2025-12-25 Phase 1-4 登录检测优化

**完成内容**：

1. `modules/utils/login_status_detector.py` (v4.8.0)：

   - Cookie 检测方法 (`_check_cookies`)
   - 等待自动跳转逻辑 (`_check_redirect`)
   - 元素检测带重试机制 (`_check_elements`)
   - 综合判断逻辑 (`_combine_results`)
   - 检测结果缓存机制
   - 调试模式和截图功能
   - 四大平台配置：shopee, tiktok, miaoshou, amazon

2. `tools/launch_inspector_recorder.py`：

   - 集成 LoginStatusDetector
   - 智能登录检测（快速检测 + 完整检测）
   - 登录后验证

3. `tools/record_component.py`：

   - 同步优化自动登录逻辑

4. `tests/unit/test_login_status_detector.py`：
   - 34 个单元测试全部通过

**验证结果**：

- URL 检测：✅ 各平台 URL 匹配正确
- Cookie 检测：✅ 认证 Cookie 检测正常
- 元素检测：✅ 登录表单和已登录元素检测正常
- 综合判断：✅ 多种检测结果正确合并
- 缓存机制：✅ 缓存有效期和失效逻辑正确
- 单元测试：✅ 34 tests passed

### 2025-12-25 Phase 9 执行器架构简化（方案 B）

**完成内容**：

1. `modules/apps/collection_center/executor_v2.py`：

   - 移除 Shopee 特殊执行顺序逻辑（navigation → shop_switch）
   - 移除其他平台的 navigation 和 shop_switch 组件执行
   - 简化执行顺序为：Login → Export（循环各数据域）
   - 更新执行器顶部注释说明新架构

2. `docs/guides/COMPONENT_COLLABORATION.md`：

   - 更新两层架构说明（执行器层面简化为 Login → Export）
   - 更新执行顺序说明（统一所有平台）
   - 更新执行流程图（导出组件自包含流程）
   - 删除 Shopee 特殊顺序说明

3. `docs/guides/COMPONENT_RECORDING_GUIDE.md`：

   - 添加导出组件自包含原则说明
   - 更新录制步骤（强调完整流程）
   - 更新示例 YAML（包含导航、店铺切换、日期选择、筛选、导出完整步骤）

**验证结果**：

- 执行器代码：✅ 无语法错误
- 执行顺序：✅ 统一为 Login → Export
- Shopee 特殊逻辑：✅ 已移除
- 文档更新：✅ 反映新架构
- 单元测试：✅ 34 tests passed

### 2025-12-27 Phase 12 发现模式组件测试配置

**问题背景**：

发现模式组件（date_picker, filters）缺少测试页面导航机制。
用户反馈：测试时需要知道导航到哪个页面才能找到日期选择器。

**解决方案**：

添加 `test_config` 配置字段，支持两种导航方式：

1. `test_url`: 直接使用 URL 导航到测试页面
2. `test_data_domain`: 使用 navigation 组件导航到对应数据域页面

**完成内容**：

1. `frontend/src/views/ComponentRecorder.vue`：

   - 添加测试配置区域（test_config section）
   - 支持选择 URL 导航或数据域导航
   - 更新 YAML 生成逻辑，包含 test_config 字段

2. `modules/apps/collection_center/component_loader.py`：

   - 更新 `_validate_discovery_mode` 验证 test_config
   - 检查 test_url 或 test_data_domain 的有效性
   - 警告缺失 test_config 的情况

3. `tools/test_component.py`：
   - 更新 `_validate_component_structure` 支持发现模式组件
   - 添加 `_validate_discovery_component` 验证发现模式结构
   - 添加 `_test_discovery_component` 测试发现模式组件
   - 添加 `_navigate_to_test_page` 使用 test_config 导航
   - 添加 `_execute_open_action` 执行打开动作
   - 添加 `_click_option` 点击选项

**发现模式测试流程**：

1. 导航到测试页面（使用 test_config）
2. 执行 open_action（打开选择器）
3. 循环测试每个 available_option：
   - 如果不是第一个选项，重新执行 open_action
   - 点击选项
   - 验证选择器关闭
4. 汇总测试结果

**YAML 结构示例**：

```yaml
name: miaoshou_date_picker
platform: miaoshou
type: date_picker

# 测试配置
test_config:
  test_url: "{{account.login_url}}/portal/sale/order"
  # 或者
  # test_data_domain: 'orders'

open_action:
  action: click
  selectors:
    - type: text
      value: "统计时间"

available_options:
  - key: today
    text: "今天"
    selectors:
      - type: text
        value: "今天"
  - key: last_7_days
    text: "最近7天"
    selectors:
      - type: text
        value: "最近7天"

default_option: last_7_days
```

**验证结果**：

- 前端配置区域：✅ 正确显示测试配置选项
- 组件验证：✅ 正确验证 test_config 字段
- 测试工具：✅ 支持发现模式组件测试
- Linter：✅ 无错误

### 2025-12-27 Phase 12.3 导出组件步骤标记功能

**问题背景**：

用户反馈导出组件录制流程过于复杂，需要自动识别日期和筛选器步骤。
用户建议简化为：手动标记哪些步骤是日期选择器、哪些是筛选器。

**解决方案**：

1. 步骤编辑器添加"步骤标记"下拉框
2. 添加批量选择和标记功能
3. 保存时自动将标记的步骤转换为 component_call
4. 测试对话框添加参数选择

**完成内容**：

1. `frontend/src/views/ComponentRecorder.vue`：

   - 修复 el-radio 兼容性问题（同时使用 value 和 label 属性）
   - 步骤编辑器添加"步骤标记"下拉框（普通/日期组件/筛选器）
   - 添加批量选择功能（全选、单选）
   - 添加批量标记按钮（标记为日期组件/筛选器/取消标记）
   - 添加步骤视觉标识（日期=橙色边框，筛选=绿色边框）
   - YAML 生成时将标记步骤转换为 component_call
   - 测试对话框添加参数选择（date_range, filter_value）

**新增 UI 元素**：

1. 批量操作工具栏：

   - 全选复选框
   - "标记为日期组件"按钮
   - "标记为筛选器"按钮
   - "取消标记"按钮
   - 已选择数量显示

2. 步骤编辑器增强：

   - 每个步骤前添加复选框
   - 步骤标签显示标记类型（日期/筛选）
   - "步骤标记"下拉框

3. 测试对话框增强：
   - 检测到日期组件步骤时显示日期范围选择
   - 检测到筛选器步骤时显示筛选值输入

**YAML 生成示例**：

标记前的步骤：

```yaml
steps:
  - action: navigate
    url: "/portal/sale/order"
  - action: click
    selector: ".date-picker"
  - action: click
    selector: ".today"
  - action: click
    selector: ".export-btn"
```

标记后的 YAML（步骤 2-3 标记为日期组件）：

```yaml
steps:
  - action: navigate
    url: "/portal/sale/order"
  # 以下步骤已标记为日期组件，建议替换为 component_call
  - action: component_call
    component: "miaoshou/date_picker"
    params:
      date_range: "{{params.date_range}}"
    comment: "调用日期选择器组件"
    # 原始录制步骤（供参考）:
    #   步骤1: click - .date-picker
    #   步骤2: click - .today
  - action: click
    selector: ".export-btn"
```

**验证结果**：

- 步骤标记功能：✅ 正常工作
- 批量选择功能：✅ 正常工作
- YAML 生成：✅ 正确转换为 component_call
- 测试参数选择：✅ 正常显示
- Linter：✅ 无错误
