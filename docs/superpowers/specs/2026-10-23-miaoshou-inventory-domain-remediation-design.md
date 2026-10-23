# 妙手 Miaoshou 库存数据域采集整改设计（Miaoshou Inventory Domain Remediation）

**日期:** 2026-10-23
**状态:** 待实施（**第 2 稿**：已吸收独立评审结论，修正 20 处事实/引用/结构问题）
**定位:** 本 spec 解决「妙手库存数据域采集组件不可靠 / 不可诊断 / 不符合既有规范」，以及「规范与实现之间缺少强制连接导致债务复发」两个问题。**不改**采集配置链路的业务语义、粒度口径、入库链路与 Dashboard。
**关联文档（规则来源，本 spec 只引用条款，不重复其内容）:**
- `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` — 《采集脚本编写规范》（唯一成文编写依据，下文简称《规范》）
- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md` — canonical 组件规则
- `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` — 活跃清单与 Archive 前置条件
- `docs/guides/CANONICAL_COMPONENT_STATUS.md` — 组件阶段性状态
- `docs/guides/CANONICAL_RUNTIME_ISSUES.md` — 真实链路问题清单
- `docs/guides/COMPONENT_COLLABORATION.md` — 组件协作规则
- `docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md` — 函数/类长度上限、覆盖率目标
- `docs/superpowers/specs/2026-09-13-miaoshou-finance-inventory-data-domain-recording-design.md` — 库存域上次重做的设计（本 spec 的直接上游）

---

## 0. 修订记录

| 稿次 | 日期 | 内容 |
|---|---|---|
| 初稿 | 2026-10-23 | 基于 2026-10-23 采集失败事件（task `7bb2a92e-a0eb-4129-ba5c-6237b852c909`）与本地库 `xihong_erp` 实测形成 |
| 第 2 稿 | 2026-10-23 | 吸收独立评审（verifier）结论，修正 4 项必须修的事实错误、1 项设计缺陷、4 处交叉引用错位、验收缺口、3 条遗漏风险、11 处引用精度问题。**关键修正见 §0.1** |

### 0.1 第 2 稿的关键修正（与初稿结论不同的地方）

| # | 初稿的说法 | 评审核实后的事实 | 影响 |
|---|---|---|---|
| 1 | 订单域 `force=True` 修复是「同平台**已验证**的实现」 | 该修复是**未提交的工作区改动**，且当前**打挂 4 个既有测试**（fake locator 的 `click()` 不接受 `force=` 关键字 → `TypeError` 被 `except Exception` 吞掉 → `RuntimeError`） | 蓝本不可直接复用；A10 验收基线不是「全绿」；风险表新增一行 |
| 2 | L1-2 只要改组件接 `ctx.logger` + `report_step` 即可 | 执行器构造 `ExecutionContext` 时**既未传 `logger=` 也未传 `step_callback=`**（`executor_v2.py:2284-2288`），且 `core.collection_task_logs` **仅由 `collection_tasks.py` 路由写入，执行器不写** | L1-2 必须同时改执行器，否则 A8 不可达成 |
| 3 | 《规范》§6 写「组件内部不自动重试」 | 《规范》§6:171 原文是「关键步骤配合 `RetryStrategy` **或组件内重试**」——**允许**组件内重试。写「组件内部不自动重试」的是**上游 2026-09-13 spec §6** | L3-2 第一条补白的依据从「《规范》缺口」改为「《规范》与上游 spec 口径冲突」 |
| 4 | 「导出流程无 `VerificationRequiredError` 抛点」 | 准确表述是「**妙手平台**导出流程无抛点」；TikTok `products_export.py:212` 正是导出流程抛点的先例 | 表述范围收窄，结论不变 |
| 5 | `inventory_config.py` 三项配置「grep 零命中」 | **定义 6 处**（L32/33/78/87/88/94），**被读取 0 处**；且 `group_titles`/`data_type_dir` 正被 `test_miaoshou_inventory_export_contract.py:23,25,26` 断言 | 处置由「接上或删除」改为「**接上**」（删除会破坏既有测试） |
| 6 | 复用 `backend/services/component_recorder_lint.py` | 该文件**不存在**；真实实现在 `backend/domains/collection/routers/component_recorder.py`，且**已有 5 条规则**（`wait_for_timeout_usage` / `fixed_sleep_usage` / `count_is_visible_pattern` / `swallow_exception_pattern` / `first_nth_usage`） | L3-1 改为「扩展既有 lint + 新增缺失检查项」 |
| 7 | L2-9 把 `warehouse_filters.py` 结构归位排进批次 2 | §5.7 明写该重命名**不在批次 1/2 执行** | L2-9 移出批次 2，改挂批次 4 |

---

## 1. 背景与目标

### 1.1 事件

2026-10-23 11:55:51（本地时间 GMT+8），用户在采集配置中执行了包含 `inventory` 数据域的妙手采集任务，任务失败：

| 本地时间 | 事件 | 证据 |
|---|---|---|
| 11:55:46 | 配置 `miaoshou-miaoshou_real_001-monthly-inventory-orders-v1` 被更新（scope 数据域改为 `['inventory']`） | `logs/backend-local.out.log:301-302` |
| 11:55:51 | 任务启动（`created_at`/`started_at` = `2026-10-23 03:55:51+00` UTC） | `backend-local.out.log:316` |
| ~11:56:09 | 前端步骤时间线显示「等待验证码回填」 | 前端时间线（后端日志无对应行） |
| 11:56:14 | 用户提交验证码，任务恢复 | `backend-local.out.log:332-333` |
| 11:56:27 | 登录态复用成功（`[LOGGED_IN] confidence=0.80`） | `backend-local.out.log:349` |
| 11:56:33 | 导航至 `/warehouse/checklist` | `backend-local.out.log:360-361` |
| **11:56:35** | **失败**：`Export failed: Locator.click: Timeout 1500ms exceeded` | `backend-local.out.log:364` |
| 11:56:38 | 任务结束，`status=failed`，`duration=44s` | `core.collection_tasks` id=637 |

> **时区说明**：`core.collection_tasks.created_at` 等字段存的是 **UTC**（`2026-10-23 03:55:51+00`），本文表格中的时间统一为**本地时间 GMT+8**（UTC+8）。§3.1 表格中的时间同样已换算为本地时间。

失败发生在库存域的**第一个交互动作**（选择仓库范围），后续的搜索 / 导出弹窗 / 字段全选 / 下载落盘全部未执行。

### 1.2 目标

1. 让 `miaoshou/inventory_export` 在真实页面上**稳定**完成采集，消除随机失败
2. 让任一步失败都能**一眼定位**（阶段 + 选择器 + 截图），不再需要翻后端原始日志
3. 把《规范》的工程强约束从**文档文字**变成**机器可执行的闸门**，阻止同类债务复发
4. 保证「采集配置勾选库存数据域 → 执行配置 → 产出文件入库」这条业务链路**稳定可用**

### 1.3 非目标（明确不做，共 5 条）

- 不改采集配置的**业务语义**：粒度口径、日期窗口、域拆分规则一律不动
- 不改入库链路：`catalog_scanner → data_sync_service → raw_data_importer → b_class.fact_miaoshou_inventory_snapshot` 不动
- 不改 Dashboard / semantic / mart / api 任何 SQL 资产
- 不做跨平台弹窗 / 选择器的硬合并（边界见 §5.6）
- 不在本 spec 内重写订单域、采购域（仅引用其模式，且引用前必须先修好其测试，见 §9 DEP-1）

---

## 2. 根因分析（2026-10-23 实测）

### 2.1 直接根因：jx-select 的透明占位层拦截点击

后端日志 `logs/backend-local.out.log:364-375` 的 Playwright call log：

```
waiting for get_by_label(re.compile(r"仓库", re.IGNORECASE)).first
  - locator resolved to <input value="" type="text" tabindex="0" role="combobox"
        aria-expanded="false" aria-haspopup="listbox" class="jx-select__input is-small"/>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div class="jx-select__selected-item jx-select__placeholder is-transparent">…</div>
        intercepts pointer events
    - retrying click action
