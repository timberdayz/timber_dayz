# pwcli + agent 采集脚本开发 SOP

版本: v1.0  
更新日期: 2026-03-27  
适用对象: 本人主导的采集组件开发  
适用范围: 外部平台页面探索、采集组件草稿生成、检测层设计、稳定版沉淀

## 正式组件产出规则

这部分比单个组件的录制清单更重要。对当前系统，`pwcli + agent` 能否稳定产出正式组件，取决于是否严格满足以下规则。

### 规则 1：`pwcli` 负责采证，不负责直接产出正式组件

- `pwcli` 的职责是探索页面、收集 snapshot、验证 locator、观察状态变化。
- `pwcli` 输出的是证据包，不是正式组件，也不是可直接进入生产的录制脚本。
- 任何直接从 `pwcli` 交互记录复制出来、未经 agent 整理和仓库契约校验的代码，都不能视为正式组件。

### 规则 2：正式产物必须是 canonical Python 组件

- 正式组件必须落在 `modules/platforms/<platform>/components/`。
- 正式组件必须符合当前 `modules/components/` 基类契约与 `ExecutionContext` 取参方式。
- 正式组件必须能进入 `ComponentVersion` 流程，而不是停留在临时脚本、回放脚本、trace 或 snapshot 阶段。

### 规则 3：录制目标不是“回放成功”，而是“运行时可编排”

- `pwcli + agent` 的目标不是生成一条线性回放链，而是生成能被现有执行器编排的组件。
- 顶层正式采集阶段默认只认 `login -> export`。
- `navigation`、`shop_switch`、`date_picker`、`filters` 默认应优先沉入 `export` 内部 helper，只有在明确存在复用价值时，才提升为独立可复用组件。

### 规则 4：组件逻辑必须从录制动作升级为检测逻辑

- 正式组件不能只有 click / fill / wait 的回放步骤。
- 每个关键动作都必须补齐：
  - pre-check：为什么现在可以执行
  - action：执行什么交互
  - post-check：怎样才算真的成功
- 关键检测应固化为 `detect_* / ensure_* / wait_*`，而不是依赖主观判断。

### 规则 5：运行时数据必须与录制数据解耦

- 账号、密码、店铺、日期、验证码回填值都必须来自 `self.ctx.account` / `self.ctx.config` / `params`。
- 录制时出现的真实值只能帮助 agent 识别字段语义，不能进入正式组件源码。
- 任何硬编码账号、密码、固定验证码、固定店铺文案，都视为不合格正式组件。

### 规则 6：验证码、弹窗、按钮状态属于正式组件必答题

- 验证码必须产出标准暂停恢复路径：`VerificationRequiredError -> 回填 -> 同页继续`。
- 业务内固定弹窗必须写进组件流程。
- 不可预期弹窗交给统一弹窗处理策略，不要在每个组件里重复堆砌兜底逻辑。
- “记住我”、disabled -> enabled、菜单展开 -> menuitem 可见、导出进行中 -> 文件落地，都必须显式建模为状态判断。

### 规则 7：正式成功标准必须是业务信号，不是点击信号

- `login` 成功以登录态成立为准，不以按钮点击完成为准。
- `navigation` 成功以目标页面特征成立为准，不以 URL 变化一次为准。
- `export` 成功以“文件实际下载落地且非空”为首选标准，不以 toast、dialog 关闭或点击成功为准。

### 规则 8：`pwcli` 交给 agent 的最小证据包必须结构化

- 当前 URL
- 关键步骤前后的 snapshot
- 关键动作说明
- 预期结果
- 实际结果
- 特殊场景标注
  - 是否有验证码
  - 是否有固定弹窗
  - 是否在 iframe
  - 是否有下载
  - 是否打开新标签页

如果缺少这些信息，agent 只能生成草稿，不能稳定生成正式组件。

### 规则 9：正式组件必须经过测试与版本沉淀

- `pwcli + agent` 产出的一律先视为草稿组件。
- 草稿组件必须经过本地验证、版本管理页测试或等价测试链路。
- 只有验证通过后，才允许进入 `stable`。
- 生产采集只运行 stable 组件，不运行 `pwcli` 现场探索结果。

### 规则 10：已有成熟组件时，优先优化，不优先重录

