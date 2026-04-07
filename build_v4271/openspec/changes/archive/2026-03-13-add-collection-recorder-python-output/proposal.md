# Change: 采集脚本录制工具产出 Python 组件（规范对齐）

## Why

1. **框架与录制产物脱节**：当前录制流程（前端开始/停止 + Inspector + Trace）产出的是步骤列表并保存为 YAML；执行器实际运行的是 `modules/platforms/*/components/*.py` 的 Python 组件。CLI 时代录制的脚本或 YAML 与现有框架的 Python 组件契约不一致，无法直接用于生产采集。
2. **规范已就绪、缺可落地的录制出口**：《采集脚本编写规范》（`docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`）已交付并归档，要求定位用 get_by_*、可重试等待、条件等待、组件契约与各场景应对。录制工具若只产出 YAML 或裸选择器步骤，无法自动对齐规范；需要「录制 → 步骤 → 规范对齐的 .py」的闭环。
3. **前端可操作、缺“一步到 .py”**：用户希望在前端完成录制操作并直接得到可保存、可执行的 .py 文件；当前前端保存仅传 `yaml_content`，未提供「由录制步骤生成并编辑 Python 代码」的能力。
4. **业界实践**：Playwright 官方通过 Codegen 实时生成 Python 代码；无 Codegen 集成时，常见做法是「录步骤 + 步骤→代码生成器」以统一风格与契约。本变更采用后者，与现有 Inspector + Trace 流程兼容，并令生成器输出符合项目规范的 .py。

## What Changes

**目标**：录制工具在前端可操作的前提下，**主产出为符合《采集脚本编写规范》的 Python 组件（.py）**；保留现有 Inspector + Trace 录制流程，新增「步骤 → Python 代码生成器」与前端「Python 预览/编辑与保存为 .py」能力。

### 1. 步骤 → Python 代码生成器（后端）

- **输入**：platform、component_type、component_name、steps 列表（与 stop 返回的 steps 结构一致）；steps 每项含 action（click/fill/navigate/wait 等）、selector、value、url、optional 等。调用生成器时 platform/component_type 由当前录制会话提供，component_name 在 stop 时尚无用户输入，以 component_type 作为默认值；前端保存时以用户填写的 component_name 写入文件名。
- **输出**：一段 Python 源码字符串，满足：
  - **组件契约**：`async def run(page, account, config)`（或当前项目约定的 LoginComponent/ExportComponent 签名），返回 ResultBase 子类；从 `ctx.config` 或 `*_config` 读取配置，不写死选择器。
  - **元素定位**：在步骤解析时若能从 selector 或 Trace 元数据推断出 role/label/text，优先生成 `page.get_by_role()` / `get_by_label()` / `get_by_text()`；否则生成 `page.locator(selector)` 并加注释「建议迁移到 get_by_*」。
  - **等待**：在 click/fill 前生成 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，避免裸的 `time.sleep`；navigate 后可按需生成等目标页特征的注释或占位。
  - **可选步骤**：对 `optional=true` 的步骤，生成 try/except 或「先判断可见再操作」等与规范一致的可选执行逻辑，或至少生成注释「可选步骤，执行失败可跳过」，使执行器行为与 YAML 的 optional 一致；同时无论是否包含可选步骤，生成的 Python 源码必须始终保持语法合法（例如避免空的 `try:` 块，对仅有注释占位的分支补充 `pass` 或 `raise NotImplementedError`），防止加载阶段因语法错误中断后续调试与测试。
  - **结构**：按《采集脚本编写规范》的复杂交互、临时弹窗等留注释占位（如「若有弹窗在此 wait 再点击关闭」），便于用户录制后补全。
- **实现位置**：可在 `backend/services/` 或 `backend/utils/` 下新增模块（如 `steps_to_python.py` 或 `collection_recorder_codegen.py`），由录制相关 router 调用；或放在 `tools/` 下供后端与 CLI 共用。
- **可选增强**：
  - 若 Trace 解析或 steps_file 中能提供 role/label/text（如从 DOM 快照或录制脚本内记录），生成器优先使用以产出更多 get_by_*。
  - 在 steps 结构中支持 `step_type` / `scene_tags` 等高层语义（如 login_form、cookie_consent、export_wizard_step、otp_dialog、iframe_step），生成器可按类型选择对应「场景模板」（例如登录表单填写、业务 Modal 关闭、导出向导步骤等），而不是逐行机械拼接 click/fill。
  - 对 login / export 等组件类型，生成器基于预置「组件模板」（class + run 方法骨架 + 常用私有 helper），将录制到的步骤映射为模板中的实现细节，使生成的代码结构清晰、贴近人工维护风格。
  - 生成完成后可选调用 Python 语法检查与轻量 Lint（如 `python -m py_compile` 或 ruff 规则子集），在 `/recorder/stop` 或 `/recorder/generate-python` 响应中返回结构化的错误/警告信息（如语法错误位置、使用了不推荐的 `wait_for_timeout` 等），前端可展示为「质量提示」，辅助用户快速修正生成结果。

