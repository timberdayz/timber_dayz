## Context

当前 `steps_to_python.py` 在生成 login 组件时注入了约 150 行的"框架逻辑"：

1. **门卫检测**（lines 144-204）：`_login_element_candidates` 循环 + `to_have_count(1)` + `_route_markers` URL 检测，用于判断"是否已到达登录页"。
2. **容器发现**（lines 206-237）：`_form_candidates` 循环 + `to_have_count(1)` + page 根作用域兜底，用于"定位登录表单容器"。

这些逻辑在真实页面上频繁失败（妙手 ERP 登录页有 8 个 `input[type='password']`、2 个登录按钮、无 `<form>` 语义标签），且与业界主流实践（Playwright Codegen、n8n、Puppeteer Recorder）相悖——业界工具只生成操作回放代码，框架能力在执行环境中提供。

当前系统中已存在手动优化的 `miaoshou_login.py` 成功运行，其设计正是"简洁回放 + 显式容器"——不含泛化门卫或容器搜索，直接使用录制时确定的 `#J_loginRegisterForm`。本次重构将这一成功模式固化到生成器中。

## Goals / Non-Goals

**Goals:**
- 生成器产出的 login 组件代码 <= 50 行框架代码（URL 导航 + 验证码处理），其余为用户录制步骤的忠实回放
- 页面就绪检测（"登录页是否可操作"）移至 `test_component.py` 和 `executor_v2.py` 的调用层，使用 `locator.first.wait_for(state="visible")` 替代 `to_have_count(1)`
- 生成代码在妙手 ERP 等真实页面上无首步失败
- 回归测试覆盖：无门卫/无容器发现场景下的生成输出

**Non-Goals:**
- 不重写测试框架整体架构（仅在调用 login 组件前增加就绪检测）
- 不修改 executor_v2 的核心组件调度逻辑
- 不影响 export/navigation/date_picker 等非 login 组件的生成逻辑
- 不修改已存在的手动组件（如 `miaoshou_login.py`）

## Decisions

### Decision 1: 生成器 login 组件移除门卫检测和容器发现

**选择**：直接移除 `_login_element_candidates` 循环、`_route_markers` 检测、`_form_candidates` 循环。

**替代方案**：
- A) 保留但改用 `.first` 替代 `to_have_count(1)` —— 掩盖歧义，违反规范口径
- B) 保留但改为 warning 而非 hard fail —— 仍然是 150 行冗余代码
- C) **移除（选定）** —— 与业界一致，生成代码只包含录制操作

**理由**：门卫检测和容器发现是运行时关注点（"页面是否准备好？"），不应嵌入生成代码。录制时用户已在真实页面上完成操作，生成器应忠实回放这些操作。

### Decision 2: URL 导航保留在组件中，但简化

**选择**：保留 `_target_url` 来源优先级（`login_url_override > account.login_url > platform default`）和 `page.goto` 调用，但移除导航后的门卫检测（`_login_element_candidates` + `_route_markers` 联合判断）。

**理由**：URL 导航是 login 组件的核心业务需求（"去哪个页面登录"），属于组件职责。但"到达页面后是否可操作"属于运行时关注点。

### Decision 3: 页面就绪检测使用 `locator.first.wait_for` 替代 `to_have_count(1)`

**选择**：在 `test_component.py` 中，执行 login 组件前，使用 `page.locator("input[type='password']").first.wait_for(state="visible", timeout=15000)` 作为页面就绪信号。

**替代方案**：
- A) 使用 `to_have_count(1)` —— 在多元素页面上失败（当前问题的根源）
- B) 使用 `page.wait_for_load_state("networkidle")` —— 官方不推荐作为唯一信号
- C) **使用 `.first.wait_for(state="visible")`（选定）** —— 兼容多元素页面，等待至少一个可见即可

**理由**：登录页就绪的含义是"至少一个密码输入框可见"，而非"页面上恰好只有一个密码输入框"。`.first` 在此处是正确的语义（"第一个匹配项可见即表示页面就绪"），而非歧义掩盖。

### Decision 4: 容器作用域由录制上下文驱动

**选择**：若录制步骤包含 `scope` 或 `container` 信息（Inspector 录制可提供），生成器写入具体的 `_form = page.locator("#specific-form")`；若无，locator 直接使用 `page` 或已有的 `_form`（由录制步骤上下文确定）。

**理由**：手动优化的 `miaoshou_login.py` 正是使用 `page.locator("#J_loginRegisterForm")` 这种显式容器，而非泛化搜索。生成器应模仿成功模式。

## Risks / Trade-offs

- **风险：移除门卫后，未登录页面的组件执行无诊断** → 缓解：测试框架层的就绪检测提供等效诊断（超时 + 结构化错误信息），且诊断质量更高（不会误报"count != 1"）
- **风险：录制步骤无容器信息时，locator 在复杂页面可能匹配多个元素** → 缓解：生成的 locator 仍遵循 `_form` 作用域（若有录制上下文）和 `.first` 策略（仅在 login form 内）；同时 lint 规则会检测并 warning
- **风险：已有回归测试用例需要更新** → 缓解：生成器输出变化是预期行为，更新测试断言即可
- **Trade-off：生成代码不再做导航后校验，"忘记配 login_url"的错误需要用户从超时报错中推断** → 可接受：生成器仍保留 `_target_url` 空值检查和 platform default fallback，覆盖绝大多数场景
