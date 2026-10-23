# 妙手库存数据域采集整改 · 批次 1 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让「采集配置勾选库存数据域 → 执行配置 → 产出文件入库」这条链路稳定可用——失败看得见、失败说得清、库存域扛得住 `jx-select` 遮挡点击。

**Architecture:** 三层改动。**展示层**（L0-1）把后端已经写进库的域级错误渲染出来；**组件层**（L1-1）给仓库范围下拉框加 C→A→B→D 四层防护；**可观测层**（L1-2）同时改执行器注入 `logger`/`step_callback`、组件按阶段 `report_step`、失败落截图。机制层（L3-1）本批次**只出 lint 设计**，不落地代码。

**Tech Stack:** Python 3.11 / Playwright async API / pytest + pytest-asyncio / SQLAlchemy async / PostgreSQL `postgresql://…@localhost:15432/xihong_erp` / Vue 3 + Element Plus / node --test

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

---

## Task 1: L0-1 前端渲染域级错误

**问题（实证）**：task 637 的 `failed_domains[0].error` 里已经存着完整 Playwright call log，但 `CollectionTasks.vue:402-407` 只渲染域名；顶层 `error_message` 为 `None`，「错误信息」栏整栏不显示。

**Files:**
- Create: `frontend/src/domains/collection/views/collection/collectionTaskErrors.js`
- Create: `frontend/scripts/collectionTaskErrors.test.mjs`
- Modify: `frontend/src/domains/collection/views/collection/CollectionTasks.vue:402-407`（模板）+ `<script setup>` 区块
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

在 `frontend/package.json` 的 `scripts` 段追加（注意保持 JSON 逗号正确）：

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
    async with AsyncSessionLocal() as session:
        changed = 0
        for row in rows:
            row.is_stable = False
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

条目内容必须包含：

| 字段 | 值 |
|---|---|
| 组件 | `miaoshou/inventory_export` |
| 现象 | 2026-10-23 11:56:35 任务失败，耗时 44s（含 23s 等验证码） |
| 直接根因 | `warehouse_filters.py:95` `trigger.click(timeout=1500)` 被 `jx-select__selected-item jx-select__placeholder is-transparent` 拦截命中测试 |
| 性质 | **flaky**（历史成功过：2026-09-14，见 `2026-10-21-inventory-aging-pipeline-recovery.md:1008`） |
| 证据 | `logs/backend-local.out.log:364-389`；`core.collection_tasks` id=637；`core.collection_task_logs` id=3984 |
| 域隔离 | 同期 task 636（orders）completed，域之间互不影响 |
| 整改 | 见 spec `2026-10-23-miaoshou-inventory-domain-remediation-design.md` §5.2 L1-1 |

同时补一条**订单域同类问题**的记录：订单状态 `filters.py` 的 `force=True` 修复曾以未提交改动存在并打挂 4 个既有单元测试，2026-10-23 已随 `162f8bb0` 修好入库。

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
- Modify: `backend/tests/test_miaoshou_warehouse_filters_contract.py`（从 22 行 contract 测试扩为行为测试）

- [ ] **Step 0: 起点自检（已完成，2026-10-23）**

本计划的「假对象模型 + 四层防护实现」配对已做过端到端自检（四条路径全部跑通）：

| 用例 | 结果 |
|---|---|
| 形态 A（触发器被拦截） | 层 A 点容器成功，`container.clicked == 1` |
| 层 A 不可用 | 层 B 生效，`click_calls == [(3000, True)]`（force=True 传到位） |
| 形态 B（已全选 `["仓库A", "+ 4"]`） | 层 C 命中，`details.skipped is True` |
| A/B/C 全失败 | 层 D 触发 `keyboard.pressed == ["Enter"]`，消息含 `warehouse_scope_open_failed` |

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
        if self.intercept_clicks:
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
    container_available: bool = True,
    overlay: FakeLocator | None = None,
    selected_tags: list[str] | None = None,
) -> FakePage:
    trigger = FakeLocator(intercept_clicks=trigger_intercepted)
    container = FakeLocator()
    label_input = FakeLocator(
        children={CONTAINER_XPATH: container} if container_available else {}
    )

    jx_select = FakeLocator(
        children={
            ".jx-select__selected-item": FakeLocator(
                children={".jx-tag": FakeTagList(selected_tags or [])},
                count=1 if selected_tags else 0,
            )
        }
    )

    return FakePage(
        locators={
            "label:仓库": label_input,
            "role:combobox:None": trigger,
            ".jx-select": jx_select,
            "role:tooltip:None": overlay if overlay is not None else FakeLocator(count=0),
        }
    )