### 2. 录制停止后返回或提供「生成 Python」接口

- **必须**：`POST /recorder/stop` 在返回 steps 的同时，在**仅当 mode=steps 且存在 steps** 时调用步骤→Python 生成器，在响应中增加 `python_code` 字段，前端据此展示与编辑后保存。无此则前端无法获得规范对齐的 .py。
  - **元数据来源**：生成器所需的 platform、component_type 从当前录制会话（recorder_session）获取；component_name 在 stop 时尚未有用户输入，以 **component_type 作为默认 component_name** 调用生成器；前端保存时用户填写或确认 component_name，写入 `{component_name}.py`。
  - **discovery 模式**：当 mode=discovery（date_picker/filters 发现模式，无 steps、为 open_action + available_options）时，**不调用生成器**，响应中不返回 `python_code` 或返回空字符串。
  - **降级**：生成器异常或 steps 为空时，响应中不包含 `python_code` 或 `python_code` 为空字符串；前端可提示「未生成代码，请检查步骤或使用重新生成」。
- **可选**：新增 `POST /recorder/generate-python`（请求体：platform、component_type、component_name、steps；响应：python_code），供前端「仅重新生成」时调用，与 stop 带 python_code 可并存。

### 3. 前端：Python 预览、编辑与保存为 .py

- **录制结果页**：在现有「步骤列表 / YAML 预览」旁增加 **Python 代码** 区域：展示后端返回或通过 generate-python 得到的 `python_code`，支持只读预览与可编辑文本框（或代码高亮编辑器）。
- **保存**：保存时调用现有 `POST /recorder/save`，传 **python_code**（及 platform、component_name 等）；后端已支持将 python_code 写入 `modules/platforms/{platform}/components/{component_name}.py` 并注册版本。若用户未编辑则使用服务端生成的默认 python_code；若用户编辑过则使用编辑后内容。
- **YAML**：可保留「导出 YAML」或兼容仅 YAML 的保存路径，但**主路径**为「生成并保存 .py」。

**前端修改清单（实施时可对照）**：

| 类别 | 内容 |
|------|------|
| **数据/状态** | 新增用于存放当前 Python 代码的 state（如 `pythonCode`）；停止录制后从 `response.python_code` 赋值（若缺失或空则提示未生成）；若有「重新生成」则从 generate-python 响应更新。 |
| **UI** | 在录制结果区（与步骤列表、YAML 并列或 Tab）增加「Python 代码」区域；绑定上述 state，支持可编辑（textarea 或带高亮的编辑器）。停止后用户可输入或确认**组件名**（component_name），保存时以该名称写入 `{component_name}.py`。 |
| **接口** | 停止录制后读取 `response.python_code` 并写入 state；保存时请求体携带 `python_code`（及 platform、component_name 等），主路径为保存 .py。可选：调用 `POST /recorder/generate-python` 实现「重新生成」按钮。 |
| **兼容** | 保留步骤列表、YAML 预览、复制 YAML；YAML 保存可作为次要路径保留，不删除现有 YAML 相关 UI。 |

**可选增强：登录场景自动变量化与智能建议（详见 design.md）**：

- 后端在处理 login 组件的录制结果时，基于 comment/selector 与 `step_type` / `scene_tags` 识别用户名/密码输入步骤，优先将其 `value` 规范化为 `{{account.username}}` / `{{account.password}}`，保证生成的 Python 组件始终通过账号变量取值，而不会将录制时输入的明文账号/密码写入仓库。
- `/recorder/stop` 响应中可选返回 `login_field_suggestions` 之类的结构化提示（包含 step 索引、字段类型、原始/建议值、是否已自动应用等），前端在录制结果页以「智能建议」的形式展示：例如顶部提示「检测到 X 处登录字段，已建议替换为账号变量」，并在对应步骤旁显示可点击的建议标签，允许用户一键应用或忽略。
- 若用户未显式采纳建议，生成器在 login 场景下对被识别为账号/密码字段的步骤仍应按账号变量生成代码（忽略明文 value，仅用 `account.username/password`），智能建议仅作为可视化与可解释性增强，不影响「不落明文密钥」这一硬性约束。

### 4. 不修改

- 不修改 `tools/launch_inspector_recorder.py` 的录制流程（Inspector + Trace + 步骤输出）；仅在「停止后」增加生成与展示 Python 的链路。
- 不修改执行器或组件适配器接口；生成的 .py 与现有 Python 组件契约一致即可被现有执行器使用。
- 不在此变更中实现 Playwright Codegen 窗口的实时代码抓取或 CDP 集成；以「步骤 → 生成器 → .py」为主方案。

### 5. 实施顺序与重点必须完成项

**当前缺口**：前端仅有步骤列表与 YAML 预览，保存只传 `yaml_content`，无 Python 代码区域、不接收/展示 `python_code`、不传 `python_code` 保存，故尚不符合「主产出 .py、规范对齐」的录制目标。

**必须完成的三项（缺一不可，且建议按序实施）**：

