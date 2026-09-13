# 妙手 Miaoshou purchase / inventory 数据域采集组件录制重做

**状态**：录制 evidence 已对齐，等待用户审阅更新后的 spec 后进入实施  
**日期**：2026-09-13  
**范围**：miaoshou 平台 inventory 数据域从"半老旧实现"升级到 V2 canonical 主链路；新增 purchase（采购单）数据域采集组件，采用**异步导出 + 导出记录轮询**子流程。  
**非范围**：不动 `miaoshou/login` 与 `miaoshou/orders_export`（已在主链路并稳定运行）；不改同步层（catalog_scanner / data_sync_service / raw_data_importer）；不改 SQL 三层（semantic / mart / api_modules）；不改前后端 Dashboard。

## 1. 决策

1. **风格**：purchase 与 inventory 均采用 **"独立精细类"** —— 每个数据域一个独立的 `ExportComponent` 子类，**不创建共享基类**、**不复制 miaoshou orders 的 base + sub_domain 薄子类**模式。
   - 依据：`docs/guides/PYTHON_COMPONENT_TEMPLATE.md`（v4.21.0）权威模板只展示独立类；`docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` 当前主链路仅收录 `miaoshou/login` 与 `miaoshou/orders_export`，后者是 orders 子域拆分（shopee / tiktok / lazada）需求驱动，purchase / inventory 不存在子域拆分需求。
2. **数据域命名**：原方案称 `finance`，录制 evidence 显示妙手 ERP 没有顶级"财务"菜单，所录页面实际是"采购单"（URL `/purchase/goods`）。改名为 `purchase`，与页面语义一致。
3. **inventory 处理**：**完全重写 + archive 旧文件**。
   - 新建 `inventory_export.py`（独立类）+ `inventory_config.py`（`InventorySelectors`）+ `warehouse_filters.py`（`MiaoshouWarehouseFilters`）。
   - 把 `inventory_snapshot_export.py` 与 `warehouse_config.py` 移到 `modules/platforms/miaoshou/archive/`。
4. **purchase 处理**：**新建独立类**，导出采用"**异步导出 + 导出记录轮询**"流程（见 §3.5）。
   - 新建 `purchase_export.py`（独立类）+ `purchase_config.py`（`PurchaseSelectors`）。
   - 在 `navigation.py` 增加 `TargetPage.PURCHASE` 分支（URL `/purchase/goods`），并复用菜单路径 `采购 → 商品采购 → 采购单`。
5. **复用策略**：复用 `MiaoshouNavigation` / `stabilize_safe_notices` / `guard_overlays` / `build_standard_output_root` / `build_filename`；复用 `MiaoshouDatePicker`（purchase 12 个筛选维度含"创建日期"自定义面板，今天/昨天/近7天/近30天/近90天 快捷按钮 + 双月日历）；不复用 `MiaoshouFilters`（订单状态专用）；**新建 `MiaoshouWarehouseFilters`** 仅供 inventory 使用；purchase 用独立的"状态 Tab + 创建日期 + 字段选择对话框"内联实现。
6. **注册位置**：在 `modules/apps/collection_center/python_component_adapter.py::DATA_DOMAIN_EXPORT_MAP["miaoshou"]` 下分别新增 / 修改 inventory 与 purchase 映射。
7. **文档更新**：把 `miaoshou/inventory` 与 `miaoshou/purchase` 列入 `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` 与 `docs/guides/CANONICAL_COMPONENT_STATUS.md`。

## 2. inventory 改动清单

### 2.1 新建

| 路径 | 内容 |
|---|---|
| `modules/platforms/miaoshou/components/inventory_config.py` | `@dataclass(frozen=True) class InventorySelectors`：路径常量、按钮/菜单/对话框 selector、弹出关闭 selector、进度文本列表 |
| `modules/platforms/miaoshou/components/inventory_export.py` | `class MiaoshouInventoryExport(ExportComponent)`：`platform="miaoshou"`、`component_type="export"`、`data_domain="inventory"`；聚合 `MiaoshouNavigation` 与 `MiaoshouWarehouseFilters` |
| `modules/platforms/miaoshou/components/warehouse_filters.py` | `class MiaoshouWarehouseFilters(ComponentBase)`：处理仓库下拉多选 + 全选 |