- 如果平台已有成熟 `export` 或 `login`，优先用 `pwcli` 补证据，再让 agent 定点修复或增强。
- 只有在现有组件已失真、缺少关键链路、或无法满足当前运行时契约时，才从头录制。

### 一句话原则

`pwcli + agent` 在当前系统中的正确职责，不是“替代运行时”，而是“成为唯一的证据采集与代码生成工具，并持续产出符合现有运行时契约的正式组件”。

V2 榛樿涓绘祦绋? `pwcli 鎺㈢储 -> agent 鍒嗘瀽 -> canonical Python 缁勪欢 -> 鏈湴楠岃瘉 -> 缁勪欢鐗堟湰绠＄悊娴嬭瘯 -> stable`

V2 椤跺眰姝ｅ紡閲囬泦闃舵鍙 `login -> export`锛宯avigation / shop_switch / date_picker / filters 鏄?`export` 鍐呴儴 helper锛屼笉鍐嶄綔涓虹嫭绔嬫寮忛噰闆嗛樁娈点€?

---

## 1. 目的

这份 SOP 解决两个问题：

1. 我应该如何使用 `pwcli` 高效探索复杂页面，而不是靠肉眼和反复试错写脚本。
2. 我应该如何把 `pwcli` 的探索结果交给 agent，让 agent 帮我产出可用的采集组件，而不是只得到一段录制式代码。

本文不是通用 Playwright 教程，而是面向当前仓库的采集组件开发流程说明。仓库现行基线仍然是：

- `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
- `docs/guides/RECORDER_PYTHON_OUTPUT.md`
- `docs/guides/COMPONENT_REUSE_WORKFLOW.md`

若本文与上述规范冲突，以上述规范为准。

---

## 2. 工具定位

### 2.1 `pwcli` 的定位

`pwcli` 不是正式组件生成器，而是页面探索工具。它最擅长做这些事：

- 打开真实页面
- 抓当前页面 `snapshot`
- 获取稳定的元素引用
- 快速点击、输入、切换、悬停
- 观察页面变化前后结构
- 生成截图、trace、snapshot 文件给 agent 分析

`pwcli` 特别适合解决以下高成本问题：

- 页面里到底哪些元素能点
- 日期控件、筛选器、店铺切换分别在哪
- 菜单、弹窗、iframe 展开后长什么样
- 哪一步之后页面发生了什么变化
- 交互前后分别可以观察哪些完成信号

### 2.2 agent 的定位

agent 不应该只被要求“直接写完整脚本”。更高效的用法是让 agent 分阶段工作：

1. 先读 `snapshot`，识别页面结构
2. 再识别关键交互区和可观察状态
3. 再产出 `detect_* / ensure_* / wait_*`
4. 最后生成符合仓库规范的 Python async 组件代码

### 2.3 正式组件的定位

正式采集组件的职责是：

- 落在 `modules/platforms/<platform>/components/`
- 符合当前组件契约
- 与 `ComponentVersion` 体系对齐
- 通过版本管理页测试
- 最终提升为 stable

`pwcli` 探索结果不能直接视为正式组件，必须经过 agent 整理和人工验证。

---

## 3. 总体原则

### 3.1 先探索，再编码

不要在未理解页面结构前直接让 agent 生成整段采集脚本。正确顺序是：

1. 用 `pwcli` 打开页面
2. 用 `snapshot` 抓状态
3. 把状态交给 agent 分析
4. 再生成组件草稿

### 3.2 先复用成熟 `export`

优先判断当前平台是否已有成熟 `export` 组件。若已有：

1. 复用成熟 `export`
2. 只补最小前置组件
3. 只修必要分支

不要默认重录或重写整个导出流程。

### 3.3 页面变化后立即重新 `snapshot`

元素引用会变。以下情况后必须重新抓 `snapshot`：

- 页面跳转
- 打开/关闭弹窗
- 展开菜单
- 切换 tab
- 展开日期选择器
- 打开店铺下拉
- 导出弹窗出现

### 3.4 只让 agent 基于证据工作

给 agent 的上下文必须尽量结构化：

- 当前 URL
- 当前页面 `snapshot`
- 必要时的 `screenshot`
- 当前步骤说明
- 预期动作
- 实际结果

不要只说“这个页面很复杂，帮我写一下”。

### 3.5 检测层先于成品脚本

真正稳定的组件，不是“能点完”，而是“知道什么时候真的完成了”。  
`pwcli` 最有价值的地方，是帮助我把以下检测依据收集完整：

- `login_ready`
- `navigation_ready`
- `shop_switch_ready`
- `date_picker_ready`
- `filters_ready`
- `export_complete`

---

## 4. 一次性准备

### 4.1 环境确认

当前机器已满足 `pwcli` 前提：`node`、`npm`、`npx` 已可用。

### 4.2 PowerShell 命令模板

建议在 PowerShell 会话里先定义：

```powershell
function pwcli {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [object[]]$CliArgs
    )
    & npx --yes --package @playwright/cli playwright-cli @CliArgs
}
```

验证：

```powershell
pwcli --help
```

如果不想每次手动定义函数，也可以直接使用仓库内包装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pwcli.ps1 --help
```

