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
  - **可选步骤**：对 `optional=true` 的步骤，生成 try/except 或「先判断可见再操作」等与规范一致的可选执行逻辑，或至少生成注释「可选步骤，执行失败可跳过」，使执行器行为与 YAML 的 optional 一致。
  - **结构**：按《采集脚本编写规范》的复杂交互、临时弹窗等留注释占位（如「若有弹窗在此 wait 再点击关闭」），便于用户录制后补全。
- **实现位置**：可在 `backend/services/` 或 `backend/utils/` 下新增模块（如 `steps_to_python.py` 或 `collection_recorder_codegen.py`），由录制相关 router 调用；或放在 `tools/` 下供后端与 CLI 共用。
- **可选增强**：若 Trace 解析或 steps_file 中能提供 role/label/text（如从 DOM 快照或录制脚本内记录），生成器优先使用以产出更多 get_by_*。

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

生成器在生成 Python 时对「临时弹窗/遮挡」留注释占位（见第 1 节），与上述执行器与规范行为一致；用户录制后可按规范补全或依赖执行器步骤边界关闭。

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
| 后端 | `backend/routers/component_recorder.py` | 在 stop 响应中增加 python_code 和/或新增 POST /recorder/generate-python |
| 前端 | `frontend/src/views/ComponentRecorder.vue`（或等价录制页） | 增加 Python 代码展示与编辑区域；保存时传 python_code 到 /recorder/save，主路径保存为 .py |
| 文档 | `docs/guides/` 或录制相关文档 | 说明录制后如何得到 .py、如何按规范微调生成结果；组件保存路径、覆盖即更新（历史依赖 Git）、淘汰与 is_active 的约定（见第 8 节） |

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
