## Design: 登录场景自动变量化与智能录制建议

### 1. 背景与目标

- **背景**：
  - 录制登录组件时，用户可能直接输入真实用户名/密码，而不是手动写 `{{account.username}}` / `{{account.password}}`。
  - 现有录制页临时测试（`/recorder/test`）中已存在一套启发式，将看起来像账号/密码的字段标准化为模板变量，但这一能力仅用于临时测试链路，未完全体现在最终生成的 Python 组件中。
  - 为了让「同一份脚本适配多个账号」且避免明文敏感信息进入仓库，需要在录制→步骤→Python 生成的主链路上，对登录场景做系统化的自动变量化与可视化提示。

- **目标**：
  - 登录组件的用户名/密码输入步骤在保存为 .py 前**统一转换为账号变量**：`{{account.username}}` / `{{account.password}}`，生成器只使用 `account`/`ctx.account` 字典，而不写入明文。
  - 录制结果页给出**智能建议与可解释提示**，让脚本作者清楚看到哪些字段被识别为账号/密码、哪些已自动改为变量，并可一键应用/调整。
  - 设计与现有「步语义（step_type/scene_tags）」「生成器场景模板」「抗干扰钩子」能力兼容，为后续扩展其他场景（如验证码、Cookie 弹窗）打模板基础。

### 2. 范围与非目标

- **本设计涵盖**：
  - login 组件录制结果（`component_type == "login"`）在 `/recorder/stop` 返回 steps 时的自动识别与变量化。
  - `/recorder/stop` 响应中的**登录字段建议结构**（例如 `login_field_suggestions`），供前端展示智能建议。
  - 生成器（`steps_to_python.py`）在 login 场景下对账号/密码字段的代码生成策略。

- **本设计不做的事情**：
  - 不改变执行器对 `account` 字典的定义与加载逻辑（由 `AccountLoaderService` 与现有执行器负责）。
  - 不引入新的账号管理 UI，仅在录制结果页增加提示与交互。
  - 不扩展到所有组件类型的任意表单字段（当前仅聚焦 login 的账号/密码字段）。

### 3. 数据模型扩展

#### 3.1 steps 结构中的语义字段（与提案 6.6/6.7 对齐）

- 在现有 steps 基础上，后端解析链路（Trace 解析 + Recorder API）将支持：
  - `step_type: Optional[str]`：如 `"fill"`, `"click"`, `"navigate"`；在 login 场景下主要仍用于标记 `fill`。
  - `scene_tags: Optional[List[str]]`：高层语义标签，例如：
    - `"login_form"`：该步骤属于登录表单流程。
    - `"login_username_field"`：该步骤是登录用户名/账号输入。
    - `"login_password_field"`：该步骤是登录密码输入。

> 说明：`scene_tags` 是一个通用机制，账号/密码只是其中两个标签；未来可在同一字段上增加如 `"otp_dialog"`, `"cookie_consent"` 等标签。

#### 3.2 登录字段建议结构（后端→前端）

- 在 `/recorder/stop` 响应中新增可选字段（仅 login 组件且存在疑似账号/密码步骤时返回）：

```json
{
  "login_field_suggestions": [
    {
      "step_index": 3,
      "kind": "username",          // "username" | "password"
      "original_value": "xihong_erp_admin",
      "suggested_value": "{{account.username}}",
      "confidence": 0.92,          // 0~1，可选
      "applied": true              // 是否已在后端自动将 steps/value 改为 suggested_value
    },
    {
      "step_index": 4,
      "kind": "password",
      "original_value": "********",
      "suggested_value": "{{account.password}}",
      "confidence": 0.88,
      "applied": true
    }
  ]
}
```

- 设计约定：
  - `step_index`：对应 `steps` 数组中的下标，便于前端在步骤列表中高亮。
  - `applied = true` 表示**后端已将该步骤的 `value` 替换为 `suggested_value`**，即对生成 Python 已生效；前端展示仅用于解释与可视化。
  - 若启发式不够确定（如字段文案模糊），可返回 `applied = false`，由用户在前端确认是否替换。

### 4. 后端设计：识别与自动变量化

#### 4.1 识别规则（Recorder/Trace 解析）