1. **步骤→Python 代码生成器（后端）**  
   新建生成模块，输入与 stop 返回一致的 steps 及元数据，输出符合《采集脚本编写规范》的 Python 字符串（契约、get_by_* 优先、条件等待、规范注释占位）。可先单测生成器再接 API。
2. **POST /recorder/stop 响应中带 python_code**  
   在 stop 解析得到 steps 后，**仅当 mode=steps 且存在 steps** 时从会话取 platform/component_type、以 component_type 为默认 component_name 调用生成器，将结果放入响应字段 `python_code`；mode=discovery 或生成器异常或 steps 为空时不返回或返回空。前端依赖此字段展示默认代码，缺失时提示未生成。
3. **前端：Python 区域 + 接 python_code + 保存主路径传 python_code**  
   录制结果页增加「Python 代码」展示与可编辑区域；停止录制后从响应取 `python_code` 并展示；保存时主路径传 `python_code`（及 platform、component_name 等）到 `POST /recorder/save`。可保留 YAML 预览与复制，但主路径为保存 .py。

**可选**：`POST /recorder/generate-python` 与前端「重新生成」按钮；Trace/步骤中增加 role/label 元数据以提升生成器 get_by_* 比例；代码高亮与 Tab 切换。

**验收**：从前端开始录制 → 停止 → 看到并可编辑生成的 Python → 保存 → 确认 `modules/platforms/{platform}/components/{component_name}.py` 存在且可被执行器加载；生成代码符合规范中的契约与定位/等待约定（可人工抽查）。

### 6. 录制方式增强：线性录制与步骤识别（可选/后续）

**背景与问题**：实践中除登录组件较易单独录制外，导航、日期选择、筛选器、店铺切换、导出等均在**同一条线性操作流**中完成（例如：进入订单页 → 选日期 → 选筛选 → 点导出）。当前录制需「先选组件类型再录」，与用户真实操作顺序不一致，导致其他组件难录。期望改为：**用户执行一次线性录制后，由系统自动识别或用户手动标记**哪些步骤属于导航、日期选择、筛选器、店铺切换、导出，再据此生成或拆分为可复用组件。

**组件衔接的标准设计（与执行器一致）**：

- **顶层顺序**：执行器按固定顺序调用 `login` → `shop_switch`（可选）→ `navigation`（可选）→ 按数据域循环 `export`。衔接方式为顺序 + 组件名约定。
- **导出内部**：export 组件可通过步骤中的 `action: component_call` 调用子组件 `date_picker`、`filters`、`shop_switch`；执行器解析 component_call 后加载并执行对应子组件。现有前端已支持将步骤**手动标记**为「日期组件」「筛选器」，生成 YAML 时转为 component_call。

**设计方向**：

1. **完整流程录制**：提供「完整流程」或「线性流程」录制入口，用户不事先选定单一组件类型即可开始录制，得到整条步骤序列。
2. **步骤/区间类型识别**：录制结束后，对步骤或连续区间进行类型归属：
   - **用户手动标记**：在步骤列表中为每步或每段选择类型（普通步骤 / 导航 / 日期选择 / 筛选器 / 店铺切换 / 导出）。现有 date_picker、filters 标记可保留并扩展为含 navigation、shop_switch、export。
   - **系统辅助（可选）**：根据点击元素（如日期控件、筛选图标、店铺选择器）、输入框、按钮文案等给出类型建议，用户可采纳或修改。
3. **从标记结果生成组件**：连续同类型步骤可生成对应子组件或转为 component_call；与执行器约定一致：顶层生成 login / shop_switch / navigation / export，export 内通过 component_call 引用 date_picker、filters、shop_switch。

**可选实现项（本变更可部分做或列为后续变更）**：

- 扩展步骤标记选项：在现有「普通步骤 / 日期组件 / 筛选器」基础上，增加「导航」「店铺切换」「导出（主流程）」等，便于在一条线性录制中切分多段并对应到执行器顺序与 component_call。
- 增加「完整流程录制」模式：录制前可选「按组件类型录制」或「完整流程录制」；完整流程录得整条步骤后，在结果页通过步骤标记（及可选区间选择）完成切分。
- 自动识别建议：基于步骤的 selector/action/文案等给出类型建议，辅助用户快速标记。
- 从标记结果生成多个 .py 或带 component_call 的 export：按标记切分后，为每段生成符合规范的 Python 或 YAML，与当前步骤→Python 生成器及 YAML 的 component_call 逻辑对齐。

本节为**设计方向与可选增强**；本变更以「步骤→Python、前端 Python 主路径保存」为核心交付，上述线性录制与步骤识别可在本变更中做部分实现（如仅扩展步骤标记）或单独列为后续变更。

### 7. 录制环境与干扰处理（现有行为说明）

本节说明录制流程中**已具备**的会话/指纹与干扰处理设计，本变更不修改这些行为，仅在此明确以便与「步骤→Python、主产出 .py」衔接一致。

**持久化会话与固定指纹**：

