## Context

采集录制流程为：前端点击录制 -> `launch_inspector_recorder.py` 启动持久化浏览器 + `page.pause()` -> 用户在 Inspector 中操作 -> JS 注入脚本捕获事件和选择器 -> 保存为 `steps.json` -> `steps_to_python.py` 生成 Python 组件代码。

当前 JS 注入（`_inject_event_capture_script`）仅通过 `element.getAttribute('role')` 检测显式 role，不检测 button/a/input 等标签的隐式角色，也不捕获 placeholder/label，导致大多数元素只能拿到 CSS 选择器。

生成器仅完整处理 login 场景，export 组件为空壳，select/press/download action 直接输出 TODO。

## Goals / Non-Goals

**Goals:**
- JS 注入生成的选择器质量接近 Playwright codegen（role > placeholder > label > text > css 优先级）
- 生成器输出覆盖 login、export、navigation、date_picker 四种组件类型
- 生成器支持 click、fill、navigate、wait、select、press、download 七种 action
- 生成代码可直接运行或仅需少量微调

**Non-Goals:**
- 不重构录制流程（保持 page.pause() + JS 注入模式）
- 不改前端录制页面
- 不替换为 Trace 解析方案（作为后续二期）
- 不处理已有手写组件的迁移

## Decisions

### D1：JS 注入增加隐式角色映射表

**选择**：在 JS 中维护一个 `tagName -> implicit role` 映射表，结合 `innerText` / accessible name 生成 role 选择器。

**理由**：
- 方案 A（调用 Playwright API 升级选择器）需要录制后额外一轮 Playwright 交互，增加复杂度和耗时
- 方案 B（JS 映射表）改动范围仅限一个 JS 函数，零依赖，立刻生效
- HTML 隐式角色是有限集（约 15 个标签），映射表维护成本极低

**映射范围**：

| 标签 | 隐式 role | name 来源 |
|------|-----------|-----------|
| `<button>` | button | innerText |
| `<a href>` | link | innerText |
| `<input type=text/email/search/tel/url>` | textbox | placeholder 或 label |
| `<input type=password>` | textbox | placeholder 或 label |
| `<input type=checkbox>` | checkbox | label |
| `<input type=radio>` | radio | label |
| `<input type=submit/button>` | button | value |
| `<select>` | combobox | label |
| `<textarea>` | textbox | placeholder 或 label |
| `<h1>`-`<h6>` | heading | innerText |
| `<nav>` | navigation | aria-label |
| `<img>` | img | alt |

### D2：选择器优先级调整为 role > placeholder > label > text > css

**选择**：在 JS 的 `generateSelectors` 函数中按此顺序 push 选择器，Python 侧 `_selector_from_selectors` 按数组顺序取第一个即可（当前逻辑不变）。

**理由**：
- role 最稳定（语义化，不受样式/结构变更影响）
- placeholder 对输入框极稳定（用户可见文本，改版时最后才变）
- label 同理
- text 作为兜底语义选择器
- css 只在以上全部不可用时使用

### D3：选择器唯一性验证

**选择**：生成每个选择器后，按类型使用不同方式验证匹配数量，结果记入 `unique: true/false` 字段。Python 侧 `_selector_from_selectors` 优先选取 `unique: true` 的选择器。

**验证方式（按选择器类型）**：

| 选择器类型 | 验证方式 |
|-----------|---------|
| CSS / 属性 | `document.querySelectorAll(selector).length` |
| placeholder | `document.querySelectorAll('[placeholder="..."]').length` |
| label | `document.querySelectorAll('label').length`（按文本过滤） |
| role（隐式） | `document.querySelectorAll(tagSelector).length`（如 `button`），再按 accessible name 过滤 |
| text | 使用 XPath `normalize-space(text())=...` 计数（已有实现） |

**Python 侧消费逻辑**：`_selector_from_selectors` 迭代选择器数组时，优先返回第一个 `unique: true` 的选择器。若最高优先级选择器（如 role）非唯一，降级到下一个唯一选择器（如 placeholder），并在生成代码中附加 `# 注意：role 选择器非唯一，已降级` 注释。若所有选择器均非唯一，取最高优先级并附加 `# 警告：选择器非唯一，建议人工收敛作用域` 注释。

**理由**：不唯一的选择器在生成代码中会导致 strict mode 报错。仅标记不消费等于白做，必须让生成器根据唯一性做出降级决策。

### D4：Export 组件生成下载模板

**选择**：生成器为 export 组件生成包含 `async with page.expect_download()` 的下载处理模板，包括文件保存、路径计算（`build_standard_output_root`）、超时处理。

**理由**：export 是采集系统的核心场景，空壳模板迫使用户从头手写下载逻辑。标准模板可覆盖 80% 导出场景。

### D5：非 login/export 组件继承正确基类

**选择**：
- navigation -> `NavigationComponent`，`run(self, page, target: TargetPage) -> NavigationResult`
- date_picker -> `DatePickerComponent`，`run(self, page, option: DateOption) -> DatePickResult`
- 其他未知类型 -> `ComponentBase`，`run(self, page) -> ResultBase`

注意：`target` 和 `option` 是**必选参数**（枚举类型），与基类签名一致，不加 `=None`。

**理由**：不继承基类会缺失 `self.logger`、`guard_overlays()`、`report_step()` 等基础能力，执行器也无法正确加载。

### D6：验证码后步骤保留策略

**选择**：`had_captcha_raise` 仅跳过验证码 fill 步骤本身之后的连续验证码相关步骤，非验证码步骤（如勾选框）继续生成，放在 raise 之前，并标注 `# 以下步骤在首次执行时运行（验证码暂停前）`。

**重排序风险**：这些步骤的执行顺序与录制顺序不同（原本在验证码 fill 之后，现在移到 raise 之前）。如果步骤依赖验证码区域已出现（如验证码输入框旁的勾选框），移到 raise 前可能找不到元素。生成代码中须附加注释提醒用户注意顺序。

**理由**：当前实现丢弃验证码后所有步骤，如果验证码与登录按钮之间有额外步骤会被永久丢失。保留并提醒优于直接丢弃。

## Risks / Trade-offs

- **[隐式角色覆盖不全]** -> 映射表只覆盖常见标签，自定义 Web Component 仍可能退化到 CSS。通过定期比对 WAI-ARIA 规范更新映射表缓解。
- **[选择器唯一性验证有时间开销]** -> 每个事件多一次 `querySelectorAll` 调用。电商页面 DOM 通常不超过数千节点，影响可忽略。
- **[Export 模板不适用所有平台]** -> 部分平台导出逻辑特殊（异步导出、新标签页下载等）。模板覆盖标准流程，特殊场景仍需人工编辑，但比空壳好得多。
- **[验证码后步骤重排序]** -> 非验证码步骤移到 raise 前执行，顺序与录制不同。若步骤依赖验证码区域已出现则会失败。通过注释提醒人工检查缓解。
- **[向后兼容]** -> 修改 JS 输出的 selectors 格式（新增 placeholder/label type、unique 字段）需确保 `_selector_from_selectors` 能正确处理。当前函数已有 placeholder/label 分支（之前是死代码），改后自然激活。新增 `unique` 字段消费逻辑需同步更新。
- **[success_criteria 传递链]** -> `generate_python_code` 新增 `success_criteria` 参数后，`component_recorder.py` 两处调用需同步修改传参。遗漏则验证码恢复块仍走硬编码逻辑。
