# 妙手库存数据域采集整改 · 批次 1 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让「采集配置勾选库存数据域 → 执行配置 → 产出文件入库」这条链路稳定可用——失败看得见、失败说得清、库存域扛得住 `jx-select` 遮挡点击。

**Architecture:** 三层改动。**展示层**（L0-1）把后端已经写进库的域级错误渲染出来；**组件层**（L1-1）给仓库范围下拉框加 C→A→B→D 四层防护；**可观测层**（L1-2）同时改执行器注入 `logger`/`step_callback`、组件按阶段 `report_step`、失败落截图。机制层（L3-1）本批次**只出 lint 设计**，不落地代码。

**Tech Stack:** Python 3.11 / Playwright async API / pytest + pytest-asyncio / SQLAlchemy async / PostgreSQL `postgresql://…@localhost:15432/xihong_erp` / Vue 3 + Element Plus / node --test

---

## 0.1 计划评审修订记录（2026-10-23，第 1 轮独立评审）

本计划经 1 轮独立评审（verifier，只读核验 + 实跑复现），结论 `ISSUES_FOUND (Blocker=2, Major=7, Minor=9)`，
已全部处理：

| 级别 | 问题 | 处理 |
|---|---|---|
| **BLOCKER** | Task 6 改的是 `create_adapter`（`:2792`），而**生产走 `_run_runtime_manifest_component`**（`:2785`）——A7/A8 生产不可达成 | Task 6 重写：主注入点改为 `_run_runtime_manifest_component`，并列出 7 个调用点、只给 3 个导出路径传参 |
| **BLOCKER** | Task 2 的 `--apply` 在 **detached ORM 实例**上改字段再 commit → 静默 no-op，库没变却报「已处理」 | `_apply` 改为按主键 `session.get` 重新取出再改（评审已用 SQLite 复现该坑） |
| MAJOR | 假对象无法复现形态 A：遮挡挂在永远不会被点的 locator 上 | 遮挡改挂到**真正会被点的触发器**；并让假对象区分 `force=True` 穿透与普通点击被拦截（对齐 Playwright 语义） |
| MAJOR | 「5 个用例全红」的预期不成立 | 改为「4 红 + 1 绿」，并说明 t4 是防回归护栏 |
| MAJOR | 层 C 用裸 `page.locator(".jx-select")` 全页扫描 → 别的 select 折叠态会**误判已全选**，导致导出数据范围错误 | 层 C 改为复用层 A 的 label→容器收敛，只检查「仓库」那一个 select；并补 t4 护栏用例 |
| MAJOR | 组件侧保留 `_ensure_popup_closed` 与 spec §5.2 L1-2f 冲突 | 阶段事件改为如实记录，注明生产清理由执行器与导航阶段承担，重复轮子留 L4-2 收回 |
| MAJOR | 6 个阶段只落实 2 个失败前缀 | 6 个阶段全部补齐前缀对照表 |
| MAJOR | 新 `run()` 62 行 > `TESTING_AND_QUALITY.md:211` 的 50 行上限 | 拆成 5 个 ≤50 行的私有方法 + `_current_stage` 标记 |
| MAJOR | CI 的 black/ruff 门禁对**每个改动文件**生效，而 6 个待改文件当前不合规 | 新增 **Task 0 Step 5**：先做一次纯格式化 + ruff 修复的独立 style 提交 |
| MINOR | 文档格式与既有条目冲突 / `erp-mb-xs` 类不存在 / `npm run build` 缺 `cd frontend` / 未使用 import / 假对象重复实现 / 层 C 缺 `tag_count < 2` 守卫 | 逐条修正（见各 Task） |

> 评审同时**确认通过**的部分（实施者不要改）：spec 与文档的行号引用逐条精确、
> `create_adapter` 确实支持 `logger`/`step_callback` 透传、`RetryStrategy` 无循环 import、
> DB 孤儿恰好 1 条、A10 基线 60 passed、`<el-collapse>` 无 `v-model` 在 element-plus 2.11.5
> 下仍可展开。

---

## 0. 适用范围

### 0.1 设计来源

- Spec：`docs/superpowers/specs/2026-10-23-miaoshou-inventory-domain-remediation-design.md`（第 4 稿，3 轮独立评审通过）
- 本计划只覆盖 spec 的**批次 1** = L0 全部 + L1 全部 + L3 的 lint **设计**（不含实现）

### 0.2 条款 → 任务 → 验收项 映射

| Spec 条款 | 计划任务 | 验收项 |
|---|---|---|
| L0-1 前端渲染域级错误 | Task 1 | A1 |
| L0-2 清理孤儿 stable 记录 | Task 2 | A2 |
| L0-3 补文档盲区 | Task 3 | A3 |
| L1-1 仓库筛选点击四层防护 | Task 4（先红）+ Task 5（转绿） | A4 A5 A6 |
| L1-2a/2b 执行器注入 logger + step_callback | Task 6 | A8 |
| L1-2c/2d/2e 组件阶段事件 + 截图 + 阶段名 | Task 7 | A7 A8 |
| L1-3 测试升级（去源码字符串断言） | Task 8 | A9 |
| L3-1 lint 设计 | Task 9 | （批次 3 落地） |
| 全量验收 + 镜像同步 | Task 10 | A1–A12 |

### 0.3 明确不在本批次范围

- L2 全部（spec §5.3）——需 pwcli 真实页面取证，属批次 2
- L3 的 lint **门禁实现**、L3-2 规范补白、L3-3 准入三门、L3-4 域可勾选校验——属批次 3
- L4 全部——属批次 4
- 采集配置业务语义、粒度口径、入库链路、Dashboard / SQL 资产——一律不动（spec §1.3）

### 0.4 全局约定

- **分支**：`main` 当前是发布分支，本批次在**特性分支**上做：`git switch -c feature/miaoshou-inventory-batch1`。合入前走 `scripts/sync_main_mirrors.ps1` 规定的镜像同步流程。
- **PowerShell 不展开 `*`**：pytest 必须显式列出文件（spec §7.1 A10 附注）。
- **提交信息风格**：仓库既有风格为 `type(scope): 中文标题` + 要点正文。参考 `162f8bb0`、`24cced1e`。
- **不新增根级临时脚本**：一次性脚本放 `scripts/`（仓库既有 `fix_*.py` / `migrate_*.py` 惯例）。
- **`*.md` 用 LF**；`.py` / `.ps1` 保持所在文件既有行尾（仓库内 `.ps1` 为 CRLF，`.py` 为 LF）。
- **不提交**并行会话产出的未跟踪文件（如 `docs/superpowers/specs/2026-10-23-min-price-change-notification-review.html`）。每次 `git add` 只加本任务的目标文件。

---

## Task 0: 确认起点基线（不改代码）

**Files:** 无

- [ ] **Step 1: 确认工作区干净且在期望的基线提交上**

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
git status --short
git log --oneline -3
```

Expected: 工作区只有其他会话的未跟踪 HTML（不碰它）；HEAD 至少包含 `24cced1e`。

- [ ] **Step 2: 跑 A10 验收集，记录基线**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_miaoshou_filters_component.py `
  backend/tests/test_miaoshou_inventory_export_contract.py `
  backend/tests/test_miaoshou_inventory_export_v2_flow.py `
  backend/tests/test_miaoshou_inventory_pageerror_recovery.py `
  backend/tests/test_miaoshou_purchase_export_contract.py `
  backend/tests/test_miaoshou_purchase_export_v2_flow.py `
  backend/tests/test_miaoshou_supporting_components_contract.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: `60 passed`（订单域 4 个红已在 `162f8bb0` 修好）。若不是 60 passed，先查清差异再继续。

- [ ] **Step 3: 记录 DEP-1 已闭合**

`filters.py` 的 `force=True` 修复已随 `162f8bb0` 入库且 4 个测试转绿 → spec §9 DEP-1 满足，A10 基线成立。**不要**在 `filters.py` 上再做改动。

- [ ] **Step 4: 建特性分支**

```powershell
git switch -c feature/miaoshou-inventory-batch1
```

- [ ] **Step 5: 先把本批次要动的文件过一遍 CI 的 black / ruff 门禁（独立 style 提交）**

CI（`ci.yml:125-134`）对**每个改动的 Python 文件**执行 `black --quiet <file>` 后
`git diff --exit-code`，不一致即红；`:139-145` 再跑 `ruff check`。
`scripts/ci_changed_python_files.py:21` 的 `ALLOWED_PREFIXES` 含 `backend/` 与 `modules/`，
**没有豁免**——只要动了这些文件，整文件就必须已经是 black 形态。

实测（black 25.1.0 = CI 固定版本；ruff 用仓库 `pyproject.toml` 配置）本批次要动的文件中：

| 文件 | 当前状态 |
|---|---|
| `modules/apps/collection_center/executor_v2.py` | black **would reformat**（diff 约 2400 行）；ruff **5 处违规**：`F821` @1233、`F841` @2047 / 2815 / 3002 / 5160 |
| `modules/platforms/miaoshou/components/warehouse_filters.py` | black would reformat |
| `modules/platforms/miaoshou/components/inventory_export.py` | black would reformat |
| `modules/platforms/miaoshou/components/inventory_config.py` | black would reformat |
| `backend/tests/test_miaoshou_warehouse_filters_contract.py` | black would reformat |
| `backend/tests/test_miaoshou_inventory_export_v2_flow.py` | black would reformat |
| `backend/services/active_collection_components.py` | ✅ 已合规 |
| `backend/tests/test_miaoshou_inventory_export_contract.py` | ✅ 已合规 |

因此先做**一次纯格式化提交**（无功能变更），再改功能：

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
python -m black --line-length 88 `
  modules/apps/collection_center/executor_v2.py `
  modules/platforms/miaoshou/components/warehouse_filters.py `
  modules/platforms/miaoshou/components/inventory_export.py `
  modules/platforms/miaoshou/components/inventory_config.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py `
  backend/tests/test_miaoshou_inventory_export_v2_flow.py
python -m ruff check --fix --unsafe-fixes modules/apps/collection_center/executor_v2.py
python -m ruff check modules/apps/collection_center/executor_v2.py
```

Expected: ruff 剩 0 报错。`F821 GateResult` 是 postponed 注解（运行时无影响），`F841` 是未使用
变量；**逐个确认修复不改变行为**（尤其 `:3002` 的 `last_error`，改名前先确认它确实没被读）。

```powershell
python -m pytest backend/tests/test_miaoshou_filters_component.py `
  backend/tests/test_miaoshou_inventory_export_contract.py `
  backend/tests/test_miaoshou_inventory_export_v2_flow.py `
  backend/tests/test_miaoshou_inventory_pageerror_recovery.py `
  backend/tests/test_miaoshou_purchase_export_contract.py `
  backend/tests/test_miaoshou_purchase_export_v2_flow.py `
  backend/tests/test_miaoshou_supporting_components_contract.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿（格式化不改变行为）。

```powershell
git add -- modules/apps/collection_center/executor_v2.py `
           modules/platforms/miaoshou/components/warehouse_filters.py `
           modules/platforms/miaoshou/components/inventory_export.py `
           modules/platforms/miaoshou/components/inventory_config.py `
           backend/tests/test_miaoshou_warehouse_filters_contract.py `
           backend/tests/test_miaoshou_inventory_export_v2_flow.py