- 录制启动时已按账号使用**持久化上下文**（`use_persistent_context: True`）与**固定指纹**（`use_fingerprint: True`），与主采集执行器、`docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md` 一致（SessionManager + DeviceFingerprintManager）。
- **录登录组件**：`skip_login: True`，不执行自动登录，仅打开登录页，由用户手动完成登录步骤录制，避免「已自动登好再录」导致录不到真实登录流程。
- **录导出/导航/店铺切换等**：`skip_login: False`，先执行自动登录（或因持久化会话直接处于已登录状态），再处理弹窗后打开 Inspector，用户可直接在主页/目标页录制，避免重复输入验证码。

**干扰（弹窗、遮蔽）处理**：

- **执行器**：在登录前、每个数据域导出前、步骤执行前后会调用 `UniversalPopupHandler.close_popups`（通用选择器 + 平台 `popup_config.yaml`）；步骤内支持 `action: close_popup`，重试可配置 `on_retry: close_popup`。详见《采集脚本编写规范》第 7 节与 `modules/apps/collection_center/popup_handler.py`。
- **组件内**：可预期弹窗在流程中显式 wait 再点击关闭/确认；可能不出现的弹窗关闭步骤可标为 **optional**，执行时失败则跳过。
- **是否需要单独录「关闭弹窗」组件**：通常不需要。通用与平台配置已覆盖大部分常见弹窗；若某平台有固定弹窗，可在该组件内加一步「点击关闭」并视情况标 optional，或将选择器放入平台 `popup_config.yaml`。仅极少数需固定顺序关闭的定制弹窗才考虑单独关弹窗组件，非默认推荐。

生成器在生成 Python 时对「临时弹窗/遮挡」：

- 至少留注释占位（见第 1 节），与上述执行器与规范行为一致；用户录制后可按规范补全或依赖执行器步骤边界关闭。
- 对于在 Trace/steps 中已识别到的「可预期弹窗」或「业务 Modal」，优先生成显式的 wait+关闭/确认逻辑（如等待 `.ant-modal, [role="dialog"]` 可见后点击确定按钮），或调用平台封装的弹窗 helper，而不完全依赖全局 close_popups。
- 对登录、导出等关键节点，生成器在合适的位置自动插入 `await self.guard_overlays(page, label="...")` 等抗干扰钩子调用，使由录制生成的组件在**不额外手写代码**的前提下具备基础的弹窗/遮挡抗干扰能力。

### 8. 组件保存、版本、更新与淘汰（与业界对齐说明）

本节说明录制组件的**保存位置、调用方式、更新与淘汰**的当前行为及与业界主流的对齐情况；本变更不修改现有保存/版本逻辑，仅在此明确约定与可选增强方向。

**保存位置与目录（与业界一致）**：

- **Python 组件**：保存至 `modules/platforms/{platform}/components/{component_name}.py`，按平台与组件名分层，代码进入仓库，与业界「脚本即代码、按能力分目录」一致。
- **YAML 组件**（兼容）：`config/collection_components/{platform}/{component_name}.yaml`。
- 保存时同时写入 **component_versions** 表（版本号、file_path、is_stable、is_active 等），用于版本选择、A/B 与统计。

**调用方式**：主执行路径通过 **Python 适配器**按 `platform` + `component_name` 动态 import 对应 .py 模块；另一路可通过 component_versions 选版本后再加载（YAML 或需灰度时）。组件化、按组件管理符合业界 Page Object / Component 库实践。

**更新行为（与业界差异与建议）**：

- **当前**：同一 component_name 再次保存时**覆盖同路径文件**，若 component_versions 中已有该 file_path 则**只更新同一条版本记录的 description/updated_at**，不新建版本行；若为同名组件首次以该路径保存则新建版本行（1.0.0 或递增 patch）。
- **业界常见**：每次保存或提交即新快照、可回滚（Git 或测试管理中的「未命名版本」）。
- **建议在文档中明确**：「覆盖即更新、不产生新版本行；若需历史与回滚，请依赖 Git 对 `modules/platforms/.../components/*.py` 的版本管理。」可选后续增强：每次保存时新建版本行（或新文件如 `name_v1.0.1.py`），以支持在系统内回滚而不依赖 Git。

**淘汰行为（与业界差异与建议）**：

- **当前**：在 **component_versions** 中将某版本设为 **is_active=False**，版本选择逻辑（select_version_for_use）不再选中该版本，实现「从版本池淘汰」。
- **注意**：主执行路径（Python 适配器）按**模块名**加载，**不查询 is_active**，因此仅设 is_active=False 后，只要磁盘上 .py 仍在，该组件仍可能被直接 import 执行。
- **建议在文档中明确**：「淘汰」在「经版本服务选版本再加载」的路径下生效；若需**彻底不再执行**某 Python 组件，需**移走或删除**对应 `modules/platforms/{platform}/components/{component_name}.py`，或后续让主执行路径也经版本服务加载（仅加载 is_active=True 的版本）。

本节为**说明与约定**；本变更交付「步骤→Python、前端保存 .py」，不修改现有保存/版本/淘汰实现，上述可选增强可列入后续变更。

## Impact

### 受影响的规格

