# Business Overview Empty Period Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 PostgreSQL Dashboard 的 Business Overview 模块在“空期（empty period）”时按统一契约返回 `0/null/[]`，并在 `meta` 中显式标记 `data_status/is_empty_period`。

**Architecture:** 在 `postgresql_dashboard_service.py` 的 reducer 层统一实现“空期判定 + 默认值填充（0/null/[]）”；在 `dashboard_api_postgresql.py` 的 envelope 层统一补充 `meta.data_status/is_empty_period` 与标准化 warnings。通过 pytest 契约测试固化规则。

**Tech Stack:** FastAPI, SQLAlchemy async, pytest

---

## Files (planned)

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`
  - Add: 空期判定 helper（`_is_empty_period_rows` / `*_EMPTY_DEFAULTS`）
  - Update: `reduce_business_overview_kpi_rows`
  - Update: `aggregate_comparison_source_rows` / `reduce_business_overview_comparison_rows`（按空期契约返回）
  - Update: 其它 BO 模块 reducer（若存在）按 `[]` 返回
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`
  - Update: `_wrap_business_overview_envelope` / `_build_business_overview_meta`（增加 `data_status/is_empty_period`）
  - Update: BO `bootstrap` 聚合 meta（全部空=empty，部分空=partial）
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\dashboard\test_business_overview_empty_period_contract.py`
  - Add: 空期契约测试（kpi/comparison/list modules/bootstrap）

## Task 1: Add failing contract tests (RED)

**Files:**
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\dashboard\test_business_overview_empty_period_contract.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _get(client: TestClient, path: str, *, period_key: str):
    return client.get(
        path,
        params={
            "granularity": "monthly",
            "period_key": period_key,
        },
    )


def test_bo_kpi_empty_period_returns_additive_zeros_and_ratio_nulls(client: TestClient):
    resp = _get(client, "/api/dashboard/business-overview/kpi", period_key="2099-01-01")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["meta"]["is_empty_period"] is True
    assert payload["meta"]["data_status"] == "empty_period"
    assert payload["data"]["gmv"] == 0
    assert payload["data"]["order_count"] == 0
    assert payload["data"]["visitor_count"] == 0
    assert payload["data"]["profit"] == 0
    assert payload["data"]["conversion_rate"] is None
    assert payload["data"]["avg_order_value"] is None
    assert payload["data"]["attach_rate"] is None


def test_bo_comparison_empty_period_sets_change_null(client: TestClient):
    resp = _get(client, "/api/dashboard/business-overview/comparison", period_key="2099-01-01")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["meta"]["is_empty_period"] is True
    assert payload["meta"]["data_status"] == "empty_period"
    assert payload["data"]["metrics"]["sales_amount"]["change"] is None
    assert payload["data"]["metrics"]["conversion_rate"]["today"] is None


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard/business-overview/traffic-ranking",
        "/api/dashboard/business-overview/shop-racing",
        "/api/dashboard/business-overview/operational-metrics",
    ],
)
def test_bo_list_modules_empty_period_return_empty_list(client: TestClient, path: str):
    resp = _get(client, path, period_key="2099-01-01")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["meta"]["is_empty_period"] is True
    assert payload["meta"]["data_status"] == "empty_period"
    assert payload["data"] == []
```

- [ ] **Step 2: Run tests to verify they fail (expected)**

Run: `pytest -q backend/tests/dashboard/test_business_overview_empty_period_contract.py -k empty_period -v`  
Expected: FAIL（`meta` 字段缺失，或 `data` 默认值不符合 0/null/[] 契约）

## Task 2: Implement service-layer empty period defaults (GREEN)

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`

- [ ] **Step 1: Add empty-period helpers**

```python
def _is_empty_period_rows(rows: list[dict[str, Any]], *, core_keys: tuple[str, ...]) -> bool:
    if not rows:
        return True
    for row in rows:
        for key in core_keys:
            if row.get(key) is not None:
                return False
    return True
```

- [ ] **Step 2: Update KPI reducer to return 0/null on empty period**

```python
_KPI_CORE_KEYS = ("gmv", "order_count", "visitor_count", "profit")

def reduce_business_overview_kpi_rows(...):
    if _is_empty_period_rows(rows, core_keys=_KPI_CORE_KEYS):
        return {
            "gmv": 0,
            "order_count": 0,
            "visitor_count": 0,
            "conversion_rate": None,
            "avg_order_value": None,
            "attach_rate": None,
            "labor_efficiency": 0,
            "profit": 0,
        }
    ...
```

- [ ] **Step 3: Ensure ratio/avg behavior uses “denominator==0 => null” (non-empty too)**

Rules:
- `conversion_rate`: visitors==0 => `None`
- `avg_order_value`: order_count==0 => `None`
- `attach_rate`: order_count==0 => `None`

- [ ] **Step 4: Update comparison reducers to treat empty period as additive=0, ratio=null, change=null**

Minimum acceptance:
- 空期时 `metrics.*.change` 全部 `None`
- `conversion_rate/avg_order_value/attach_rate` 的 `today` 为 `None`

- [ ] **Step 5: Run tests for GREEN**

Run: `pytest -q backend/tests/dashboard/test_business_overview_empty_period_contract.py -k empty_period -v`  
Expected: PASS

## Task 3: Implement router meta contract (GREEN)

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`

- [ ] **Step 1: Extend meta builder/wrapper**

Add to `meta`:
- `data_status` default `"ok"`
- `is_empty_period` default `False`

And ensure `warnings` is list.

- [ ] **Step 2: Set empty status based on module payload**

Strategy:
- If `data` is `[]` -> empty
- If `data` is dict and all additive core fields are `0` AND all ratio fields are `null` -> empty
  - For first cut: only enforce this heuristic for `kpi/comparison` endpoints

- [ ] **Step 3: Add standard warning on empty**

Append warning:
- `"empty_period: no rows matched for the requested period"`

- [ ] **Step 4: Run contract tests**

Run: `pytest -q backend/tests/dashboard/test_business_overview_empty_period_contract.py -k empty_period -v`  
Expected: PASS

## Task 4: Bootstrap meta aggregation (optional in this pass)

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`（bootstrap endpoint）

- [ ] **Step 1: If bootstrap exists, set meta.data_status**

Rules:
- all modules empty -> `empty_period`
- some empty -> `partial` and add warnings like `"partial: kpi is empty_period"`
- none empty -> `ok`

- [ ] **Step 2: Add/extend tests (if bootstrap endpoint is used by frontend)**

Add a test case similar to:
- call `/api/dashboard/business-overview/bootstrap?granularity=monthly&period_key=2099-01-01`
- assert `meta.data_status` is `empty_period`

## Task 5: Verification & commits

**Files:**
- Modify/Create: from tasks above

- [ ] **Step 1: Run focused tests**

Run:
- `pytest -q backend/tests/dashboard/test_business_overview_empty_period_contract.py -v`

- [ ] **Step 2: Run related regression tests**

Run:
- `pytest -q backend/tests/data_pipeline/test_postgresql_dashboard_router.py -v`

- [ ] **Step 3: Commit**

```bash
git add backend/services/postgresql_dashboard_service.py backend/routers/dashboard_api_postgresql.py backend/tests/dashboard/test_business_overview_empty_period_contract.py
git commit -m "feat(dashboard): business overview empty period contract"
```