或在当前目录下定义一个更稳定的别名：

```powershell
Set-Alias pwcli-script .\scripts\pwcli.ps1
pwcli-script --help
```

### 4.3 工作目录约定

为避免产物散落，按 skill 约定，在仓库内统一使用：

```powershell
New-Item -ItemType Directory -Force output\playwright\shopee-orders | Out-Null
Set-Location output\playwright\shopee-orders
```

建议每次探索一个页面/数据域就新建一个目录，例如：

- `output/playwright/shopee-orders`
- `output/playwright/tiktok-products`
- `output/playwright/miaoshou-warehouse`

### 4.4 会话命名

建议每个探索任务固定会话名，避免串状态：

```powershell
$env:PLAYWRIGHT_CLI_SESSION = "shopee-orders"
```

如果切换任务，先改会话名：

```powershell
$env:PLAYWRIGHT_CLI_SESSION = "tiktok-products"
```

### 4.5 登录态持久化策略

默认 `pwcli open` 会使用内存中的临时浏览器资料目录。若输出里出现：

```text
user-data-dir: <in-memory>
```

说明当前登录态不会在关闭浏览器后保留。

对采集脚本开发，推荐固定使用：

- 平台级 profile 目录
- 任务级 work 目录
- 命名 session
- 必要时再额外导出 storage state

推荐目录结构：

```text
output/playwright/
  profiles/
    miaoshou/
    shopee/
    tiktok/
  state/
    miaoshou.json
    shopee.json
    tiktok.json
  work/
    miaoshou/
      orders-shopee/
      orders-tiktok/
    shopee/
      traffic-overview/
      products-export/
    tiktok/
      traffic-overview/
      orders-export/
```

推荐打开方式：

```powershell
Open-PwcliMiaoshou -WorkTag "orders-shopee"
Open-PwcliShopee -WorkTag "traffic-overview"
Open-PwcliTiktok -WorkTag "orders-export"
```

说明：

- profile 目录按平台复用，适合一个平台录制多个组件
- work 目录按任务隔离，适合保留不同组件的 snapshot / screenshot / trace
- 同一个平台下只要继续使用同一个 profile 目录，通常不需要重新登录
- 同一个 profile 目录不要同时被多个浏览器会话共用

如需额外保存认证状态快照，可在登录成功后执行：

```powershell
Save-PwcliMiaoshouState
Save-PwcliShopeeState
Save-PwcliTiktokState
```

之后可通过以下方式加载：

```powershell
pwcli state-load ".\output\playwright\state\miaoshou.json"
```

在当前仓库场景下，推荐优先使用 `--profile`，`state-save/state-load` 作为补充备份。

---

## 5. `pwcli` 最小命令集

日常只需要先掌握这组命令：

```powershell
pwcli open "https://example.com" --headed
pwcli snapshot
pwcli snapshot --filename ".\01-home.md"
pwcli click e3
pwcli fill e8 "text"
pwcli hover e10
pwcli press Enter
pwcli screenshot --filename ".\01-home.png"
pwcli reload
pwcli tab-list
pwcli tab-select 0
pwcli tracing-start
pwcli tracing-stop
pwcli console warning
pwcli network
```

说明：