- **data-collection**：ADDED 录制工具产出 Python 组件（步骤→Python 生成器、前端 Python 预览/编辑与保存为 .py）。

### 受影响的代码与文档

| 类型 | 位置 | 修改内容 |
|------|------|----------|
| 后端 | 新建 `backend/services/steps_to_python.py` 或 `backend/utils/collection_recorder_codegen.py` | 步骤→Python 代码生成器：输入 steps + 元数据，输出符合《采集脚本编写规范》的 .py 字符串 |
| 后端 | `backend/routers/component_recorder.py` | 在 stop 响应中增加 python_code 和/或新增 POST /recorder/generate-python；步骤语义 enrich（含验证码类型扩展见 §10.1） |
| 后端 | `backend/routers/component_versions.py` | 版本统计与测试历史改为同步 Session（§9.2/§10.3）；待实施：完整路径含 version_id，status 返回 verification_screenshot_url，GET verification-screenshot 返回截图流，POST resume 校验权限与状态并写 verification_response.json，超时/结束后 4xx（§10.2） |
| 前端 | `frontend/src/views/ComponentRecorder.vue`（或等价录制页） | 增加 Python 代码展示与编辑区域；保存时传 python_code；步骤标记扩展（含验证码子类型见 §10.1） |
| 前端 | `frontend/src/views/ComponentVersions.vue` | 测试弹窗轮询 status；待实施：verification_required 时展示截图/输入框并提交 resume（§10.2） |
| 工具 | `tools/test_component.py`、`tools/run_component_test.py` | 有头模式 viewport 与最大化（§10.3）；待实施：捕获 VerificationRequiredError、写 progress、轮询 verification_response.json、同 page 填入继续（§10.2） |
| 文档 | `docs/guides/` 或录制相关文档 | 说明录制后如何得到 .py、如何按规范微调；RECORDER_PYTHON_OUTPUT.md 职责边界与步骤标记；验证码类型与测试/采集回传设计（§10.1、§10.2） |

### 不修改

- 不修改 `modules/apps/collection_center/` 执行器逻辑。
- 不修改 `tools/launch_inspector_recorder.py` 的录制与步骤输出格式（可后续在步骤中增加 role/label 等元数据以优化生成器）。

## Non-Goals

- 不在此变更中实现「从 Playwright Codegen 窗口实时拉取代码」；以步骤→生成器为唯一代码来源。
- 不强制移除 YAML 保存路径；可保留为兼容或次要导出。
- 不在此变更中批量将既有 YAML 组件迁移为 .py；仅保证新录制可一步到 .py。

## 依赖与参考

- **《采集脚本编写规范》**：`docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`（已归档变更 add-collection-script-writing-guide）；生成器输出须与该规范对齐（定位、等待、契约、场景注释）。
- **现有录制 API**：`backend/routers/component_recorder.py` 的 /recorder/start、/recorder/stop、/recorder/save（已支持 python_code）；本变更扩展 stop 或新增 generate-python，并让前端主路径使用 python_code 保存。

---

## 9. 已实施优化与后续可做（2026-02 补充）

本节记录本变更实施过程中完成的优化及新开对话可继续推进的项，便于后续迭代。

### 9.1 已实施优化

| 类别 | 内容 | 位置 |
|------|------|------|
| **步骤重复** | Trace 解析仅认 `action` 事件（方案 A），不处理 before/after；500ms 时间窗内 (action_type, selector, value) 去重（方案 C）。 | `backend/utils/trace_parser.py` |
| **可执行代码** | 生成器从 step 的 `selectors` 推导 `selector`（Inspector 仅写 selectors 时也能生成 locator/expect/click/fill）。 | `backend/services/steps_to_python.py`（`_selector_from_selectors`） |
| **步骤衔接** | navigate/goto 后插入 `await page.wait_for_load_state("domcontentloaded", timeout=10000)`。 | `backend/services/steps_to_python.py` |
| **Inspector 去重** | 最近 2～3 步内相同 action + 主 selector 则合并/跳过，避免同一操作多次记录。 | `tools/launch_inspector_recorder.py`（`_handle_normal_event`） |
| **测试组件（录制页临时测试，已移除）** | 历史上，录制页曾提供基于 `/recorder/test` 的临时组件测试能力（登录组件测试时账号/密码字段自动替换为 `{{account.username}}`/`{{account.password}}`，验证码相关步骤自动设为 optional）。该能力已按本提案 9.2 的「测试路径收敛」收束至组件版本管理测试入口，录制页不再直接触发测试。 | `backend/routers/component_recorder.py`（历史 `/recorder/test`，现已移除） |
| **步骤标记** | 新增「标记为验证码」；captcha 在 YAML 导出中按普通步骤输出，不生成 component_call（暂无 captcha 组件）。 | `frontend/src/views/ComponentRecorder.vue` |
| **步骤编辑 UI** | 「全选、标记为日期组件、标记为筛选器、标记为验证码…」工具条使用 `position: sticky; top: 0`，仅下方步骤列表滚动。 | `frontend/src/views/ComponentRecorder.vue`（`.steps-toolbar`） |

