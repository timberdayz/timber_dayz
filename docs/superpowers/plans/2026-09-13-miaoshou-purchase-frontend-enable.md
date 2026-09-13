# Miaoshou purchase 数据域前端启用 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前后端的"数据域枚举层"暴露 `purchase` 域，使前端的采集任务 / 采集配置面板可勾选"采购"，并被后端的 capability / data domain 校验通过，从而触发已合并的 `MiaoshouPurchaseExport`。

**Architecture:** 加性扩展（不替换 `finance`）。
- 后端：在 3 处枚举层加入 `purchase`（`DEFAULT_CONFIG_DATA_DOMAINS` + `get_default_shop_capabilities` + `_default_capabilities_for`）。
- 前端：在 SSOT 常量 `DEFAULT_DOMAIN_OPTIONS` 加入"采购"，同步两个 Vue 模板的 checkbox 组与 `getDomainLabel` 映射。
- 测试：先写红，再写绿，断言枚举与 capability 完整覆盖 `purchase`。

**Tech Stack:** Python (FastAPI / Pydantic / SQLAlchemy async), Vue 3 (Element Plus), pytest。

## Global Constraints

- **加性扩展**：不修改 `finance` / 其他已有数据域；不改 component_name / runtime resolver / adapter（已合并到 main，逻辑完整）。
- **TDD 严格**：每个后端改动步骤必须 RED→GREEN（先写断言失败的测试，再实现，再验证通过）。
- **前端 label 一致性**：UI 文案 "采购" 必须与 `getDomainLabel` 映射同步，否则详情区会显示原始 `purchase` 字符串。
- **pre-existing 改动不动**：当前 working tree 中 6 个 modified + 3 个 untracked 文件属另一条 SDD 流程（product_category），本任务不得触碰。
- **不引入 emoji / 不使用 `datetime.utcnow()` / 不使用 `page.keyboard.press("Escape")`**（架构惯例）。
- **follow repo instructions**: `AGENTS.md` 优先；改动前后按 `docs/guides/DEVELOPMENT_WORKFLOW.md` 与 `docs/DEVELOPMENT_RULES/README.md` 自检。

---

### Task 1: 后端枚举层扩展 + capability 默认值 + 测试

**Files:**
- Modify: `backend/services/collection_contracts.py:27-34`（`DEFAULT_CONFIG_DATA_DOMAINS`）
- Modify: `backend/services/collection_contracts.py:43-54`（`get_default_shop_capabilities`）
- Modify: `backend/domains/collection/routers/shop_accounts.py:50-61`（`_default_capabilities_for`）
- Create: `backend/tests/test_purchase_data_domain_enablement_contract.py`

**Interfaces:**
- Consumes: 后端入口 `get_supported_config_data_domains(platform)` → 调用 `DEFAULT_CONFIG_DATA_DOMAINS`；`resolve_shop_capabilities` → 调用 `get_default_shop_capabilities`。
- Produces: 新 `purchase` 数据域在 capability 默认表 / 默认域列表 / 单店默认 capability 中均可用。

- [ ] **Step 1: 写 contract 测试（RED）**

```python
"""
采购数据域启用契约测试（feat/miaoshou-purchase-frontend-enable 配套）

约束：保持加性扩展，不破坏 finance / orders / products / analytics / services / inventory 现有契约。
"""

from backend.services.collection_contracts import (
    DEFAULT_CONFIG_DATA_DOMAINS,
    get_default_shop_capabilities,
    get_recommended_config_domains,
    get_supported_config_data_domains,
    resolve_shop_capabilities,
)


def test_default_config_data_domains_includes_purchase():
    assert "purchase" in DEFAULT_CONFIG_DATA_DOMAINS


def test_default_config_data_domains_preserves_existing_six():
    expected = {"orders", "products", "analytics", "finance", "services", "inventory", "purchase"}
    assert set(DEFAULT_CONFIG_DATA_DOMAINS) == expected


def test_get_default_shop_capabilities_includes_purchase_true():
    caps = get_default_shop_capabilities(shop_type="regional")
    assert caps.get("purchase") is True


def test_get_default_shop_capabilities_preserves_existing_six():
    caps = get_default_shop_capabilities(shop_type="regional")
    for domain in ("orders", "products", "analytics", "finance", "services", "inventory"):
        assert caps.get(domain) is True, f"existing domain {domain} must remain True"


def test_get_supported_config_data_domains_returns_purchase():
    domains = get_supported_config_data_domains(platform="miaoshou")
    assert "purchase" in domains


def test_resolve_shop_capabilities_when_missing_purchase_in_db_row_returns_default_true():
    """店铺 capability 表只存了 orders=true；purchase 未写入时，应默认 True"""
    db_caps = {"orders": True}
    resolved = resolve_shop_capabilities(db_caps, shop_type="regional")
    assert resolved.get("purchase") is True
    assert resolved.get("orders") is True


def test_get_recommended_config_domains_includes_purchase():
    domains = get_recommended_config_domains(
        capabilities={"orders": True, "products": True, "purchase": True},
        shop_type="regional",
    )
    assert "purchase" in domains
```

