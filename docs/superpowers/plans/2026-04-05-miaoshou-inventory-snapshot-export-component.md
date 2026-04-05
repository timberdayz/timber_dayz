# Miaoshou Inventory Snapshot Export Component Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a canonical Miaoshou inventory snapshot export component that reuses the existing automatic login flow, navigates from the logged-in homepage to `warehouse/checklist`, applies the required full-selection filters, exports all fields, and waits for the real download to land.

**Architecture:** Keep login responsibility in `modules/platforms/miaoshou/components/login.py`; do not let the inventory exporter open the login page or decide login success. Extend the existing navigation component to support `TargetPage.WAREHOUSE_CHECKLIST`, keep warehouse-page selectors in `warehouse_config.py`, and implement inventory export as its own export component with explicit `ensure_*` / `wait_*` detection logic for the two critical full-select filters and the export progress dialog.

**Tech Stack:** Python 3.13, Playwright async API, pytest, repository V2 collection components, Miaoshou canonical component adapter

---

## File Structure

### Component Runtime

- Modify: `modules/platforms/miaoshou/components/warehouse_config.py`
  - Keep this file as the SSOT for warehouse checklist URL, toolbar selectors, export dialog selectors, progress texts, and output directory semantics.
- Modify: `modules/platforms/miaoshou/components/navigation.py`
  - Extend the existing navigation component to handle `TargetPage.WAREHOUSE_CHECKLIST` after login completes on `/welcome` or `/dashboard`.
- Create: `modules/platforms/miaoshou/components/inventory_snapshot_export.py`
  - Canonical inventory export component. It should own the warehouse checklist export flow only, not login.

### Tests

- Create: `backend/tests/test_miaoshou_inventory_export_contract.py`
  - Contract tests for selectors, data-domain/granularity semantics, output path choices, and login/navigation boundaries.
- Create: `backend/tests/test_miaoshou_inventory_export_v2_flow.py`
  - Source-order and flow-shape tests for warehouse navigation, first filter full-select, search, export dialog full-select, export click, waiting, and download-finalization.
- Modify: `backend/tests/test_miaoshou_supporting_components_contract.py`
  - Include the inventory export component in the supporting-component contract.
- Modify: `backend/tests/test_canonical_miaoshou_combo_paths.py`
  - Add a login+inventory-export shared-context check so the adapter path stays aligned with the existing login-first architecture.

### Naming Decisions Locked In

- Canonical export file name: `modules/platforms/miaoshou/components/inventory_snapshot_export.py`
- Canonical class name: `MiaoshouInventorySnapshotExport`
- `data_domain`: `inventory`
- Export granularity/output semantics: `snapshot`
- Warehouse page path stays `"/warehouse/checklist"` but is reached only through post-login navigation, never through the login component entry URL.

---

### Task 1: Lock Config And Navigation Boundaries

**Files:**
- Create: `backend/tests/test_miaoshou_inventory_export_contract.py`
- Modify: `modules/platforms/miaoshou/components/warehouse_config.py`
- Modify: `modules/platforms/miaoshou/components/navigation.py`

- [ ] **Step 1: Write the failing contract test for warehouse config and login boundary**