### 2.2 修改

| 路径 | 改动 |
|---|---|
| `modules/apps/collection_center/python_component_adapter.py` | `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["inventory"]` → `"MiaoshouInventoryExport"` |
| `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` | 把 `miaoshou/inventory_export` 加入"当前活跃组件" |
| `docs/guides/CANONICAL_COMPONENT_STATUS.md` | miaoshou 表格新增 `miaoshou/inventory_export`，标记 `可测试` |

### 2.3 archive

| 路径 | 动作 |
|---|---|
| `modules/platforms/miaoshou/components/inventory_snapshot_export.py` | 移到 `archive/inventory_snapshot_export.py` |
| `modules/platforms/miaoshou/components/warehouse_config.py` | 移到 `archive/warehouse_config.py` |

archive 前必须满足 `ACTIVE_COLLECTION_COMPONENTS.md` 中"Archive 前置条件"：不在 active 清单；没有 stable `ComponentVersion.file_path` 指向；register / loader guard 已生效；新 canonical 不再 import 旧文件。

### 2.4 测试

| 路径 | 用途 |
|---|---|
| `backend/tests/test_miaoshou_inventory_export_contract.py` | contract 测试：元数据 / `__init__` 签名 / selector 路径常量 / login 不重打开 / navigation 工厂 |
| `backend/tests/test_miaoshou_inventory_export_v2_flow.py` | v2_flow 测试：mock page 验证 navigation → filters → search → dialog → download → 落盘步骤序列与 `ExportResult` 形状 |

## 3. purchase 新建清单

### 3.1 录制 evidence 摘要

用户在妙手 ERP `/purchase/goods` 页面（"采购单"模块）完成完整录制，evidence 位于 `output/playwright/work/miaoshou/finance-inventory-recording/`：

- 导航：菜单路径 `采购 → 商品采购 → 采购单`，URL `https://erp.91miaoshou.com/purchase/goods`，标题 `妙手-采购单`。
- 状态 Tab：`全部(375) / 草稿箱(1) / 待审核(4) / 待收货(14) / 已完成(348) / 已取消/退货(8)`。
- 筛选维度（12 个）：采购单号、货源单号、商品 SKU、中文名称、收货仓库、供货商、有无物流单号、备注、采购员、**创建日期**、采购单类型、关联包裹号。
- **创建日期控件**：自定义面板，含快捷按钮 `今天/昨天/近7天/近30天/近90天` + 自定义起止时间 + 双月日历视图 + 底部 `清空/确定`。
- 操作按钮区：`搜索 / 重置 / 创建采购单 / 获取1688订单 / 批量打印 / 采购单设置 / 更新1688信息 / 自动获取1688订单 / 导入/导出`。
- **"导入/导出"下拉菜单**：`导入采购单 / 导出选中 / 导出全部搜索结果 / 导出记录`。
- **"导出全部搜索结果"字段选择对话框**：分三组可勾选字段：
  - 采购单信息（17 项）：采购单号、状态、创建时间、到货数量、采购数量、货款、应付、运费、其他、已付、供货商、采购员、付款申请、付款状态、费用均摊方式、预计到货时间、采购备注。
  - 商品信息（8 项）：商品 SKU、第三方 SKU、商品名称、商品图片、规格、单价、采购数量、采购价、小计。
  - 关联运单信息（6 项）：快递号、快递公司、下单平台、货源单号、买家账号、卖家账号。
  - 底部按钮：`取消 / 导出`。
- **异步导出行为**：点 `导出` 后弹出 `正在导出` 进度对话框（百分比进度 + "关闭后系统后台继续，您可在 **采购单 > 导出 > 导出记录** 中查看结果"提示）。**不是直接触发文件下载**。

### 3.2 新建