- [ ] **Step 2: 跑测试确认 RED**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_purchase_data_domain_enablement_contract.py -v
```
Expected: 7 failed (默认 capability / 默认域列表未含 purchase)。

- [ ] **Step 3: 实现后端枚举扩展**

`backend/services/collection_contracts.py` 修改（line 27-34 与 line 43-54）：

```python
DEFAULT_CONFIG_DATA_DOMAINS: List[str] = [
    "orders",
    "products",
    "analytics",
    "finance",
    "services",
    "inventory",
    "purchase",
]


def get_default_shop_capabilities(shop_type: str | None) -> Dict[str, bool]:
    defaults = {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
        "purchase": True,
    }
    if str(shop_type or "").strip().lower() == "global":
        defaults["services"] = False
    return defaults
```

`backend/domains/collection/routers/shop_accounts.py` 修改（line 50-61 的 `_default_capabilities_for`）：

```python
def _default_capabilities_for(shop_type: str | None) -> dict[str, bool]:
    defaults = {
        "orders": True,
        "products": True,
        "services": True,
        "analytics": True,
        "finance": True,
        "inventory": True,
        "purchase": True,
    }
    if shop_type == "global":
        defaults["services"] = False
    return defaults
```

- [ ] **Step 4: 跑测试确认 GREEN**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_purchase_data_domain_enablement_contract.py -v
```
Expected: 7 passed。

- [ ] **Step 5: 跑相关回归测试，确认未破坏**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_collection_contracts.py backend/tests/test_shop_accounts_api.py backend/tests/test_collection_account_capability_alignment.py -v
```
Expected: 全部 passed（pre-existing 失败可接受，需记录）。

- [ ] **Step 6: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add backend/services/collection_contracts.py backend/domains/collection/routers/shop_accounts.py backend/tests/test_purchase_data_domain_enablement_contract.py
git commit -m "feat(collection): enable purchase data domain in config templates and shop capabilities"
```

---

### Task 2: 前端 SSOT 常量 + 两个面板 checkbox 与 label

**Files:**
- Modify: `frontend/src/constants/collection.js:12-19`（`DEFAULT_DOMAIN_OPTIONS`）
- Modify: `frontend/src/domains/collection/views/collection/CollectionTasks.vue:36-43`（checkbox 组）
- Modify: `frontend/src/domains/collection/views/collection/CollectionTasks.vue:1007-1013`（`getDomainLabel`）
- Modify: `frontend/src/domains/collection/views/collection/CollectionConfig.vue:1171-1174`（`getDomainLabel`）

**Interfaces:**
- Consumes: 前后端通过 `purchase` 字符串互通。
- Produces: 前端两处 checkbox 与两处 `getDomainLabel` 都覆盖 `purchase` 标签"采购"。

- [ ] **Step 1: 修改 SSOT 常量**

`frontend/src/constants/collection.js` line 12-19：

```javascript
export const DEFAULT_DOMAIN_OPTIONS = [
  { label: '订单', value: 'orders' },
  { label: '产品', value: 'products' },
  { label: '流量分析', value: 'analytics' },
  { label: '财务', value: 'finance' },
  { label: '服务', value: 'services' },
  { label: '库存', value: 'inventory' },
  { label: '采购', value: 'purchase' }
]
```

- [ ] **Step 2: 修改 CollectionTasks checkbox 组**

`frontend/src/domains/collection/views/collection/CollectionTasks.vue` line 36-43 内追加一行：

```vue
<el-checkbox label="orders">订单</el-checkbox>
<el-checkbox label="products">产品</el-checkbox>
<el-checkbox label="analytics">流量</el-checkbox>
<el-checkbox label="inventory">库存</el-checkbox>
<el-checkbox label="finance">财务</el-checkbox>
<el-checkbox label="services">服务</el-checkbox>
<el-checkbox label="purchase">采购</el-checkbox>
```

- [ ] **Step 3: 修改 CollectionTasks getDomainLabel 映射**

`frontend/src/domains/collection/views/collection/CollectionTasks.vue` line 1007-1013：

```javascript
const getDomainLabel = (domain) => {
  const labels = {
    orders: '订单', products: '产品', analytics: '流量',
    finance: '财务', services: '服务', inventory: '库存',
    purchase: '采购'
  }
  return labels[domain] || domain
}
```