### 9.2 后续可优化与本轮实现结论

- **测试路径收敛（录制页不再直接测试组件）**：本轮实现已删除录制页「测试组件」按钮与 `/recorder/test` 接口，仅保留组件版本管理页作为唯一组件执行入口。录制页职责限定为「录制 → 步骤编辑 → 生成/编辑 Python → 保存组件」，保存成功后通过弹窗引导「前往组件版本管理并测试」完成测试闭环。
- **success_criteria**：登录组件在保存时可配置 success_criteria（目前支持 url_contains），`/recorder/save` 会在写入组件前将生成器默认的 TODO + `LoginResult(success=True)` 替换为基于 URL 片段的成功校验逻辑；未配置时保持原有 TODO 模板。后续可在文档中补充 element_visible、title_contains 等扩展类型及前端配置入口。
- **标记扩展（导航 / 弹窗/通知栏）**：前端已在步骤工具条与编辑表单中增加「标记为导航」「标记为弹窗/通知栏」，对应 step_group = navigation/popup；后端在 `_enrich_steps_semantics` 中为其补充 scene_tags，生成器对 popup 步骤统一视为可选（try/except 包裹 + 通用 dialog 关闭模板），navigation 步骤在 navigate 后自动插入 wait_for_load_state 与 guard_overlays 钩子。
- **验证码组件与步骤语义**：当前 step_group=captcha 仅用于在 steps/scene_tags 上打语义标记，生成器仍按普通步骤生成代码，不自动将其设为可选；是否必选由 `optional` 字段决定。本轮已统一前端提示与文档文案：验证码标记仅做语义标注，执行/测试仍按普通步骤处理，如需可选需手动勾选。若未来引入 `platform/captcha_solver` 等组件，可将 captcha 标记转为 component_call，并在执行器中实现相应求解逻辑。
- **文档与组件并存策略**：`docs/guides/RECORDER_PYTHON_OUTPUT.md` 已补充录制页与组件版本管理的分工、步骤标记含义（含验证码/导航/弹窗）及后续优化方向。本轮实现中，录制器生成的新 Python 组件按 `modules/platforms/{platform}/components/{component_name}.py` 存放，可与既有手写组件（如 `miaoshou/login`）并存使用；默认执行顺序仍指向既有组件名，新录制组件通过组件版本管理页单独测试或灰度，不强制替换旧组件，以避免误用。
- **组件测试流程（版本统计、浏览器、失败提示）**：版本统计与测试历史改为同步 Session、有头模式全屏、统计失败时写 `stats_update_error` 并由前端提示等实现细节见本变更目录下的 `OPTIMIZATION_IMPLEMENTATION.md` §5、§6；待实施的验证码暂停与回传见 §10.2 与 tasks §7。

---

## 10. 综合优化规划：验证码类型与测试阶段回传（待实施）

本节汇总多轮对话中达成一致的优化项，作为提案的完整扩展，便于后续按序实施。

### 10.1 验证码类型区分（与规范对齐）

**现状**：录制器步骤标记仅有单一「验证码」选项（step_group=captcha），未区分图形验证码与短信/OTP；《COLLECTION_LOGIN_VERIFICATION》与执行器已区分 `verification_type`：`graphical_captcha`（需截图给用户看后输入）与 `otp`（用户查收短信/邮件后输入，无需截图）。

**优化目标**：

- **录制器步骤标记**：将「验证码」拆分为两种可选标记（或保留「验证码」并增加子类型）：
  - **图形验证码**：step_group = `captcha_graphical`（或等价 scene_tags）。含义：该步骤需要**截图给用户看**，用户**看后**输入；与 `verification_type=graphical_captcha` 一致。
  - **短信/OTP 验证码**：step_group = `captcha_otp`。含义：用户**查收短信/邮件**后输入，**不需要截图**；与 `verification_type=otp` 一致。
- **语义与生成器**：在 `_enrich_steps_semantics` 中为上述 step_group 补充 scene_tags（如 `graphical_captcha` / `otp`），供生成器或后续验证码处理逻辑区分「需截图」与「仅输入框」。
- **文档**：在《采集脚本编写规范》或 RECORDER 相关文档中明确：录制时验证码步骤需区分「图形验证码（用户查看截图后输入）」与「短信/OTP（用户查收后输入）」；与执行器、前端的 `verification_type` 一致。
- **向后兼容**：保留对既有 `step_group=captcha` 的识别；未区分子类型时视为默认「图形验证码」（或 scene_tags 保留 `captcha`），生成器/执行器按「需截图」的保守方式处理，直至用户重新标记为图形/OTP。

### 10.2 测试阶段验证码暂停与回传（设计）

**适用范围**：本设计适用于**组件版本管理**中的 **Python 组件测试**（`adapter.login(page)` 及手写/录制生成的 .py 组件）。YAML/步骤组件的验证码回传若有需求留作后续扩展。