| 路径 | 内容 |
|---|---|
| `modules/platforms/miaoshou/components/purchase_config.py` | `@dataclass(frozen=True) class PurchaseSelectors`：导航 URL、菜单路径、状态 Tab selector、12 字段筛选 selector、"导入/导出"按钮 selector、下拉菜单 4 项 selector、字段选择对话框分组 + 复选框 selector、异步进度弹窗 selector、导出记录页 selector |
| `modules/platforms/miaoshou/components/purchase_export.py` | `class MiaoshouPurchaseExport(ExportComponent)`：`platform="miaoshou"`、`component_type="export"`、`data_domain="purchase"`；聚合 `MiaoshouNavigation` + `MiaoshouDatePicker`（复用创建日期）+ 内联 purchase 特定逻辑（状态 Tab + 字段对话框） |

### 3.3 修改

| 路径 | 改动 |
|---|---|
| `modules/platforms/miaoshou/components/navigation.py` | 增加 `if target is TargetPage.PURCHASE:` 分支，路径 `采购 → 商品采购 → 采购单`，目标 URL `https://erp.91miaoshou.com/purchase/goods` |
| `modules/apps/collection_center/python_component_adapter.py` | `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["purchase"] = "MiaoshouPurchaseExport"` |
| `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` | 把 `miaoshou/purchase_export` 加入"当前活跃组件" |
| `docs/guides/CANONICAL_COMPONENT_STATUS.md` | miaoshou 表格新增 `miaoshou/purchase_export`，标记 `可测试` |

### 3.4 测试

| 路径 | 用途 |
|---|---|
| `backend/tests/test_miaoshou_purchase_export_contract.py` | contract 测试：元数据 / `__init__` 签名 / selector 路径常量 / login 不重打开 / navigation 工厂 |
| `backend/tests/test_miaoshou_purchase_export_v2_flow.py` | v2_flow 测试：mock page 验证完整异步链路：navigation → filters(含日期) → search → 字段对话框 → 关闭进度弹窗 → 导航导出记录 → 轮询可下载 → download → 落盘 |

### 3.5 异步导出 + 导出记录轮询流程

妙手 ERP 采购单导出是**异步后台处理**，不能像 inventory 那样直接 `page.expect_download()`。子流程：

1. **触发导出**（在 `/purchase/goods`）：
   - 点击"导入/导出"按钮 → 弹出下拉菜单。
   - 点击"导出全部搜索结果"菜单项 → 弹出"选择导出字段"对话框。
   - 在对话框中：勾选所有三组字段（或按参数选择子集，默认全选）。
   - 点击"导出"按钮 → 弹出"正在导出"进度对话框（提示后台处理）。
2. **关闭进度弹窗**：点对话框右上角"关闭"按钮（弹窗可关闭，不影响后台任务）。
3. **导航到"导出记录"页**：通过菜单 `采购 → 商品采购 → 采购单 → 导出记录`，或直接 URL 跳转（如 `/purchase/goods?tab=export_record` 或独立路由，需录制 evidence 校正）。
4. **轮询导出记录**：
   - 在导出记录列表中找到**最新一条**记录（按"创建时间"或位置排序第一行）。
   - 轮询该行状态，直到变为"可下载 / 导出成功 / 下载链接可见"（最多等待 `EXPORT_RECORD_TIMEOUT`，默认 300s，间隔 5s）。
   - 状态判定 selector 由录制 evidence 校正。
5. **下载文件**：点击该行的"下载"按钮 / 图标，使用 `page.expect_download()` 接收文件。
6. **落盘**：`build_standard_output_root` + `build_filename` → `download.save_as` → 返回 `ExportResult`。

子流程封装为 `purchase_export.py` 的私有方法 `_trigger_async_export_and_download(page, ctx, selectors) -> ExportResult`，避免污染主 `run()`。

错误处理：
- 轮询超时 → 返回 `ExportResult(success=False, message="导出记录轮询超时", file_path=None)`，附 `state="timeout"`。
- 找不到最新记录 → 返回 `ExportResult(success=False, message="导出记录列表为空", file_path=None)`。
- 下载被取消 / 弹窗未关闭 → 返回 `ExportResult(success=False, message=str(e), file_path=None)`。

## 4. 公共组件复用矩阵