def _container_of(page: FakePage) -> FakeLocator:
    return page.locators["label:仓库"].children[CONTAINER_XPATH]
```

**五个红灯用例**（追加到同一文件）：

```python
@pytest.mark.asyncio
async def test_warehouse_filters_opens_dropdown_when_placeholder_intercepts_trigger_click() -> None:
    """形态 A：空态 placeholder 遮挡触发器点击时，靠层 A（点容器外壳）仍能打开下拉。

    这是线上 task 637 的复现用例。
    """
    component = MiaoshouWarehouseFilters(_ctx())
    overlay = _overlay(checked=True)
    page = _page(trigger_intercepted=True, overlay=overlay)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert _container_of(page).clicked == 1
    assert overlay.get_by_role("checkbox", name="全选").clicked == 0


@pytest.mark.asyncio
async def test_warehouse_filters_falls_back_to_force_click_when_container_unavailable() -> None:
    """层 A 不可用时，层 B 用 force=True 穿透遮挡。"""
    component = MiaoshouWarehouseFilters(_ctx())
    overlay = _overlay(checked=True)
    page = _page(trigger_intercepted=False, container_available=False, overlay=overlay)

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    trigger = page.locators["label:仓库"]
    assert trigger.click_calls  # 层 B 至少点过一次触发器


@pytest.mark.asyncio
async def test_warehouse_filters_skips_dropdown_when_scope_already_all_selected() -> None:
    """形态 B：已全选（折叠出 "+ N" 标签）时不开下拉直接返回。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(selected_tags=["仓库A", "+ 4"])

    result = await component.run(page, {"select_all": True})

    assert result.success is True
    assert result.details.get("skipped") is True


@pytest.mark.asyncio
async def test_warehouse_filters_tries_keyboard_fallback_then_reports_stage_name() -> None:
    """A/B/C 全失败后触发层 D 键盘兜底，并给出带阶段名的失败信息。"""
    component = MiaoshouWarehouseFilters(_ctx())
    page = _page(
        trigger_intercepted=True,
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

Expected: **FAILED**（新增的 5 个行为用例应全部失败或因实现缺失而报错——层 A/B/C/D 与阶段名都还没实现；原有的 2 个 contract 断言应仍然通过）。

- [ ] **Step 4: 提交（测试先行，红灯提交）**

```powershell
git add -- backend/tests/miaoshou_page_fakes.py backend/tests/test_miaoshou_warehouse_filters_contract.py
git commit -m "test(妙手采集): 补库存域仓库筛选四层防护的行为测试"
```

---

## Task 5: L1-1 实现四层防护（转绿）

**Files:**
- Modify: `modules/platforms/miaoshou/components/inventory_config.py`
- Modify: `modules/platforms/miaoshou/components/warehouse_filters.py`

**明确不做**：不复用订单域 `filters.py` 的 `except Exception: continue` 吞异常写法（spec §2.3）；不复用其文本匹配式「已全选」判定。

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

        仓库筛选是「全选仓库」单复选框；已全选时折叠区会渲染 "+ N" 折叠标签。
        ⚠️ 该 DOM 形态未经真实页面取证，可能恒为 False；因此只有命中才跳过，
        未命中一律继续走 A → B → D。
        """
        try:
            containers = page.locator(".jx-select")
            total = await containers.count()
            for index in range(total):
                try:
                    selected = containers.nth(index).locator(".jx-select__selected-item").first
                    if await selected.count() == 0:
                        continue
                    tags = selected.locator(".jx-tag")
                    tag_total = await tags.count()
                    for tag_index in range(tag_total):
                        text = (await tags.nth(tag_index).text_content() or "").strip()
                        if text.startswith("+ "):
                            return True
                except Exception as e:
                    self._log(f"[warehouse_filters] 层C 候选 {index} 判定失败: {e}")
                    continue
        except Exception as e:
            self._log(f"[warehouse_filters] 层C 整体失败: {e}")
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

```powershell
python -m ruff check modules/platforms/miaoshou/components/warehouse_filters.py modules/platforms/miaoshou/components/inventory_config.py backend/tests/miaoshou_page_fakes.py
python -m black --check --line-length 88 modules/platforms/miaoshou/components/warehouse_filters.py modules/platforms/miaoshou/components/inventory_config.py backend/tests/miaoshou_page_fakes.py
```