**问题**：手写登录组件（如妙手 login.py）在检测到图形验证码时抛出 `VerificationRequiredError("graphical_captcha", screenshot_path)`，由**采集任务**执行器捕获后暂停、持久化截图、阻塞等待用户回传、同一 page 填入继续。**组件测试**在独立子进程中运行，无 task_id、无 Redis 回传通道，目前将上述异常当作普通失败处理，导致测试直接报错「Verification required: graphical_captcha」。录制生成的登录组件（如 miaoshou_login.py）则把验证码写死为录制时的值，测试时页面验证码每次不同，同样导致失败。

**设计目标**：测试阶段与采集环境**语义一致**——需要验证码时暂停、用户回传、系统在同一 page 上填入并继续；差异仅在于**回传介质**与**用户入口**。

**采集环境（已有）**：

- 执行器带 task_id；验证码时通过回调持久化 `verification_type`、`verification_screenshot`，任务置为 paused；回传介质为 **Redis**（key = task_id）；用户在**采集任务列表/详情**看到 paused 任务，打开验证码弹窗（图形则展示截图，OTP 则仅输入框），输入后提交 `POST /collection/tasks/{task_id}/resume`（body：`captcha_code` 或 `otp`）；执行器轮询 Redis 后在**同一 page** 填入并继续。

**测试环境（待实现）**：

- 执行主体为**独立子进程**（run_component_test.py），仅有 test_id；无 Redis。回传介质采用**测试目录下文件**：`temp/component_tests/{test_id}/verification_response.json`（内容如 `{"captcha_code": "3g7"}` 或 `{"otp": "123456"}`）。
- **API 路径（与现有 status 一致）**：上述接口均在同一 router 下，**完整路径**为 `GET/POST /component-versions/{version_id}/test/{test_id}/status`、`GET /component-versions/{version_id}/test/{test_id}/verification-screenshot`、`POST /component-versions/{version_id}/test/{test_id}/resume`；`version_id` 为必选路径参数。
- **子进程**：在执行 `adapter.login(page)` 时单独捕获 `VerificationRequiredError`；不关浏览器、不立即失败；将 **verification 相关字段合并写入**现有 `progress.json`（读→改→写，保留 progress、current_step、step_index 等），写入 `status: "verification_required"`、`verification_type`、`verification_screenshot`（test_dir 内截图相对路径或绝对路径）；然后**轮询** `verification_response.json`（建议超时约 5 分钟）；**超时**则关闭浏览器、将 status 置为 failed，并在 progress/result 中写入 `verification_timeout: true` 或 error 含「验证码输入超时」，便于前端区分；若在超时内读到回传值，则在**当前 page** 上填入验证码并继续（手写组件可带 `params.captcha_code` 再执行一次 login；录制生成的组件由测试工具代为 fill + click 登录按钮），最后写 `result.json` / `progress.json`。
- **后端**：`GET /component-versions/{version_id}/test/{test_id}/status` 在 progress 为 `verification_required` 时返回 `verification_type`、**`verification_screenshot_url`**（指向 `GET .../verification-screenshot` 的 URL，供前端直接展示截图）；`GET /component-versions/{version_id}/test/{test_id}/verification-screenshot` 读取 test_dir 内截图文件并返回图片流。`POST /component-versions/{version_id}/test/{test_id}/resume`：请求体 `{ "captcha_code": "..." }` 或 `{ "otp": "..." }`，后端**校验**测试存在且当前 status 为 `verification_required`、且当前用户对该 version/test 有权限（如测试发起者或同项目权限），否则返回 4xx；**超时或测试已结束（completed/failed）后**再次调用 resume 返回 4xx，提示「验证已超时或测试已结束」；通过校验后将内容写入 `temp/component_tests/{test_id}/verification_response.json`。
- **前端**：轮询 status 时若发现 `verification_required`，根据 `verification_type` 展示「图形验证码」则用 **verification_screenshot_url** 请求并显示截图 + 输入框，「短信/OTP」则仅输入框；用户输入后提交 `POST .../resume`；继续轮询直至测试完成。

**用户如何传验证码（测试环节）**：在**组件版本管理页**的测试弹窗内，当测试进入「需要验证码」状态时，弹窗展示验证码输入区域（图形验证码时先通过 verification_screenshot_url 展示截图）；用户**查看截图或查收短信/邮件**后，在输入框输入验证码并点击「提交」；前端调用 resume 接口，后端写入 `verification_response.json`，子进程轮询到后代为填入页面并继续执行。与采集环境一致，仅入口为「测试弹窗」而非「采集任务列表」。

**多实例与存储**：组件测试验证码截图当前假定**单实例**或「测试与实例绑定」；多实例部署时需共享存储（如 NFS/对象存储）或保证同一 test 的 status/resume/verification-screenshot 请求路由到同一实例，否则 GET verification-screenshot 可能读不到子进程写入的本地文件。

### 10.3 组件测试流程已实施优化（已完成）