| 组件 | inventory | purchase |
|---|---|---|
| `MiaoshouNavigation` | ✅ 复用（`TargetPage.WAREHOUSE_CHECKLIST` 已存在） | ✅ 复用（需新增 `TargetPage.PURCHASE` 分支） |
| `MiaoshouDatePicker` | ❌ 不复用（snapshot 无日期） | ✅ **复用**（创建日期筛选含自定义日期面板） |
| `MiaoshouFilters` | ❌ 不复用（订单状态专用） | ❌ 不复用（12 字段筛选独立） |
| `MiaoshouWarehouseFilters`（新建） | ✅ 复用 | ❌ |
| `stabilize_safe_notices` | ✅ 复用 | ✅ 复用 |
| `guard_overlays`（仅 `is_test_mode=True`） | ✅ 复用 | ✅ 复用 |
| `build_standard_output_root` + `build_filename` | ✅ 复用（`data_type="inventory"`, `granularity="snapshot"`） | ✅ 复用（`data_type="purchase"`, `granularity="manual"`） |

## 5. 数据流（沿用现有规范）

```
inventory 同步下载：
MiaoshouInventoryExport.run(page)
  → navigation（TargetPage.WAREHOUSE_CHECKLIST）
  → stabilize_safe_notices + _ensure_popup_closed
  → warehouse filters（MiaoshouWarehouseFilters）
  → search → wait_search_results_ready
  → 导出按钮 → async with page.expect_download(timeout=180s)
  → build_standard_output_root + build_filename → download.save_as → 重命名
  → ExportResult(success, message, file_path)

purchase 异步轮询：
MiaoshouPurchaseExport.run(page)
  → navigation（TargetPage.PURCHASE）
  → stabilize_safe_notices + _ensure_popup_closed
  → 状态 Tab 切换（默认"全部"）
  → 日期筛选（MiaoshouDatePicker.近30天 或 自定义）
  → search → wait_search_results_ready
  → _trigger_async_export_and_download(page, ctx, selectors)  # 异步子流程，见 §3.5
  → ExportResult(success, message, file_path)
```

入库链路不变：`catalog_scanner → data_sync_service → raw_data_importer → b_class.fact_miaoshou_inventory_snapshot / b_class.fact_miaoshou_purchase`。

## 6. 错误处理

- `try/except` 包裹整个 `run()`，返回 `ExportResult(success=False, message=str(e), file_path=None)`。
- 弹窗处理走 `_ensure_popup_closed` 统一轮询，**不再用 `page.keyboard.press("Escape")` 散落关弹窗**。
- 异步进度弹窗关闭按钮单独处理（不依赖 `_ensure_popup_closed`，因为它有自己的关闭按钮 selector）。
- 重试由执行器层 `modules/apps/collection_center/retry_strategy.py` 控制，组件内部不自动重试。
- 增量由 `CollectionSyncPoint(platform, account_id, data_domain)` 与上游 `time_selection` 注入控制，组件不感知增量。

## 7. 测试策略

每个数据域两个测试，遵循现有 `backend/tests/test_miaoshou_orders_export_*` 模式：

- **contract 测试**：静态读源文件 + 反射检查元数据（`platform` / `component_type` / `data_domain`）、`__init__(ctx, selectors=None)` 签名、selector 路径常量、`MiaoshouNavigation` 处理对应 `TargetPage` 分支、login 不重打开。
- **v2_flow 测试**：mock page 注入，验证步骤调用序列与 `ExportResult` 形状（`success` / `message` / `file_path`）。purchase 测试额外 mock 异步轮询的多次 page 状态变化。

## 8. 落地步骤

### Phase 1：用户录制（已完成 ✓）

1. ✓ 用户加载 `pwcli_helpers.ps1`，运行 `Open-PwcliMiaoshou -AccountId <account_id>`。
2. ✓ 用户手动操作妙手 purchase（采购单）与 inventory 页面，每步 `pwsnap` / `pwnote` / `pwshot` 抓 evidence。
3. ✓ evidence 已落入 `output/playwright/work/miaoshou/finance-inventory-recording/`。

### Phase 2：inventory 重写