git commit -m "style(采集): 本批次要改的文件过 CI 的 black 与 ruff 门禁"
```

> 这个提交是**纯机械变更**，diff 大但与业务无关——这是 CI 的硬要求，不是顺手清理。
> `PRE_LAUNCH_RULES.md` 禁止的是「与上线无关的大范围重构」；格式化属于「要动这个文件
> 就必须付的过门禁成本」。单独成 commit 后，评审时可以直接跳过这一段。

---

## Task 1: L0-1 前端渲染域级错误

**问题（实证）**：task 637 的 `failed_domains[0].error` 里已经存着完整 Playwright call log，但 `CollectionTasks.vue:402-407` 只渲染域名；顶层 `error_message` 为 `None`，「错误信息」栏整栏不显示。

**Files:**
- Create: `frontend/src/domains/collection/views/collection/collectionTaskErrors.js`
- Create: `frontend/scripts/collectionTaskErrors.test.mjs`
- Modify: `frontend/src/domains/collection/views/collection/CollectionTasks.vue:402-407`（模板）+ `<script setup>` 区块
- Modify: `frontend/src/assets/erp-layout.css`（补 `.erp-mb-xs` 工具类）
- Modify: `frontend/package.json`（新增 test script）

- [ ] **Step 1: 写失败测试**

创建 `frontend/scripts/collectionTaskErrors.test.mjs`：

```js
import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeFailedDomains,
  pickPrimaryErrorMessage
} from '../src/domains/collection/views/collection/collectionTaskErrors.js'

test('normalizeFailedDomains 提取域级错误并保留完整 call log', () => {
  const rows = normalizeFailedDomains([
    {
      domain: 'inventory',
      error: 'StepExecutionError: Export failed: Locator.click: Timeout 1500ms exceeded.\nCall log:\n  - <div class="jx-select__selected-item jx-select__placeholder is-transparent"> intercepts pointer events'
    }
  ])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].label, 'inventory')
  assert.match(rows[0].error, /intercepts pointer events/)
})

test('normalizeFailedDomains 兼容字符串形态的失败域', () => {
  const rows = normalizeFailedDomains(['orders'])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].label, 'orders')
  assert.equal(rows[0].error, '')
})

test('normalizeFailedDomains 对非数组输入返回空数组', () => {
  assert.deepEqual(normalizeFailedDomains(null), [])
  assert.deepEqual(normalizeFailedDomains(undefined), [])
})

test('pickPrimaryErrorMessage 在顶层 error_message 为空时回落到域级错误', () => {
  const message = pickPrimaryErrorMessage({
    error_message: null,
    failed_domains: [{ domain: 'inventory', error: 'boom' }]
  })

  assert.equal(message, 'boom')
})

test('pickPrimaryErrorMessage 优先使用顶层 error_message', () => {
  const message = pickPrimaryErrorMessage({
    error_message: '顶层错误',
    failed_domains: [{ domain: 'inventory', error: '域级错误' }]
  })

  assert.equal(message, '顶层错误')
})

test('pickPrimaryErrorMessage 在没有任何错误时返回空串', () => {
  assert.equal(pickPrimaryErrorMessage({ error_message: null, failed_domains: [] }), '')
})
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp\frontend
node --test scripts/collectionTaskErrors.test.mjs
```

Expected: FAIL —— `Cannot find module '../src/domains/collection/views/collection/collectionTaskErrors.js'`。

- [ ] **Step 3: 实现纯函数模块**

创建 `frontend/src/domains/collection/views/collection/collectionTaskErrors.js`：

```js
/**
 * 采集任务详情页的域级错误展示辅助（纯函数，便于单测）。
 *
 * 背景：域级失败时，后端把完整 Playwright call log 写进
 * `failed_domains[].error`，而顶层 `error_message` 为空。
 * 旧模板只渲染域名，导致已在库中的诊断信息完全不可见。
 */

const asText = (value) => (typeof value === 'string' ? value : '')

/**
 * 把后端的 failed_domains 规整成可渲染的 { key, label, error } 列表。
 * 兼容字符串形态（历史数据里存在裸域名数组）。
 */
export const normalizeFailedDomains = (failedDomains) => {
  if (!Array.isArray(failedDomains)) return []

  return failedDomains.map((item, index) => {
    if (item && typeof item === 'object') {
      const label = asText(item.domain) || asText(item.name) || `域 ${index + 1}`
      return { key: `${label}-${index}`, label, error: asText(item.error) }
    }
    const label = asText(item) || `域 ${index + 1}`
    return { key: `${label}-${index}`, label, error: '' }
  })
}

/**
 * 顶部「错误信息」栏的取值：顶层 error_message 优先，其次回落到首个域级错误。
 */
export const pickPrimaryErrorMessage = (task) => {
  const topLevel = asText(task && task.error_message)
  if (topLevel) return topLevel

  const failed = normalizeFailedDomains(task && task.failed_domains)
  const withError = failed.find((item) => item.error)
  return withError ? withError.error : ''
}
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
node --test scripts/collectionTaskErrors.test.mjs
```

Expected: 6 passed。

- [ ] **Step 5: 接入 Vue 模板**

> **关于 `el-collapse` 不带 `v-model`**：Element Plus 2.11.5 的 `useCollapse` 里
> `setActiveNames` 直接改内部 `activeNames` ref，`watch(props.modelValue)` 只在外部
> 变化时重置——没有 `v-model` 时它是**非受控**的，点击仍能正常展开。**同一文件
> `:424` 的时间线折叠已经是同样的无 `v-model` 用法**，照此保持一致即可，不必额外绑定。

修改 `frontend/src/domains/collection/views/collection/CollectionTasks.vue`。

先改模板 `:402-407`，把原来的「失败域」「错误信息」两项替换为：

```html
            <el-descriptions-item v-if="failedDomainRows.length" label="失败域">
              <div v-for="row in failedDomainRows" :key="row.key" class="erp-mb-xs">
                <span class="text-danger">{{ row.label }}</span>
                <el-collapse v-if="row.error">
                  <el-collapse-item name="domain-error">
                    <template #title>
                      <span class="text-danger">错误详情</span>
                    </template>
                    <pre class="detail-error">{{ row.error }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </el-descriptions-item>
            <el-descriptions-item v-if="primaryErrorMessage" label="错误信息">
              <span class="text-danger">{{ primaryErrorMessage }}</span>
            </el-descriptions-item>
```

再在 `<script setup>` 中加 import（放在 `import collectionApi from '@/api/collection'` 附近）：

```js
import {
  normalizeFailedDomains,
  pickPrimaryErrorMessage
} from './collectionTaskErrors.js'
```

在 `const detailTask = ref(null)`（`:527`）之后加两个 computed：

```js
// 任务详情抽屉：域级失败错误（后端已把完整 call log 写进 failed_domains[].error）
const failedDomainRows = computed(() => normalizeFailedDomains(detailTask.value?.failed_domains))
const primaryErrorMessage = computed(() => pickPrimaryErrorMessage(detailTask.value))
```

- [ ] **Step 6: 注册 test script 并跑测试**

先补工具类：`frontend/src/assets/erp-layout.css` 里有 `.erp-mr-xs`（`:273`），但**没有** `.erp-mb-xs`（全仓不存在）。在 `.erp-mr-xs` 后面加：

```css
.erp-mb-xs {
  margin-bottom: 4px;
}
```

再在 `frontend/package.json` 的 `scripts` 段追加（注意保持 JSON 逗号正确）：

```json
    "test:collection-task-errors": "node --test scripts/collectionTaskErrors.test.mjs",
```

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp\frontend
npm run test:collection-task-errors
```

Expected: 6 passed。

- [ ] **Step 7: 前端构建校验**

```powershell
npm run build
```

Expected: 构建成功，无新增报错。

> **注意**：`ci.yml` 只跑 Python 的 change-scoped pytest，**不跑前端 node 测试**。这个测试目前是本地门禁，不是 CI 门禁——不要为此改 CI（属于批次 3 范围）。

- [ ] **Step 8: 提交**

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
git add -- frontend/src/domains/collection/views/collection/collectionTaskErrors.js `
           frontend/scripts/collectionTaskErrors.test.mjs `
           frontend/src/domains/collection/views/collection/CollectionTasks.vue `
           frontend/src/assets/erp-layout.css `
           frontend/package.json
git commit -m "feat(采集): 任务详情页展示域级采集错误"
```

---

## Task 2: L0-2 清理孤儿 stable 记录

**问题（实证）**：`core.component_versions` 里 `miaoshou/inventory_snapshot_export` 的 `is_stable=True`，但 `file_path` 指向 `modules/platforms/miaoshou/components/inventory_snapshot_export.py`——该文件已于 2026-09-13（`ee8d7551`）移入 `archive/`。违反 `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md:75` 的 Archive 前置条件。

**只处理这一条**：`miaoshou/orders_export` 是「无 stable 记录」类问题（`is_stable=False` 且指向不存在的文件），属批次 3 的守卫设计，**本任务不碰**。

**Files:**
- Modify: `backend/services/active_collection_components.py`（新增 `is_missing_component_file` —— 判定逻辑放服务层，脚本只做薄 CLI）
- Create: `scripts/fix_orphan_stable_component_versions.py`
- Test: `backend/tests/test_fix_orphan_stable_component_versions.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_fix_orphan_stable_component_versions.py`：

```python
"""孤儿 stable 组件记录的判定逻辑测试。

sys.path 引导是必需的：`backend/` 下没有 `__init__.py`（命名空间包），
不同 pytest 调用方式下仓库根未必在 sys.path 上。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.active_collection_components import is_missing_component_file


def test_is_missing_component_file_detects_missing_file():
    assert is_missing_component_file("modules/platforms/miaoshou/components/__not_exist__.py") is True


def test_is_missing_component_file_detects_archived_path():
    assert (
        is_missing_component_file(
            "modules/platforms/miaoshou/archive/inventory_snapshot_export.py"
        )
        is True
    )


def test_is_missing_component_file_accepts_existing_active_file():
    assert (
        is_missing_component_file("modules/platforms/miaoshou/components/inventory_export.py")
        is False
    )


def test_is_missing_component_file_treats_empty_path_as_missing():
    assert is_missing_component_file("") is True
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_fix_orphan_stable_component_versions.py -q -p no:cacheprovider --no-header
```

Expected: FAIL —— `ImportError: cannot import name 'is_missing_component_file'`。

- [ ] **Step 3: 在服务层实现判定**

在 `backend/services/active_collection_components.py` 末尾追加：

```python
def is_missing_component_file(file_path: str, *, project_root: Path | None = None) -> bool:
    """file_path 指向的组件文件是否已不可用。

    判定：路径为空 / 位于 archive/ 目录 / 文件在磁盘上不存在。

    用于发现「stable 记录指向已归档或缺失文件」的孤儿记录
    （docs/guides/ACTIVE_COLLECTION_COMPONENTS.md「Archive 目录语义 → 前置条件」第 2 条：
      没有 stable ComponentVersion.file_path 指向该文件）。
    """
    raw = str(file_path or "").replace("\\", "/").strip()
    if not raw:
        return True
    if "/archive/" in raw:
        return True
    root = project_root or _default_project_root()
    return not (root / raw).exists()
```

- [ ] **Step 4: 写薄 CLI 脚本**

创建 `scripts/fix_orphan_stable_component_versions.py`：

```python
"""清理指向已归档或缺失文件的 stable 组件版本记录。

依据：docs/guides/ACTIVE_COLLECTION_COMPONENTS.md:75
      —— 组件文件移入 archive/ 前，必须确认没有 stable 记录指向它。

默认 dry-run，只打印将要做的变更；加 --apply 才写库。
幂等：重复执行不产生额外副作用。

用法：
    python scripts/fix_orphan_stable_component_versions.py
    python scripts/fix_orphan_stable_component_versions.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from backend.models.database import AsyncSessionLocal
from backend.services.active_collection_components import is_missing_component_file
from modules.core.db.schema import ComponentVersion


def find_orphaned_stable_records(rows: List[Any]) -> List[Any]:
    """筛出 is_stable=True 且 file_path 已失效的记录。"""
    return [
        row
        for row in rows
        if bool(getattr(row, "is_stable", False))
        and is_missing_component_file(getattr(row, "file_path", "") or "")
    ]


async def _collect_rows() -> List[Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ComponentVersion).where(ComponentVersion.is_stable.is_(True))
        )
        return list(result.scalars().all())