- [ ] **Step 4: 修改 CollectionConfig getDomainLabel 映射**

`frontend/src/domains/collection/views/collection/CollectionConfig.vue` line 1171-1174：

```javascript
function getDomainLabel(domain) {
  const option = getAvailableDomainOptions().find((item) => item.value === domain)
  return option?.label || domain
}
```

**注**：本文件 `getDomainLabel` 实际从 SSOT `getAvailableDomainOptions` 查 label，由于 Step 1 已把 `purchase` 加进 SSOT，**本文件无需修改**。仅在 `getAvailableDomainOptions` 返回值含 `purchase` 时自动获得"采购"标签。验证此点后跳过。

- [ ] **Step 5: 视觉抽检（静态验证）**

打开 [frontend/src/domains/collection/views/collection/CollectionTasks.vue](frontend/src/domains/collection/views/collection/CollectionTasks.vue) line 36-43，确认 `采购` checkbox 出现；打开 [frontend/src/constants/collection.js](frontend/src/constants/collection.js) line 12-19，确认 SSOT 含 `purchase`；CollectionConfig 的 `getAvailableDomainOptions()` 调用（[CollectionConfig.vue:1163](frontend/src/domains/collection/views/collection/CollectionConfig.vue#L1163)）自然继承。

- [ ] **Step 6: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add frontend/src/constants/collection.js frontend/src/domains/collection/views/collection/CollectionTasks.vue
git commit -m "feat(collection-ui): expose purchase data domain in quick collect and config panels"
```

---

### Task 3: 静态验收（ruff / mypy / pytest 全量 / 前端 ESLint）

**Files:** 无（只跑命令）

- [ ] **Step 1: ruff lint（修改文件 + 新文件）**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m ruff check backend/services/collection_contracts.py backend/domains/collection/routers/shop_accounts.py backend/tests/test_purchase_data_domain_enablement_contract.py
```
Expected: 无错误。

- [ ] **Step 2: mypy（修改文件）**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m mypy backend/services/collection_contracts.py backend/domains/collection/routers/shop_accounts.py backend/tests/test_purchase_data_domain_enablement_contract.py
```
Expected: 无新增错误（pre-existing 无关错误可忽略）。

- [ ] **Step 3: pytest 全量验证（miaoshou 系列 + collection contracts）**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_purchase_data_domain_enablement_contract.py backend/tests/test_collection_contracts.py backend/tests/test_shop_accounts_api.py backend/tests/test_collection_account_capability_alignment.py backend/tests/test_miaoshou_purchase_export_contract.py backend/tests/test_miaoshou_purchase_export_v2_flow.py -v
```
Expected: 7（新）+ collection_contracts + shop_accounts + alignment + 10+8（miaoshou purchase）全部 passed，pre-existing 无关失败允许。

- [ ] **Step 4: 前端 ESLint 静态检查**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp/frontend
npx eslint src/constants/collection.js src/domains/collection/views/collection/CollectionTasks.vue 2>&1 | tail -40
```
Expected: 无错误（pre-existing warning 可接受）。

- [ ] **Step 5: 工作区状态确认**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git status --short
```
Expected: 仅显示 pre-existing product_category 改动；本任务的 3 个文件已 commit。

- [ ] **Step 6: 最终验证报告**

输出 ruff / mypy / pytest / eslint 实际结果，列出 commit 列表，标记是否通过。

---

## Self-Review

### Spec coverage 检查

| 段落 | 对应 Task |
|---|---|
| 1. 后端枚举 + capability 默认值 | Task 1 |
| 2. 前端 SSOT + checkbox + label | Task 2 |
| 3. 静态验收 | Task 3 |

### Placeholder 扫描

- ✅ 无 TBD / TODO / "implement later"
- ✅ 无 "Similar to Task N" 重复
- ✅ 每 step 含完整代码块

### Type 一致性

- `DEFAULT_CONFIG_DATA_DOMAINS` 加 `"purchase"` ↔ `DATA_DOMAIN_SUB_TYPES` 不变（purchase 无子域，与 services/orders 区分） ↔ `get_default_shop_capabilities` 加 `"purchase": True` ↔ `_default_capabilities_for` 加 `"purchase": True` ↔ 前端 SSOT `purchase: '采购'` ↔ CollectionTasks checkbox `label="purchase">采购` ↔ CollectionTasks getDomainLabel `purchase: '采购'` ↔ CollectionConfig getDomainLabel 经 `getAvailableDomainOptions()` 自动继承 ✅

### Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-13-miaoshou-purchase-frontend-enable.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - 我为每个 Task 分发独立子代理，在 Task 之间做两阶段审阅（实现审阅 + 测试验证）
2. **Inline Execution** - 在当前会话中顺序执行所有 Task

选择 **Subagent-Driven**。