```

出问题的代码：`modules/platforms/miaoshou/components/warehouse_filters.py:95`

```python
trigger = await self._warehouse_scope_trigger(page)   # :21-35
await trigger.click(timeout=1500)                      # :95  ← 失败点
```

妙手 ERP 使用 `jx-select` 组件库，其 `.jx-select__selected-item` 覆盖在 `.jx-select__input` 之上。空选择时该层是 placeholder（`is-transparent` = 视觉透明但仍参与命中测试）。Playwright 的 actionability 检查判定命中测试被拦截，重试至 1500ms 超时。

### 2.2 两种遮挡形态（必须分别防护）

同平台订单域的实现表明 `jx-select` 存在两类覆盖层，**不是同一个 bug**：

| 形态 | 覆盖层 | 出现条件 | 订单域现状 |
|---|---|---|---|
| **A. 空态 placeholder** | `.jx-select__selected-item.is-transparent`（无选中项时的占位文案层） | 选框为空 | 订单域无此形态（订单状态总被选中） |
| **B. tags 堆积** | `.jx-select__selected-item` 内堆叠多个 `.jx-tag`，含 `+ N` 折叠标签 | 已全选时 | 工作区版本尝试处理（见 §2.3） |

**本次失败是形态 A。** 只针对 B 的补丁无法覆盖本次失败。

### 2.3 订单域的同类修复：未提交，且当前测试不通过

订单域 `modules/platforms/miaoshou/components/filters.py` 的工作区版本处理过形态 B：

```python
# 全选状态下 selected-item 区域堆着 jx-tag,盖住 trigger(input)
# 的可点击区。force=True 穿透遮挡点击；万一还失败,重试 1 次。
clicked = False
for _ in range(2):
    try:
        await trigger.click(timeout=1500, force=True)
        clicked = True
        break
    except Exception:
        continue
if not clicked:
    raise RuntimeError("无法点开订单状态下拉框")