async def _apply(rows: List[Any]) -> int:
    """按主键重新查出来再改。

    ⚠️ 不能直接改 `_collect_rows()` 返回的实例：那个 session 已关闭，
    ORM 实例是 detached 的，对 detached 实例改字段再 `commit()` **不产生 UPDATE**——
    脚本会打印「已处理 N 条」而库里没变（静默 no-op）。
    """
    async with AsyncSessionLocal() as session:
        changed = 0
        for row in rows:
            target = await session.get(ComponentVersion, row.id)
            if target is None:
                continue
            target.is_stable = False
            changed += 1
        await session.commit()
        return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际写库（默认只 dry-run）")
    args = parser.parse_args()

    rows = asyncio.run(_collect_rows())
    orphans = find_orphaned_stable_records(rows)

    if not orphans:
        print("未发现指向缺失/已归档文件的 stable 记录，无需处理。")
        return 0

    for row in orphans:
        print(
            f"[dry-run] component_name={row.component_name} version={row.version} "
            f"file_path={row.file_path} -> is_stable=False"
        )

    if not args.apply:
        print(f"共 {len(orphans)} 条待处理记录。加 --apply 执行写库。")
        return 0

    changed = asyncio.run(_apply(orphans))
    print(f"已处理 {changed} 条记录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
python -m pytest backend/tests/test_fix_orphan_stable_component_versions.py -q -p no:cacheprovider --no-header
```

Expected: 4 passed。

- [ ] **Step 6: dry-run 确认真实库现状**

```powershell
python scripts/fix_orphan_stable_component_versions.py
```

Expected 输出**恰好命中** `miaoshou/inventory_snapshot_export`（以及任何其他同类孤儿）。若命中了不该动的记录（例如 `miaoshou/inventory_export`），先查 `is_missing_component_file` 的判定再继续。

- [ ] **Step 7: 写库**

```powershell
python scripts/fix_orphan_stable_component_versions.py --apply
```

- [ ] **Step 8: 验收 A2**

```powershell
python scripts/fix_orphan_stable_component_versions.py
```

Expected: `未发现指向缺失/已归档文件的 stable 记录，无需处理。`

> `.venv` 里没有 sqlalchemy，用 PATH 上的系统 python 执行（sqlalchemy 2.0.41）。写库连接串来自 `.env`，本机为 `postgresql://…@localhost:15432/xihong_erp`。

- [ ] **Step 9: 提交**

```powershell
git add -- backend/services/active_collection_components.py `
           scripts/fix_orphan_stable_component_versions.py `
           backend/tests/test_fix_orphan_stable_component_versions.py
git commit -m "fix(采集): 清理指向已归档文件的孤儿 stable 组件记录"
```

---

## Task 3: L0-3 补文档盲区

**问题**：`CANONICAL_RUNTIME_ISSUES.md` 至今没有 `miaoshou/inventory_export` 条目（只有旧的 `miaoshou/export`），这是本次 flaky 失败未被提前发现的直接原因。

**Files:**
- Modify: `docs/guides/CANONICAL_RUNTIME_ISSUES.md`
- Modify: `docs/guides/CANONICAL_COMPONENT_STATUS.md`
- Modify: `docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md:1008` 附近

- [ ] **Step 1: 读现有格式**

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
Get-Content docs/guides/CANONICAL_RUNTIME_ISSUES.md -Encoding UTF8 -TotalCount 60
```

照抄现有条目的字段与标题层级，**不要自创格式**。

- [ ] **Step 2: 在 `CANONICAL_RUNTIME_ISSUES.md` 新增条目**

**格式必须照既有条目**（该文档 `:85-108` 的写法）：`### \`组件名\`` 小节 + 以
`- \`P0\` / \`P1\` 标题` 起头的条目 + 缩进的说明行。**不要用表格**。

新增一个 `### \`miaoshou/inventory_export\`` 小节，内容必须覆盖这些要点（写成条目，不要写成表格）：

| 要点 | 内容 |
|---|---|
| 优先级 | 建议 `P0`（线上任务失败） |
| 现象 | 2026-10-23 11:56:35 任务失败，耗时 44s（含 23s 等验证码） |
| 直接根因 | `warehouse_filters.py` 点击仓库范围下拉框时，`jx-select__selected-item jx-select__placeholder is-transparent` 拦截命中测试 → `Locator.click: Timeout 1500ms exceeded` |
| 性质 | **flaky**（历史成功过：2026-09-14，见 `2026-10-21-inventory-aging-pipeline-recovery.md:1008`） |
| 证据 | `logs/backend-local.out.log:364-389`；`core.collection_tasks` id=637；`core.collection_task_logs` id=3984 |
| 域隔离 | 同期 task 636（orders）completed，域之间互不影响 |
| 整改 | 见 spec `2026-10-23-miaoshou-inventory-domain-remediation-design.md` §5.2 L1-1 |

同时补一条**订单域同类问题**的记录：订单状态 `filters.py` 的 `force=True` 修复曾以未提交改动
存在并打挂 4 个既有单元测试，2026-10-23 已随 `162f8bb0` 修好入库。

- [ ] **Step 3: 更新 `CANONICAL_COMPONENT_STATUS.md`**

该文档 `:57-64` 是一张「组件 / 当前状态 / 说明」的表，`miaoshou/inventory_export` 在 **`:63`**，当前状态为「可测试」。把这一行更新为反映「已完成四层防护整改、等待真实页面复验」的状态，说明列写清改动范围与未决项（层 A 的 CSS 待批次 2 取证）。

措辞与该表既有风格保持一致（状态词用「可测试 / 继续修 / 待复验」这类既有取值，不要自造）。

- [ ] **Step 4: 补注 flaky 记录**

在 `docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md:1008` 记录「inventory 域历史上成功过（2026-09-14）」的位置，补一条后续注记：

```markdown
> **2026-10-23 更新**：同一数据域再次失败（flaky，非必现）。任务 `7bb2a92e-a0eb-4129-ba5c-6237b852c909`，失败于 `warehouse_filters.py` 点击仓库范围下拉框时被 `jx-select` 透明占位层拦截命中测试。根因与整改见 `docs/superpowers/specs/2026-10-23-miaoshou-inventory-domain-remediation-design.md`。
```

- [ ] **Step 5: 校验行尾与内容**

```powershell
git diff --check
```

Expected: 无空白错误。三份 `.md` 必须是 LF（`git diff` 不应出现整文件重写）。

- [ ] **Step 6: 提交**

```powershell
git add -- docs/guides/CANONICAL_RUNTIME_ISSUES.md docs/guides/CANONICAL_COMPONENT_STATUS.md docs/superpowers/plans/2026-10-21-inventory-aging-pipeline-recovery.md
git commit -m "docs(采集): 登记妙手库存域 2026-10-23 失败与 flaky 性质"
```

---

## Task 4: L1-1 先写行为测试（红灯）

**目标**：把「本次失败的复现路径」写成可执行的行为测试。**这一步不改生产代码**，只产出测试夹具与用例，结束时必须仍然是红的。

**Files:**
- Create: `backend/tests/miaoshou_page_fakes.py`（共享假对象）
- Modify: `backend/tests/test_miaoshou_filters_component.py`（删掉本地 jx-select 假模型副本，改为 import 共享模块）
- Modify: `backend/tests/test_miaoshou_warehouse_filters_contract.py`（从 22 行 contract 测试扩为行为测试）

- [ ] **Step 0: 起点自检（已完成，2026-10-23）**

本计划的「假对象模型 + 四层防护 + 层 C」配对已做过端到端自检，**5 条路径全部跑通**：

| 用例 | 结果 |
|---|---|
| t1 层 A 治本 | 容器被点开（`container.clicked == 1`），触发器无需点击 |
| t2 层 B 穿透 | `click_calls == [(3000, True)]` —— force=True 已传到点击上且穿透成功 |
| t3 形态 B（已全选 `["仓库A", "+ 4"]`） | 层 C 命中，`details.skipped is True` |
| t4 层 C 不误判 | 别的 select 处于 `"+ 9"` 折叠态时，仓库筛选**仍被正常执行** |
| t5 层 D 兜底 | `keyboard.pressed == ["Enter"]`，消息含 `warehouse_scope_open_failed` |

自检脚本未入库（临时文件，跑完即弃）。实现时若行为与上表不符，说明假对象或实现有偏差，**先查清再改**。

- [ ] **Step 1: 创建共享假对象模块**

创建 `backend/tests/miaoshou_page_fakes.py`：

```python
"""妙手采集组件测试用的 Playwright 假对象。

设计要点：
- `click()` **必须支持 `force=` 关键字**。真实 Playwright 的
  `Locator.click(timeout=..., force=...)` 是公开 API；早期版本的假对象
  没有这个参数，导致生产代码里的 `force=True` 在测试里抛 TypeError，
  再被 `except Exception` 吞掉（spec §2.3 记录的踩坑点）。这里一次性对齐。
- `wait_for()` 在「不可见」或「数量为 0」时抛 TimeoutError，对应真实页面
  「元素不存在 / 不可见」时 Playwright 的等待超时。
- `intercept_clicks` 模拟「命中测试被覆盖层拦截」：click 直接抛
  TimeoutError，消息里带上拦截元素描述。

导入约定：`backend/tests` 下没有 `__init__.py`，pytest 会把该目录加入
`sys.path`，因此同目录测试文件用 `from miaoshou_page_fakes import ...`。

保真度说明：`locator()` / `get_by_role()` / `get_by_text()` 是**按字符串分发的查表**，
不是真实 DOM 树。真实页面上 `get_by_label("仓库")` 命中的是 `.jx-select` 内部的
`<input role="combobox">`，而 `.jx-select` 容器是它的**祖先**；假对象里容器配成
被选中元素的**子节点**，调用形状一致、方向相反。实现者不要据此推断真实 DOM 结构，
真实结构以批次 2 的 pwcli 取证为准。

**不要造第二份 jx-select 假模型（评审纠正）**：`backend/tests/test_miaoshou_filters_component.py:101-165`
已经有一套 jx-select 假模型（`_FakeTag` / `_FakeTagList` / `_FakeSelectedItem` /
`_FakeJxSelect` / `_FakeJxSelectList`，随 `162f8bb0` 入库）。`PRE_LAUNCH_RULES.md:23`
明确禁止「新增重复实现」。因此：

- 本模块提供 `FakeTag` / `FakeTagList` / `FakeSelectedItem` / `FakeJxSelect` / `FakeJxSelectList`，
  **并让 `test_miaoshou_filters_component.py` 改为从本模块 import，删掉它自己的 `_Fake*` 副本**；
- 本任务的行为测试用例直接复用这套模型，不要另写一套。

改动 `test_miaoshou_filters_component.py` 后必须重跑 A10 全量（它包含在 A10 集合里）。
"""
from __future__ import annotations

from typing import Any


class FakeTag:
    """单个 .jx-tag 文本节点。"""

    def __init__(self, text: str) -> None:
        self._text = text

    async def text_content(self) -> str:
        return self._text


class FakeTagList:
    """.jx-tag 集合：count() 返回标签数，nth(i) 返回第 i 个标签。"""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)

    async def count(self) -> int:
        return len(self._texts)

    def nth(self, index: int) -> FakeTag:
        return FakeTag(self._texts[index])


class FakeLocator:
    """通用 Locator 替身。"""

    def __init__(
        self,
        *,
        text: str = "",
        visible: bool = True,
        count: int = 1,
        checked: bool = False,
        evaluate_checked: bool | None = None,
        intercept_clicks: bool = False,
        fail_clicks: int = 0,
        children: dict[str, Any] | None = None,
    ) -> None:
        self.text = text
        self.visible = visible
        self._count = count
        self.checked = checked
        self.evaluate_checked = evaluate_checked
        self.intercept_clicks = intercept_clicks
        self.fail_clicks = fail_clicks
        self.children: dict[str, Any] = children or {}
        self.clicked = 0
        self.click_calls: list[tuple[int | None, bool | None]] = []
        self.wait_calls: list[tuple[str, int | None]] = []

    # ── Locator 协议 ────────────────────────────────────────────────
    @property
    def first(self) -> "FakeLocator":
        return self

    @property
    def last(self) -> "FakeLocator":
        return self

    def nth(self, index: int) -> "FakeLocator":
        return self

    def locator(self, query: str) -> Any:
        return self.children.get(query, FakeLocator(count=0))

    def filter(self, **kwargs: Any) -> "FakeLocator":
        return self

    def get_by_role(self, role: str, name: Any = None) -> Any:
        return self.children.get(f"role:{role}:{name}", FakeLocator(count=0))

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        return self.children.get(f"text:{text}", FakeLocator(count=0))

    async def count(self) -> int:
        return self._count

    async def wait_for(self, state: str = "visible", timeout: int | None = None) -> None:
        self.wait_calls.append((state, timeout))
        if not self.visible or self._count == 0:
            raise TimeoutError(f"locator not available ({state}, count={self._count})")

    async def is_visible(self) -> bool:
        return self.visible and self._count > 0

    async def is_checked(self) -> bool:
        return self.checked

    async def evaluate(self, script: str) -> bool:
        if self.evaluate_checked is None:
            raise RuntimeError("evaluate not configured")
        return self.evaluate_checked

    async def text_content(self) -> str:
        return self.text

    async def focus(self, timeout: int | None = None) -> None:
        self.wait_calls.append(("focus", timeout))

    async def click(self, timeout: int | None = None, force: bool | None = None) -> None:
        self.click_calls.append((timeout, force))
        if self.fail_clicks > 0:
            self.fail_clicks -= 1
            raise TimeoutError("locator.click: Timeout 1500ms exceeded")
        if self.intercept_clicks and not force:
            # 真实 Playwright 语义：命中测试被覆盖层拦截时普通 click 会超时，
            # 而 force=True 会跳过 actionability 检查从而**穿透遮挡**。
            # 这个区分是层 B 的行为测试能成立的前提。
            raise TimeoutError(
                "locator.click: Timeout 1500ms exceeded\nCall log:\n"
                '  - <div class="jx-select__selected-item jx-select__placeholder is-transparent">'
                " intercepts pointer events"
            )
        self.clicked += 1


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class FakePage:
    """Page 替身：按选择器字符串分发到 FakeLocator。"""

    def __init__(self, *, locators: dict[str, Any] | None = None) -> None:
        self.locators: dict[str, Any] = locators or {}
        self.keyboard = FakeKeyboard()
        self.waits: list[tuple[str, int | None]] = []

    def locator(self, query: str) -> Any:
        return self.locators.get(query, FakeLocator(count=0))

    def get_by_role(self, role: str, name: Any = None) -> Any:
        return self.locators.get(f"role:{role}:{name}", FakeLocator(count=0))

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        return self.locators.get(f"text:{text}", FakeLocator(count=0))

    def get_by_label(self, text: Any) -> Any:
        return self.locators.get("label:仓库", FakeLocator(count=0))

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(("timeout", ms))
```

- [ ] **Step 2: 写红灯用例**

把 `backend/tests/test_miaoshou_warehouse_filters_contract.py` 改写为行为测试。保留原有两个 contract 断言（`platform` / `component_type` / `data_domain` / 构造函数），**追加**下面五个行为用例：

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from miaoshou_page_fakes import FakeLocator, FakePage, FakeTagList
from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.warehouse_filters import MiaoshouWarehouseFilters

CONTAINER_XPATH = "xpath=ancestor::*[contains(@class,'jx-select')][1]"


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def _overlay(*, checked: bool = False) -> FakeLocator:
    """模拟已打开的下拉浮层，内含「全选」复选框与文字。"""
    full_select = FakeLocator(checked=checked, evaluate_checked=checked)
    return FakeLocator(
        children={
            "role:checkbox:全选": full_select,
            "text:全选": FakeLocator(),
        }
    )


def _page(
    *,
    trigger_intercepted: bool = False,
    trigger_always_fails: bool = False,
    label_available: bool = True,
    container_available: bool = True,
    overlay: FakeLocator | None = None,
    selected_tags: list[str] | None = None,
) -> FakePage:
    """构造妙手仓库清单页的假 page。

    ⚠️ **遮挡必须挂在 label_input 上**（评审纠正）：`_warehouse_scope_trigger` 的
    **第一个**候选是 `page.get_by_label(re.compile("仓库"))`，假对象里它恒可见 →
    直接返回。**真实页面上被遮挡的正是这个 input**（`.jx-select__input` 被
    `.jx-select__selected-item` 盖住），所以形态 A 的拦截要挂在这里。

    `trigger_intercepted`：普通 click 被覆盖层拦截，但 `force=True` 能穿透
    （对应真实 Playwright 的 actionability 检查语义）。
    `trigger_always_fails`：任何点击都失败（连 force 也失败）——用于逼出层 D。
    """
    label_input = FakeLocator(
        visible=label_available,
        count=1 if label_available else 0,
        intercept_clicks=trigger_intercepted,
        fail_clicks=99 if trigger_always_fails else 0,
    )
    container = FakeLocator(
        children={
            ".jx-select__selected-item": FakeLocator(
                children={".jx-tag": FakeTagList(selected_tags or [])},
                count=1 if selected_tags else 0,
            )
        }
    )
    if container_available:
        label_input.children = {CONTAINER_XPATH: container}

    combobox_trigger = FakeLocator(
        intercept_clicks=trigger_intercepted,
        fail_clicks=99 if trigger_always_fails else 0,
    )

    return FakePage(
        locators={
            "label:仓库": label_input,
            "role:combobox:None": combobox_trigger,
            "role:tooltip:None": overlay if overlay is not None else FakeLocator(count=0),
        }
    )


def _container_of(page: FakePage) -> FakeLocator:
    return page.locators["label:仓库"].children[CONTAINER_XPATH]
```

**五个红灯用例**（追加到同一文件）：

```python
@pytest.mark.asyncio
async def test_warehouse_filters_opens_dropdown_by_clicking_container_when_trigger_is_covered() -> None:
    """层 A 治本：触发器被 placeholder 遮挡时，改点 .jx-select 容器外壳即可打开下拉。

    这是线上 task 637 的复现用例——原实现点的是被遮挡的 input。
    """
    component = MiaoshouWarehouseFilters(_ctx())
    overlay = _overlay(checked=True)
    page = _page(trigger_intercepted=True, overlay=overlay)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    # 层 A 生效：容器被点开
    assert _container_of(page).clicked == 1
    # 组件不再依赖点那个被遮挡的触发器
    assert page.locators["label:仓库"].click_calls == []
    assert overlay.get_by_role("checkbox", name="全选").clicked == 0


@pytest.mark.asyncio
async def test_warehouse_filters_penetrates_cover_with_force_click_when_container_unavailable() -> None:
    """层 B：容器定位不到时，用 force=True 穿透遮挡点触发器。"""
    component = MiaoshouWarehouseFilters(_ctx())
    overlay = _overlay(checked=True)
    page = _page(trigger_intercepted=True, container_available=False, overlay=overlay)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    trigger = page.locators["label:仓库"]
    assert trigger.click_calls == [(3000, True)]  # force=True 已传入，且穿透成功


@pytest.mark.asyncio
async def test_warehouse_filters_skips_dropdown_when_scope_already_all_selected() -> None:
    """形态 B：已全选（折叠出 "+ N" 标签）时不开下拉直接返回。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(selected_tags=["仓库A", "+ 4"])

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is True


@pytest.mark.asyncio
async def test_warehouse_filters_does_not_mistake_other_select_for_all_selected() -> None:
    """层 C 不得误判：页面上**别的** jx-select 处于 "+ N" 折叠态时，
    不能因此跳过仓库范围筛选（否则导出数据范围错误）。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(overlay=_overlay(checked=True))
    # 页面级存在另一个处于 "+ N" 折叠态的 jx-select（店铺 / 分类等）
    page.locators[".jx-select"] = FakeLocator(
        children={
            ".jx-select__selected-item": FakeLocator(
                children={".jx-tag": FakeTagList(["店铺A", "+ 9"])},
                count=1,
            )
        }
    )

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is not True


@pytest.mark.asyncio
async def test_warehouse_filters_tries_keyboard_fallback_then_reports_stage_name() -> None:
    """A/B/C 全失败后触发层 D 键盘兜底，并给出带阶段名的失败信息。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(
        trigger_always_fails=True,
        label_available=False,
        container_available=False,
        overlay=FakeLocator(count=0),
    )

    result = await component.run(page, {"select_all": True})

    assert result.success is False
    assert page.keyboard.pressed == ["Enter"]
    assert "warehouse_scope_open_failed" in (result.message or "")
```

> **注意**：层 B 的用例只断言「触发器被点过」，不断言 `force=True` 的具体值——因为「哪一层生效」取决于层 A 是否可用，用例目的是锁住「层 A 不可用时仍能打开下拉」这个行为。层 A 的用例断言容器被点击，两条用例合起来覆盖 A/B 两层。

- [ ] **Step 3: 运行确认红灯**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: **5 个行为用例中 4 个 FAILED**（t4 例外，见下），原有的 2 个 contract 断言仍然通过。逐条预期：

| 用例 | 当前实现下的结果 | 原因 |
|---|---|---|
| t1 层 A 治本 | ❌ FAIL | 现行实现点的是被遮挡的触发器 → 组件返回 `success=False` |
| t2 层 B 穿透 | ❌ FAIL | 现行点击是 `click(timeout=1500)`，**没有 `force=True`** → 遮挡拦截生效 → `success=False` |
| t3 形态 B | ❌ FAIL | 现行实现没有「已全选」前置检测 → 去开下拉 → 找不到浮层 → `success=False` |
| t4 层 C 不误判 | ✅ **PASS** | 现行实现**根本不跳过**，所以天然满足。它的价值是**防回归**：防止将来把层 C 写成裸 `.jx-select` 全页扫描 |
| t5 层 D 兜底 | ❌ FAIL | 现行实现没有键盘兜底也没有阶段名 → 无 `Enter` 事件、消息不含 `warehouse_scope_open_failed` |

> t4 在红灯阶段就是绿的，这是**有意的**：它是一道「数据正确性护栏」，
> 锁住「别的 select 折叠态不得让仓库筛选被跳过」——写错层 C 会导致导出数据范围错误。

- [ ] **Step 4: 提交（测试先行，红灯提交）**

```powershell
git add -- backend/tests/miaoshou_page_fakes.py `
           backend/tests/test_miaoshou_filters_component.py `
           backend/tests/test_miaoshou_warehouse_filters_contract.py
git commit -m "test(妙手采集): 补库存域仓库筛选四层防护的行为测试"
```

> 改了 `test_miaoshou_filters_component.py`（抽走重复的 jx-select 假模型）→ **必须重跑 A10 全量**，
> 它在 A10 集合里。

---

## Task 5: L1-1 实现四层防护（转绿）

**Files:**
- Modify: `modules/platforms/miaoshou/components/inventory_config.py`
- Modify: `modules/platforms/miaoshou/components/warehouse_filters.py`

**明确不做**：

- 不复用订单域 `filters.py` 的 `except Exception: continue` 吞异常写法（spec §2.3）。
- **不复用订单域的「已全选」判定**：`162f8bb0` 之后订单域 `filters.py:68-100` 已经改成
  DOM 结构判定（`.jx-select__selected-item` → `.jx-tag` → `"+ "` 前缀），与本任务的层 C
  思路同构，但**它扫的是页面级 `.jx-select` 容器**（`:78` `page.locator(".jx-select")`）。
  本任务的层 C **不照抄这一点**——见下面 Step 2 的说明：必须收敛到「仓库」那一个 select，
  否则会误判别的 select 而跳过仓库筛选，导致**导出数据范围错误**。
- 订单域那个文件本身**不动**（`filters.py` 已随 `162f8bb0` 入库，A10 基线依赖它）。

- [ ] **Step 1: 在 `inventory_config.py` 增加防护参数**

在 `PROGRESS_TEXTS` 与 `DATA_TYPE_DIR` 之间插入：

```python
# ── 仓库范围下拉框（jx-select）防护参数 ──────────────────────────────
# ⚠️ 改版风险：层 A 依赖 jx-select 的 DOM 结构（.jx-select / .jx-select__selected-item /
#    .jx-tag），妙手前端改版会失效。批次 2 需用 pwcli 真实页面取证校正（《规范》§1 要求注明）。
WAREHOUSE_SCOPE_TRIGGER_TIMEOUT_MS: Final[int] = 3000
WAREHOUSE_SCOPE_OPEN_MAX_ATTEMPTS: Final[int] = 2
WAREHOUSE_SCOPE_RETRY_BACKOFF_SECONDS: Final[float] = 0.5
WAREHOUSE_SCOPE_CONTAINER_XPATH: Final[str] = (
    "xpath=ancestor::*[contains(@class,'jx-select')][1]"
)
```

在 `InventorySelectors` 数据类末尾（`data_type_dir` 之后）追加字段：

```python
    warehouse_scope_trigger_timeout_ms: int = WAREHOUSE_SCOPE_TRIGGER_TIMEOUT_MS
    warehouse_scope_open_max_attempts: int = WAREHOUSE_SCOPE_OPEN_MAX_ATTEMPTS
    warehouse_scope_retry_backoff_seconds: float = WAREHOUSE_SCOPE_RETRY_BACKOFF_SECONDS
    warehouse_scope_container_xpath: str = WAREHOUSE_SCOPE_CONTAINER_XPATH
```

- [ ] **Step 2: 在 `warehouse_filters.py` 增加四层防护实现**

改 imports：

```python
from modules.apps.collection_center.retry_strategy import RetryStrategy
from modules.components.base import ComponentBase, ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
```

> **层次先例（实测）**：平台组件从 `modules.apps.collection_center.*` 取公共能力是仓库既有做法——`miaoshou/components/overlay_guard.py:6`（`UniversalPopupHandler`）、三个平台的 `login.py:10`（`VerificationRequiredError`）。`retry_strategy.py` 只依赖 `modules.core.logger`，**不构成循环导入**（2026-10-23 已实测 import 通过）。

在类里新增以下方法（放在 `_is_checkbox_selected` 之后）：

```python
    def _log(self, message: str) -> None:
        logger = self.logger
        if logger:
            logger.info(message)

    async def _warehouse_scope_container(self, page: Any) -> Any | None:
        """层 A：由「仓库」标签语义锚点收敛到所属 .jx-select 容器外壳。

        点容器外壳而不是被 selected-item 覆盖的 .jx-select__input，是形态 A 的治本手段。
        返回 None 表示层 A 不可用（DOM 形态未取证 / 改版），由层 B 兜底。
        """
        try:
            label_input = page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first
            await label_input.wait_for(
                state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
            )
            container = label_input.locator(self.sel.warehouse_scope_container_xpath)
            await container.wait_for(
                state="visible", timeout=self.sel.warehouse_scope_trigger_timeout_ms
            )
            return container
        except Exception as e:
            self._log(f"[warehouse_filters] 层A 容器定位不可用: {e}")
            return None

    async def _scope_already_all_selected(self, page: Any) -> bool:
        """层 C：已全选前置检测（尽力而为，**不得作为唯一防线**）。

        ⚠️ **不使用裸 `.jx-select` 全页扫描**（评审纠正）：仓库清单页可能有多个
        jx-select（店铺 / 分类等），任一 select 处于 "+ N" 折叠态就会误判
        「仓库已全选」→ 直接跳过开下拉 → **导出数据范围错误**。
        必须复用层 A 的 label→容器收敛路径，**只检查「仓库」这一个 select**。

        仓库筛选是「全选仓库」单复选框；已全选时折叠区会渲染 "+ N" 折叠标签。
        ⚠️ 该 DOM 形态未经真实页面取证，可能恒为 False；因此只有命中才跳过，
        未命中一律继续走 A → B → D。
        """
        container = await self._warehouse_scope_container(page)
        if container is None:
            return False

        try:
            selected = container.locator(".jx-select__selected-item").first
            if await selected.count() == 0:
                return False
            tags = selected.locator(".jx-tag")
            tag_count = await tags.count()
            if tag_count < 2:
                # 只有一个标签 = 只选了一项 ≠ 全选（与订单域 filters.py 的守卫一致）
                return False
            for tag_index in range(tag_count):
                text = (await tags.nth(tag_index).text_content() or "").strip()
                if text.startswith("+ "):
                    return True
        except Exception as e:
            self._log(f"[warehouse_filters] 层C 判定失败: {e}")
        return False

    async def _force_click(self, trigger: Any) -> None:
        """层 B 的单次尝试：force=True 穿透遮挡点击。"""
        await trigger.click(timeout=self.sel.warehouse_scope_trigger_timeout_ms, force=True)

    async def _click_trigger_with_retry(self, trigger: Any) -> None:
        """层 B：force=True 穿透遮挡 + 有界重试。

        使用既有 RetryStrategy（《规范》§6 要求用既有重试机制，不自造内联循环）。
        """
        retry = RetryStrategy()
        await retry.execute_with_retry(
            self._force_click,
            trigger,
            retry_config={
                "max_attempts": self.sel.warehouse_scope_open_max_attempts,
                "backoff_strategy": "fixed",
                "backoff_base": self.sel.warehouse_scope_retry_backoff_seconds,
            },
            step_id="warehouse_scope_open",
        )

    async def _keyboard_open(self, page: Any, trigger: Any) -> None:
        """层 D：键盘兜底（**仅在层 A / 层 B 均失败后触发**）。

        工程兜底，《规范》未覆盖此场景。jx-select 是否响应 Enter 需批次 2 取证确认。
        """
        try:
            await trigger.focus(timeout=self.sel.warehouse_scope_trigger_timeout_ms)
        except Exception as e:
            self._log(f"[warehouse_filters] 层D focus 失败: {e}")
        await page.keyboard.press("Enter")

    async def _open_scope_dropdown(self, page: Any) -> Any | None:
        """按 C → A → B → D 打开仓库范围下拉框，返回浮层容器。

        - C 已全选前置检测：命中即跳过开下拉（返回 None）
        - A 点 .jx-select 容器外壳（治本）
        - B force=True 穿透 + 有界重试
        - D 键盘兜底（仅 A / B 均失败后触发）

        全部失败时抛 RuntimeError，消息带阶段名 warehouse_scope_open_failed。
        """
        if await self._scope_already_all_selected(page):
            self._log("[warehouse_filters] 层C 命中已全选，跳过开下拉")
            return None

        trigger = await self._warehouse_scope_trigger(page)

        container = await self._warehouse_scope_container(page)
        if container is not None:
            try:
                await container.click(timeout=self.sel.warehouse_scope_trigger_timeout_ms)
                return await self._wait_overlay_ready(page)
            except Exception as e:
                self._log(f"[warehouse_filters] 层A 打开下拉失败: {e}")

        try:
            await self._click_trigger_with_retry(trigger)
            return await self._wait_overlay_ready(page)
        except Exception as e:
            self._log(f"[warehouse_filters] 层B 打开下拉失败: {e}")
            layer_b_error = e

        try:
            await self._keyboard_open(page, trigger)
            return await self._wait_overlay_ready(page)
        except Exception as e:
            raise RuntimeError(
                "warehouse_scope_open_failed: 层A/层B/层D 均无法打开仓库范围下拉框"
                f"（层B: {layer_b_error}; 层D: {e}）"
            ) from layer_b_error
```

- [ ] **Step 3: 改 `run()` 接入四层防护与阶段事件**

把 `_warehouse_scope_trigger` 的 timeout 从 1500 提到配置值（`self.sel.warehouse_scope_trigger_timeout_ms`），并把 `run()` 改为：

```python
    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        try:
            await self.report_step(
                "step_start", step_id="warehouse_scope_ready", action="打开仓库范围筛选"
            )
            overlay = await self._open_scope_dropdown(page)
            if overlay is None:
                await self.report_step(
                    "step_success",
                    step_id="warehouse_scope_ready",
                    action="仓库范围已全选，跳过开下拉",
                )
                return ResultBase(
                    success=True, message="ok", details={"select_all": True, "skipped": True}
                )

            full_select = overlay.get_by_role("checkbox", name="全选").first
            try:
                await full_select.wait_for(state="visible", timeout=2000)
            except Exception:
                full_select = overlay.locator("label:has-text('全选') input[type='checkbox']").first
                await full_select.wait_for(state="attached", timeout=2000)

            checked = await self._is_checkbox_selected(full_select)
            if not checked:
                try:
                    await overlay.get_by_text("全选", exact=True).first.click(timeout=1000)
                except Exception:
                    await full_select.click(timeout=1000)

            await self._ensure_popup_closed(page)
            await self.report_step(
                "step_success", step_id="warehouse_scope_ready", action="仓库范围已全选"
            )
            return ResultBase(success=True, message="ok", details={"select_all": True})
        except Exception as e:
            await self.report_step(
                "step_failed",
                step_id="warehouse_scope_ready",
                action="仓库范围筛选失败",
                error=str(e),
            )
            return ResultBase(success=False, message=str(e))
```

- [ ] **Step 4: 跑行为测试确认转绿**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿。若层 C 用例失败，说明 `FakeLocator` 的 tag 文本模型不够——**扩展假对象**，不要削弱生产逻辑。

- [ ] **Step 5: 跑 A10 全量确认没打破别的域**

```powershell
python -m pytest backend/tests/test_miaoshou_filters_component.py `
  backend/tests/test_miaoshou_inventory_export_contract.py `
  backend/tests/test_miaoshou_inventory_export_v2_flow.py `
  backend/tests/test_miaoshou_inventory_pageerror_recovery.py `
  backend/tests/test_miaoshou_purchase_export_contract.py `
  backend/tests/test_miaoshou_purchase_export_v2_flow.py `
  backend/tests/test_miaoshou_supporting_components_contract.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿（用例数 ≥ 60 + 新增）。

- [ ] **Step 6: 代码规范自检**

本批次要改的这些文件在 **Task 0 Step 5** 已经 black 化过；本步只需确认新增代码没有破坏合规状态：

```powershell
python -m black --check --line-length 88 `
  modules/platforms/miaoshou/components/warehouse_filters.py `
  modules/platforms/miaoshou/components/inventory_config.py `
  modules/platforms/miaoshou/components/inventory_export.py `
  backend/tests/miaoshou_page_fakes.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py
python -m ruff check `
  modules/platforms/miaoshou/components/warehouse_filters.py `
  modules/platforms/miaoshou/components/inventory_config.py `
  modules/platforms/miaoshou/components/inventory_export.py `
  backend/tests/miaoshou_page_fakes.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py
```

Expected: 两者都无输出（通过）。若 black 报错，说明新增代码不符合格式 → **跑 black 就地修正**
再提交（不要手改格式）。

Expected: 两者都无输出（通过）。CI 会对改动的 Python 文件跑 black + ruff。

- [ ] **Step 7: 提交**

```powershell
git add -- modules/platforms/miaoshou/components/inventory_config.py modules/platforms/miaoshou/components/warehouse_filters.py
git commit -m "fix(妙手采集): 仓库范围下拉框加四层遮挡防护"
```

---

## Task 6: L1-2a/2b 执行器注入 logger 与 step_callback

**为什么必须改执行器**：组件拿到的 `ExecutionContext` 由执行器构造，而生产路径上**既没传 `logger=` 也没传 `step_callback=`** → `ctx.logger` 与 `ctx.step_callback` 全为 `None`：组件写日志会 `AttributeError`，`report_step` 会在 `base.py:83-84` 提前 return，**一条事件都上报不了**。

**生产路径到底是哪一条（评审纠正，2026-10-23 实测）**：

```
collection_tasks.py:681  resolver.resolve_task_manifests(...)
  → component_runtime_resolver.py:151-155 返回 {"login":…, "exports_by_domain":…}
  → 执行器拿到 runtime_manifests（非 None）
  → executor_v2.py:2779  if runtime_manifests is not None:   ← 生产走这一支
  → executor_v2.py:2785  export_result = await self._run_runtime_manifest_component(...)
  → executor_v2.py:2364-2368  ctx = ExecutionContext(platform=…, account=…, config=…)   ← 注入点
```

`create_adapter(...)` 那一支（`:2792` / `:2868`）是 `runtime_manifests is None` 时的**兜底路径**，
生产**不走**。只改它 = A7/A8 在生产不可达成。**两条都要改，但主注入点是
`_run_runtime_manifest_component`。**

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`

- [ ] **Step 1: 确认 `executor_v2.py` 已过 black / ruff 门禁**

`executor_v2.py` 的整文件 black 重排与 5 处 ruff 违规修复，已在 **Task 0 Step 5** 以
独立 style 提交完成。本任务只在其上叠加功能改动。

改完后复核：

```powershell
python -m black --check --line-length 88 modules/apps/collection_center/executor_v2.py
python -m ruff check modules/apps/collection_center/executor_v2.py
```

Expected: 两者都无输出。

- [ ] **Step 2: 在执行器里加一个 step 回调工厂**

在 `CollectionExecutorV2` 类里（`__init__` 之后）新增：

```python
    def _build_step_callback(
        self,
        task_id: str,
        domain: Optional[str] = None,
        progress: int = 0,
    ) -> Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]]:
        """把组件的 report_step 事件接到任务步骤日志。

        复用既有的 status_callback（collection_tasks.py:1309-1315 的签名是
        `(task_id, progress, message, current_domain=None, details=None)`），
        其中 `details` 正是决定是否写入 core.collection_task_logs 的参数
        （:1337-1342 仅在 details is not None 时写表，
        且 log_level = "error" if details.get("error") else "info"）。

        `details.step_id` 是前端 getStepLabel（CollectionTasks.vue:1145-1152）
        识别阶段名的字段，必须原样带上。
        """
        if not self.status_callback or not task_id:
            return None

        async def _on_step(event_type: str, data: Dict[str, Any]) -> None:
            payload = dict(data or {})
            step_id = str(payload.get("step_id") or "unknown")
            action = str(payload.get("action") or step_id)
            payload["step_id"] = step_id
            payload["event_type"] = event_type
            message = f"[{event_type}] {action}"
            try:
                await self.status_callback(
                    task_id, progress, message, domain, payload
                )
            except TypeError:
                # 兼容只接受 (task_id, progress, message) 的旧回调签名
                await self.status_callback(task_id, progress, message)

        return _on_step
```

> **为什么不复用 `self._update_status`**：`_update_status`（`executor_v2.py:4669-4672`）
> 负责维护 `self._task_progress_state` 的内存记账并推送 WebSocket 进度；
> `report_step` 是**组件内部的阶段事件**，不该反过来改写任务级进度百分比，
> 否则一个域内的 6 个阶段会把进度条来回抖动。两者分工不同，这里只写步骤日志。

- [ ] **Step 3: 在生产注入点 `_run_runtime_manifest_component` 里注入**

`executor_v2.py:2349-2372` 改成：

```python
    async def _run_runtime_manifest_component(
        self,
        *,
        page,
        manifest: Any,
        account: Dict[str, Any],
        config: Dict[str, Any],
        run_args: Optional[List[Any]] = None,
        run_kwargs: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        domain: Optional[str] = None,
        progress: int = 0,
    ):
        """Execute a component resolved from a stable runtime manifest."""
        from modules.components.base import ExecutionContext

        component_class = self._load_runtime_manifest_component_class(manifest)
        platform = getattr(manifest, "platform", None) or manifest.get("platform")
        ctx = ExecutionContext(
            platform=platform,
            account=account,
            logger=logger,
            config=config,
            step_callback=self._build_step_callback(
                task_id or "", domain=domain, progress=progress
            ),
        )
        component = component_class(ctx)
        args = run_args or []
        kwargs = run_kwargs or {}
        return await component.run(page, *args, **kwargs)
```

- [ ] **Step 4: 在 3 个导出调用点传参**

`_run_runtime_manifest_component` 共 7 个调用点。**只有导出路径的 3 个需要传参**：

| 调用点 | 用途 | 要传参吗 |
|---|---|---|
| `:1014` | 登录 | 否（登录已有自己的 `details={"step_id": "login", …}` 上报，见 `:1948`） |
| `:2514` | 有头登录兜底 | 否 |
| `:2633` | 登录 | 否 |
| **`:2785`** | **导出（主路径）** | **是** |
| **`:2861`** | **导出（验证码重试路径）** | **是** |
| `:5163` | 登录 | 否 |
| **`:5425`** | **导出（单域路径）** | **是** |

`:2785` 改成：

```python
                        export_result = await self._run_runtime_manifest_component(
                            page=page,
                            manifest=export_manifest,
                            account=account,
                            config=export_params,
                            task_id=task_id,
                            domain=full_domain,
                            progress=progress,
                        )
```

`:2861` 同构（`domain=full_domain`）；`:5425` 用 `domain=data_domain`。
`progress` 变量在这三处都在作用域内（导出循环里 `progress = 20 + int(70 * domain_index / …)`）。

- [ ] **Step 5: 兜底路径 `create_adapter` 也注入**

`runtime_manifests is None` 时走 `create_adapter(...)`（`:2792` / `:2868`）。虽然生产不走，
但保持两条路径行为一致，避免以后切回时又出现「事件发不出去」：

```python
                        domain_adapter = create_adapter(
                            platform=platform,
                            account=account,
                            config=export_params,
                            logger=logger,
                            step_callback=self._build_step_callback(
                                task_id, domain=full_domain, progress=progress
                            ),
                        )
```

`python_component_adapter.py:435-449` 的 `create_adapter` 已声明 `logger` 与 `step_callback`
参数并透传给 `ExecutionContext`（`:123-131`）——**无需改动该文件**。

- [ ] **Step 6: `_execute_python_component` 路径本批次不改（写明理由）**

`executor_v2.py:2263` 的签名是 `_execute_python_component(self, page, adapter, component_type, params=None, component=None)`——**没有 `task_id`**。5 个调用点里：

| 调用点 | 作用域里有 `task_id` 吗 |
|---|---|
| `:1022`（登录） | 有（`_execute_shared_login_phase` 的 keyword-only 参数，`:987`） |
| `:2527`（有头登录兜底） | 有（`:2476` keyword-only） |
| `:2641`（登录） | 有 |
| `:2953`（`_execute_component` → `_execute_step`） | **无**——`_execute_step(self, page, step, component)`（`:3212`）也没有 |
| `:5172`（登录） | 有 |

要把 `task_id` 送进 `_execute_python_component`，得一路给 `_execute_component` 与
`_execute_step` 加参数——**改动面 3 层**，且 `_execute_step` 是通用步骤执行器，影响面
远超本批次范围。且库存域**不走**这条路径（见开头）。**本批次不要动它**，挂到批次 3。

- [ ] **Step 7: 验证**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_miaoshou_filters_component.py `
  backend/tests/test_miaoshou_inventory_export_contract.py `
  backend/tests/test_miaoshou_inventory_export_v2_flow.py `
  backend/tests/test_miaoshou_inventory_pageerror_recovery.py `
  backend/tests/test_miaoshou_purchase_export_contract.py `
  backend/tests/test_miaoshou_purchase_export_v2_flow.py `
  backend/tests/test_miaoshou_supporting_components_contract.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿。

再确认 `logger` 在该作用域可见：`executor_v2.py` 顶部已有模块级 `logger`
（`from modules.core.logger import get_logger`），`logger.info` 在 `:2280` 已被使用 ✓。

- [ ] **Step 8: 提交**

```powershell
git add -- modules/apps/collection_center/executor_v2.py
git commit -m "feat(采集): 执行器向组件注入 logger 与步骤回调"
```

---

## Task 7: L1-2c/2d/2e 组件阶段事件、截图与阶段名

**Files:**
- Modify: `modules/platforms/miaoshou/components/inventory_export.py`
- Modify: `modules/platforms/miaoshou/components/warehouse_filters.py`（Task 5 已加 `warehouse_scope_ready`，本任务补截图）

- [ ] **Step 1: 定义 6 个阶段常量**

在 `inventory_export.py` 的类里加：

```python
    # 采集阶段名（写进步骤日志的 details.step_id，前端 getStepLabel 依赖它）
    STAGE_NAVIGATION_READY = "navigation_ready"
    STAGE_POPUP_CLEARED = "popup_cleared"
    STAGE_WAREHOUSE_SCOPE_READY = "warehouse_scope_ready"
    STAGE_SEARCH_RESULTS_READY = "search_results_ready"
    STAGE_EXPORT_DIALOG_READY = "export_dialog_ready"
    STAGE_DOWNLOAD_SAVED = "download_saved"
```

- [ ] **Step 2: 拆分 `run()` 并给 6 个阶段补齐事件与失败前缀**

`run()` 现在会膨胀到 60+ 行，超过 `docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md:211`
的「函数 ≤50 行」上限（而 Task 9 准备把 `oversized_function` 定为 error 级别）。
同时 6 个阶段必须有**各自**的失败前缀，否则 A7「错误消息含阶段名」只在 2/6 阶段成立。

在 `inventory_export.py` 里加一个当前阶段标记：

```python
    def __init__(self, ctx: ExecutionContext, selectors: InventorySelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or InventorySelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)
        self.warehouse_filters_component = MiaoshouWarehouseFilters(ctx, self.sel)
        # 当前阶段名：失败时用它给步骤日志一个准确的 step_id
        self._current_stage = self.STAGE_NAVIGATION_READY
```

（`__init__` 已有前四行，只补最后一行。）

把 `run()` 改成下面这样——**拆成 5 个私有方法，每个 ≤50 行，每个阶段自带失败前缀**：

```python
    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            await self._navigate_to_warehouse_checklist(page)
            await self._select_warehouse_scope(page)
            await self._search_and_wait(page)
            await self._open_export_dialog_and_select_all(page)
            target = await self._export_and_save(page)
            return ExportResult(success=True, message="download complete", file_path=str(target))
        except Exception as e:
            screenshot_path = await self._capture_failure_screenshot(page, "export")
            message = str(e)
            if screenshot_path:
                message = f"{message} (screenshot: {screenshot_path})"
            await self.report_step(
                "step_failed",
                step_id=self._current_stage,
                action="导出流程失败",
                error=message,
                screenshot_path=screenshot_path or "",
            )
            return ExportResult(success=False, message=message, file_path=None)

    async def _navigate_to_warehouse_checklist(self, page: Any) -> None:
        self._current_stage = self.STAGE_NAVIGATION_READY
        await self.report_step(
            "step_start", step_id=self.STAGE_NAVIGATION_READY, action="导航到仓库清单"
        )
        nav_result = await self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)
        if not nav_result.success:
            raise RuntimeError(
                f"navigation_failed: {nav_result.message or 'navigation failed'}"
            )
        await self.report_step(
            "step_success", step_id=self.STAGE_NAVIGATION_READY, action="已到仓库清单"
        )

        # 弹窗清理的**生产主责不在组件**：执行器在每域导出前调 close_popups，
        # navigation 内部已有 stabilize_safe_notices 调用。组件侧这一份
        # _ensure_popup_closed 是历史重复实现，收回统一机制属 L4-2（批次 4）。
        # 本批次只保留调用（删掉会改变行为），并如实记录阶段事件。
        self._current_stage = self.STAGE_POPUP_CLEARED
        try:
            await self._ensure_popup_closed(page)
        except Exception as e:
            raise RuntimeError(f"popup_cleanup_failed: {e}") from e
        await self.report_step(
            "step_success",
            step_id=self.STAGE_POPUP_CLEARED,
            action="弹窗清理阶段结束",
        )

    async def _select_warehouse_scope(self, page: Any) -> None:
        self._current_stage = self.STAGE_WAREHOUSE_SCOPE_READY
        await self.report_step(
            "step_start", step_id=self.STAGE_WAREHOUSE_SCOPE_READY, action="仓库范围筛选"
        )
        filter_result = await self.warehouse_filters_component.run(
            page, {"select_all": True}
        )
        if not filter_result.success:
            raise RuntimeError(
                f"warehouse_scope_failed: {filter_result.message or 'warehouse filters failed'}"
            )
        await self.report_step(
            "step_success",
            step_id=self.STAGE_WAREHOUSE_SCOPE_READY,
            action="仓库范围已全选",
        )

    async def _search_and_wait(self, page: Any) -> None:
        self._current_stage = self.STAGE_SEARCH_RESULTS_READY
        await self.report_step(
            "step_start", step_id=self.STAGE_SEARCH_RESULTS_READY, action="搜索并等待结果"
        )
        try:
            await self._click_search(page)
            await self._wait_search_results_ready(page)
        except Exception as e:
            raise RuntimeError(f"search_failed: {e}") from e
        await self.report_step(
            "step_success", step_id=self.STAGE_SEARCH_RESULTS_READY, action="搜索结果就绪"
        )

    async def _open_export_dialog_and_select_all(self, page: Any) -> None:
        self._current_stage = self.STAGE_EXPORT_DIALOG_READY
        await self.report_step(
            "step_start", step_id=self.STAGE_EXPORT_DIALOG_READY, action="打开导出弹窗"
        )
        try:
            await self._open_export_dialog(page)
            await self._ensure_export_fields_all_selected(page)
        except Exception as e:
            raise RuntimeError(f"export_dialog_failed: {e}") from e
        await self.report_step(
            "step_success", step_id=self.STAGE_EXPORT_DIALOG_READY, action="导出字段已全选"
        )

    async def _export_and_save(self, page: Any) -> Path:
        self._current_stage = self.STAGE_DOWNLOAD_SAVED
        await self.report_step(
            "step_start", step_id=self.STAGE_DOWNLOAD_SAVED, action="触发导出并落盘"
        )
        try:
            download = await self._expect_download_with_pageerror_guard(page)
            target = await self._wait_download_complete(page, download)
        except Exception as e:
            raise RuntimeError(f"download_failed: {e}") from e
        await self.report_step(
            "step_success", step_id=self.STAGE_DOWNLOAD_SAVED, action="文件已落盘"
        )
        return target
```

**6 个阶段 ↔ 失败前缀对照**（与 spec §5.2 的阶段表一一对应）：

| step_id | 失败前缀 | 落在哪个方法 |
|---|---|---|
| `navigation_ready` | `navigation_failed` | `_navigate_to_warehouse_checklist` |
| `popup_cleared` | `popup_cleanup_failed` | `_navigate_to_warehouse_checklist` |
| `warehouse_scope_ready` | `warehouse_scope_failed` | `_select_warehouse_scope` |
| `search_results_ready` | `search_failed` | `_search_and_wait` |
| `export_dialog_ready` | `export_dialog_failed` | `_open_export_dialog_and_select_all` |
| `download_saved` | `download_failed` | `_export_and_save` |

> **不要改用 `guard_overlays`**（`base.py:116-140`）：它**仅在 `is_test_mode=True` 时生效**，
> 拿它当生产清理手段会让 `popup_cleared` 阶段永远「成功」而什么都不做。
> 组件侧生产可用的清理机制是 `stabilize_safe_notices`（`base.py:142-165`，无门控）。

- [ ] **Step 3: 失败时落截图**

在 `inventory_export.py` 里新增一个私有方法：

```python
    async def _capture_failure_screenshot(self, page: Any, stage: str) -> str | None:
        """失败时截图落盘到 ctx.config['task']['screenshot_dir']（对齐 TikTok products_export）。

        截图失败不得影响主流程。
        """
        screenshot_dir = ""
        config = self.ctx.config or {}
        task_cfg = config.get("task") if isinstance(config, dict) else None
        if isinstance(task_cfg, dict):
            screenshot_dir = str(task_cfg.get("screenshot_dir") or "")
        if not screenshot_dir:
            return None

        try:
            target_dir = Path(screenshot_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = target_dir / f"miaoshou_inventory_{stage}_{stamp}.png"
            await page.screenshot(path=str(path))
            return str(path)
        except Exception as e:
            logger = self.logger
            if logger:
                logger.warning(f"inventory export 截图失败（已忽略）: {e}")
            return None
```

`inventory_export.py` 顶部已有 `from pathlib import Path`（`:9`）与 `from datetime import datetime`（`:8`），无需补 import。

`run()` 的 `except` 分支（Step 2 已给出）会调用它，并把截图路径带进错误信息与步骤日志的
`screenshot_path` 字段——**不要重复实现一遍**。

- [ ] **Step 4: 给仓库筛选补同样的截图**

`warehouse_filters.py` 的 `except` 分支同样加截图（路径取同一个 `ctx.config['task']['screenshot_dir']`），失败消息前缀 `warehouse_scope_*_failed`。

- [ ] **Step 5: 跑测试**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_miaoshou_filters_component.py `
  backend/tests/test_miaoshou_inventory_export_contract.py `
  backend/tests/test_miaoshou_inventory_export_v2_flow.py `
  backend/tests/test_miaoshou_inventory_pageerror_recovery.py `
  backend/tests/test_miaoshou_purchase_export_contract.py `
  backend/tests/test_miaoshou_purchase_export_v2_flow.py `
  backend/tests/test_miaoshou_supporting_components_contract.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿。

- [ ] **Step 6: 提交**

```powershell
git add -- modules/platforms/miaoshou/components/inventory_export.py modules/platforms/miaoshou/components/warehouse_filters.py
git commit -m "feat(妙手采集): 库存域按阶段上报事件并在失败时留截图"
```

---

## Task 8: L1-3 测试升级（去源码字符串断言）

**问题**：`test_miaoshou_inventory_export_v2_flow.py` 全是 `assert "..." in source` 的源码字符串断言（11 处），这正是「组件一直绿灯却抓不到真实故障」的原因（spec §2.8）。上游 spec §7 原本要求的是 mock page 行为验证，落地退化了。

**Files:**
- Modify: `backend/tests/test_miaoshou_inventory_export_v2_flow.py`（重写为行为测试）
- Modify: `backend/tests/test_miaoshou_inventory_export_contract.py`（只移除源码文本断言，保留 `selectors.*` 实例断言）

- [ ] **Step 0: 起点自检（已完成，2026-10-23）**

替身法已用**真实生产代码**实测通过：

| 断言 | 结果 |
|---|---|
| `calls == [navigation, warehouse_filters, search, search_results, open_export_dialog, ensure_export_fields, expect_download, save_download]` | 通过（顺序与现行 `run()` 完全一致） |
| 导航失败时不进入 `search` | 通过 |
| 筛选失败时不进入 `search` | 通过 |
| `page.keyboard.pressed` 不含 `Escape` | 通过 |

**依赖顺序**：本任务的两个失败用例断言 `navigation_failed` / `warehouse_scope_failed` 阶段名，
而阶段名由 **Task 7** 落地。Task 7 未完成时这两个用例会红——这是**预期的依赖**，不是缺陷。

- [ ] **Step 1: 重写 `test_miaoshou_inventory_export_v2_flow.py`**

用 mock page 驱动 `MiaoshouInventoryExport.run()`，断言**调用顺序与结果形状**（不是源码文本）。骨架：

```python
"""妙手库存导出组件的行为测试（替代原源码字符串断言）。

对齐上游 spec 2026-09-13 §7「mock page 注入，验证步骤调用序列与 ExportResult 形状」。

做法：用**替身组件/替身方法**替换导出流程里的协作组件与各步骤方法，把调用记进
共享的 `calls` 列表；断言的是**运行时的调用顺序与结果形状**，不是源码文本。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from miaoshou_page_fakes import FakePage
from modules.components.base import ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_export import MiaoshouInventoryExport


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


def _component(calls: list[str]) -> MiaoshouInventoryExport:
    """把各协作组件与步骤方法替换为替身，记录调用序列。"""
    component = MiaoshouInventoryExport(_ctx())

    async def _nav(page, target):
        calls.append("navigation")
        return ResultBase(success=True, message="ok")

    async def _filters(page, filters):
        calls.append("warehouse_filters")
        return ResultBase(success=True, message="ok")

    async def _search(page):
        calls.append("search")

    async def _results(page):
        calls.append("search_results")

    async def _open_dialog(page):
        calls.append("open_export_dialog")

    async def _fields(page):
        calls.append("ensure_export_fields")

    async def _download(page):
        calls.append("expect_download")
        return object()

    async def _save(page, download):
        calls.append("save_download")
        return Path("inventory_snapshot.xlsx")

    component.navigation_component.run = _nav
    component.warehouse_filters_component.run = _filters
    component._click_search = _search
    component._wait_search_results_ready = _results
    component._open_export_dialog = _open_dialog
    component._ensure_export_fields_all_selected = _fields
    component._expect_download_with_pageerror_guard = _download
    component._wait_download_complete = _save
    return component


@pytest.mark.asyncio
async def test_inventory_export_calls_stages_in_expected_order() -> None:
    calls: list[str] = []
    component = _component(calls)

    result = await component.run(FakePage())

    assert result.success is True
    assert result.file_path.endswith("inventory_snapshot.xlsx")
    assert calls == [
        "navigation",
        "warehouse_filters",
        "search",
        "search_results",
        "open_export_dialog",
        "ensure_export_fields",
        "expect_download",
        "save_download",
    ]


@pytest.mark.asyncio
async def test_inventory_export_reports_navigation_failure_with_stage_name() -> None:
    calls: list[str] = []
    component = _component(calls)

    async def _failed_navigation(page, target):
        calls.append("navigation")
        return ResultBase(success=False, message="导航超时")

    component.navigation_component.run = _failed_navigation

    result = await component.run(FakePage())

    assert result.success is False
    assert "navigation_failed" in (result.message or "")
    assert "search" not in calls


@pytest.mark.asyncio
async def test_inventory_export_reports_warehouse_scope_failure_with_stage_name() -> None:
    calls: list[str] = []
    component = _component(calls)

    async def _failed_filters(page, filters):
        calls.append("warehouse_filters")
        return ResultBase(success=False, message="warehouse_scope_open_failed: 打不开")

    component.warehouse_filters_component.run = _failed_filters

    result = await component.run(FakePage())

    assert result.success is False
    assert "warehouse_scope_failed" in (result.message or "")
    assert "search" not in calls


@pytest.mark.asyncio
async def test_inventory_export_does_not_use_keyboard_escape_to_close_popups() -> None:
    calls: list[str] = []
    component = _component(calls)
    page = FakePage()

    await component.run(page)

    assert "Escape" not in page.keyboard.pressed
```

**为什么用替身而不是纯 mock page**：`page.expect_download()` 是 async context manager，
真要 mock 出来需要模拟 `dl_info.value` 整套异步协议，成本高且脆。替身法同样验证
「**步骤调用序列**」与「**ExportResult 形状**」——正是上游 spec §7 要求的两件事，
而且对 `run()` 的重排敏感（把 `_click_search` 挪到筛选之前，`calls` 断言立刻失败）。

**注意**：`_ensure_popup_closed(page)` 仍会真的跑在假 page 上（它遍历 20 个弹窗选择器，
全部 `count()==0` 直接跳过）——这是有意保留的真实路径覆盖，不要把它也替身掉。

- [ ] **Step 2: 移除 `test_miaoshou_inventory_export_contract.py` 的源码文本断言**

删掉这 6 处**源码文本**断言（spec A9 注 1 列出的行 49/50/51/57/58/64）：

- `test_miaoshou_inventory_export_source_reuses_navigation_without_opening_login`（整条删除）
- `test_miaoshou_inventory_export_uses_warehouse_filters_for_scope_filter`（整条删除）
- `test_miaoshou_inventory_export_does_not_use_keyboard_escape_for_popups`（整条删除）

**保留**（L2-7 依赖）：

- `test_miaoshou_inventory_config_uses_inventory_snapshot_semantics`（含 `selectors.data_type_dir` / `group_titles` 断言，行 23/25/26）
- `test_miaoshou_inventory_export_component_declares_inventory_domain`
- `test_miaoshou_inventory_export_constructor_uses_inventory_selectors_by_default`
- `test_miaoshou_inventory_export_constructor_accepts_custom_selectors`
- `test_miaoshou_navigation_supports_warehouse_checklist_target`

「不复用导航组件、不用键盘 Escape 关弹窗」这两个意图，**改用行为断言**放进 `v2_flow` 文件：

```python
@pytest.mark.asyncio
async def test_inventory_export_does_not_use_keyboard_escape_to_close_popups() -> None:
    component = MiaoshouInventoryExport(_ctx())
    page = FakePage()
    ...
    await component.run(page)
    assert "Escape" not in page.keyboard.pressed
```

- [ ] **Step 3: 确认三个文件都不再有源码字符串断言**

```powershell
Select-String -Path backend/tests/test_miaoshou_inventory_export_v2_flow.py,backend/tests/test_miaoshou_inventory_export_contract.py,backend/tests/test_miaoshou_warehouse_filters_contract.py -Pattern 'in source|_source\(\)|read_text'
```

Expected: 无匹配。

- [ ] **Step 4: 跑测试**

```powershell
python -m pytest backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿。

- [ ] **Step 5: 提交**

```powershell
git add -- backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_inventory_export_contract.py
git commit -m "test(妙手采集): 库存域导出测试升级为 mock page 行为验证"
```

---

## Task 9: L3-1 lint 设计（本批次只出设计，不实现）

**为什么本批次只做设计**：spec §5.4 已定「lint 真实实现在 `backend/domains/collection/routers/component_recorder.py:458`，已有 5 条规则」，但**现有 lint 挂在录制器保存路径上，手写组件不经过那条路径**；且仓库有 24 条 stable 记录，一次性阻断会打挂流水线。因此先出设计（批次 3 实现：告警模式 → 新增/修改组件阻断）。

**Files:**
- Create: `docs/superpowers/specs/2026-10-23-collection-component-lint-gate-design.md`

- [ ] **Step 1: 读现有 lint 实现**

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
Get-Content backend/domains/collection/routers/component_recorder.py -Encoding UTF8 | Select-Object -Skip 450 -First 140
```

记录：`_analyze_python_code_for_lints` 的函数签名、既有规则的 type 名与正则、以及 lint 结果如何挂到响应体上。

**注意（实测，2026-10-23）**：除 spec 提到的 5 条规则外，同一处还有 **4 条 `_with_reason` 对应规则**——`wait_for_timeout_with_reason`（`:514`）、`fixed_sleep_with_reason`（`:540`）、`first_nth_with_reason`（`:576`），以及 `syntax_error`（`:478`）。也就是说「**有注释才放行**」的判定**已经实现**（`_with_reason` 是合规形态，不报违规）。设计新规则时**不要重复实现**这套「带理由注释则放行」的语义，直接沿用既有写法。

- [ ] **Step 2: 写设计文档**

设计文档必须覆盖 spec §5.4 L3-1 的全部条目，逐条给出**规则名、正则/判定方式、严重级别、误报豁免方式**：

| 检查项 | 规则 type | 严重级别 | 备注 |
|---|---|---|---|
| `.first`/`.nth` 无邻近业务语义注释 | `first_nth_usage`（已有） | error | |
| `except Exception: pass` 吞异常 | `swallow_exception_pattern`（已有） | error | |
| 单次 `count()` + `is_visible()` 后即操作 | `count_is_visible_pattern`（已有） | error | |
| 无理由固定等待 | `wait_for_timeout_usage` / `fixed_sleep_usage`（已有） | error | |
| **扩展 `swallow_exception_pattern` 覆盖 `continue` / `return` 形态** | 同名扩展 | error | 现正则只覆盖 26 处中的 4 处 |
| 关键步骤缺 `report_step` | 新增 `missing_report_step` | error | |
| 未接 `ctx.logger` | 新增 `missing_logger_usage` | warn | |
| 函数 > 50 行 / 类 > 500 行 | 新增 `oversized_function` / `oversized_class` | error | 对齐 `TESTING_AND_QUALITY.md:211,213` |
| 组件无 stable 记录 | 新增 `missing_stable_component_record` | error | |
| stable 记录指向 `archive/` 或缺失文件 | 新增 `stable_points_to_archived_file` | error | 运行时已有守卫，CI 前置；判定复用 Task 2 落在 `backend/services/active_collection_components.py` 的 `is_missing_component_file` |
| 导航单信号 | 新增 `single_signal_navigation` | warn | |
| 缺重试预算声明 | 新增 `missing_retry_budget` | warn | |

并写清：

- **接入点**：独立 CLI / CI step，**不依赖录制器路径**
- **告警 → 阻断**的两阶段策略与切换判据
- **豁免机制**（例如 `# lint:ignore[rule]` 行内注释），以及为什么 `.first` 用「有注释才放行」而非直接禁止（spec §16）
- **与 spec §5.4 L3-2 / L3-3 / L3-4 的边界**

- [ ] **Step 3: 提交**

```powershell
git add -- docs/superpowers/specs/2026-10-23-collection-component-lint-gate-design.md
git commit -m "docs(spec): 采集组件 lint 门禁设计"
```

---

## Task 10: 终验（A1–A12）与镜像同步

- [ ] **Step 1: 跑 A10 全量**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_miaoshou_filters_component.py `
  backend/tests/test_miaoshou_inventory_export_contract.py `
  backend/tests/test_miaoshou_inventory_export_v2_flow.py `
  backend/tests/test_miaoshou_inventory_pageerror_recovery.py `
  backend/tests/test_miaoshou_purchase_export_contract.py `
  backend/tests/test_miaoshou_purchase_export_v2_flow.py `
  backend/tests/test_miaoshou_supporting_components_contract.py `
  backend/tests/test_miaoshou_warehouse_filters_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿（A10 ✓）。

- [ ] **Step 2: 跑新增测试**

```powershell
python -m pytest backend/tests/test_fix_orphan_stable_component_versions.py -q -p no:cacheprovider --no-header
cd frontend; npm run test:collection-task-errors
```

Expected: 全绿。

- [ ] **Step 3: 前端构建**

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp\frontend
npm run build
```

Expected: 构建成功。（注意：**必须先 `cd frontend`**——仓库根的 `package.json` 的 `scripts`
是空的，在根目录跑 `npm run build` 会报 Missing script。）

- [ ] **Step 4: 手动验收 A1 / A7 / A8 / A12**

本地 backend + frontend 已在运行（DEP-4 ✓）：

1. 打开 task `7bb2a92e-a0eb-4129-ba5c-6237b852c909` 的详情页 → 「失败域 inventory」下方能看到折叠的「错误详情」，内容含 `intercepts pointer events`（A1 ✓）
2. 执行一次只勾选库存域的采集配置 → 任务详情「步骤时间线」出现 `navigation_ready` / `warehouse_scope_ready` / `search_results_ready` / `export_dialog_ready` / `download_saved` 阶段条目（A8 ✓）
3. 人为制造失败（如临时改坏选择器）→ 错误消息含阶段名，截图文件存在于 `ctx.config['task']['screenshot_dir']`（A7 ✓）

- [ ] **Step 5: 验收 A4 / A11（真实页面）**

需要能人工处理验证码的环境：勾选库存域执行配置 → 任务 `status=completed`、`files_collected ≥ 1`（A4 ✓）；产出文件被 `catalog_scanner` 扫描并入库 `b_class.fact_miaoshou_inventory_snapshot`（A11 ✓）。

> **若当前环境无法处理验证码**：把 A4 / A11 记为「待真实环境复验」，在 PR 描述里写明，**不要**伪造通过结论。层 A 的具体 CSS 也要等批次 2 的 pwcli 取证校正。

- [ ] **Step 6: 验收 A2**

```powershell
python scripts/fix_orphan_stable_component_versions.py
```

Expected: `未发现指向缺失/已归档文件的 stable 记录，无需处理。`（A2 ✓）

- [ ] **Step 7: 验收 A3**

```powershell
Select-String -Path docs/guides/CANONICAL_RUNTIME_ISSUES.md -Pattern 'miaoshou/inventory_export'
```

Expected: 有命中（A3 ✓）。

- [ ] **Step 8: 合并到 main 并同步镜像**

```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
git switch main
git merge --ff-only feature/miaoshou-inventory-batch1
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync
```

Expected: `XIHONG_GIT_MIRROR_SYNCED=<sha>`。

> **若 GitHub HTTPS 不通**（本机 2026-10-23 实测 `github.com:443` 被重置/超时，SSH 22 与 `ssh.github.com:443` 通）：用 SSH 通道执行同一脚本，不要绕过脚本直接单 remote push：

```powershell
$env:GIT_SSH_COMMAND = 'ssh -i C:/Users/18689/.ssh/github_actions_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
$sshUrl = 'ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git'
$origFetch = (git remote get-url origin)
try {
  git remote set-url origin $sshUrl
  & .\scripts\sync_main_mirrors.ps1 -GitHubUrl $sshUrl -Sync
} finally {
  git remote set-url origin $origFetch
}
```

**验收**：两个远端同 commit。

```powershell
git ls-remote 'ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git' refs/heads/main
git ls-remote 'https://cnb.cool/timberdayz/xihong_erp' refs/heads/main
```

---

## 附录 A: 验收项自检表

| # | 验收项 | 本计划的达成方式 | 判定方式 |
|---|---|---|---|
| A1 | 域级错误可见 | Task 1 | 打开 task 637 详情页 |
| A2 | 孤儿 stable 已清理 | Task 2 | `scripts/fix_orphan_stable_component_versions.py` 无输出 |
| A3 | 三份文档已更新 | Task 3 | `Select-String` 命中 |
| A4 | 库存域能跑通 | Task 5 + Task 10 Step 5 | 真实执行配置 |
| A5 | 形态 A 可恢复 | Task 4/5 行为用例 | pytest |
| A6 | 形态 B 跳过下拉 | Task 4/5 行为用例 | pytest |
| A7 | 失败可诊断 | Task 6 + Task 7 | 阶段名 + 截图 |
| A8 | 时间线可见步骤 | Task 6 | 前端时间线 |
| A9 | 测试形态升级 | Task 8 | 无源码字符串断言 |
| A10 | 不破坏其他域 | 全程 | A10 集合全绿 |
| A11 | 落库目标达成 | Task 10 Step 5 | `b_class.fact_miaoshou_inventory_snapshot` |
| A12 | 层 D 键盘兜底可达 | Task 5 | 行为用例：A/B/C 均失败时尝试键盘并给出可诊断失败信息 |

## 附录 B: 本批次不做、留给后续的账

| 事项 | 去向 |
|---|---|
| 层 A 的具体 CSS 校正、层 C 的 DOM 形态确认、层 D 的键盘响应、导出阶段验证码（L2-5） | 批次 2（需 pwcli 真实页面取证） |
| lint 门禁实现、准入三门、域可勾选校验（L3-2/3/4） | 批次 3 |
| 同平台去重与平台无关算法下沉、`warehouse_filters.py` → `filters_inventory.py`（L4-6） | 批次 4（上线后 V2） |
| `miaoshou/orders_export` 无 stable 记录类问题 | 批次 3 的守卫设计 |
| 执行器失败语义分级（L3-5） | 未排期（spec 只登记验收口径 C7） |