```python
from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.login import MiaoshouLogin
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors


def _ctx():
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop", "login_url": "https://erp.91miaoshou.com/login"},
        logger=None,
        config={},
    )


def test_warehouse_config_uses_inventory_snapshot_semantics():
    selectors = WarehouseSelectors()

    assert selectors.checklist_path == "/warehouse/checklist"
    assert selectors.data_type_dir == "inventory"
    assert "正在导出" in selectors.progress_texts
    assert "商品信息" in selectors.group_titles
    assert "其他信息" in selectors.group_titles


def test_login_component_keeps_login_url_as_only_entrypoint():
    source = MiaoshouLogin.run.__code__.co_filename
    text = open(source, encoding="utf-8").read()

    assert "account.get(\"login_url\")" in text
    assert "/warehouse/checklist" not in text


def test_navigation_component_supports_warehouse_checklist_target():
    nav = MiaoshouNavigation(_ctx())

    assert hasattr(nav, "_warehouse_checklist_url")
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run: `pytest backend/tests/test_miaoshou_inventory_export_contract.py -v`

Expected: FAIL because the config still uses `warehouse` output semantics and navigation does not expose warehouse checklist handling yet.

- [ ] **Step 3: Align warehouse config with inventory snapshot semantics**

Update `modules/platforms/miaoshou/components/warehouse_config.py` so it includes:

```python
WAREHOUSE_CHECKLIST_PATH: Final[str] = "/warehouse/checklist"
DATA_TYPE_DIR: Final[str] = "inventory"
PROGRESS_TEXTS: Final[List[str]] = [
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
    "导出成功",
]
GROUP_TITLES: Final[List[str]] = ["商品信息", "其他信息"]
```

Keep the file as selector/config SSOT; do not move login knowledge here.

- [ ] **Step 4: Extend navigation to support logged-in warehouse checklist navigation**

Update `modules/platforms/miaoshou/components/navigation.py` so it keeps `TargetPage.ORDERS` behavior and adds:

```python
    def _warehouse_checklist_url(self) -> str:
        return f"{self.sel.base_url}{self.sel.checklist_path}"