- `snapshot --filename` 用于把页面结构固化成文件，便于发给 agent
- `screenshot --filename` 用于保留视觉证据
- `tracing-start / tracing-stop` 用于复杂流程排查
- `console warning` 和 `network` 用于辅助判断异常

---

## 6. 标准工作流

这是默认工作流。除非任务极简单，否则按此顺序执行。

### Step 1: 先判定复用策略

开始之前，先让 agent 看现有组件，输出这三项：

1. 是否已有成熟 `export`
2. 最小需要补哪些前置组件
3. 当前最大风险点是什么

推荐提示词：

```text
请先不要重写脚本。参考当前平台已有组件，判断这个页面/数据域应该复用哪个成熟 export，只列出最小需要补的前置组件和改动点。输出：
1. 复用对象
2. 需要补的 login / navigation / shop_switch / date_picker / filters
3. 风险点
```

### Step 2: 用 `pwcli` 探索页面

先打开页面并抓第一张快照：

```powershell
pwcli open "目标URL" --headed
pwcli snapshot --filename ".\01-entry.md"
pwcli screenshot --filename ".\01-entry.png"
```

然后只做一件事：找页面里的关键交互区。

我不在这一步强行写代码，也不要求 agent 直接给整段脚本。

### Step 3: 展开关键状态并分别抓快照

至少抓这些状态：

- 登录页
- 登录成功后的首页
- 店铺切换展开态
- 日期面板展开态
- 筛选器展开态
- 导出菜单/导出弹窗展开态
- 下载前一刻
- 失败现场

每展开一个关键状态，立刻重新抓：

```powershell
pwcli click e3
pwcli snapshot --filename ".\02-shop-switch-open.md"
pwcli screenshot --filename ".\02-shop-switch-open.png"
```

### Step 4: 先让 agent 做结构分析

推荐提示词：

```text
这是当前页面的 playwright snapshot。
请先不要写整段脚本。
请识别：
1. 店铺切换区域
2. 日期控件
3. 筛选器
4. 导出入口
5. 每一步前后的可观察完成信号
6. 哪些区域需要在 dialog / menu / iframe 内再次定位
```

这一阶段的目标是“看懂页面”，不是“生成最终代码”。

### Step 5: 再让 agent 产出组件草稿

当页面结构分析清楚后，再要求 agent 输出代码：

```text
请基于这个页面结构，输出 Playwright Python async 组件草稿。
要求：
1. 优先使用 get_by_role / get_by_label / get_by_text
2. 关键步骤写成 pre-check -> action -> post-check
3. 提炼 detect_* / ensure_* / wait_* helper
4. 选择器差异集中到 *_config.py
5. 不要只写录制式直线脚本
6. 导出完成必须检查文件真实下载成功
```

### Step 6: 我本人跑真实流程

这一步必须人工参与，因为以下事情只能由我确认：

- 业务上到底该切哪个店
- 日期是否真的生效
- 筛选是否真的命中目标数据
- 导出文件是否真的是正确内容
- 页面是否存在偶发验证码、限流、会话过期

### Step 7: 把失败现场再次交给 agent

失败时，至少保留：

- 当前 URL
- 当前 `snapshot`
- 当前 `screenshot`
- 失败步骤
- 实际报错
- 预期行为

推荐提示词：

```text
这是失败时的 snapshot / screenshot / 日志。
请不要重写整个组件，只做最小补丁。
先判断失败属于哪一层：
login / shop_switch / navigation_ready / date_picker_ready / filters_ready / export_complete
然后只修这一层。
```

### Step 8: 正式沉淀为组件版本

当组件已经基本稳定后：

1. 保存 `.py`
2. 进入 `ComponentVersion` 体系
3. 在版本管理页测试
4. 提升为 stable

---

## 7. 我与 agent 的协作分工

### 7.1 我负责什么

- 选择目标页面和真实账号
- 用 `pwcli` 抓关键状态
- 描述业务目标
- 判断组件是否真的满足业务
- 回传失败现场

### 7.2 agent 负责什么

- 读 `snapshot` 理解页面结构
- 识别关键交互区
- 设计 locator
- 提炼 `detect_* / ensure_* / wait_*`
- 生成或修补 Python async 组件
- 把平台差异收敛到配置层

### 7.3 明确不该让 agent 做什么

