# 妙手 Miaoshou 库存数据域采集整改设计（Miaoshou Inventory Domain Remediation）

**日期:** 2026-10-23
**状态:** 待实施
**定位:** 本 spec 解决「妙手库存数据域采集组件不可靠 / 不可诊断 / 不符合既有规范」，以及「规范与实现之间缺少强制连接导致债务复发」两个问题。**不改**采集配置链路的业务语义、粒度口径、入库链路与 Dashboard。
**关联文档（规则来源，本 spec 不重复其内容，只引用条款）:**
- `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` — 《采集脚本编写规范》（唯一成文编写依据，下文简称《规范》）
- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md` — canonical 组件规则
- `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` — 活跃清单与 Archive 前置条件
- `docs/guides/CANONICAL_COMPONENT_STATUS.md` — 组件阶段性状态
- `docs/guides/CANONICAL_RUNTIME_ISSUES.md` — 真实链路问题清单
- `docs/guides/COMPONENT_COLLABORATION.md` — 组件协作规则
- `docs/superpowers/specs/2026-09-13-miaoshou-finance-inventory-data-domain-recording-design.md` — 库存域上次重做的设计（本 spec 的直接上游）

---

## 0. 修订记录

| 日期 | 内容 |
|---|---|
| 2026-10-23 | 初稿。基于 2026-10-23 采集失败事件（task `7bb2a92e-a0eb-4129-ba5c-6237b852c909`）与本地库 `xihong_erp` 实测形成 |

---

## 1. 背景与目标

### 1.1 事件

2026-10-23 11:55:51，用户在采集配置中执行了包含 `inventory` 数据域的妙手采集任务，任务失败：

| 时刻 | 事件 |
|---|---|
| 11:55:46 | 配置 `miaoshou-miaoshou_real_001-monthly-inventory-orders-v1` 被更新（scope 数据域改为 `['inventory']`） |
| 11:55:51 | 任务启动 |
| 11:56:09 | 等待验证码回填 |
| 11:56:14 | 用户提交验证码，任务恢复 |
| 11:56:27 | 登录态复用成功（`[LOGGED_IN] confidence=0.80`） |
| 11:56:33 | 导航至 `/warehouse/checklist` |
| **11:56:35** | **失败**：`Export failed: Locator.click: Timeout 1500ms exceeded` |
| 11:56:38 | 任务结束，`status=failed`，`duration=44s` |

失败发生在库存域的**第一个交互动作**（选择仓库范围），后续的搜索 / 导出弹窗 / 字段全选 / 下载落盘全部未执行。

### 1.2 目标

1. 让 `miaoshou/inventory_export` 在真实页面上**稳定**完成采集，消除随机失败
2. 让任一步失败都能**一眼定位**（阶段 + 选择器 + 截图），不再需要翻后端原始日志
3. 把《规范》的工程强约束从**文档文字**变成**机器可执行的闸门**，阻止同类债务复发
4. 保证「采集配置勾选库存数据域 → 执行配置 → 产出文件入库」这条业务链路**稳定可用**

### 1.3 非目标（明确不做）

- 不改采集配置的**业务语义**：粒度口径、日期窗口、域拆分规则一律不动
- 不改入库链路：`catalog_scanner → data_sync_service → raw_data_importer → b_class.fact_miaoshou_inventory_snapshot` 不动
- 不改 Dashboard / semantic / mart / api 任何 SQL 资产
- 不做跨平台弹窗 / 选择器的硬合并（见 §5.3 边界）
- 不在本 spec 内重写订单域、采购域（仅引用其已验证模式）

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

《规范》§1 与同平台订单域的实现表明 `jx-select` 存在两类覆盖层，**不是同一个 bug**：

| 形态 | 覆盖层 | 出现条件 | 订单域现状 |
|---|---|---|---|
| **A. 空态 placeholder** | `.jx-select__selected-item.is-transparent`（无选中项时的占位文案层） | 选框为空 | 订单域无此形态（订单状态总被选中） |
| **B. tags 堆积** | `.jx-select__selected-item` 内堆叠多个 `.jx-tag`，含 `+ N` 折叠标签 | 已全选时 | **订单域已修**（`filters.py:111-122` 注释明确记录） |

**本次失败是形态 A。** 任何只修 B 的补丁都无法覆盖本次失败。

### 2.3 为什么订单域修好了库存域没修好

订单域 `modules/platforms/miaoshou/components/filters.py` 已经踩过同类坑并给出解法（当前为**工作区未提交改动**）：

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

而库存域的 `warehouse_filters.py` 是从更早的归档实现 `modules/platforms/miaoshou/archive/inventory_snapshot_export.py` 逐字复制演化而来，两处的 `_warehouse_scope_trigger` 与 `trigger.click(timeout=1500)` 逻辑一致，**同一个缺陷被原样继承**。

根因是**结构性**的，不是笔误：

- 《规范》§1 要求共享原语放在 `modules/components/`，但 `_is_checkbox_selected` 在 miaoshou 的 `components/` 目录内存在 **3 份逐字相同**的副本（`filters.py:46` / `inventory_export.py:45` / `warehouse_filters.py:52`），`_ensure_popup_closed` 存在 **4 份**（`inventory_export.py:67` / `orders_export_base.py:98` / `purchase_export.py:46` / `warehouse_filters.py:74`）
- 没有共享层 ⇒ 修复只能靠人工复制 ⇒ 复制是可选的 ⇒ 订单域修好了库存域拿不到

### 2.4 这是 flaky，不是必现

`docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md:1008` 记录：**「`inventory` 域历史上成功过（2026-09-14）」**。

触发条件是「刚过完验证码 / 刚导航 / 选框尚未就绪」的时序窗口。本次时间线正好落在窗口内：登录完成 11:56:27 → 导航完成 11:56:33 → 失败 11:56:35。

**flaky 比必现失败更危险**：它会以「随机失败」形式反复出现，且每次伴随一次验证码等待（本次 44 秒总耗时中 23 秒在等验证码）。执行器对 export 域失败**不做自动重试**（`modules/apps/collection_center/executor_v2.py:2813` 直接 `raise StepExecutionError` → 追加 `failed_domains` → `continue`），因此每次 flaky 都等于整域失败。

### 2.5 规范符合性逐条对照

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
| §5.5 / §8.1 | 导出阶段验证码与登录阶段同一套（检测→暂停→回传→同 page 继续） | 全仓仅 `miaoshou/components/login.py:91` 抛 `VerificationRequiredError`；导出流程无抛点 | ✗ |
| §6 | 明确错误类型，区分可重试/不可重试 | `message=str(e)` 裸字符串 | ✗ |
| §7 | 执行器在每域导出前调 `close_popups`；组件内已知弹窗应显式 wait | 自造 `_ensure_popup_closed`，miaoshou 内 4 份重复 | △ |
| §13.2 | 导航完成契约：URL/路由特征 **+** 关键元素可见（双信号） | `navigation.py:82` 只等 `get_by_text("仓库清单")` 文字可见 | ✗ 强约束 2 |
| §13.5 | 每个关键步骤定义 timeout 与重试上限 | click 全部 `timeout=1500`，无重试 | ✗ 强约束 5 |
| `CANONICAL_COLLECTION_COMPONENTS.md` | 固定槽位 `login/navigation/date_picker/shop_switch/filters`，或 `*_export.py` | `warehouse_filters.py` 两者皆非 | ✗（但见 §2.6，设计上有意） |
| `ACTIVE_COLLECTION_COMPONENTS.md:76` | Archive 前置条件：不得有 stable `ComponentVersion.file_path` 指向被归档文件 | **DB 中 `miaoshou/inventory_snapshot_export` stable=True 仍指向已归档的缺失文件** | ✗ 治理违规 |
| `TESTING_AND_QUALITY.md:209-213` | 函数 ≤50 行、类 ≤500 行 | `_expect_download_with_pageerror_guard` **91 行** | ✗ |

### 2.6 上游设计的正确决策（不应被改）

`2026-09-13-miaoshou-finance-inventory-data-domain-recording-design.md` §4「公共组件复用矩阵」明确写：

```
| `MiaoshouFilters` | ❌ 不复用（订单状态专用） | ❌ 不复用（12 字段筛选独立） |
| `MiaoshouDatePicker` | ❌ 不复用（snapshot 无日期） | ✅ 复用 |
```

**域隔离是被刻意决策的**，`warehouse_filters.py` 的存在是设计结果，不是随手乱建。因此本 spec **不**把三个平台的筛选逻辑合并，而是：
- 把**平台无关的算法**下沉到 `modules/components/`
- 把**域特定的业务选择**留在平台内
- 给「域内 filters」补一条 canonical 命名约定，消除当前的规范缺口

### 2.7 上游设计的落地偏差

上游 spec §7「测试策略」原文要求：

> **v2_flow 测试**：mock page 注入，验证步骤调用序列与 `ExportResult` 形状

实际交付（`backend/tests/test_miaoshou_inventory_export_v2_flow.py`）是**源码字符串断言**（10 处 `assert "..." in source`）。这直接解释了「组件一直绿灯却抓不到真实故障」。**设计是对的，落地退化了。**

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

| 任务 id | `data_domains` | 状态 | 创建时间 |
|---|---|---|---|
| 636 | `['orders']` | ✅ completed | 2026-10-23 03:52 |
| 637 | `['inventory']` | ❌ failed | 2026-10-23 03:55 |

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

前端 `getAvailableDomainOptions(platform)` **忽略 platform 参数**。后端保存校验（`backend/domains/collection/routers/collection_config.py:188-200`）只校验「域名合法」与「店铺能力允许」，**不校验该平台是否真有对应组件**。

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
| **批次 4** | L4 全部 | 上线后 | 低 |

**本 spec 的交付范围 = 批次 1**，批次 2/3/4 在本 spec 内给出设计与边界，实施时另开 spec 或按 §7 的批次划分执行。

---

## 5. 详细设计

### 5.1 L0：立刻做（批次 1）

#### L0-1 前端渲染域级错误（最高性价比）

**改动**：`frontend/src/domains/collection/views/collection/CollectionTasks.vue:402-407`

- 「失败域」栏：除域名外，渲染 `d.error`（折叠展示，保留完整 call log）
- 「错误信息」栏：当 `error_message` 为空但 `failed_domains` 非空时，从 `failed_domains[].error` 取首个作为兜底展示
- 不改后端、不改 API 契约

**验收**：任务 637 的失败详情页能看到「哪个元素被什么挡住」的完整原因。

#### L0-2 清理孤儿 stable 记录

**改动**：`core.component_versions` 中 `miaoshou/inventory_snapshot_export`（stable=True，`file_path` 指向 `modules/platforms/miaoshou/components/inventory_snapshot_export.py`，该文件已于 2026-09-13 提交 `ee8d7551` 移入 `archive/`）。

**动作**：将该记录置为非 stable（或按 `component_version_service` 的既有删除规则处理）。**不删除** `miaoshou/inventory_export` 的 stable 记录。

**依据**：`ACTIVE_COLLECTION_COMPONENTS.md:76` 的 Archive 前置条件。

**风险**：当前 resolver 别名只指向新的 `inventory_export`，因此该孤儿记录不参与运行；清理是消除隐患，不是修 bug。

#### L0-3 补文档盲区

- `docs/guides/CANONICAL_RUNTIME_ISSUES.md`：新增 `miaoshou/inventory_export` 条目（含本次 2026-10-23 失败的现象与根因）
- `docs/guides/CANONICAL_COMPONENT_STATUS.md`：更新 `miaoshou/inventory_export` 状态标记
- `docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md:1008` 的「历史成功过」记录保留，但需补注「2026-10-23 再次失败（flaky）」

**理由**：`CANONICAL_RUNTIME_ISSUES.md` 至今未列 `miaoshou/inventory_export`（只列了旧的 `miaoshou/export`），这是本次问题未被提前发现的直接原因。

### 5.2 L1：止血 + 可诊断（批次 1）

#### L1-1 仓库筛选点击：四层防护

**改动文件**：`modules/platforms/miaoshou/components/warehouse_filters.py`

| 层 | 手段 | 针对形态 | 依据 |
|---|---|---|---|
| **A** | 定位并点击 `.jx-select` 触发器容器（而非被覆盖的 `.jx-select__input`） | 空态 placeholder | §1（选择器集中在 `*_config.py`） |
| **B** | `click(force=True)` + 最多 1 次重试 | tags 堆积 | 同平台订单域已验证 |
| **C** | 「已全选」前置检测：命中即跳过开下拉 | 两种形态都防 | 订单域 `_collapsed_summary_already_shows_all_selected` 同款 |
| **D** | 键盘兜底：focus + `Enter`/`ArrowDown` | 最后一道 | 《规范》§4 复杂交互 |

**定位器**：`get_by_label(re.compile(r"仓库"))` → `get_by_role("combobox", name=re.compile(r"^仓库\s*[:：]?$", re.IGNORECASE))`，对齐订单域写法。

**新增 CSS 选择器**必须落在 `modules/platforms/miaoshou/components/inventory_config.py`，并注明多语言/改版风险（《规范》§1）。

**超时**：`timeout=1500` → `3000`（《规范》§13.5；TikTok 组件用 3000）。

#### L1-2 组件可观测性

**改动文件**：`modules/platforms/miaoshou/components/inventory_export.py`、`warehouse_filters.py`

- 接入 `self.ctx.logger`（`ComponentBase.logger`），每阶段 `info` / 失败 `error`
- 每阶段调用 `await self.report_step("step_start"|"step_success"|"step_failed", step_id=..., action=...)`（《规范》§5.3）
- 失败时截图落盘到 `ctx.config["task"]["screenshot_dir"]`（对齐 TikTok `products_export.py:202-212`）
- 失败消息带**阶段名**，如 `warehouse_scope_open_failed: <原始错误>`

**效果**：步骤时间线的数据源就是任务日志流（`CollectionTasks.vue:410-438` 渲染 `log.message` 与 `log.details.error`），组件一旦写日志，界面立刻可见。

**阶段划分**（6 段，作为 §5.5 的实施基线）：

| step_id | 动作 |
|---|---|
| `navigation_ready` | 导航到仓库清单并双信号确认就绪 |
| `popup_cleared` | 弹窗清理 |
| `warehouse_scope_ready` | 仓库范围筛选（pre/action/post 三段） |
| `search_results_ready` | 搜索并确认结果 |
| `export_dialog_ready` | 打开导出弹窗 + 字段全选 |
| `download_saved` | 下载并落盘校验 |

#### L1-3 测试升级

**改动文件**：`backend/tests/test_miaoshou_inventory_export_v2_flow.py`、`backend/tests/test_miaoshou_warehouse_filters_contract.py`

- 把源码字符串断言改为 **mock page 行为测试**（对齐上游 spec §7 的原始要求，以及 `tests/unit/test_shopee_products_export.py` 的 1504 行范式）
- **新增用例必须覆盖**：
  1. 空态 placeholder 遮挡 → 组件能穿透或前置检测能识别（**本次失败的复现用例**）
  2. tags 堆积态（已全选）→ 不开下拉直接跳过
  3. 空态无遮挡 → 正常路径
  4. 各阶段失败 → 错误消息含对应阶段名
- `test_miaoshou_warehouse_filters_contract.py` 从 22 行扩为真正的行为测试

**约束**：新测试**不得**使用源码字符串断言。

### 5.3 L2：按规范全面整改（批次 2）

| # | 整改项 | 《规范》条款 |
|---|---|---|
| L2-1 | 定位器唯一性 + 作用域收敛（先定位稳定容器，再 `get_by_*`） | §1 / §13.1 / §16 |
| L2-2 | `.first`/`.nth` 收敛到具体容器 + 补业务语义注释（§16 要求「有注释才放行」） | §16 |
| L2-3 | 检测层三分：pre-check / action / **post-check**（筛选后回读勾选状态） | §3.5 |
| L2-4 | 结构化错误：`stage/status/reason/current_url/matched_signal/screenshot_path` | §3.5.1 / §13.4 |
| L2-5 | 导出阶段验证码：按登录阶段同一套（检测 → `VerificationRequiredError` → 暂停 → 回传 → 同 page 继续） | §5.5 / §8.1 |
| L2-6 | 导航双信号：URL/路由特征 + 关键元素可见 | §13.2 |
| L2-7 | 死配置清理：`inventory_config.py` 的 `GROUP_TITLES` / `GROUP_CHECK_ALL_TEXT` / `DATA_TYPE_DIR`（当前 grep 零命中）—— **接上或删除，不留假配置** | §1 |
| L2-8 | 拆分 `_expect_download_with_pageerror_guard`（91 行 → ≤50 行） | `TESTING_AND_QUALITY.md:209` |
| L2-9 | `warehouse_filters.py` 结构归位（见 §5.6 命名约定） | `CANONICAL_COLLECTION_COMPONENTS.md` |

**执行前提**：L2-1/L2-2 需要 pwcli 重新抓取真实页面 DOM 取证（《规范》Authoring Sequence 第 2 步）。**取证必须在有头模式、能人工处理验证码的环境下进行。**

### 5.4 L3：机制层（批次 1 出设计，批次 3 落地）

#### L3-1 把 §13 五条强约束做成机器 lint

**目标**：让《规范》从文档文字变成合入门禁。

**可静态检测的检查项**：

| 检查项 | 对应条款 | 判定 |
|---|---|---|
| `.first` / `.nth(` 无邻近业务语义注释 | §13.1 / §16 | error |
| `except Exception: pass`（吞异常） | §2 / §13 | error |
| 单次 `count()` + `is_visible()` 后即操作 | §2 | error |
| 关键步骤缺 `report_step` 调用 | §5.3 / §13.4 | warning |
| 函数 > 50 行 / 类 > 500 行 | `TESTING_AND_QUALITY.md:209-213` | warning |
| 无 `ctx.logger` 接入 | §13.4 | warning |
| 组件无 stable 记录 / 指向 `archive/` 或缺失文件 | `ACTIVE_COLLECTION_COMPONENTS.md:76` | error |

**复用**：仓库已有 lint 基础设施（`backend/services/component_recorder_lint.py` 一带，`backend/tests/test_component_recorder_lint.py`），扩展它而非从零造。

**关键约束（已查证）**：现有 lint 挂在**录制器保存路径**上，**手写组件不经过那条路径**。因此要让 lint 覆盖手写组件，必须单独接入 CI / pre-commit，不能依赖录制器。

**上线策略**：仓库现有 27 条 stable 组件记录，lint 一次性强制阻断会爆出大量历史违规并可能打挂流水线。

→ **第一阶段：告警模式跑一轮**，先清 miaoshou 与新增/修改组件；
→ **第二阶段：只对新增/修改的组件强制阻断**。

#### L3-2 规范补三处空白

| 缺口 | 现状 | 补充内容 |
|---|---|---|
| 组件内交互重试 vs 执行器域级重试的边界 | 《规范》§6 写「组件内部不自动重试」，但订单域在线上做组件内 `force=True` 重试，实证必要 | 明确区分：**交互级重试**（组件内，针对遮挡/时序，允许）vs **域级重试**（执行器层，针对网络/5xx） |
| 同平台多域共用 filters 的结构约定 | 固定槽位 `filters.py` 已被订单域占用，库存域的 `warehouse_filters.py` 无合法位置 | 增加「域内 filters」约定：`filters.py` + `filters_<domain>.py`，并写明何时允许域隔离 |
| archive 前置条件的机器校验 | 纯靠人记得，导致孤儿 stable 记录 | 增加 guard：文件移入 `archive/` 前检查无 stable 记录指向 |

#### L3-3 收紧「进入 active 清单」的准入门槛

**现状**：`is_active_component_name()` **从文件系统推导** —— 文件名符合 `*_export.py` 即算活跃组件。结果是半成品也能进主链路（库存域即如此）。

**建议准入三门**（新增组件必须满足）：
1. 有对应的 `CANONICAL_RUNTIME_ISSUES.md` 条目（含真实页面验证状态）
2. 有**行为测试**（不接受源码字符串断言）
3. 有 stable 版本记录且指向非 archive 文件

#### L3-4 修「域可勾选但无组件」的静默剪枝

**改动面**：
- 前端 `getAvailableDomainOptions(platform)` 按平台过滤（当前忽略 platform）
- 后端保存校验增加「该平台该域是否有可用组件」，不可用时明确报错而非静默剪掉
- 执行期 `skipped_targets` 应回写到任务详情（`failed_domains` 或独立字段），让用户看得见「你勾的某个域没跑」

**注意**：miaoshou 的 `orders` 是子域拆分（`orders_shopee_export` / `orders_tiktok_export`），校验逻辑需按 `build_component_name` 的真实语义实现，不能简单按 `<domain>_export.py` 判存在。

#### L3-5 执行器失败语义分级（可选，低优先）

区分「可重试」（网络抖动、遮挡、时序）与「不可重试」（页面改版、控件消失），让 flaky 与真故障在任务详情里可区分。

### 5.5 L4：结构性去重（批次 4，上线后 V2）

| # | 项 | 说明 |
|---|---|---|
| L4-1 | 同平台内去重 + 平台无关算法下沉 | `_is_checkbox_selected`（判定算法，平台无关）、下载捕获、遮挡穿透、结构化错误 → `modules/components/` |
| L4-2 | `popup_config` 填真实选择器 | 三个平台的 `get_close_selectors()` **当前全返回 `[]`**，机制存在但配置为空，导致组件各自造 `_ensure_popup_closed` 轮子。先用 pwcli 取证填充，再把组件内重复轮询收回统一机制 |
| L4-3 | 三平台各自的 `_download_helpers.py` 合并 | tiktok(2.1KB) / shopee(7.3KB) 内容不同但功能重叠 |
| L4-4 | `warehouse` vs `inventory` 域映射统一 | `python_component_adapter.py:54-55`：`warehouse` 指向**不存在的** `MiaoshouExport` 类（该类全仓不存在），`inventory` 指向 `MiaoshouInventoryExport` —— 两个域打同一个页面 |
| L4-5 | 订单域组件文件结构统一 | 当前为 `orders_export_base.py`（非 canonical 命名）+ `orders_shopee_export.py` + `orders_tiktok_export.py` |

### 5.6 关键边界：什么**不**下沉

这是本 spec 最容易被误读的地方，明确写死：

| 下沉到 `modules/components/` | **不下沉**，留在各平台 |
|---|---|
| 复选框勾选**判定算法**（`aria-checked` / class 含 `checked` / `input:checked`）—— DOM 语义，三平台通用 | 复选框/下拉框的**选择器与文案** → 各平台 `*_config.py`（《规范》§1 要求注明改版风险） |
| 下载捕获与落盘 | 弹窗容器结构、关闭按钮选择器 → 各平台 `popup_config.py` |
| 遮挡穿透点击（force + 重试） | 平台特有的业务筛选逻辑（订单状态 vs 仓库范围）→ 域内 filters |
| 结构化错误格式与阶段命名约定 | 域特定的数据流（inventory 同步下载 vs purchase 异步导出轮询） |

**理由**：合并平台特有选择器会制造改版风险（一个平台改版就炸全部），且违反《规范》§1。合并**同平台内**的重复副本则是零风险的纯去重。

### 5.7 领域隔离的合法化（规范补白的一部分）

`warehouse_filters.py` 的存在是上游设计的刻意决策（§2.6），但当前不在 canonical 槽位内。

**约定**：`filters.py`（平台级筛选入口）+ `filters_<domain>.py`（域特定实现），后者由前者按 `data_domain` 分派。

这样：
- 订单域：`filters.py` → `filters_orders.py`
- 库存域：`filters.py` → `filters_inventory.py`
- 采购域：`filters.py` → `filters_purchase.py`（若需要）

**收益**：共享分派入口 + 域隔离实现 + 消除 `warehouse_filters.py` 的规范缺口。

**成本**：改动面比「保留 `warehouse_filters.py`」大。**本 spec 不在批次 1/2 执行此重命名**，仅在 §5.3 L3-2 中把约定写进规范，作为批次 4 的重构项。

---

## 6. 数据与契约影响

| 契约 | 是否变更 |
|---|---|
| `ComponentVersion` 表结构 | 否（仅改数据行：孤儿记录置非 stable） |
| 组件基类签名 `run(self, page, mode=...) -> ExportResult` | 否 |
| `ExecutionContext` 字段 | 否 |
| 采集配置 API / 前端数据结构 | 否（L0-1 只改展示） |
| 落库表 `b_class.fact_miaoshou_inventory_snapshot` | 否 |
| 粒度口径（inventory → snapshot） | 否 |
| `data_domain` / `component_type` 元数据 | 否 |

---

## 7. 验收标准

### 7.1 批次 1（L0 + L1）

| # | 验收项 | 判定方式 |
|---|---|---|
| A1 | 任务详情页能看到域级完整错误（含 Playwright call log） | 打开 task 637 的详情页，可见「失败域 inventory」下方有错误详情 |
| A2 | 孤儿 stable 记录已清理 | `SELECT ... FROM core.component_versions WHERE component_name='miaoshou/inventory_snapshot_export'` 的 `is_stable` 为 false |
| A3 | 三份文档已更新 | `CANONICAL_RUNTIME_ISSUES.md` 含 `miaoshou/inventory_export` 条目 |
| A4 | 库存域能跑通 | 勾选库存域执行配置 → 任务 `status=completed`，`files_collected ≥ 1` |
| A5 | 遮挡场景可恢复 | 行为测试覆盖形态 A（placeholder 遮挡）并通过 |
| A6 | 已全选态跳过下拉 | 行为测试覆盖形态 B 并通过 |
| A7 | 失败可诊断 | 故意让某阶段失败 → 错误消息含阶段名；`report_step` 有记录；截图文件存在 |
| A8 | 时间线可见步骤 | 任务详情「步骤时间线」出现组件写入的阶段条目 |
| A9 | 测试形态升级 | `test_miaoshou_inventory_export_v2_flow.py` 与 `test_miaoshou_warehouse_filters_contract.py` **不再包含源码字符串断言** |
| A10 | 不破坏其他域 | `pytest backend/tests/test_miaoshou_*` 全绿；`shopee` / `tiktok` 采集测试不受影响 |

### 7.2 批次 2（L2）

| # | 验收项 |
|---|---|
| B1 | 库存域两文件对《规范》§13 五条强约束**零违反**（由批次 3 的 lint 判定） |
| B2 | 定位器唯一性：交互目标的 `.first` 均有邻近业务语义注释或已消除 |
| B3 | 检测层：每个关键动作有 post-check |
| B4 | 导出阶段弹验证码能触发 `VerificationRequiredError` 并进入暂停→回填→继续 |
| B5 | 导航为双信号判定 |
| B6 | `inventory_config.py` 无零引用配置项 |
| B7 | 所有函数 ≤50 行、类 ≤500 行 |

### 7.3 批次 3（L3）

| # | 验收项 |
|---|---|
| C1 | lint 可对手写组件运行（不依赖录制器路径） |
| C2 | lint 覆盖 §13 五条强约束的 §5.4 表中全部检查项 |
| C3 | 告警模式运行一轮后，转为对新增/修改组件强制阻断 |
| C4 | 《规范》补入三处空白 |
| C5 | 新增组件需过三门准入才进 active 清单 |
| C6 | 勾选无组件的域时，保存报错或界面明确提示，不再静默剪掉 |

### 7.4 批次 4（L4）

| # | 验收项 |
|---|---|
| D1 | `modules/components/` 下无平台特有选择器 |
| D2 | `_is_checkbox_selected` / `_ensure_popup_closed` 在 miaoshou 内各只剩一份 |
| D3 | 三平台共用一份 `_download_helpers` |
| D4 | `popup_config` 三平台的 `get_close_selectors()` 非空且有真实页面证据 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 订单域参考实现（`filters.py`）当前是**未提交的工作区改动** | 本 spec 引用它作为模式依据，但仓库 HEAD 中不存在该实现 | 批次 1 需把订单域修复单独提交并说明来源；**本 spec 不代替该提交** |
| 形态 A（点容器外壳）在真实页面上未必能打开下拉 | L1-1 的 A 层失效 | 四层防护逐级降级，A 失败自动落到 B；批次 2 用 pwcli 取证校正 |
| 改前端渲染 `d.error` 可能暴露内部路径/选择器 | 信息暴露 | 只在管理员可见的任务详情页展示（该页面本身是管理端） |
| 清理孤儿 stable 记录时误删有效记录 | 运行时解析失败 | 只处理 `component_name='miaoshou/inventory_snapshot_export'` 且 `file_path` 已不存在的记录；执行前后各查一次并记录 |
| lint 一次性阻断打挂流水线 | CI 红灯 | 批次 3 第一阶段告警模式 |
| 批次 2 取证受验证码环境限制 | 延期 | 批次 1 的四层防护已覆盖 A/B 两形态，不阻塞业务恢复 |

---

## 9. 前置依赖

| # | 依赖 | 状态 |
|---|---|---|
| D1 | 订单域 `filters.py` 修复（`force=True` + DOM 结构化已全选检测）提交入库 | ⚠️ **当前为未提交工作区改动**，需先落库 |
| D2 | 本地库 `xihong_erp` 可访问（用于 stable 记录清理与验收查询） | ✅ 已验证 |
| D3 | pwcli + 有头浏览器环境（批次 2 取证用） | ⏳ 批次 2 前置 |
| D4 | `frontend` 与 `backend` 本地可运行（验收 A1/A4 用） | ✅ 已在运行 |

---

## 10. 遗留与后续

- **批次 2/3/4** 各自另开执行任务时，引用本 spec 的条款编号，不重复推导
- 库存域从「历史成功过」到「本次失败」的 flaky 记录，已在 `CANONICAL_RUNTIME_ISSUES.md` 登记，作为后续回归基线
- `2026-09-13` 上游 spec 的 §7 测试策略（mock page 行为验证）在本 spec §5.2 L1-3 得到落实，**该上游 spec 的落地偏差至此关闭**