- 在 login 场景下（`component_type == "login"`），后端在构造 steps 时对每个 `fill` 步骤执行：
  - 提取：
    - `selector`（CSS/role/text 选择器）
    - `comment`（录制器/用户备注，可为空）
    - `value`（用户在浏览器中输入的内容）
  - 应用启发式（与现有 `/recorder/test` 中逻辑保持一致，并在此基础上扩展）：
    - 若 comment 或 selector 包含以下任一特征，则认为是用户名字段：
      - comment 中包含：「账号」「用户名」「子账号」「邮箱」「手机号」等中文关键词（可配置）。
      - selector 中包含：`account`, `username`, `user`, `email`, `phone` 等英文关键词。
    - 若 comment 或 selector 中包含以下特征，则认为是密码字段：
      - comment 中包含：「密码」「安全码」等中文关键词。
      - comment 或 selector 中包含：`password`, `passwd`, `pwd` 等英文关键词。
  - 满足识别条件时：
    - 在该步骤的 `scene_tags` 中加入：
      - 用户名字段：`["login_form", "login_username_field"]`
      - 密码字段：`["login_form", "login_password_field"]`

#### 4.2 自动变量化策略

- 对于被标记为 `login_username_field` / `login_password_field` 的步骤，后端在**构建用于生成 Python 的 steps 列表**时执行：
  - 如果 `value` 已经包含 `{{account.username}}` 或 `{{account.password}}`，则保持不变，仅在 `scene_tags` 上补充标签。
  - 如果 `value` 是普通字符串（录制时输入的明文）且不含模板变量：
    - 用户名字段 → 将 `value` 设置为 `{{account.username}}`。
    - 密码字段 → 将 `value` 设置为 `{{account.password}}`。
  - 无论是否自动替换，均在 `login_field_suggestions` 中添加对应条目，`applied = true`。

- 硬性约束：
  - 对于 login 组件中被识别为账号/密码的步骤，**不允许在最终 steps（用于生成 Python）中保留明文账号/密码**；即使前端未展示或用户忽略建议，生成器也只看见模板变量。
  - 若未来出现配置错误或识别冲突，宁可「多用一次模板变量」也不将明文写入仓库。

### 5. 生成器行为（steps_to_python.py）

#### 5.1 通用模板变量支持

- 已存在的逻辑（示意）：

```12:18:backend/services/steps_to_python.py
if "{{account.username}}" in value or "{{account.password}}" in value:
    lines.append(step_indent + "# Value from ctx.account - use acc.get(\"username\") / acc.get(\"password\")")
    fill_val = "acc.get(\"password\", \"\")" if "password" in value.lower() else "acc.get(\"username\", \"\")"
    lines.append(step_indent + f"await {loc_var}.fill({fill_val}, timeout=10000)")
```

- 本设计不改变这一通用分支，仅保证登录场景下账号/密码字段的 `value` 一定是上述模板变量，从而自然触发该分支。

#### 5.2 登录场景下的附加约束

- 在生成器内部（或调用生成器前），对 login 组件施加以下附加约束：
  - 若步骤的 `scene_tags` 包含 `login_username_field` 或 `login_password_field`：
    - 忽略任何与账号/密码不相关的自定义 `value`，只使用 `{{account.username}}` / `{{account.password}}` 对应的 `acc.get(...)`。
    - 可以在生成的 Python 中加入一行注释，解释这一行为，例如：

```python
# 登录字段已按账号变量处理；录制时输入的值不会写入脚本
```

- 这样，**生成器层面**保证：
  - 登录组件对所有账号/密码字段的取值方式完全统一。
  - 即使未来后端识别逻辑调整或前端不展示建议，只要 `scene_tags` 中包含对应标签，就不会生成包含明文的代码。

### 6. 前端交互设计：智能建议与应用

#### 6.1 顶部提示条

- 在录制结果页（`ComponentRecorder.vue` 等价页面），当响应中有非空 `login_field_suggestions` 时：
  - 在步骤列表上方显示一条信息条，例如：
    - 「检测到 2 处登录用户名/密码输入，已建议替换为账号变量（{{account.username}} / {{account.password}}）。」
  - 提供按钮：
    - 「查看详情」：展开/滚动到第一条相关步骤。
    - （可选）「全部应用」：仅当存在 `applied = false` 的建议时，触发对本地 steps 的批量替换，并（可选）调用 `/recorder/generate-python` 重新生成 `python_code`。

#### 6.2 步骤级标记与操作

- 在步骤列表中，对于出现在 `login_field_suggestions` 中的步：
  - 在该行右侧显示一个小标签，例如：
    - 用户名字段：`[账号字段 → 建议使用 {{account.username}} ]`
    - 密码字段：`[密码字段 → 建议使用 {{account.password}} ]`
  - 若 `applied = true`，标签可展示为「已按账号变量处理」样式（不可点，仅提示）。
  - 若 `applied = false`（低置信度或需用户确认），标签为可点击按钮：
    - 点击后：
      - 更新前端 steps state 中该步的 `value` 为 `suggested_value`。
      - 标记本地 `applied = true`。
      - （可选）触发一次 `generate-python` 以刷新 `python_code`。