```

and in `run()`:

```python
        if target is TargetPage.WAREHOUSE_CHECKLIST:
            await page.goto(
                self._warehouse_checklist_url(),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("仓库清单", exact=False).first.wait_for(state="visible", timeout=15000)
            return NavigationResult(success=True, message="ok", url=str(getattr(page, "url", "") or ""))
```

Also switch the navigation constructor away from `OrdersSelectors` and let it accept both selectors cleanly, for example by defaulting to `WarehouseSelectors` when no orders-specific selector is passed.

- [ ] **Step 5: Re-run the contract test and verify it passes**

Run: `pytest backend/tests/test_miaoshou_inventory_export_contract.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_miaoshou_inventory_export_contract.py modules/platforms/miaoshou/components/warehouse_config.py modules/platforms/miaoshou/components/navigation.py
git commit -m "feat(miaoshou): add warehouse checklist navigation boundary"
```

---

### Task 2: Add The Inventory Snapshot Export Contract

**Files:**
- Modify: `backend/tests/test_miaoshou_inventory_export_contract.py`
- Create: `modules/platforms/miaoshou/components/inventory_snapshot_export.py`

- [ ] **Step 1: Add a failing contract test for the new export component**

Append to `backend/tests/test_miaoshou_inventory_export_contract.py`:

```python
from pathlib import Path

from modules.platforms.miaoshou.components.inventory_snapshot_export import MiaoshouInventorySnapshotExport


def test_inventory_snapshot_export_component_declares_inventory_domain():
    assert MiaoshouInventorySnapshotExport.platform == "miaoshou"
    assert MiaoshouInventorySnapshotExport.component_type == "export"
    assert MiaoshouInventorySnapshotExport.data_domain == "inventory"


def test_inventory_snapshot_export_source_reuses_navigation_without_opening_login():
    source = Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.WAREHOUSE_CHECKLIST" in source
    assert "page.goto(login_url" not in source
    assert "/warehouse/checklist" not in source or "_warehouse_checklist_url" not in source
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest backend/tests/test_miaoshou_inventory_export_contract.py -v`

Expected: FAIL because `inventory_snapshot_export.py` does not exist yet.

- [ ] **Step 3: Create the exporter skeleton**

Create `modules/platforms/miaoshou/components/inventory_snapshot_export.py` with the canonical structure:

```python
from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportMode, ExportResult
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors


class MiaoshouInventorySnapshotExport(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "inventory"

    def __init__(self, ctx: ExecutionContext, selectors: WarehouseSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or WarehouseSelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        raise NotImplementedError
```

- [ ] **Step 4: Re-run the contract test and verify it passes**

Run: `pytest backend/tests/test_miaoshou_inventory_export_contract.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_miaoshou_inventory_export_contract.py modules/platforms/miaoshou/components/inventory_snapshot_export.py
git commit -m "feat(miaoshou): add inventory snapshot exporter skeleton"
```

---

### Task 3: Implement The Warehouse Checklist Export Flow With TDD

**Files:**
- Create: `backend/tests/test_miaoshou_inventory_export_v2_flow.py`
- Modify: `modules/platforms/miaoshou/components/inventory_snapshot_export.py`
- Modify: `modules/platforms/miaoshou/components/warehouse_config.py`

- [ ] **Step 1: Write failing source-order tests for the inventory export flow**

Create `backend/tests/test_miaoshou_inventory_export_v2_flow.py`:

```python
from pathlib import Path


SOURCE_PATH = Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_inventory_export_navigates_to_warehouse_after_login():
    source = _source()

    assert "await self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)" in source
    assert "page.goto(login_url" not in source


def test_inventory_export_applies_scope_filter_before_search():
    source = _source()

    ensure_scope = source.index("await self._ensure_scope_filter_all_selected(page)")
    click_search = source.index("await self._click_search(page)")

    assert ensure_scope < click_search


def test_inventory_export_opens_export_dialog_and_selects_all_groups_before_export():
    source = _source()

    open_dialog = source.index("await self._open_export_dialog(page)")
    ensure_fields = source.index("await self._ensure_export_fields_all_selected(page)")
    trigger_export = source.index("await self._trigger_export(page)")

    assert open_dialog < ensure_fields < trigger_export


def test_inventory_export_treats_progress_as_intermediate_and_download_as_final_signal():
    source = _source()

    assert "await self._wait_export_progress_ready(page)" in source
    assert "async with page.expect_download(" in source
    assert "if not tmp_path.exists() or tmp_path.stat().st_size <= 0" in source
```

- [ ] **Step 2: Run the flow test and verify it fails**

Run: `pytest backend/tests/test_miaoshou_inventory_export_v2_flow.py -v`

Expected: FAIL because the inventory exporter skeleton does not implement the flow yet.

- [ ] **Step 3: Implement the minimal warehouse checklist export flow**

Implement focused helpers in `modules/platforms/miaoshou/components/inventory_snapshot_export.py`:

```python
    async def _ensure_scope_filter_all_selected(self, page: Any) -> None: ...
    async def _click_search(self, page: Any) -> None: ...
    async def _wait_search_results_ready(self, page: Any) -> None: ...
    async def _open_export_dialog(self, page: Any) -> None: ...
    async def _ensure_export_fields_all_selected(self, page: Any) -> None: ...
    async def _trigger_export(self, page: Any) -> None: ...
    async def _wait_export_progress_ready(self, page: Any) -> None: ...
    async def _wait_download_complete(self, page: Any, download: Any) -> Path: ...
```

Required runtime behavior:

- use `self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)`
- scope filter means the warehouse-range multi-select is in a full-selected state before search
- export dialog means both `商品信息` and `其他信息` group-level `全选` are on
- progress dialog `正在导出` is treated as an intermediate signal only
- actual file existence and non-zero size remain the final success signal
- output path uses:

```python
build_standard_output_root(self.ctx, data_type="inventory", granularity="snapshot")
```

- [ ] **Step 4: Run the flow test and verify it passes**

Run: `pytest backend/tests/test_miaoshou_inventory_export_v2_flow.py -v`

Expected: PASS

- [ ] **Step 5: Run the contract test again to verify no boundary regression**

Run: `pytest backend/tests/test_miaoshou_inventory_export_contract.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_inventory_export_contract.py modules/platforms/miaoshou/components/inventory_snapshot_export.py modules/platforms/miaoshou/components/warehouse_config.py
git commit -m "feat(miaoshou): implement inventory snapshot export flow"
```

---

### Task 4: Wire Supporting Contracts And Adapter Expectations

**Files:**
- Modify: `backend/tests/test_miaoshou_supporting_components_contract.py`
- Modify: `backend/tests/test_canonical_miaoshou_combo_paths.py`

- [ ] **Step 1: Write the failing supporting-component assertions**

Update `backend/tests/test_miaoshou_supporting_components_contract.py`:

```python
def test_miaoshou_supporting_component_files_exist():
    assert Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py").exists()


def test_miaoshou_inventory_export_reuses_supporting_components():
    source = Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.WAREHOUSE_CHECKLIST" in source
```

- [ ] **Step 2: Add a failing adapter shared-context test**

Append to `backend/tests/test_canonical_miaoshou_combo_paths.py`:

```python
class _FakeInventoryExportResult:
    def __init__(self):
        self.success = True
        self.message = "inventory exported"
        self.file_path = "downloads/miaoshou/acc/shop/inventory/snapshot/file.xlsx"


class _FakeInventoryExportComponent:
    def __init__(self, ctx):
        self.ctx = ctx

    async def run(self, page):
        assert self.ctx.config["session_ready"] is True
        assert self.ctx.config["data_domain"] == "inventory"
        return _FakeInventoryExportResult()


@pytest.mark.asyncio
async def test_miaoshou_login_inventory_export_combo_uses_shared_context():
    adapter = create_adapter(
        platform="miaoshou",
        account={"username": "u", "password": "p"},
        config={"data_domain": "inventory"},
        override_login_class=_FakeLoginComponent,
        override_export_class=_FakeInventoryExportComponent,
    )

    login_result = await adapter.login(page=object())
    export_result = await adapter.export(page=object(), data_domain="inventory")

    assert login_result.success is True
    assert export_result.success is True
    assert export_result.file_path.endswith(".xlsx")
```

- [ ] **Step 3: Run the focused tests and verify they fail if wiring is incomplete**

Run: `pytest backend/tests/test_miaoshou_supporting_components_contract.py backend/tests/test_canonical_miaoshou_combo_paths.py -v`

Expected: FAIL until the new inventory exporter is referenced consistently.

- [ ] **Step 4: Make the minimum changes required to keep the contracts consistent**

If needed, update imports/exports or adapter lookup wiring so `data_domain="inventory"` resolves cleanly to the new exporter without changing login semantics.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run: `pytest backend/tests/test_miaoshou_supporting_components_contract.py backend/tests/test_canonical_miaoshou_combo_paths.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_miaoshou_supporting_components_contract.py backend/tests/test_canonical_miaoshou_combo_paths.py
git commit -m "test(miaoshou): wire inventory export supporting contracts"
```

---

### Task 5: Final Verification

**Files:**
- No new files; verify the implementation as a whole

- [ ] **Step 1: Run the full focused verification suite**

Run:

```bash
pytest \
  backend/tests/test_miaoshou_inventory_export_contract.py \
  backend/tests/test_miaoshou_inventory_export_v2_flow.py \
  backend/tests/test_miaoshou_supporting_components_contract.py \
  backend/tests/test_canonical_miaoshou_combo_paths.py \
  backend/tests/test_miaoshou_login_component.py \
  -v
```

Expected: PASS

- [ ] **Step 2: Verify no login-boundary regression in source**

Run:

```bash
python - <<'PY'
from pathlib import Path
login_text = Path("modules/platforms/miaoshou/components/login.py").read_text(encoding="utf-8")
export_text = Path("modules/platforms/miaoshou/components/inventory_snapshot_export.py").read_text(encoding="utf-8")
assert "/warehouse/checklist" not in login_text
assert "page.goto(login_url" not in export_text
print("boundary-ok")
PY
```

Expected: `boundary-ok`

- [ ] **Step 3: Commit the verification-safe final state**

```bash
git add modules/platforms/miaoshou/components/navigation.py modules/platforms/miaoshou/components/warehouse_config.py modules/platforms/miaoshou/components/inventory_snapshot_export.py backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_supporting_components_contract.py backend/tests/test_canonical_miaoshou_combo_paths.py
git commit -m "feat(miaoshou): add inventory snapshot export component"
```