- **版本统计更新**：子进程结束后在回调线程内使用**同步** `SessionLocal` 更新 ComponentVersion 与测试历史，不再在线程内新建事件循环使用 AsyncSession，避免 asyncpg 跨 loop 报错；若更新失败则写入 `stats_update_error`，状态接口返回该字段，前端可提示「测试已执行完成，但版本统计更新失败」。
- **测试浏览器窗口**：有头模式下 `viewport=None` 且 `args=['--start-maximized']`，页面随窗口全屏显示，便于观察自动化效果；无头模式保持固定 viewport。
- **录制生成组件的验证码问题**：录制生成的登录组件（如 miaoshou_login.py）将验证码写死为录制时值，测试时必然失败；待 10.2 的「测试阶段验证码回传」实现后，用户可在测试弹窗中看到截图并输入当前验证码，由系统填入后继续，即可通过验证码环节。

### 10.4 登录与步骤完成度检测（本次补充）

**问题**：录制生成的登录组件在点击「登录」后，仅做一次性 URL 字符串判断（例如 `if "/welcome" in cur or "login" not in cur`），未按真实站点「短暂等待 → 跳转首页/仪表盘」的行为设计完整检测逻辑；当网络慢或页面存在中间过渡状态时，生成代码可能错误地认为登录失败并重新执行整段登录步骤，导致再次触发验证码或表现为「似乎没有用用户输入的验证码」。

**设计原则（与《采集脚本编写规范》及业界最佳实践对齐）**：

- **三层检测**：
  - **动作级（micro-level）**：每个 `click`/`fill` 前使用 `expect(locator).to_be_visible()` 或 `locator.wait_for(state="visible")`，避免一次性 `count()>0` 判断。
  - **步骤级（step-level）**：对「会改变页面状态」的关键步骤（登录、导航、导出、关闭业务弹窗等），在动作之后等待**目标状态特征**（URL 变化 + 目标元素出现 / loading 消失），而不是固定 `sleep` 或单次 URL 判断。
  - **流程级（flow-level）**：通过 `success_criteria` 描述组件完成业务目标后的条件（如 URL/元素/标题），由生成器统一生成结尾的成功判定逻辑。
- **条件等待优先**：对于登录/导航/导出等长耗时动作，使用「多次短轮询 + 条件判断」的模式（例如 10×1s），优先检测成功特征，同时可选检测失败特征（错误提示、仍在登录页），而非长时间固定 `sleep`。
- **不在组件内部做隐式重试**：登录组件内部只执行一次完整流程（含验证码恢复后的一次提交）；若登录后检测失败，组件应返回 `LoginResult(success=False, message=...)`，由上层 RetryStrategy 或执行器决定是否整体重试，而不是在组件内部静默重放步骤。

**登录场景的检测规范**：

- **成功特征（至少配置一项，推荐组合）**：
  - `url_not_contains: '/login'` 或 `url_contains: '/welcome'` / 实际后台首页 URL 片段；
  - 一个或多个后台仪表盘/导航栏的稳定元素存在，例如 `role=navigation`、`.sidebar-nav` 等。
- **失败特征（可选，用于给出更明确错误）**：
  - 登录错误提示元素出现，如「账号或密码错误」「验证码错误」等；
  - 登录表单的核心输入框（用户名/密码）在超时时间后仍然可见。
- **生成器职责**：
  - 当登录组件保存时配置了 `success_criteria`（目前支持 `url_contains` 等），生成器应在组件末尾插入统一的「登录结果检测块」，按 `success_criteria` 依次验证；失败时返回 `LoginResult(success=False, message=...)`，成功时返回 `LoginResult(success=True, message="ok")`。
  - 登录组件的**验证码恢复路径**必须在填入验证码并点击登录后，**无论成功还是失败都立即 return**，不得继续执行下方的主登录步骤，避免再次触发验证码；恢复路径的成功/失败判断也应复用同一套 `success_criteria`（或至少遵循同样的 URL + 元素组合规则）。

**其他关键步骤的完成度检测（导航 / 导出 / 弹窗）**：

- **导航组件**：
  - 点击菜单/链接后，等待 `page.wait_for_load_state("domcontentloaded")` 或 `networkidle`；
  - 再根据导航组件的 `success_criteria`（目标 URL 片段 + 目标页面特征元素）判断是否到达目标页。
- **导出组件**：
  - 点击「导出」按钮时，应使用 Playwright 的 `expect_download` 或等价机制等待下载开始；若平台通过「生成中…/导出中…」文案提示，则以该文案消失或「下载」按钮出现作为完成条件。
- **业务弹窗 / Modal**：
  - 触发行为后，明确等待弹窗容器可见（如 `.ant-modal, .jx-dialog__body, [role="dialog"]`），再在其作用域内点击「确定/关闭」按钮；步骤结束时可以通过弹窗容器隐藏来确认步骤完成。

本小节不要求在本次变更中一次性实现所有检测模式，但要求：

- 录制生成的 **登录组件** 在验证码恢复路径与主流程结束处，必须具备**明确的成功/失败返回**，不得因为检测不严谨而在单次执行中重复整段登录步骤。
- 录制器与生成器后续扩展 `success_criteria`（如 `element_visible`、`title_contains`）时，需遵循上述三层检测原则，并在文档中为常见场景（登录、导航、导出）提供推荐模板，便于录制时按真实站点行为配置检测条件。