```

**两个必须记录的事实：**

1. **该改动未提交**：`git status` 显示这是工作区唯一未提交改动；`git show HEAD:...filters.py` 中**不存在** `force=True` / `clicked` 逻辑。
2. **该改动当前打挂 4 个既有测试**（2026-10-23 实测）：
   ```
   python -m pytest backend/tests/test_miaoshou_filters_component.py -q
   → 4 failed in 2.73s
     test_miaoshou_filters_does_not_click_full_select_when_overlay_checkbox_is_already_selected
     test_miaoshou_filters_clicks_full_select_when_overlay_checkbox_is_not_selected
     test_miaoshou_filters_uses_visible_overlay_instead_of_waiting_on_hidden_checkbox_input
     test_miaoshou_filters_skips_overlay_when_summary_already_shows_all_selected
   ```
   根因：`backend/tests/test_miaoshou_filters_component.py:41` 的 fake locator 签名为 `async def click(self, timeout: int | None = None)`，**不接受 `force` 关键字** → `TypeError` → 被 `except Exception: continue` 吞掉 → `filters.py:122` 抛 `RuntimeError`。

> **两点推论**：
> ① 订单域实现**不能**直接当作「已验证蓝本」复制，库存域若照抄会引入同样的 fake-locator 不兼容问题；
> ② 该实现本身**违反《规范》§2/§13**（用 `except Exception: continue` 吞异常），且违反《规范》§16（`.first` 在 page 根作用域使用）。**它不是本 spec 的模仿对象。**
>
> 正确做法见 §5.2 L1-1：**不复用这段代码，只复用它想解决的问题**，并用本 spec 的测试策略（fake locator 支持 `force=`）从一开始就避免这个坑。

### 2.4 根因是结构性的：没有共享层

《规范》§1 要求共享原语放在 `modules/components/`。实际：

- `_is_checkbox_selected` 在 miaoshou 的 `components/` 目录内存在 **3 份逐字相同**的副本（SHA256 一致）：`filters.py:46` / `inventory_export.py:45` / `warehouse_filters.py:52`
- `_ensure_popup_closed` 存在 **4 份**：`inventory_export.py:67` / `orders_export_base.py:98` / `purchase_export.py:46` / `warehouse_filters.py:74`

没有共享层 ⇒ 修复只能靠人工复制 ⇒ 复制是可选的 ⇒ 订单域的修复拿不到库存域。

库存域的 `warehouse_filters.py` 本身也是从更早的归档实现 `modules/platforms/miaoshou/archive/inventory_snapshot_export.py`（其 `:73`/`:75`/`:89` 与库存域同源）复制演化而来，**同一个缺陷被原样继承**。

### 2.5 这是 flaky，不是必现

`docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md:1008` 记录：**「`inventory` 域历史上成功过（2026-09-14）」**。

触发条件是「刚过完验证码 / 刚导航 / 选框尚未就绪」的时序窗口。本次时间线正好落在窗口内：登录完成 11:56:27 → 导航完成 11:56:33 → 失败 11:56:35（**8 秒内**）。

**flaky 比必现失败更危险**：它会以「随机失败」形式反复出现，且每次伴随一次验证码等待（本次 44 秒总耗时中 23 秒在等验证码：11:55:51 → 11:56:14）。执行器对 export 域失败**不做自动重试**（`executor_v2.py:2813` `raise StepExecutionError` → `:2887 except Exception` → `:2890 failed_domains.append` → `:2894 continue`），因此每次 flaky 都等于整域失败。

### 2.6 规范符合性逐条对照

《规范》§13 列了 5 条工程强约束，明写「**违反其中任一条即视为代码缺陷，需在合入前修复**」。库存域违反其中 4 条：

| 条款 | 要求 | 库存域现状 | 判定 |
|---|---|---|---|
| §1 / §13.1 / §16 | 定位器唯一性；`.first`/`.nth` 禁止当默认消歧手段，lint 要求「有注释才放行」 | `inventory_export.py` 18 处 `.first` + 2 处 `.nth(`；`warehouse_filters.py` 7 处 `.first`；**零处**业务语义注释 | ✗ 强约束 1 |
| §1 | 先收敛作用域，避免在 page 根用宽泛选择器 | `_warehouse_scope_trigger` 直接在 page 根用 `get_by_label(re.compile("仓库"))` | ✗ |
| §2 | 禁止单次 `count()+is_visible()` 后即操作 | `_first_visible_selector`（`inventory_export.py:33-43`）正是如此 | ✗ |
| §2 / §13 | 禁止 `except Exception: pass` 吞掉定位失败 | 两文件合计 26 处 `except Exception` | ✗ |
| §3.5 | 检测层强制三段式：pre-check → action → **post-check** | 仓库筛选只「点了全选」即视为成功，无 post-check | ✗ |
| §3.5.1 | 检测应结构化：`stage/status/reason/current_url/matched_signal/screenshot_path` | 无 | ✗ |
| §5.3 / §13.4 | `self.report_step` 每个关键步骤前后；失败须含阶段/组件名/版本/URL/核心选择器；关键路径保留截图 | **完全未使用** `report_step`、未接 `ctx.logger`、无截图 | ✗ 强约束 4 |
| §5.5 / §8.1 | 导出阶段验证码与登录阶段同一套（检测→暂停→回传→同 page 继续） | **妙手平台**导出流程无抛点（全仓仅 `miaoshou/components/login.py:91` 抛 `VerificationRequiredError`；TikTok `products_export.py:212` 是导出流程抛点的先例） | ✗ |
| §6 | 关键步骤配合 `RetryStrategy` **或组件内重试**；明确错误类型，区分可重试/不可重试 | `message=str(e)` 裸字符串；无重试 | ✗（重试缺失 + 错误无类型） |
| §7 | 执行器在每域导出前调 `close_popups`；组件内已知弹窗应显式 wait | 自造 `_ensure_popup_closed`，miaoshou 内 4 份重复 | △ |
| §13.2 | 导航完成契约：URL/路由特征 **+** 关键元素可见（双信号） | `navigation.py:82` 只等 `get_by_text("仓库清单")` 文字可见 | ✗ 强约束 2 |
| §13.3 | 动态 DOM 契约：关键交互前重新定位元素，禁止长期持有可能失效的 locator 跨步骤复用 | 库存域未长期持有跨步骤 locator，但**也没有**「重新定位」的显式约定 | △ **（初稿遗漏，本次补入）** |
| §13.5 | 每个关键步骤定义 timeout 与重试上限 | click 全部 `timeout=1500`，无重试 | ✗ 强约束 5 |
| `CANONICAL_COLLECTION_COMPONENTS.md` | 固定槽位 `login/navigation/date_picker/shop_switch/filters`，或 `*_export.py` | `warehouse_filters.py` 两者皆非 | ✗（但见 §2.7，设计上有意） |
| `ACTIVE_COLLECTION_COMPONENTS.md:75` | Archive 前置条件：不得有 stable `ComponentVersion.file_path` 指向被归档文件 | **DB 中 `miaoshou/inventory_snapshot_export` stable=True 仍指向已归档的缺失文件** | ✗ 治理违规 |
| `docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md:211,213` | 函数 ≤50 行、类 ≤500 行 | `_expect_download_with_pageerror_guard` **90 行**（`inventory_export.py:226-315`） | ✗ |

### 2.7 上游设计的正确决策（不应被改）

上游 spec §4「公共组件复用矩阵」明确写：

```
| `MiaoshouFilters` | ❌ 不复用（订单状态专用） | ❌ 不复用（12 字段筛选独立） |
| `MiaoshouDatePicker` | ❌ 不复用（snapshot 无日期） | ✅ 复用 |
```

**域隔离是被刻意决策的**，`warehouse_filters.py` 的存在是设计结果，不是随手乱建。因此本 spec **不**把三个平台的筛选逻辑合并，而是：
- 把**平台无关的算法**下沉到 `modules/components/`
- 把**域特定的业务选择**留在平台内
- 给「域内 filters」补一条 canonical 命名约定，消除当前的规范缺口（§5.7）

### 2.8 上游设计的落地偏差

上游 spec §7「测试策略」原文要求：

> **v2_flow 测试**：mock page 注入，验证步骤调用序列与 `ExportResult` 形状

实际交付（`backend/tests/test_miaoshou_inventory_export_v2_flow.py`）是**源码字符串断言**（共 11 处字符串断言：9 处 `assert "..." in source` + 2 处 `not in source`，行 13/14/58/59/60/65/66/71/72/77/78）。这直接解释了「组件一直绿灯却抓不到真实故障」。**设计是对的，落地退化了。**

---

## 3. 链路验证结论（本次改动不触碰的部分）

本节是对「勾选库存数据域执行配置能否满足需求」的完整回答，**结论：链路本身正确，卡点唯一**。

| # | 环节 | 验证方式 | 结果 |
|---|---|---|---|
| 1 | 前端可勾选「库存」 | `frontend/src/constants/collection.js:18` | ✅ `getAvailableDomainOptions()` 返回全部 7 域 |
| 2 | 店铺能力过滤 | `backend/services/collection_contracts.py:51` | ✅ `inventory: True` 默认开启 |
| 3 | 域 → 组件名解析 | `backend/services/component_runtime_resolver.py:18` | ✅ 显式别名 `("miaoshou","inventory",None) → ("miaoshou/inventory_export",)` |
| 4 | stable 组件记录 | 本地库实查 `core.component_versions` | ✅ `miaoshou/inventory_export v1.0.0 stable=True → modules/platforms/miaoshou/components/inventory_export.py` |
| 5 | 组件被文件系统推导为活跃 | `backend/services/active_collection_components.py:20-51` | ✅ `inventory_export.py` 匹配 `*_export.py` |
| 6 | 执行 | 2026-10-23 实测 | ❌ **卡点在此** |
| 7 | 粒度归一 | `modules/apps/collection_center/landing_semantics.py:12-13`；`modules/services/file_semantics.py:65` | ✅ inventory → `snapshot`，有回归测试 `test_collection_output_path_unification.py:596` |
| 8 | 落库 | `catalog_scanner → data_sync_service → raw_data_importer → b_class.fact_miaoshou_inventory_snapshot` | ✅ |

### 3.1 域之间互相隔离（重要）

配置 `id=27`（`monthly-inventory-orders-v1`，`granularity=monthly`，`date_range_type=custom`）在实测中产生的任务：

| 任务 id | `data_domains` | 状态 | 本地时间 |
|---|---|---|---|
| 636 | `['orders']` | ✅ completed | 2026-10-23 11:52 |
| 637 | `['inventory']` | ❌ failed | 2026-10-23 11:55 |

（11:55:46 配置被更新为只勾 `inventory`，故 11:55 的执行只生成任务 637。）

**一个域失败不影响另一个域，失败域不污染成功域的数据。** 这条链路是健康的。

### 3.2 新发现的两个缺口（与库存组件无关，但影响「配置正常使用」）

**缺口 1｜错误信息已在库中，前端未渲染**

任务 637 的库中记录：

```
failed_domains        [{'domain': 'inventory', 'error': 'StepExecutionError: Export failed: Locator.click:
                       Timeout 1500ms exceeded.\nCall log:\n  - waiting for get_by_label(...)...\n  - <div class=
                       "jx-select__selected-item jx-select__placeholder is-transparent"> intercepts pointer events'}]
error_message         None
error_screenshot_path None
```

**完整的 Playwright 诊断信息（含「哪个元素被什么挡住」）已在库中**，但前端 `frontend/src/domains/collection/views/collection/CollectionTasks.vue:402-407`：

- 「失败域」栏只渲染 `d.domain || d.name`，**不渲染 `d.error`**
- 「错误信息」栏只渲染顶层 `detailTask.error_message`，而域级失败时该字段为 `None`

**这是展示层缺口，不是数据缺失。** 修复成本极低，收益覆盖所有采集域。

**缺口 2｜平台可勾选但无组件的域会被静默剪掉**

前端 `getAvailableDomainOptions(platform)`（`collection.js:38`）**忽略 platform 参数**（调用点 `CollectionConfig.vue:1197` 传了 `account.platform` 但被忽略）。后端保存校验（`backend/domains/collection/routers/collection_config.py:188-200`）只校验「域名合法」与「店铺能力允许」，**不校验该平台是否真有对应组件**。

实测 miaoshou 的组件覆盖：

| 域 | miaoshou 组件文件 | 状态 |
|---|---|---|
| `inventory` | `inventory_export.py` | ✅ |
| `purchase` | `purchase_export.py` | ✅ |
| `orders` | `orders_shopee_export.py` / `orders_tiktok_export.py` | ✅（按子域拆分） |
| `products` | — | ❌ 无 |
| `analytics` | — | ❌ 无 |
| `finance` | — | ❌ 无 |
| `services` | — | ❌ 无 |

执行期 `backend/services/collection_config_execution.py:66-74` 对解析失败的域执行 `skipped_targets.append(...)` 后 `continue` —— **域被静默剪掉，只写一条 warning 日志，界面上没有任何提示**。

后果：在妙手配置里勾选「产品/流量分析/财务/服务」能保存成功，但执行时这些域不会出现任何任务，用户以为在采多个域、实际只跑了一部分。

---

## 4. 设计总览

### 4.1 分层原则

技术债的根因不是「库存域写得差」，而是**规范与实现之间没有强制连接**：规范写了 → 实现没照做 → 没人发现 → 测试绿灯 → 债务继续累积。

因此设计分四层：

| 层 | 目的 | 交付批次 |
|---|---|---|
| **L0** 立即做 | 让失败可见 + 清雷 + 补文档盲区 | 批次 1 |
| **L1** 止血 | 让库存域能跑且可诊断 | 批次 1 |
| **L2** 规范整改 | 按《规范》全面整改库存域 | 批次 2 |
| **L3** 机制层 | 把规范变成机器闸门，阻止复发 | 批次 1（lint 设计）+ 批次 3 |
| **L4** 结构性去重 | 平台无关算法下沉 + 同平台去重 | 批次 4（上线后 V2） |

### 4.2 交付批次

| 批次 | 内容 | 依赖 | 前置风险 |
|---|---|---|---|
| **批次 1** | L0 全部 + L1 全部 + L3 的 lint **设计** | 无 | 极低 |
| **批次 2** | L2 全部 | 需 pwcli 真实页面取证 | 中（取证受验证码环境限制） |
| **批次 3** | L3 的 lint **门禁 + 准入门槛 + 域可勾选校验** | 批次 1 | 中（历史违规一次性爆出） |
| **批次 4** | L4 全部 + L2-9 结构归位 | 上线后 | 低 |

**依赖方向**：批次 3 依赖批次 1；批次 4 依赖批次 2 的取证结论。**批次 2 的验收不依赖批次 3**（B1 改为独立可判定的自查，见 §7.2）。

**本 spec 的交付范围 = 批次 1**，批次 2/3/4 在本 spec 内给出设计与边界，实施时另开任务并引用本文条款编号。

---

## 5. 详细设计

### 5.1 L0：立刻做（批次 1）

#### L0-1 前端渲染域级错误（最高性价比）

**改动**：`frontend/src/domains/collection/views/collection/CollectionTasks.vue:402-407`

- 「失败域」栏：除域名外，渲染 `d.error`（折叠展示，保留完整 call log）
- 「错误信息」栏：当 `error_message` 为空但 `failed_domains` 非空时，从 `failed_domains[].error` 取首个作为兜底展示
- 不改后端、不改 API 契约

**验收**：A1

#### L0-2 清理孤儿 stable 记录

**改动**：`core.component_versions` 中 `miaoshou/inventory_snapshot_export`（stable=True，`file_path` = `modules/platforms/miaoshou/components/inventory_snapshot_export.py`，该文件已于 2026-09-13 提交 `ee8d7551` 移入 `archive/`）。

**动作**：将该记录置为非 stable。**不删除** `miaoshou/inventory_export` 的 stable 记录。

**依据**：`ACTIVE_COLLECTION_COMPONENTS.md:75` 的 Archive 前置条件。

**说明**：当前 resolver 别名只指向新的 `inventory_export`，该孤儿记录不参与运行；清理是消除隐患，不是修 bug。
**同类但不同的问题**：`miaoshou/orders_export` 也是 stable=False 且 `file_path` 指向不存在的 `components/orders_export.py`——这属于「无 stable 记录」类，与本条「指向已归档的缺失文件」是**两类不同问题**，L0-2 只处理后者，前者留给 L3-1 的守卫设计。

**验收**：A2

#### L0-3 补文档盲区

- `docs/guides/CANONICAL_RUNTIME_ISSUES.md`：新增 `miaoshou/inventory_export` 条目（含本次现象与根因）
- `docs/guides/CANONICAL_COMPONENT_STATUS.md`：更新 `miaoshou/inventory_export` 状态标记
- `docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md:1008`：补注「2026-10-23 再次失败（flaky）」

**理由**：`CANONICAL_RUNTIME_ISSUES.md` 至今未列 `miaoshou/inventory_export`（只列了旧的 `miaoshou/export`），这是本次问题未被提前发现的直接原因。

**验收**：A3

### 5.2 L1：止血 + 可诊断（批次 1）

#### L1-1 仓库筛选点击：四层防护

**改动文件**：`modules/platforms/miaoshou/components/warehouse_filters.py`、`modules/platforms/miaoshou/components/inventory_config.py`

| 层 | 手段 | 针对形态 | 说明 |
|---|---|---|---|
| **A** | 点击 **`.jx-select` 触发器容器**而非被覆盖的 `.jx-select__input` | 空态 placeholder | **需先按 label 关联定位到正确的那个 `.jx-select`**——页面可能存在多个 jx-select，不能用裸 `.jx-select`。做法：先 `get_by_label`/`get_by_text` 定位到「仓库」标签，再取其最近的 `.jx-select` 祖先容器。具体 CSS 需在批次 2 用 pwcli 取证后确定，**候选存放在 `inventory_config.py` 并注明改版风险**（§1） |
| **B** | `click(force=True)` + 最多 1 次重试 | tags 堆积 | **不复用订单域那段代码**（其 `except Exception: continue` 吞异常，且 fake locator 不兼容，见 §2.3）。此处应显式捕获并记录失败原因，重试次数有上限，失败要带阶段名 |
| **C** | 「已全选」前置检测：命中即跳过开下拉 | 两种形态都防 | **⚠️ 依赖 DOM 形态，未经验证**：订单域的判定基于「选中 ≥2 项才出现的 `+ N` 折叠标签」，而仓库筛选是**单个「全选」复选框**，已全选时 DOM 形态未知（可能只有 1 个 tag、无 `+ N`）⇒ 该判定**可能恒返回 False**。**批次 2 取证前，层 C 仅为尽力而为，不得作为唯一防线** |
| **D** | 键盘兜底：focus + `Enter`/`ArrowDown` | 最后一道 | **工程兜底，《规范》未覆盖此场景**（§4 讲的是「悬停→内容出现→点击」，不含键盘兜底）。实现时需在取证后确认 `jx-select` 是否响应键盘 |

**定位器**：`get_by_label(re.compile(r"仓库"))` → 语义锚定形式。**注意**：订单域的 `get_by_role("combobox", name=...).first` 本身违反《规范》§16 表第 1 行（page 根作用域 + `.first`），**不要照抄**。目标形态是「先收敛作用域（label → 关联容器），再在容器内定位」。

**超时**：`timeout=1500` → `3000`（《规范》§13.5；TikTok 组件用 3000）。

**重试**：优先使用既有 `modules/apps/collection_center/retry_strategy.py:20` 的 `RetryStrategy`，**不自造内联重试循环**（《规范》§6 点名了 `RetryStrategy`）。

**验收**：A4、A5、A6

#### L1-2 组件可观测性

**改动文件（4 个，比初稿多 2 个）**：
1. `modules/platforms/miaoshou/components/inventory_export.py`
2. `modules/platforms/miaoshou/components/warehouse_filters.py`
3. **`modules/apps/collection_center/executor_v2.py`（新增）**
4. **`backend/domains/collection/routers/collection_tasks.py`（新增，可能）**

**为什么必须改执行器（关键）**：

当前执行器构造 `ExecutionContext` 时（`executor_v2.py:2284-2288`）**既未传 `logger=` 也未传 `step_callback=`**：

```python
ctx = ExecutionContext(
    platform=(component or {}).get("platform", ""),
    account=account,
    config=config,
)
```

后果：
- `ctx.logger` 为 `None` → `self.ctx.logger.info()` 抛 `AttributeError`（且会被组件内 `except Exception` 吞掉，**反而制造我们正要消灭的吞异常违规**）
- `ctx.step_callback` 为 `None` → `ComponentBase.report_step` 在 `base.py:83-84` 直接 `return`，**一条事件都不会上报**

且 `core.collection_task_logs` **仅由 `backend/domains/collection/routers/collection_tasks.py` 写入**（任务创建/取消/重试等生命周期事件），**执行器不写**。前端时间线读的就是这张表（`collection_tasks.py:547-549`）。

**因此 L1-2 必须包含：**

| 子项 | 改动 | 说明 |
|---|---|---|
| L1-2a | 执行器构造 `ExecutionContext` 时注入 `logger=`（任务级 logger，输出需能落到任务日志）与 `step_callback=` | `logger` 需适配 `SupportsLogger` 协议（`base.py:32-35`：`info/warning/error`） |
| L1-2b | `step_callback` 的落地通道需把 `step_start`/`step_success`/`step_failed` 事件写入 `core.collection_task_logs` | 复用执行器既有的 `status_callback`（`executor_v2.py:695,712`，签名 `(task_id, progress, message, current_domain=None)`）或新增专用回调 |
| L1-2c | 组件每阶段 `await self.report_step("step_start"\|"step_success"\|"step_failed", step_id=..., action=...)` | 《规范》§5.3 |
| L1-2d | 失败时截图落盘到 `ctx.config["task"]["screenshot_dir"]` | 该路径在执行期可得（`executor_v2.py:333-336`）；对齐 TikTok `products_export.py:202-212` |
| L1-2e | 失败消息带**阶段名**，如 `warehouse_scope_open_failed: <原始错误>` | 《规范》§13.4 |

**阶段划分（6 段）**：

| step_id | 动作 | 失败消息前缀 |
|---|---|---|
| `navigation_ready` | 导航到仓库清单并双信号确认就绪 | `navigation_failed` |
| `popup_cleared` | 弹窗清理（见 L1-2f） | `popup_cleanup_failed` |
| `warehouse_scope_ready` | 仓库范围筛选（pre/action/post 三段） | `warehouse_scope_*_failed` |
| `search_results_ready` | 搜索并确认结果 | `search_*_failed` |
| `export_dialog_ready` | 打开导出弹窗 + 字段全选 | `export_dialog_*_failed` |
| `download_saved` | 下载并落盘校验 | `download_*_failed` |

**L1-2f 弹窗清理**：应使用既有机制 `ComponentBase.guard_overlays`（`base.py:116-140`，仅 `is_test_mode=True` 生效）→ `modules/platforms/miaoshou/components/overlay_guard.py` → `UniversalPopupHandler().close_safe_notices(platform="miaoshou")`。**不新增第 5 份 `_ensure_popup_closed`**（见 §5.6）。

**验收**：A7、A8

#### L1-3 测试升级

**改动文件（3 个，比初稿多 1 个）**：
1. `backend/tests/test_miaoshou_inventory_export_v2_flow.py`
2. `backend/tests/test_miaoshou_warehouse_filters_contract.py`
3. **`backend/tests/test_miaoshou_inventory_export_contract.py`（新增，因 L2-7 依赖它）**

- 把源码字符串断言改为 **mock page 行为测试**（对齐上游 spec §7 的原始要求，以及 `tests/unit/test_shopee_products_export.py` 的 1583 行范式）
- **新增用例必须覆盖**：
  1. 空态 placeholder 遮挡 → 组件能穿透或前置检测能识别（**本次失败的复现用例**）
  2. tags 堆积态（已全选）→ 不开下拉直接跳过
  3. 空态无遮挡 → 正常路径
  4. 各阶段失败 → 错误消息含对应阶段名
  5. **fake locator 的 `click()` 必须支持 `force=` 关键字**（避免重演 §2.3 的 TypeError 陷阱）
- `test_miaoshou_warehouse_filters_contract.py` 从 22 行扩为真正的行为测试

**约束**：新测试**不得**使用源码字符串断言。

**验收**：A9

### 5.3 L2：按规范全面整改（批次 2）

| # | 整改项 | 《规范》条款 |
|---|---|---|
| L2-1 | 定位器唯一性 + 作用域收敛（先定位稳定容器，再 `get_by_*`） | §1 / §13.1 / §16 |
| L2-2 | `.first`/`.nth` 收敛到具体容器 + 补业务语义注释（§16 要求「有注释才放行」） | §16 |
| L2-3 | 检测层三分：pre-check / action / **post-check**（筛选后回读勾选状态） | §3.5 |
| L2-4 | 结构化错误：`stage/status/reason/current_url/matched_signal/screenshot_path` | §3.5.1 / §13.4 |
| L2-5 | 导出阶段验证码：按登录阶段同一套（检测 → `VerificationRequiredError` → 暂停 → 回填 → 同 page 继续） | §5.5 / §8.1 |
| L2-6 | 导航双信号：URL/路由特征 + 关键元素可见 | §13.2 |
| L2-7 | 假配置接上：`inventory_config.py` 的 `group_titles` / `group_check_all_text` / `data_type_dir`（**定义 6 处、被读取 0 处**；`group_titles`/`data_type_dir` 正被 `test_miaoshou_inventory_export_contract.py:23,25,26` 断言）→ **接上使用，不删除** | §1 |
| L2-8 | 拆分 `_expect_download_with_pageerror_guard`（90 行 → ≤50 行） | `TESTING_AND_QUALITY.md:211` |
| L2-9 | 动态 DOM：关键交互前重新定位元素，不跨步骤长期持有 locator | §13.3 |

> **L2-10（原 L2-9「`warehouse_filters.py` 结构归位」）已移出批次 2**，改挂批次 4，与 §5.7 的「不在批次 1/2 执行此重命名」保持一致。

**执行前提**：L2-1/L2-2 需要 pwcli 重新抓取真实页面 DOM 取证（《规范》Authoring Sequence 第 2 步）。**取证必须在有头模式、能人工处理验证码的环境下进行。**

### 5.4 L3：机制层（批次 1 出设计，批次 3 落地）

#### L3-1 把《规范》§13 强约束做成机器 lint

**现状（2026-10-23 实测）**：lint 真实实现在 **`backend/domains/collection/routers/component_recorder.py`**（`:458` 起），**不是** `backend/services/component_recorder_lint.py`（该文件不存在）。已有 5 条规则：

| 规则 type | 位置 | 对应《规范》条款 |
|---|---|---|
| `wait_for_timeout_usage` | `component_recorder.py:507` | §3（无理由固定等待） |
| `fixed_sleep_usage` | `component_recorder.py:533` | §3 |
| `count_is_visible_pattern` | `component_recorder.py:547` | §2 |
| `swallow_exception_pattern` | `component_recorder.py:554` | §2 / §13 |
| `first_nth_usage` | `component_recorder.py:569` | §13.1 / §16 |

**已覆盖 vs 需新增**：

| 检查项 | 状态 | 对应条款 |
|---|---|---|
| `.first`/`.nth` 无邻近业务语义注释 | ✅ 已有（`first_nth_usage`） | §13.1 / §16 |
| `except Exception: pass` 吞异常 | ✅ 已有（`swallow_exception_pattern`） | §2 / §13 |
| 单次 `count()` + `is_visible()` 后即操作 | ✅ 已有（`count_is_visible_pattern`） | §2 |
| 无理由固定等待 | ✅ 已有（`wait_for_timeout_usage` / `fixed_sleep_usage`） | §3 |
| 关键步骤缺 `report_step` | 🆕 需新增 | §5.3 / §13.4 |
| 未接 `ctx.logger` | 🆕 需新增 | §13.4 |
| 函数 > 50 行 / 类 > 500 行 | 🆕 需新增 | `TESTING_AND_QUALITY.md:211,213` |
| 组件无 stable 记录 | 🆕 需新增（区别于「指向缺失文件」，后者已有 `MissingStableComponentFileError` 覆盖，见 `component_runtime_resolver.py:43-51`） | `ACTIVE_COLLECTION_COMPONENTS.md:75` |
| stable 记录指向 `archive/` 或缺失文件 | 🆕 需新增（运行时已有守卫，CI 侧需前置） | 同上 |
| 导航单信号（未做 URL + 元素双信号） | 🆕 需新增 | §13.2 |
| 缺重试预算声明 | 🆕 需新增 | §13.5 |

**关键约束（已查证）**：现有 lint 挂在**录制器保存路径**上，**手写组件不经过那条路径**。要让 lint 覆盖手写组件，必须**单独接入 CI / pre-commit**，不能依赖录制器。

**上线策略**：仓库现有 **24 条** stable 组件记录（`SELECT count(*) FROM core.component_versions WHERE is_stable IS TRUE`），lint 一次性强制阻断会爆出大量历史违规并可能打挂流水线。

→ **第一阶段：告警模式跑一轮**，先清 miaoshou 与新增/修改组件；
→ **第二阶段：只对新增/修改的组件强制阻断**。

#### L3-2 规范补三处空白

| 缺口 | 现状 | 补充内容 |
|---|---|---|
| 重试口径冲突 | 《规范》§6:171 明确「关键步骤配合 `RetryStrategy` **或组件内重试**」——**允许**组件内重试；而**上游 2026-09-13 spec §6** 写「重试由执行器层 `retry_strategy.py` 控制，组件内部不自动重试」。**两者口径相反** | 统一口径：明确区分**交互级重试**（组件内，针对遮挡/时序，允许）与**域级重试**（执行器层，针对网络/5xx）。以《规范》§6 为准，修订上游 spec 的表述 |
| 同平台多域共用 filters 的结构约定 | 固定槽位 `filters.py` 已被订单域占用，库存域的 `warehouse_filters.py` 无合法位置 | 增加「域内 filters」约定：`filters.py`（平台级入口）+ `filters_<domain>.py`（域特定实现），写明何时允许域隔离 |
| archive 前置条件的机器校验 | 纯靠人记得，导致孤儿 stable 记录 | 增加 guard：文件移入 `archive/` 前检查无 stable 记录指向 |

#### L3-3 收紧「进入 active 清单」的准入门槛

**现状**：`is_active_component_name()` **从文件系统推导**（`active_collection_components.py:20-51` glob `components/*.py`）—— 文件名符合 `*_export.py` 即算活跃组件。结果是半成品也能进主链路（库存域即如此）。

**建议准入三门**（新增组件必须满足）：
1. 有对应的 `CANONICAL_RUNTIME_ISSUES.md` 条目（含真实页面验证状态）
2. 有**行为测试**（不接受源码字符串断言）
3. 有 stable 版本记录且指向非 archive 文件

#### L3-4 修「域可勾选但无组件」的静默剪枝

**改动面**：
- 前端 `getAvailableDomainOptions(platform)` 按平台过滤（当前忽略 platform）
- 后端保存校验增加「该平台该域是否有可用组件」，不可用时明确报错
- 执行期 `skipped_targets` 回写到任务详情，让用户看得见「你勾的某个域没跑」

**注意**：miaoshou 的 `orders` 是子域拆分（`orders_shopee_export` / `orders_tiktok_export`），校验逻辑需按 `build_component_name` 的真实语义实现，**不能简单按 `<domain>_export.py` 判存在**。

**⚠️ 口径待确认**：C6 的判定是「保存时报错**或**界面明确提示」二选一，不唯一可判定。**需人工裁定取哪一种**（建议：保存时报错 + 界面灰显并注明「该平台暂不支持」，两者都做）。

#### L3-5 执行器失败语义分级（可选，低优先）

区分「可重试」（网络抖动、遮挡、时序）与「不可重试」（页面改版、控件消失），让 flaky 与真故障在任务详情里可区分。

### 5.5 L4：结构性去重（批次 4，上线后 V2）

| # | 项 | 说明 |
|---|---|---|
| L4-1 | 同平台内去重 + 平台无关算法下沉 | `_is_checkbox_selected`（判定算法，平台无关）、下载捕获、遮挡穿透、结构化错误 → `modules/components/` |
| L4-2 | `popup_config` 填真实选择器 | 三个平台的 `get_close_selectors()` **当前全返回 `[]`**，机制存在但配置为空，导致组件各自造 `_ensure_popup_closed` 轮子。先用 pwcli 取证填充，再把组件内重复轮询收回统一机制 |
| L4-3 | 三平台各自的 `_download_helpers.py` 合并 | tiktok(2.1KB) / shopee(7.3KB) 内容不同但功能重叠 |
| L4-4 | `warehouse` vs `inventory` 域映射统一 | `python_component_adapter.py:54-55`：`warehouse` 指向**全仓不存在**的 `MiaoshouExport` 类，`inventory` 指向 `MiaoshouInventoryExport` —— 两个域打同一个页面 |
| L4-5 | 订单域组件文件结构统一 | 当前为 `orders_export_base.py`（非 canonical 命名）+ `orders_shopee_export.py` + `orders_tiktok_export.py` |
| L4-6 | `warehouse_filters.py` → `filters_inventory.py` 结构归位（原 L2-9，与 §5.7 约定同步） | 见 §5.7 |

### 5.6 关键边界：什么**不**下沉

这是本 spec 最容易被误读的地方，明确写死：

| 下沉到 `modules/components/` | **不下沉**，留在各平台 |
|---|---|
| 复选框勾选**判定算法**（`aria-checked` / class 含 `checked` / `input:checked`）—— DOM 语义，三平台通用 | 复选框/下拉框的**选择器与文案** → 各平台 `*_config.py`（《规范》§1 要求注明改版风险） |
| 下载捕获与落盘 | 弹窗容器结构、关闭按钮选择器 → 各平台 `popup_config.py` |
| 遮挡穿透点击（force + 重试） | 平台特有的业务筛选逻辑（订单状态 vs 仓库范围）→ 域内 filters |
| 结构化错误格式与阶段命名约定 | 域特定的数据流（inventory 同步下载 vs purchase 异步导出轮询） |

**理由**：合并平台特有选择器会制造改版风险（一个平台改版就炸全部），且违反《规范》§1。合并**同平台内**的重复副本则是零风险的纯去重。

### 5.7 域内 filters 的命名约定（规范补白的一部分）

`warehouse_filters.py` 的存在是上游设计的刻意决策（§2.7），但当前不在 canonical 槽位内。

**约定**：`filters.py`（平台级筛选入口，按 `data_domain` 分派）+ `filters_<domain>.py`（域特定实现）。

- 订单域：`filters.py` → `filters_orders.py`
- 库存域：`filters.py` → `filters_inventory.py`
- 采购域：`filters.py` → `filters_purchase.py`（若需要）

**收益**：共享分派入口 + 域隔离实现 + 消除 `warehouse_filters.py` 的规范缺口。

**成本**：改动面比「保留 `warehouse_filters.py`」大。**本 spec 不在批次 1/2 执行此重命名**（L4-6 挂批次 4），仅在 §5.4 L3-2 中把约定写进规范。

---

## 6. 数据与契约影响

| 契约 | 是否变更 |
|---|---|
| `ComponentVersion` 表结构 | 否（仅改数据行：孤儿记录置非 stable） |
| 组件基类签名 `run(self, page, mode=...) -> ExportResult` | 否 |
| `ExecutionContext` 字段定义 | 否（**注入点变化**：执行器需传 `logger=` / `step_callback=`） |
| `core.collection_task_logs` 表结构 | 否（写入方增加执行器侧一条路径） |
| 采集配置 API / 前端数据结构 | 否（L0-1 只改展示） |
| 落库表 `b_class.fact_miaoshou_inventory_snapshot` | 否 |
| 粒度口径（inventory → snapshot） | 否 |
| `data_domain` / `component_type` 元数据 | 否 |

---

## 7. 验收标准

### 7.1 批次 1（L0 + L1）

| # | 验收项 | 判定方式 |
|---|---|---|
| A1 | 任务详情页能看到域级完整错误（含 Playwright call log） | 打开 task 637 的详情页，「失败域 inventory」下方可见错误详情折叠区 |
| A2 | 孤儿 stable 记录已清理 | `SELECT is_stable FROM core.component_versions WHERE component_name='miaoshou/inventory_snapshot_export'` 为 false |
| A3 | 三份文档已更新 | `CANONICAL_RUNTIME_ISSUES.md` 含 `miaoshou/inventory_export` 条目 |
| A4 | 库存域能跑通 | 勾选库存域执行配置 → 任务 `status=completed`，`files_collected ≥ 1` |
| A5 | 遮挡场景可恢复 | 行为测试覆盖形态 A（placeholder 遮挡）并通过 |
| A6 | 已全选态跳过下拉 | 行为测试覆盖形态 B 并通过 |
| A7 | 失败可诊断 | 故意让某阶段失败 → 错误消息含阶段名；`report_step` 有记录；截图文件存在于 `ctx.config["task"]["screenshot_dir"]` |
| A8 | 时间线可见步骤 | 任务详情「步骤时间线」出现组件写入的阶段条目（**前提：L1-2a/2b 已落地**） |
| A9 | 测试形态升级 | 三个 `test_miaoshou_inventory_*` 文件**不再包含源码字符串断言**；fake locator 支持 `force=` |
| A10 | 不破坏其他域 | `python -m pytest backend/tests/test_miaoshou_filters_component.py backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_inventory_pageerror_recovery.py backend/tests/test_miaoshou_purchase_export_contract.py backend/tests/test_miaoshou_purchase_export_v2_flow.py backend/tests/test_miaoshou_supporting_components_contract.py backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider` 全绿（**当前基线：`test_miaoshou_filters_component.py` 因 §2.3 的未提交改动 4 failed，批次 1 必须先修好或一并修掉**） |
| A11 | 落库目标达成 | 产出文件被 `catalog_scanner` 扫描并入库 `b_class.fact_miaoshou_inventory_snapshot`（对应 §1.2 目标 4） |

> **A10 的命令形式**：仓库默认 shell 为 PowerShell 5.1，**不展开 `*` 通配符**（`pytest backend/tests/test_miaoshou_*` 会报 `file or directory not found`）。实施时必须显式列出文件，或用 `Get-ChildItem` 展开。

### 7.2 批次 2（L2）

| # | 验收项 |
|---|---|
| B1 | 库存域两文件对《规范》§13 五条强约束**零违反**（**自查**：按 §5.4 L3-1 的检查项逐条人工核对；**复核**：批次 3 lint 上线后再跑一次自动化判定） |
| B2 | 定位器唯一性：交互目标的 `.first` 均有邻近业务语义注释或已消除 |
| B3 | 检测层：每个关键动作有 post-check |
| B4 | 导出阶段弹验证码能触发 `VerificationRequiredError` 并进入暂停→回填→继续 |
| B5 | 导航为双信号判定 |
| B6 | `inventory_config.py` 的三项假配置**被实际读取**（不再是定义即死） |
| B7 | 所有函数 ≤50 行、类 ≤500 行 |
| B8 | 动态 DOM：关键交互前重新定位元素 |

### 7.3 批次 3（L3）

| # | 验收项 |
|---|---|
| C1 | lint 可对手写组件运行（不依赖录制器路径），且**复用** `component_recorder.py` 的既有 5 条规则，不重复实现 |
| C2 | lint 覆盖 §5.4 L3-1 表中**全部** 🆕 需新增项（`report_step` 缺失 / 未接 logger / 函数与类超长 / 无 stable 记录 / stable 指向 archive 或缺失 / 导航单信号 / 缺重试预算），**逐项可验** |
| C3 | 告警模式运行一轮后，转为对新增/修改组件强制阻断 |
| C4 | 《规范》补入三处空白（重试口径冲突以《规范》§6 为准修订上游 spec） |
| C5 | 新增组件需过三门准入才进 active 清单 |
| C6 | 勾选无组件的域时，**保存时报错**（口径已裁定，见 L3-4 ⚠️），或界面明确提示不再静默剪掉 |

### 7.4 批次 4（L4）

| # | 验收项 |
|---|---|
| D1 | `modules/components/` 下无平台特有选择器 |
| D2 | `_is_checkbox_selected` / `_ensure_popup_closed` 在 miaoshou 内各只剩一份 |
| D3 | 三平台共用一份 `_download_helpers` |
| D4 | `popup_config` 三平台的 `get_close_selectors()` 非空且有真实页面证据 |
| D5 | `warehouse` vs `inventory` 域映射统一，`MiaoshouExport` 不存在的引用被清理 |
| D6 | 订单域组件文件结构统一（`orders_export_base.py` 归位） |
| D7 | `warehouse_filters.py` → `filters_inventory.py` 完成，canonical 命名无缺口 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| **订单域工作区改动当前打挂 4 个既有测试**（§2.3），且是本可参照的实现 | 若照抄，库存域会引入同样的 fake-locator 不兼容与吞异常问题；A10 基线不成立 | **不复用该段代码**，只复用其要解决的问题；批次 1 需先修好或一并修掉这 4 个测试；§2.3 的结论同步写入 `CANONICAL_RUNTIME_ISSUES.md` |
| **L1-2 缺执行器改动则完全不生效**（§5.2） | `ctx.logger`/`ctx.step_callback` 为 None，A8 不可达成，且组件写日志会引入新的吞异常违规 | L1-2 明确拆为 a–f 六个子项，执行器改动与组件改动同批交付；A7/A8 依赖此前提 |
| 形态 A（点容器外壳）在真实页面上未必能打开下拉 | L1-1 的 A 层失效 | 四层防护逐级降级，A 失败自动落到 B；批次 2 用 pwcli 取证校正；A 层不可作为唯一防线 |
| **层 C 的 DOM 形态未经验证**（§5.2 L1-1 层 C 注） | 「已全选」判定可能恒为 False，形同虚设 | 明确标注为「尽力而为，不得作为唯一防线」；批次 2 取证确认后再定是否保留 |
| 改前端渲染 `d.error` 可能暴露内部路径/选择器 | 信息暴露 | 只在管理员可见的任务详情页展示（该页面本身是管理端） |
| 清理孤儿 stable 记录时误删有效记录 | 运行时解析失败 | 只处理 `component_name='miaoshou/inventory_snapshot_export'` 且 `file_path` 已不存在的记录；执行前后各查一次并记录 |
| **L2-5 导出阶段误抛 `VerificationRequiredError`** | 任务会长期挂在「等待验证码」，且没有验证码实际出现 | 抛点必须先有正向检测信号（不能「宁滥勿缺」）；设等待超时；批次 2 真实页面验证 |
| **L3-4 跨前后端改动** | 前端过滤会改变妙手可勾选域集合（现 7 域全可选），可能与用户既有习惯冲突；且与 §1.3「域拆分规则一律不动」有解释空间 | 口径先由人工裁定（保存报错 + 界面灰显并注明）；实施前确认 §1.3 的边界表述 |
| lint 一次性阻断打挂流水线 | CI 红灯 | 批次 3 第一阶段告警模式 |
| 批次 2 取证受验证码环境限制 | 延期 | 批次 1 的四层防护已覆盖 A/B 两形态，不阻塞业务恢复 |

---

## 9. 前置依赖

| # | 依赖 | 状态 |
|---|---|---|
| DEP-1 | 订单域 `filters.py` 的 `force=True` 修复需先**修好其 4 个失败测试**并提交入库 | ⚠️ **当前为未提交工作区改动且测试 4 failed**。本 spec 不代替该修复，但批次 1 的 A10 以它为基线 |
| DEP-2 | 本地库 `xihong_erp` 可访问（用于 stable 记录清理与验收查询） | ✅ 已验证 |
| DEP-3 | pwcli + 有头浏览器环境（批次 2 取证用） | ⏳ 批次 2 前置 |
| DEP-4 | `frontend` 与 `backend` 本地可运行（验收 A1/A4/A11 用） | ✅ 已在运行 |

> 编号前缀 `DEP-` 与 §7.4 的验收编号 `D1–D7` 刻意区分，避免交叉阅读时串号。

---

## 10. 遗留与后续

- 批次 2/3/4 各自另开执行任务时，引用本 spec 的条款编号，不重复推导
- 库存域从「历史成功过」到「本次失败」的 flaky 记录，已在 `CANONICAL_RUNTIME_ISSUES.md` 登记，作为后续回归基线
- 上游 spec §7 的测试策略（mock page 行为验证）在本 spec §5.2 L1-3 得到落实，**该上游 spec 的落地偏差至此关闭**
- 《规范》§6 与上游 2026-09-13 spec §6 的重试口径冲突，在 L3-2 中以《规范》为准统一