#### 6.3 与 Python 代码编辑区域的联动

- 若前端以「只编辑 Python 文本」为主而不再频繁更新 steps：
  - 推荐流程：
    - 在应用登录字段建议（无论自动还是用户点击）后，调用 `/recorder/generate-python`，以登录变量化后的 steps 作为输入。
    - 更新 `pythonCode` 区域，使其自动使用 `account.username` / `account.password` 访问逻辑，保证前端看到的代码与真实执行一致。

### 7. 安全性与兼容性

- **安全性**：
  - 登录组件中被识别为账号/密码的字段在持久化前即转换为模板变量，并由生成器统一从 `account` 字典取值，避免明文用户名/密码进入仓库。
  - 对于未被识别的字段（如留言备注），仍按普通字符串处理，不变更现有行为。

- **兼容性**：
  - 老的录制结果（无 `scene_tags` 字段）仍然可以工作：系统可回退到现有的启发式（基于 comment/selector），并在转换 steps 时直接写入模板变量。
  - 若未来扩展更多场景（如 OTP、Cookie 弹窗），可在同一 `scene_tags` 机制下增加标签，不影响本设计。

### 8. 验收要点

1. **自动变量化验证**：
   - 使用真实账号/密码录制一个 login 组件，停止录制。
   - 检查 `/recorder/stop` 响应：
     - login 相关 steps 的 `value` 中不再包含明文账号/密码，而是 `{{account.username}}` / `{{account.password}}`。
     - `login_field_suggestions` 包含对应步骤，`applied = true`。
   - 检查生成的 Python 代码：
     - 对用户名/密码字段仅使用 `account`/`ctx.account` 字典取值（不包含明文）。

2. **智能建议展示**：
   - 在前端录制结果页看到顶部提示条与步骤级标签。
   - 若强制将某步识别为低置信度（`applied = false`），用户可通过点击标签将其转为模板变量，并看到 Python 代码更新。

3. **多账号复用**：
   - 使用同一 login 组件，在组件版本管理中选择不同账号进行测试。
   - 验证登录流程对多个账号均能复用，无需修改组件代码。

### 9. 开发与实现注意事项

- **删除录制页测试功能时的文档同步**：
  - 在按 tasks 6.1 实施「测试路径收敛（删除录制页“测试组件”）」时，需同步更新 `proposal.md` 第 9.1 节中关于 `/recorder/test` 的「已实施优化」描述，改为「已归档/已移除」，避免后续阅读时误以为录制页仍然支持测试。

- **登录自动变量化的安全兜底**：
  - 启发式无法 100% 识别所有账号/密码字段时，应倾向于「宁可多用一次账号变量，也不要将疑似口令的明文写入 steps」：例如在 login 组件中，若某 `fill` 步骤的 selector/comment 同时具备一定特征（如包含 password 关键字）且 value 看起来像随机口令，即使置信度不满，也应替换为模板变量并通过 `login_field_suggestions` 提醒用户。
  - 对于明确不属于登录表单的字段（如备注/说明），仍保持普通字符串行为，防止过度「智能」造成逻辑错误；相关规则可通过配置（关键字白名单/黑名单）调整。

- **兼容无 `scene_tags` 的旧 steps**：
  - 生成器和后端识别逻辑在实现时不得强依赖 `scene_tags` 字段；当 steps 中没有 `scene_tags` 时，应自动回退到基于 comment/selector 的旧启发式行为，保证历史录制结果仍可用于生成 Python。
  - 仅当 `scene_tags` 存在且包含诸如 `login_username_field`/`login_password_field` 等标签时，才启用更精细的场景模板与安全策略；否则按「基础变量替换 + 注释占位」的保守模式运行。

- **生成后质量检查的行为分级**：
  - 语法错误（如 `py_compile` 失败、无法 import）应视为 hard fail：后端在 `/recorder/stop` 或 `/recorder/generate-python` 响应中返回错误详情，并阻止前端直接保存为 .py，提示用户先修复语法问题。
  - 规范/最佳实践类问题（如使用 `wait_for_timeout`、未使用 get_by_* 而使用脆弱的 CSS 选择器）应视为 soft warning：在响应中以 warnings 列表形式返回，前端展示为「质量建议」，但不阻断保存路径，留给脚本作者在合适时机优化。
  - 具体的规则集与严重级别可随着项目迭代在实现中调整，但需保证：**所有会阻塞保存的错误类型在前端有清晰可见的提示文案**，避免用户产生「为什么不能保存」的困惑。