- 不给任何页面证据就盲写完整脚本
- 只凭截图猜按钮
- 把录制动作原样堆成一条直线脚本
- 在没有业务上下文时替我决定最终成功标准

---

## 8. 如何用 `pwcli` 帮助设计检测层

`pwcli` 本身不会自动生成 `wait_export_complete()`，但它能帮我收集写这个函数需要的证据。

### 8.1 登录检测

用 `pwcli` 确认以下哪一个或哪两个信号能作为 `login_ready`：

- URL 已离开登录页
- 登录表单消失
- 首页主导航出现
- 工作台关键元素出现

建议动作：

```powershell
pwcli snapshot --filename ".\login-before.md"
# 执行登录动作后
pwcli snapshot --filename ".\login-after.md"
```

然后让 agent 提炼：

- `detect_login_ready()`
- `wait_login_ready()`

### 8.2 导航检测

导航成功不等于“点过菜单”。要用 `pwcli` 观察：

- URL 是否变化
- 目标页 tab 是否高亮
- 目标页标题是否出现
- 目标页主表格/主图表是否出现

然后让 agent 提炼：

- `wait_navigation_ready()`

### 8.3 店铺切换检测

店铺切换不要只看是否点了菜单项。要确认：

- 当前店铺名是否变化
- 当前页面数据区域是否刷新
- 目标店铺高亮是否出现

然后让 agent 提炼：

- `detect_current_shop()`
- `ensure_shop_selected()`

### 8.4 日期检测

日期选择不要只看输入框被点过。要确认：

- 日期面板已展开
- 目标日期已选中
- 输入框值已变化
- 页面数据已刷新或日期标签已变化

然后让 agent 提炼：

- `wait_date_picker_ready()`
- `ensure_date_range_selected()`

### 8.5 筛选器检测

筛选器通常需要确认：

- 筛选器面板已展开
- 目标项已选中
- “应用”或“搜索”已执行
- 结果区域已刷新

然后让 agent 提炼：

- `wait_filters_ready()`
- `ensure_filters_applied()`

### 8.6 导出完成检测

这是最重要的一层。

我必须用 `pwcli` 确认：

- 点击导出后是否出现导出弹窗
- 是否需要二次确认
- 是否存在“下载”按钮
- 是否触发新标签页
- 是否真实开始下载

正式组件的成功标准仍应优先是：

- 文件实际下载落地
- 文件非空

然后让 agent 提炼：

- `wait_export_dialog_ready()`
- `wait_download_ready()`
- `wait_export_complete()`

---

## 9. 什么时候抓什么证据

### 9.1 最低证据包

对一个新页面，最低要求保留：

- `01-entry.md`
- `01-entry.png`
- `02-key-state.md`
- `02-key-state.png`
- `03-export-open.md`
- `03-export-open.png`

### 9.2 失败时必保留

失败时必须补：

- `xx-fail.md`
- `xx-fail.png`
- 当前 URL
- 当前步骤描述
- 是否出现弹窗 / iframe / 重定向

### 9.3 复杂问题时补 trace

复杂问题包括：

- 偶发失败
- 新标签页
- 下载事件不稳定
- 页面无明显报错但脚本失败

此时使用：

```powershell
pwcli tracing-start
# 复现流程
pwcli tracing-stop
```

---

## 10. 面向 agent 的固定输入模板

### 10.1 页面结构分析模板

```text
这是当前页面的 playwright snapshot。
目标：我需要在这个页面完成店铺切换、日期选择、筛选和导出。

请先不要直接写完整脚本。
请按下面顺序输出：
1. 页面关键交互区识别
2. 每个区域推荐的 locator 策略
3. 每一步操作前后的完成信号
4. 哪些地方需要在 dialog / menu / iframe 内再次定位
5. 可能的脆弱点
```

### 10.2 组件草稿模板

```text
请基于这个页面结构输出 Playwright Python async 组件草稿。
要求：
- 优先 get_by_role / get_by_label / get_by_text
- 提炼 detect_* / ensure_* / wait_* helper
- 关键步骤必须写成 pre-check -> action -> post-check
- 选择器差异集中到 *_config.py
- 保持与当前仓库采集组件规范一致
- 导出完成必须检查文件真实下载成功
```

### 10.3 最小补丁模板