Expected: 两者都无输出（通过）。CI 会对改动的 Python 文件跑 black + ruff。

- [ ] **Step 7: 提交**

```powershell
git add -- modules/platforms/miaoshou/components/inventory_config.py modules/platforms/miaoshou/components/warehouse_filters.py
git commit -m "fix(妙手采集): 仓库范围下拉框加四层遮挡防护"
```

---

## Task 6: L1-2a/2b 执行器注入 logger 与 step_callback

**为什么必须改执行器**：`executor_v2.py` 构造 `ExecutionContext` 时（`:2284-2288`）**既未传 `logger=` 也未传 `step_callback=`**；`python_component_adapter.py:123-131` 虽然支持这两个参数，但执行器里**所有** `create_adapter(...)` 调用都没有传。结果是 `ctx.logger` 与 `ctx.step_callback` 全为 `None` —— 组件写日志会 `AttributeError`，`report_step` 会在 `base.py:83-84` 提前 return，**一条事件都上报不了**。

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`

- [ ] **Step 1: 在执行器里加一个 step 回调工厂**

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
        （:1337-1342 仅在 details is not None 时写表）。

        `details.step_id` 是前端 getStepLabel（CollectionTasks.vue:1145-1152）
        识别阶段名的字段，必须原样带上。
        """
        if not self.status_callback:
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

- [ ] **Step 2: 在导出循环里把回调与 logger 注入 adapter**

在 `executor_v2.py` 的导出循环（`:2791-2796` 那个 `else` 分支）把

```python
                        domain_adapter = create_adapter(platform=platform, account=account, config=export_params)
```

改成

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

同样改 `:2868` 那个重复的 `create_adapter` 调用（结构相同，`domain=full_domain`）。

- [ ] **Step 3: `_execute_python_component` 路径本批次不改（写明理由）**

`executor_v2.py:2263` 的签名是 `_execute_python_component(self, page, adapter, component_type, params=None, component=None)`——**没有 `task_id`**。它的调用链上：

| 调用点 | 作用域里有 `task_id` 吗 |
|---|---|
| `:1022`（登录） | 有 |
| `:2527`（有头登录兜底） | 有 |
| `:2641`（登录） | 有 |
| `:2953`（`_execute_component` → `_execute_step`） | **无**——`_execute_step(self, page, step, component)`（`:3212`）也没有 |
| `:5172`（登录） | 有 |

要把 `task_id` 送进 `_execute_python_component`，得一路给 `_execute_component` 与 `_execute_step` 加参数——**改动面 3 层**，且 `_execute_step` 是通用步骤执行器，影响面远超本批次范围。

**关键事实：库存域走的不是这条路径。** `python_component_adapter.py:53-57` 把 `inventory` 域映射到 `MiaoshouInventoryExport`，导出流程经由 `executor_v2.py:2792` 的 `create_adapter(...).export(...)` 执行（`runtime_manifests is None` 的常规路径）。**Step 2 的 adapter 注入才是库存域的生产路径**，Step 2 做完 A8 即对库存域成立。

`_execute_python_component` 的注入挂到**批次 3**，届时一并处理 `task_id` 穿线。**本批次不要动它。**

- [ ] **Step 4: 确认 `create_adapter` 支持这两个参数**

`python_component_adapter.py:435-449` 的 `create_adapter` 已声明 `logger` 与 `step_callback` 参数并透传给 `ExecutionContext`（`:123-131`）——**无需改动该文件**。

- [ ] **Step 5: 验证事件真的落库**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest backend/tests/test_miaoshou_filters_component.py backend/tests/test_miaoshou_inventory_export_contract.py -q -p no:cacheprovider --no-header
```

Expected: 全绿（本次改动不影响既有组件行为）。

再确认 `logger` 变量在该作用域可见：`executor_v2.py` 顶部已有模块级 `logger`（`from modules.core.logger import get_logger`），`logger.info` 在 `:2280` 已被使用。✓

- [ ] **Step 6: 提交**

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

- [ ] **Step 2: 给 `run()` 加阶段事件**

把 `inventory_export.py` 的 `run()` 改为：