1. 读录制 evidence 与下载样本，确认 selector 与流程。
2. 创建 `inventory_config.py` / `inventory_export.py` / `warehouse_filters.py`。
3. 重写 `backend/tests/test_miaoshou_inventory_export_contract.py` + `test_miaoshou_inventory_export_v2_flow.py`。
4. 更新 `python_component_adapter.py` 的 `DATA_DOMAIN_EXPORT_MAP`。
5. archive 旧文件（`inventory_snapshot_export.py` / `warehouse_config.py`）。
6. 更新 `ACTIVE_COLLECTION_COMPONENTS.md` + `CANONICAL_COMPONENT_STATUS.md`。
7. 跑 `ruff` / `mypy` / `pytest backend/tests/test_miaoshou_inventory_*` 验证。

### Phase 3：purchase 新建

1. 读录制 evidence，确认导航 URL、12 字段筛选 selector、字段对话框结构、异步进度弹窗关闭按钮 selector、导出记录页 URL。
2. 创建 `purchase_config.py` / `purchase_export.py`。
3. 修改 `navigation.py` 增加 `TargetPage.PURCHASE` 分支。
4. 更新 `DATA_DOMAIN_EXPORT_MAP`。
5. 创建 `backend/tests/test_miaoshou_purchase_export_contract.py` + `test_miaoshou_purchase_export_v2_flow.py`。
6. 更新 `ACTIVE_COLLECTION_COMPONENTS.md` + `CANONICAL_COMPONENT_STATUS.md`。
7. 跑 `ruff` / `mypy` / `pytest backend/tests/test_miaoshou_purchase_*` 验证。

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `archive/export.py` 中 `MiaoshouExport` 被 `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["products"/"warehouse"/"analytics"]` 引用 | Phase 2 实施时检查所有引用，必要时清理或保留 alias；本设计不强行重构 products / warehouse / analytics |
| 旧 `inventory_snapshot_export.py` / `warehouse_config.py` 有 `ComponentVersion` stable 引用 | archive 前在 DB 中查证，无 stable 引用才移动 |
| `MiaoshouNavigation` 的 `TargetPage.PURCHASE` 分支路径未经验证 | Phase 3 录制 evidence 已提供菜单路径 `采购 → 商品采购 → 采购单` 与 URL `/purchase/goods`，直接写入 |
| 旧测试仍引用 `MiaoshouInventorySnapshotExport` 类名 | Phase 2 同步重写测试 |
| purchase 数据域是首次引入，调度层 / 同步层若无相应配置 | 检查 `CollectionConfigTemplate.data_domains` 是否支持 `"purchase"`；若无，扩展模板 |
| 异步导出轮询超时（妙手后台处理慢） | `EXPORT_RECORD_TIMEOUT` 默认 300s，可由执行器层传入覆盖；超时返回明确错误，不静默失败 |
| "导出记录"页面找不到最新记录（多账号并发 / 列表为空） | 轮询前先验证列表非空；找不到时返回明确错误 |
| 字段选择对话框的全选操作失败 | 默认策略：直接点每组第一个复选框（"全选"勾选框），若失败则按字段名逐个勾选（fallback）；先按"全选"实现 |

## 10. 验收标准

- inventory：新 `MiaoshouInventoryExport` 通过 `test_miaoshou_inventory_export_contract.py` 与 `test_miaoshou_inventory_export_v2_flow.py`；旧 `inventory_snapshot_export.py` 与 `warehouse_config.py` 进入 archive 且无主链路 import；`DATA_DOMAIN_EXPORT_MAP` 注册到新类；`ACTIVE_COLLECTION_COMPONENTS.md` 与 `CANONICAL_COMPONENT_STATUS.md` 更新。
- purchase：新 `MiaoshouPurchaseExport` 通过 `test_miaoshou_purchase_export_contract.py` 与 `test_miaoshou_purchase_export_v2_flow.py`（含异步轮询子流程 mock）；`navigation.py` 含 `TargetPage.PURCHASE` 分支；`DATA_DOMAIN_EXPORT_MAP` 注册到新类；下载样本落入 `build_standard_output_root` 路径并被 `catalog_scanner` 正确识别。
- 两者都不创建第二个共享基类；不绕过 `build_standard_output_root` / `build_filename`；不在 `collectors/` 根目录新增；不修改 `raw_data_importer`；不用 emoji；不用 `datetime.utcnow()`。