```text
这是失败时的 snapshot / screenshot / 日志。
请不要重写整个组件。
只做最小补丁。
请先判断失败属于哪一层：
login / shop_switch / navigation_ready / date_picker_ready / filters_ready / export_complete
然后给出：
1. 根因判断
2. 最小代码补丁
3. 还需要我再补哪一个 snapshot
```

---

## 11. 组件产出策略

### 11.1 默认优先级

默认按这个优先级处理：

1. 复用成熟 `export`
2. 只补最小前置组件
3. 只在必要时新建数据域级 `export`

### 11.2 何时只补前置组件

以下情况优先只补：

- 导出页面结构与现役页面接近
- 复杂度主要在登录、店铺切换、日期、筛选
- 下载链路本身没有大变化

常见补充对象：

- `login`
- `navigation`
- `shop_switch`
- `date_picker`
- `filters`

### 11.3 何时新建或大改 `export`

只有当以下情况明显成立时，才考虑新建或大改：

- 导出链路完全不同
- 二次确认流程明显变化
- 成功标准发生本质变化
- 原有 `export` 的配置抽象无法承载差异

---

## 12. 日常最小作战模板

这是我平时可以直接照做的最小流程。

### 12.1 准备

```powershell
function pwcli {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [object[]]$CliArgs
    )
    & npx --yes --package @playwright/cli playwright-cli @CliArgs
}
New-Item -ItemType Directory -Force output\playwright\shopee-orders | Out-Null
Set-Location output\playwright\shopee-orders
$env:PLAYWRIGHT_CLI_SESSION = "shopee-orders"
```

### 12.2 打开并抓第一页

```powershell
pwcli open "目标URL" --headed
pwcli snapshot --filename ".\01-entry.md"
pwcli screenshot --filename ".\01-entry.png"
```

### 12.3 展开关键控件并抓状态

```powershell
pwcli click e3
pwcli snapshot --filename ".\02-opened.md"
pwcli screenshot --filename ".\02-opened.png"
```

### 12.4 发给 agent 做结构分析

使用 10.1 的模板。

### 12.5 再让 agent 产出组件草稿

使用 10.2 的模板。

### 12.6 跑真实页面并保留失败现场

失败时再抓：

```powershell
pwcli snapshot --filename ".\99-fail.md"
pwcli screenshot --filename ".\99-fail.png"
```

### 12.7 让 agent 做最小补丁

使用 10.3 的模板。

---

## 13. 交付前检查表

在把组件保存、注册版本、提 stable 之前，至少确认：

- 是否优先尝试了复用成熟 `export`
- 关键页面状态是否都抓过 `snapshot`
- agent 是否先做了结构分析，而不是直接盲写
- 组件是否用了 `detect_* / ensure_* / wait_*`
- 关键步骤是否是 `pre-check -> action -> post-check`
- 成功标准是否依赖可观察信号，而不是“按钮刚点过”
- 导出成功是否以文件真实落地为准
- 是否已在真实账号下跑过至少一轮
- 失败分支是否至少覆盖了最常见的一种
- 代码是否准备进入 `ComponentVersion` 流程

---

## 14. 反模式

以下做法应避免：

- 只凭截图让 agent 猜页面结构
- 不抓 `snapshot` 就直接引用旧的 `e12`
- 让 agent 一上来写完整平台脚本
- 只记录成功路径，不记录失败现场
- 用录制式直线代码替代检测层
- 把所有平台差异写进一个大文件
- 点击成功就当业务成功
- 下载弹窗出现就当导出完成

---

## 15. 最终结论

`pwcli` 最适合做的是：

- 把复杂页面探索变成可重复的证据收集过程
- 把“我看不懂页面”变成“我能给 agent 一组结构化上下文”
- 把组件开发里最难的检测依据收集出来

agent 最适合做的是：

- 基于这些证据提炼结构
- 生成和修补组件代码
- 把页面探索结果变成符合仓库规范的正式组件

对我本人来说，最重要的不是让 `pwcli` 直接生成最终脚本，而是坚持这条流程：

`pwcli` 探索页面 -> 固化 snapshot / screenshot -> agent 做结构分析 -> agent 产出组件草稿 -> 我用真实页面验证 -> agent 做最小补丁 -> 沉淀为正式组件版本。