```python
    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
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

            await self._ensure_popup_closed(page)
            await self.report_step(
                "step_success", step_id=self.STAGE_POPUP_CLEARED, action="弹窗清理完成"
            )

            filter_result = await self.warehouse_filters_component.run(
                page, {"select_all": True}
            )
            if not filter_result.success:
                raise RuntimeError(
                    f"warehouse_scope_failed: {filter_result.message or 'warehouse filters failed'}"
                )

            await self.report_step(
                "step_start", step_id=self.STAGE_SEARCH_RESULTS_READY, action="搜索并等待结果"
            )
            await self._click_search(page)
            await self._wait_search_results_ready(page)
            await self.report_step(
                "step_success", step_id=self.STAGE_SEARCH_RESULTS_READY, action="搜索结果就绪"
            )

            await self.report_step(
                "step_start", step_id=self.STAGE_EXPORT_DIALOG_READY, action="打开导出弹窗"
            )
            await self._open_export_dialog(page)
            await self._ensure_export_fields_all_selected(page)
            await self.report_step(
                "step_success", step_id=self.STAGE_EXPORT_DIALOG_READY, action="导出字段已全选"
            )

            await self.report_step(
                "step_start", step_id=self.STAGE_DOWNLOAD_SAVED, action="触发导出并落盘"
            )
            download = await self._expect_download_with_pageerror_guard(page)
            target = await self._wait_download_complete(page, download)
            await self.report_step(
                "step_success", step_id=self.STAGE_DOWNLOAD_SAVED, action="文件已落盘"
            )
            return ExportResult(success=True, message="download complete", file_path=str(target))
        except Exception as e:
            await self.report_step(
                "step_failed",
                step_id=self.STAGE_DOWNLOAD_SAVED,
                action="导出流程失败",
                error=str(e),
            )
            return ExportResult(success=False, message=str(e), file_path=None)
```

> **注意（spec §5.2 L1-2f）**：弹窗清理的**生产主责在执行器**（`executor_v2.py:2776` 每域导出前 `close_popups`）。组件侧**不重复调用**清理，只在既有的 `await self._ensure_popup_closed(page)` 之后记录 `popup_cleared` 阶段事件。**不要**改用 `guard_overlays`（`base.py:116-140` 仅 `is_test_mode=True` 生效，生产会空转）。

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

`inventory_export.py` 顶部补 `from pathlib import Path`（已有）与 `from datetime import datetime`（已有 `:9`）。若 `logger` 名字冲突，用 `self.logger`。

在 `run()` 的 `except` 分支里，把截图路径带进错误信息：

```python
        except Exception as e:
            screenshot_path = await self._capture_failure_screenshot(page, "export")
            message = str(e)
            if screenshot_path:
                message = f"{message} (screenshot: {screenshot_path})"
            await self.report_step(
                "step_failed",
                step_id=self.STAGE_DOWNLOAD_SAVED,
                action="导出流程失败",
                error=message,
                screenshot_path=screenshot_path or "",
            )
            return ExportResult(success=False, message=message, file_path=None)
```

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

- [ ] **Step 1: 重写 `test_miaoshou_inventory_export_v2_flow.py`**

用 mock page 驱动 `MiaoshouInventoryExport.run()`，断言**调用顺序与结果形状**（不是源码文本）。骨架：

```python
"""妙手库存导出组件的行为测试（替代原源码字符串断言）。

对齐上游 spec 2026-09-13 §7「mock page 注入，验证步骤调用序列与 ExportResult 形状」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from miaoshou_page_fakes import FakeLocator, FakePage
from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_export import MiaoshouInventoryExport


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )


@pytest.mark.asyncio
async def test_inventory_export_reports_navigation_failure_with_stage_name() -> None:
    component = MiaoshouInventoryExport(_ctx())
    page = FakePage()

    # 让导航组件直接返回失败
    async def _failed_navigation(page, target):
        from modules.components.base import ResultBase

        return ResultBase(success=False, message="导航超时")

    component.navigation_component.run = _failed_navigation

    result = await component.run(page)

    assert result.success is False
    assert "navigation_failed" in (result.message or "")
```

再加三个用例（断言**序列**而非源码文本）：

| 用例 | 断言 |
|---|---|
| 仓库筛选先于搜索 | 记录 mock page 收到的调用序列，`warehouse_filters_component.run` 的序号 < 搜索按钮 click 的序号 |
| 导出弹窗字段全选先于触发下载 | 序列里「字段全选」< 「expect_download」 |
| 下载成功后返回 `file_path` | 断言 `result.success is True` 且 `result.file_path` 指向落盘路径 |

实现要点：给 `FakePage` 记录调用序列（`page.calls: list[str]`），在假对象的关键方法上追加标记；`component.navigation_component` / `component.warehouse_filters_component` 用替身对象替换。

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
npm run build
```

Expected: 构建成功。

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
