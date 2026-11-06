# 商品中心优化实施方案

> 状态：**待评审** —— 阶段 0 已获批准，可立即开工
> 日期：2026-11-06
> 上游设计稿：`docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md`（**术语与口径的唯一权威**，本方案不重复定义，只负责"怎么改"）
> 范围：`frontend/src/domains/business/views/ProductCenter.vue`、`frontend/src/api/productCenter.js`、`backend/domains/business/routers/product_center.py`、`backend/schemas/product_center.py`、`backend/services/{product_profit_service,product_finance_service,product_pricing_service}.py`、`modules/core/db/schema_parts/{dimensions,business}.py`、`current_migrations/versions/`、`scripts/sync_product_center_to_cloud.py`
> 关联：`2026-10-20-sku-pricing-guardrails-design.md`（最低售价与定价纪律）、`docs/team-skills/sea-metrics-language/`（指标口径治理）

---

## 0. 执行摘要

**一句话**：商品中心从「只管价格下限」升级为「价格下限 + 广告投放边界」，分 6 个阶段落地，其中**阶段 0 零业务语义变更、可以独立上线**。

| 阶段 | 内容 | 产出 | 依赖 | 风险 | 可独立上线 |
|---|---|---|---|---|---|
| **0** | 稳定性修复 | 8 个缺陷修复（静默丢数据、崩溃、软删不可逆、同步缺表） | 无 | 低 | ✅ |
| **1** | ROI 只读层 | 保本ROI / 建议ROI / 广告前贡献毛利率 三列 | 0 | 低 | ✅（但**必须在 0 之后**） |
| **2** | ROI 输入与判定 | 目标ROI / 平台报告ROI 两列 + 三色判定 | 1 | 低 | ✅ |
| **3** | 广告分成率降级 + 字段瘦身 | 手填口收敛为一个；删 3 列、折叠 2 列 | 2 | 中 | ✅（保留手填入口即可回退） |
| **4** | 基准售价工具 | 来源枚举 + 确认日期 + 即时影响预览 + 偏差校验 | 0 | 低 | ✅ |
| **5** | 指标口径登记 | `sea-metrics-language` 登记 | 1 | 低 | ✅（纯文档） |

**三条铁律**：

1. **阶段 1 之前必须先修 B1/B2/B3。** 否则新列上线时运营改字段照样丢数据（`saveSpuRows`/`saveSkuRows` 只提交 dirtyRows）。
2. **阶段 3 不能一步到位。** 直接取消广告费率手填会让存量 SKU（无目标ROI）广告成本变 None → 利润空白，比现在更糟。必须经过阶段 1–2 的过渡期。
3. **新增列全部可空。** 任何阶段都不允许出现"运营不填新东西就用不了旧功能"。

**范围外（明确不做）**：销量预测、价格优化建议、历史利润版本重算、`other_cost_rate` 黑桶拆明细、飞书投影逻辑变更、仓储费账单采集。

---

## 1. 实施总览

### 1.1 依赖图

```
                  ┌─────────────────────────────────────────┐
                  │  阶段 0  稳定性修复（纯代码，不动语义）    │
                  │  B1 B2 B3 B4 B5 B6 C2 C5 C6              │
                  └────────────┬────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                                 │
    ┌─────────▼──────────┐          ┌─────────▼──────────┐
    │ 阶段 1  ROI 只读层  │          │ 阶段 4  基准售价工具│
    │ +3列 +3个迁移列     │          │ 规则与工具，不碰数据 │
    └─────────┬──────────┘          └────────────────────┘
              │
    ┌─────────▼──────────┐
    │ 阶段 2  ROI 输入判定 │
    │ +2手填列 + 三色判定  │
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │ 阶段 3  广告分成率降级│
    │ 手填口收敛 + 列瘦身  │
    └────────────────────┘

    ┌─────────────────────────────────────────┐
    │ 阶段 5  指标口径登记（阶段 1 之后即可做）  │
    └─────────────────────────────────────────┘
```

**可并行**：阶段 4 与阶段 1/2/3 完全无交集（阶段 4 动的是 SKU 资料 tab 与基准售价，阶段 1–3 动的是利润测算 tab），可由不同人同时做。

### 1.2 标准命令

```powershell
# 迁移（必须用 alembic-current.ini；alembic.ini 是只读历史链）
alembic -c alembic-current.ini upgrade heads
alembic -c alembic-current.ini downgrade -1
alembic -c alembic-current.ini upgrade heads     # 三步可重复

# 后端测试（契约）
python -m pytest -q backend/tests -m "not slow and not requires_browser" --ignore=backend/tests/data_pipeline --ignore=backend/tests/archive

# 单文件快跑
python -m pytest -q backend/tests/test_product_center_schema_contract.py
python -m pytest -q backend/tests/test_platform_sku_profit_workbench.py

# 前端测试
node --test frontend/tests/productCenterUi.test.mjs

# 质量门禁
python scripts/run_lint.py
python scripts/run_typecheck.py
```

> 迁移目录是 `current_migrations/versions/`（44 个文件，head = `current_schema_20261111_add_refresh_queue_domain_and_retry`），**不是** `migrations/versions/`。`alembic-current.ini` 的 `script_location = current_migrations`。

### 1.3 迁移文件写法（沿用仓库既有范式）

参照 `current_migrations/versions/20261109_add_commission_calculation_audit.py`：

```python
revision = "current_schema_20261112_<slug>"
down_revision = "current_schema_20261111_add_refresh_queue_domain_and_retry"
branch_labels = None
depends_on = None

def _columns(connection, table_name: str, schema_name: str) -> set[str]:
    """information_schema 查询，返回已有列名集合"""
```

- `upgrade()` / `downgrade()` **都要写**，且都带存在性守卫
- 新增列用 `op.add_column(..., schema=SCHEMA)`
- 删列用 `op.drop_column(TABLE, column, schema=SCHEMA)`，`downgrade()` 里也要先判存在

---

## 2. 阶段 0 · 稳定性修复

**目标**：修掉 8 个已核实缺陷。**不动任何业务语义** —— 成本线、纪律线、最低售价、利润的公式一个字不改。

### 2.0 验收总表

| # | 缺陷 | 类型 | 文件 | 验收 |
|---|---|---|---|---|
| B1 | 9 个可编辑字段未标脏 → 静默丢数据 | 前端 | `ProductCenter.vue` | 改任一字段 → 保存按钮可点 → 保存后值生效 |
| B2 | `formatVolume` 未定义 → 物流批次崩溃 | 前端 | `ProductCenter.vue` | 勾选采购单能生成账单行 |
| B3 | SPU 软删不可逆 → 恢复按钮不可达 | 前端 | `ProductCenter.vue` | 软删 SPU 能在列表里看到并恢复 |
| B4 | SKU 列表无状态过滤 | 前端+后端 | `ProductCenter.vue` / `product_center.py` | 能按状态筛选 |
| B5 | 仓储规则按钮无权限门禁 → 必得 403 | 前端 | `ProductCenter.vue` | operator 看不到仓储规则写入口 |
| B6 | 同步清单缺档位规则表 → 云端底线全失效 | 脚本 | `sync_product_center_to_cloud.py` | 同步后规则表非空 |
| C2 | 完整度三套取值域混用 | 后端 | `product_center.py` / `product_center.py`(schemas) | 取值域自解释，无 pattern 冲突（**DB CHECK 约束在阶段 1 迁移 B**） |
| C5/C6 | 实际仓储恒 null；完整度 fallback 到无关字段 | 后端+前端 | 多个 | 列不再显示恒定文案 |

### 2.1 B1 · 补齐 9 个字段的 `markDirty`

**根因**：`saveSpuRows` / `saveSkuRows` 只提交 `dirtyRows` 里的行（`ProductCenter.vue:997-1006` 的 `spuDirty` / `skuDirty` computed），而 9 个字段的输入框没有触发 `markDirty`（`markDirty` 定义在 `:1013`）→ **用户改了但行不在 payload 里，静默丢失**。

**9 个字段与位置**（行号已核实）：

| 字段 | 行号 | 控件 | 当前事件 | 改法 |
|---|---|---|---|---|
| SPU `spu_name` | `:56` | `el-input` | 无 | `@change="markDirty('spu', row)"` |
| SPU `category_l1_code` | `:61` | `el-select` | `@change="row.category_l2_code = ''"` | **合并**为新 handler（见下） |
| SPU `category_l2_code` | `:76` | `el-select` | 无 | `@change="markDirty('spu', row)"` |
| SPU `biz_status` | `:111` | `el-select` | 无 | `@change="markDirty('spu', row)"` |
| SPU `owner_user_id` | `:122` | `el-input-number` | 无 | `@change="markDirty('spu', row)"` |
| SKU `sku_name` | `:220` | `el-input` | 无 | `@change="markDirty('sku', row)"` |
| SKU `specification` | `:225` | `el-input` | 无 | `@change="markDirty('sku', row)"` |
| SKU `weight_kg` | `:230` | `el-input-number` | 无 | `@change="markDirty('sku', row)"` |
| SKU `units_per_carton` | `:248` | `el-input-number` | 无 | `@change="markDirty('sku', row)"` |

**注意事项**：

1. **`category_l1_code` 的 `@change` 已被占用**（`:64` 清空二级品类）。**不能挂两个 `@change`**，必须合并：

   ```js
   const onSpuL1CategoryChange = (row) => {
     row.category_l2_code = "";
     markDirty("spu", row);
   };
   ```
   模板改为 `@change="onSpuL1CategoryChange(row)"`。

2. **用 `@change` 不用 `@input`。** `el-input` 的 `change` 在失焦/回车时触发，`el-input-number` 的 `change` 在值变化并失焦时触发。点「保存变更」按钮会先失焦 → `change` 先触发 → 行已标脏。用 `@input` 会每敲一个字都置脏，且 `el-input-number` 的 `input` 在清空时也会触发，噪音太大。

3. **不要改成行级 deep-watch。** 那样会让所有行都进入 dirty 集合 → 保存时提交全部行 → 触发后端批量校验，且失去"只提交改动行"的语义。当前组件 2291 行、表格大，deep-watch 还有性能问题。

4. `el-input-number` 的 `:precision="3"` / `:precision="2"` 等属性保持不动。

**验收**：

- 改 SPU 的商品名称 → 「保存变更」按钮从 disabled 变可点
- 改 SKU 的规格 → 同上
- 保存后刷新页面，值仍在
- **回归**：改 `spu_name` 后保存，`saveSpuRows` 的 payload 里该行存在

### 2.2 B2 · 补 `formatVolume`

**根因**：`ProductCenter.vue:2069` 调用 `formatVolume(sku)`，但**全仓库没有这个函数定义，也没有 import** → `ReferenceError` → 物流批次 tab「勾选采购单自动生成账单行」必崩，被 watch 的 catch 吞成一句提示。

**实现**（放在 `ProductCenter.vue` 的 script 里，与 `fromPercent` / `percent` 同组工具函数区，约 `:2120-2123` 附近）：

```js
const formatVolume = (sku) => {
  const value = Number(sku?.unit_volume_cbm);
  return Number.isFinite(value) && value > 0 ? value : 0;
};
```

**依据**：`sku` 来自 `skus.value`（`core.dim_erp_sku` 的行），单件体积字段是 `unit_volume_cbm`（SKU 表格列见 `:238`，DB 列 `dimensions.py` 的 `DimErpSku`）。物流账单按体积计费 → 行体积 = 单件体积 × 发货数量。

**必须一起做的静默风险处理**：

`unit_volume_cbm` 为空时 `unitVolume = 0` → 账单行体积为 0 → **按体积计费的仓储/运费算出 0，但不报错**。这是另一种静默失败。所以：

- 在物流批次抽屉里，对 `unit_volume_cbm` 为空/0 的 SKU **显式标红提示**「体积未填，账单金额会偏低」
- 批量生成时把这些 SKU 归入 `unmapped` 数组，**不静默塞进 lines**

**验收**：物流批次 tab 勾选采购单 → 正常生成账单行，无控制台报错；体积未填的 SKU 被标出而不是静默算 0。

### 2.3 B3 · SPU 软删可恢复

**根因**：后端 `list_spus` 的 `include_inactive` 默认 `False`（`product_center.py:416`），`:422-423` 据此过滤 `DimSpu.active IS TRUE`。前端**只给品类（`:1136`）和仓储规则（`:1213`）传了** `include_inactive: true`，SPU 列表没传 → 已软删 SPU 永远不会出现在列表里 → 恢复按钮（`:131` 的 `v-if="row.active === false"`）不可达。

**改法**：SPU 列表请求也传 `include_inactive: true`。

**配套**（避免运营误操作）：

- 软删行在表格里**灰显**（`:active === false` 时加一个 class）
- 软删行**不可勾选**（`:45` 的 `:selectable="(row) => !row.__new && row.active !== false"` 已经处理了，确认即可）
- 「恢复」按钮（`:131`）保持现状

**验收**：软删一个 SPU → 刷新 → 列表里能看到（灰显）→ 点「恢复」→ `dim_spu.active` 回到 true。

### 2.4 B4 · SKU 列表加状态筛选

**后端**：`list_skus`（`product_center.py:1195`）目前无 status 过滤。加：

```python
status: Optional[str] = Query(None, description="按 SKU 状态过滤（active/inactive/...）"),
```

并在查询构造里加对应条件（**注意与 `include_inactive` 的交互**：`include_inactive=True` 时不自动过滤 `active`，由 `status` 参数显式控制）。

**前端**：SKU tab 工具栏加一个 `el-select` 状态筛选器，与现有筛选器同一行。

**验收**：勾选「停用」只看到停用 SKU；不选时按现有行为（全部）。

### 2.5 B5 · 仓储规则权限门禁

**根因**：后端 3 个仓储规则写接口都有 `_require_platform_fee_editor`（`product_center.py:1888` / `:1941` / `:2000`），但前端按钮**完全没有门禁** → operator 可见可点 → 必得 403。

**改法**：`canManagePlatformFee` 前端**已经有了**（`ProductCenter.vue:980-982`，检查 `userStore.hasRole(["admin","manager","finance"])`），已有两处在用（`:182`、`:332` 定价设置按钮）。

| 位置 | 内容 | 改法 |
|---|---|---|
| `:516` | 「新增仓储规则」按钮 | 加 `v-if="canManagePlatformFee"` |
| `:530` | 「操作」列（保存/停用/启用/删除 4 个按钮） | **整列**加 `v-if="canManagePlatformFee"` |

**设计决策**：整列 `v-if` 而不是"disabled + tooltip"。理由：

- 与仓库既有范式一致（`:182`、`:332` 都是 `v-if`）
- 这 4 个按钮**全部**需要 admin/manager/finance，留一列空操作列反而是噪音
- operator 看不到会问，但总比点了报 403 好；必要时在 tab 上加一句说明文案

> 上游设计稿 §6 阶段 0 写的是"disabled + tooltip"。**本方案改判为整列 `v-if`**，理由如上；若 Walter 坚持 disabled 方案，改动同样只有一行。

**验收**：用 operator 账号登录 → 仓储规则 tab 看不到「新增仓储规则」和「操作」列；用 admin 登录两者都在。

### 2.6 B6 · 同步清单补表

**根因（最严重的一个）**：`scripts/sync_product_center_to_cloud.py:38-55` 的 `PRODUCT_CENTER_TABLES` 共 16 张表，含 `core.dim_platforms` / `core.dim_erp_sku`，**唯独没有 `finance.sku_pricing_policies`**。而 `overwrite` 模式会执行 `TRUNCATE ... RESTART IDENTITY CASCADE`（`:241`）→ **云端同步后档位规则表被清空** → 全 SKU 落进 `missing_pricing_policy` → **最低售价整体算不出来、护栏同时失效**。

**改法**：

```python
PRODUCT_CENTER_TABLES = [
    ("core", "dim_platforms"),
    ("core", "dim_warehouses"),
    ("core", "dim_product_categories"),
    ("finance", "product_cost_assumption_profiles"),
    ("finance", "warehouse_storage_rules"),
    ("finance", "logistics_provider_rules"),
    ("finance", "sku_pricing_policies"),     # ← 新增：档位规则表
    ("core", "dim_spu"),
    ("core", "dim_erp_sku"),
    ("core", "bridge_erp_sku_keys"),
    ("core", "bridge_spu_sku"),
    ("finance", "sku_operating_profiles"),
    ("finance", "logistics_bills"),
    ("finance", "logistics_bill_lines"),
    ("finance", "logistics_bill_line_allocations"),
    ("finance", "logistics_bill_purchase_orders"),
    ("finance", "sku_profit_estimates"),
]
```

**插入位置**：放在 `finance.sku_operating_profiles` **之前**。`sku_pricing_policies` 引用 `core.dim_erp_sku` 与 `core.dim_platforms`，而 `sku_operating_profiles` 引用 `dim_erp_sku` / `dim_platforms` / `dim_warehouses`，两者之间无直接 FK 依赖，但按父先子后的顺序放更安全。`TRUNCATE_ORDER` 是 `reversed(PRODUCT_CENTER_TABLES)`（`:58`），**会自动跟着反转，无需额外改**。

**补一条同步后校验**（防止以后再漏表）：

```python
# 同步后断言关键表非空，避免"同步成功但数据是空的"这种静默失败
for schema, table in (("finance", "sku_pricing_policies"), ("core", "dim_erp_sku")):
    n = conn.execute(text(f'SELECT count(*) FROM "{schema}"."{table}"')).scalar()
    if not n:
        raise SystemExit(f"[ABORT] {schema}.{table} 同步后为空 —— 规则表缺失会导致最低售价全部算不出来")
```

**验收**：在测试环境跑一次 overwrite 同步 → 云端 `finance.sku_pricing_policies` 行数与本地一致 → 商品中心最低售价能正常算出。

### 2.7 C2 · 完整度取值域统一

**根因：三套取值域 + 第四个语义混用**（已逐处核实）：

| 字段 | 产出点 | 实际取值域 | 语义 |
|---|---|---|---|
| `data_completeness` | router `:1249` | `complete` / `partial` | **资料完整性**：采购成本、预估物流、预估仓储、货损率、退货损失率填了没有 |
| `cost_completeness`（利润版本列） | router `:2813` `section.get("completeness", "complete")` | schema pattern `^(complete\|partial\|incomplete)$`（`schemas:889`） | 落库时 **expected 段和 actual_recost 段共用一列** |
| `actual_recost.completeness` | `product_profit_service.py:290-298` | `incomplete` / `estimated` / `mixed` / `actual` | **实际数据占比**：实际物流/实际仓储有几个是真的 |
| `configuration_status` | router `:2608` | `configured` / `unconfigured` | **档案配没配**（与完整度无关） |

**具体冲突**：router `:2813` 对 `expected` 和 `actual_recost` 两个 basis 循环，都写进同一列 `cost_completeness`。当 basis = `actual_recost` 时，`section["completeness"]` 是 `estimated`/`mixed`/`actual` —— **违反 schema 的 pattern**。

**为什么一直没炸**：DB 列 `cost_completeness = Column(String(32), nullable=False, default="incomplete")`（`business.py:1140`）和 `actual_recost_completeness`（`:1129`）**都没有 CHECK 约束**（该表只有 `ck_sku_profit_estimate_scenario` / `ck_sku_profit_estimate_basis` 两个约束，`:1147-1153`）→ 错值直接静默写入；只有走带 pattern 的 API 入口才会 422。

**改法（拆成两个互不重叠的字段）**：

1. **router `:2813` 按 basis 分流** —— `expected` 段的 completeness 写 `cost_completeness`，`actual_recost` 段的写 `actual_recost_completeness`，**不再共用一列**。
2. **`cost_completeness` 的 schema pattern 收窄为 `^(complete|partial|incomplete)$`**（`schemas:889` 已是）；**`actual_recost_completeness` 加 pattern `^(incomplete|estimated|mixed|actual)$`**（`schemas:704` / `:756`）。
3. **`configuration_status` 不再当完整度用** —— 前端 `:419` 的 `row.preview?.actual_recost?.completeness || row.configuration_status` **去掉 `|| row.configuration_status` 兜底**。

> `reference_cost_status`（`schemas:831`，值 `"ready"`）+ `reference_cost_missing_reasons`（`:832`）+ `reference_logistics_missing_reasons`（`:833`）+ `reference_storage_missing_reasons`（`:834`）**已存在且已在候选响应里** —— 这是阶段 1 守卫要用的口径，**不要再造一套**。

**阶段划分上的刻意取舍**：

| 层 | 阶段 | 为什么 |
|---|---|---|
| router 分流 + schema pattern + 前端去兜底 | **阶段 0**（纯 Python，无迁移） | 立即止住"继续写错值" |
| DB 层 CHECK 约束 + 存量数据清洗 | **阶段 1 迁移 B** | 加约束前**必须先查生产库存量值**（§11），否则加约束会失败；生产数据未查清前不能动 |

**验收**：`cost_completeness` 与 `actual_recost_completeness` 的取值域各自自解释；前端「重估完整度」列不再出现 `configured`/`unconfigured`；新写的利润版本行里，`cost_completeness` 不再出现 `estimated`/`mixed`/`actual`。

### 2.8 C5/C6 · 删「实际仓储」列 + 完整度列拆分

**C5 根因**：`actual_storage_cost` 恒为 `None`（`product_finance_service.py:1116` 硬编码 `actual_storage_cost=None`，`:1136` 输出 `"actual_storage_cost": None`）。

**为什么永远补不上**：**系统里不存在仓储费账单。** `LogisticsBill`（`business.py:730`）的费用构成全是运费 —— `headhaul_cost` / `handling_cost` / `last_mile_cost` / `freight_amount` / `customs_amount` / `delivery_amount` / `sensitive_amount`，且 `transport_type ∈ ('sea','air','rail')`。`WarehouseStorageRule`（`:837`）是「固定按体积 CNY/CBM/月」的**规则预估**，不是账单。

**改法**：

| 动作 | 位置 |
|---|---|
| 前端删「实际仓储」列 | `ProductCenter.vue:401-407` |
| 「实际物流」列折叠进「混合成本利润」的 tooltip | `:396-400` → 移到 tooltip |
| 「重估利润」改名「**混合成本利润**」 | `:418`（术语依据见上游设计稿 §4.1） |
| 「重估完整度」改名「**混合成本完整度**」 | `:419` |

> ⚠️ 改名清单要同步到 `frontend/tests/productCenterUi.test.mjs:92`（`assert.match(source, /重估利润/)`）。**这条断言会因改名失败，必须同步改。**

**验收**：「实际仓储」列消失；「混合成本利润」tooltip 里能看到实际物流与预估仓储分别多少；完整度列不再出现恒定文案。

### 2.9 阶段 0 测试清单

| # | 用例 | 文件 | 类型 |
|---|---|---|---|
| 1 | 9 个字段每个都触发 `markDirty` | `frontend/tests/productCenterUi.test.mjs` | 源码断言 |
| 2 | `category_l1_code` 的 handler 同时清空二级 + 标脏 | 同上 | 源码断言 |
| 3 | `formatVolume` 有定义且返回 `unit_volume_cbm` | 同上 | 源码断言 |
| 4 | SPU 列表请求带 `include_inactive: true` | 同上 | 源码断言 |
| 5 | 仓储规则 2 处带 `canManagePlatformFee` | 同上 | 源码断言 |
| 6 | `PRODUCT_CENTER_TABLES` 含 `sku_pricing_policies` 且在 `sku_operating_profiles` 之前 | 新建 `backend/tests/test_product_center_sync_contract.py` | 源码断言 |
| 7 | `cost_completeness` 与 `actual_recost_completeness` 的 pattern 各自收窄 | `backend/tests/test_product_center_schema_contract.py` | 契约 |
| 8 | `actual_storage_cost` 不再出现在候选响应 | 同上 | 契约 |
| 9 | 「重估利润」→「混合成本利润」改名 | `frontend/tests/productCenterUi.test.mjs:92` | 同步更新 |

**新增断言的写法**（参照现有 `productCenterUi.test.mjs` 的源码正则风格）：

```js
test("9 个可编辑字段都会标脏，改动不丢失", () => {
  for (const [field, kind] of [
    ["spu_name", "spu"], ["category_l2_code", "spu"], ["biz_status", "spu"],
    ["owner_user_id", "spu"], ["sku_name", "sku"], ["specification", "sku"],
    ["weight_kg", "sku"], ["units_per_carton", "sku"],
  ]) {
    assert.match(source, new RegExp(`${field}[\\s\\S]{0,320}markDirty\\('${kind}'`));
  }
  // category_l1_code 的 @change 已被占用，必须走合并后的 handler
  assert.match(source, /onSpuL1CategoryChange/);
});
```

### 2.10 阶段 0 回滚

**无迁移、无接口变更** → 回滚 = 还原代码。

```powershell
git checkout -- frontend/src/domains/business/views/ProductCenter.vue
git checkout -- backend/schemas/product_center.py
git checkout -- backend/domains/business/routers/product_center.py
git checkout -- scripts/sync_product_center_to_cloud.py
```

> **C2 的 DB 层 CHECK 约束不在阶段 0** —— 它在阶段 1 迁移 B 里，理由见 §2.7（加约束前必须先查生产库存量值并清洗）。

**唯一的外部副作用**：B6 改了同步脚本。如果已经用旧脚本同步过云端，云端档位表可能已被清空 —— 回滚代码**不会**恢复数据，需要重新同步一次（修好的脚本）。

---

## 3. 阶段 1 · ROI 只读层

**目标**：在利润测算 tab 加 3 个只读列，让运营能回答「这个品投广告，ROI 低于多少就亏、建议设多少」。**运营不需要填任何新东西。**

### 3.1 后端 · 新增纯函数模块

**新建** `backend/services/product_roi_service.py`（无 ORM、无 DB、无 I/O，与 `product_pricing_service.py` 同风格）：

```python
def compute_roi_metrics(
    *,
    net_revenue: Decimal,
    pre_ad_profit: Decimal,
    safety_margin: Decimal = Decimal("0.20"),
    target_roi_ceiling: Decimal = Decimal("50"),
) -> dict:
    """
    net_revenue         商家实收 = 测算售价 − 卖家优惠券（= TikTok GMV）
    pre_ad_profit       广告前利润
    safety_margin       安全边际，默认 0.20
    target_roi_ceiling  平台可填上限的全局最大值（各平台取 max）
    返回 advertising_contribution_margin_rate / break_even_roi /
         suggested_roi / suggested_roi_clamped / suggestion_note
    """
```

**规则**（口径依据见上游设计稿 §2.5⑦⑨⑩）：

| 输出 | 公式 | 边界 |
|---|---|---|
| `advertising_contribution_margin_rate` | `pre_ad_profit ÷ net_revenue` | 分母 ≤ 0 → 返回 None + `missing_reasons` |
| `break_even_roi` | `net_revenue ÷ pre_ad_profit` | `pre_ad_profit ≤ 0` → None |
| `suggested_roi` | `break_even_roi × (1 + safety_margin)` | |
| `suggested_roi_clamped` | `min(suggested_roi, target_roi_ceiling)` | **只封顶不封底** |
| `suggestion_note` | | `above_platform_ceiling` / `null` |

**只封顶不封底的理由**：保本ROI < 1 意味着毛利率 > 100%，是"成本算错了或有大额收入补贴"的**异常信号**，应当报错而不是被 clamp 藏起来。正常情况保本ROI ≥ 1（毛利率 ≤ 100% 是物理事实）。

**`pre_ad_profit ≤ 0` 时一律返回 None**，不返回乐观值（`missing_reasons` 加 `non_positive_cost_denominator`）。

### 3.2 后端 · 接入现有链路

**接入点**：`product_finance_service.py` 的 `preview_platform_sku_profit`（`:1053`）在组装 `preview["expected"]` / `preview["actual_recost"]` 时各调一次 `compute_roi_metrics`。

**注意**：`preview` 在候选响应里是 `Optional[dict] = None`（`schemas:835`）—— **自由 dict，ROI 三个字段塞进 `preview.expected` / `preview.actual_recost` 不需要改 Pydantic 模型，零契约风险**。

但**顶层新增的字段必须进模型**（否则被 `extra='ignore'` 静默丢弃，`schemas:838-839` 有明文警告）：

| 字段 | 类型 | 位置 |
|---|---|---|
| `expected_selling_price_source` | `Optional[str]` | `PlatformSkuProfitCandidateResponse` |
| `roi_safety_margin` | `Optional[float]` | 同上 |
| `target_roi_ceiling` | `Optional[float]` | 同上 |

### 3.3 迁移（2 个文件）

**建议拆成 2 个**，理由见上游设计稿 §11：平台级配置无 FK、先做；两张 finance 表有 FK、后做。任何一个环节出问题都能单独回滚。

**迁移 A** `current_migrations/versions/20261112_add_platform_roi_config.py`

```python
revision = "current_schema_20261112_add_platform_roi_config"
down_revision = "current_schema_20261111_add_refresh_queue_domain_and_retry"
```

给 `core.dim_platforms` 加 3 列：

| 列 | 类型 | 默认 |
|---|---|---|
| `roi_safety_margin` | `Numeric(6, 4)` | `0.20` |
| `target_roi_ceiling` | `Numeric(10, 2)` | `50` |
| `target_roi_floor` | `Numeric(10, 2)` | `1`（**备用**，当前不参与 clamp，仅记录平台可填下限） |

并回填平台实际值（TikTok 20 / Shopee 50）：

```sql
UPDATE core.dim_platforms SET target_roi_ceiling = 20 WHERE platform_code = 'tiktok';
UPDATE core.dim_platforms SET target_roi_ceiling = 50 WHERE platform_code = 'shopee';
```

**迁移 B** `current_migrations/versions/20261113_add_sku_roi_columns.py`

```python
revision = "current_schema_20261113_add_sku_roi_columns"
down_revision = "current_schema_20261112_add_platform_roi_config"
```

| 表 | 列 | 类型 | 可空 |
|---|---|---|---|
| `finance.sku_operating_profiles` | `expected_selling_price_source` | `String(32)` | ✓ |
| `finance.sku_profit_estimates` | `expected_selling_price_source` | `String(32)` | ✓ |
| `finance.sku_profit_estimates` | `break_even_roi` | `Numeric(12, 4)` | ✓ |
| `finance.sku_profit_estimates` | `suggested_roi` | `Numeric(12, 4)` | ✓ |
| `finance.sku_profit_estimates` | `suggested_roi_clamped` | `Numeric(12, 4)` | ✓ |
| `finance.sku_profit_estimates` | `equivalent_target_roi` | `Numeric(12, 4)` | ✓ |

**全部可空、全部带存在性守卫**，`downgrade()` 逐列判存在后 drop。

**同时在迁移 B 里完成 C2 的 DB 层收口**（阶段 0 只做 Python 层，理由见 §2.7）：

1. **先清洗存量数据**：`UPDATE finance.sku_profit_estimates SET cost_completeness = 'incomplete' WHERE cost_completeness NOT IN ('complete','partial','incomplete')` —— 把历史上被 actual_recost 段污染的值归位。**这一步必须在 §11 的生产库核查之后做**，且要先备份。
2. **再加 CHECK 约束**：
   - `ck_sku_profit_estimate_cost_completeness`：`cost_completeness IN ('complete','partial','incomplete')`
   - `ck_sku_profit_estimate_actual_completeness`：`actual_recost_completeness IN ('incomplete','estimated','mixed','actual') OR actual_recost_completeness IS NULL`
3. `downgrade()` 要先 drop 约束再删列。

### 3.4 前端 · 3 个只读列 + 成本完整度守卫

**列位置**：最低售价（`:349`）右侧、测算售价（`:358`）之前 —— 对应截图标注的位置。

| 列 | 内容 | 宽度 | tooltip |
|---|---|---|---|
| 广告前贡献毛利率 | `row.preview?.expected?.advertising_contribution_margin_rate` | 120 | 「扣掉采购、物流、仓储、贴单、平台佣金、达人佣金、货损、退货后的占比。分母是商家实收（售价−优惠券），与平台 GMV 同一口径」 |
| 保本ROI | `row.preview?.expected?.break_even_roi` | 100 | 「低于这个 ROI，广告就是亏的（财务口径）。分母为商家实收，与平台 GMV 同一把标尺」 |
| 建议ROI | `row.preview?.expected?.suggested_roi_clamped` | 100 | 「保本线上浮 20%（业界惯例 20–30%）。超过平台可填上限时截断，并提示广告空间不足」 |

**成本完整度守卫（必须同批实现，否则本阶段不能上线）**：

数据源**已经存在**，不需要新增字段：
- `row.reference_cost_status`（`"ready"` / 其他）
- `row.reference_cost_missing_reasons`
- `row.reference_logistics_missing_reasons`
- `row.reference_storage_missing_reasons`

守卫逻辑：

```js
const roiGuarded = (row) => row.reference_cost_status !== "ready";
```

- `reference_cost_status !== 'ready'` → **三个 ROI 数字全部置灰**
- 显示「成本不全，保本ROI 偏乐观」
- 缺失原因按三份清单**分列显示**（缺物流规则 / 缺仓储规则 / 缺SKU体积）

> ⚠️ 这是本阶段**最容易出事**的点：成本不全 → `pre_ad_profit` 高估 → p 偏大 → 保本ROI 偏小 → 看起来宽松 → 运营真投广告 → 亏损。**没有守卫，本阶段不能上线。**

### 3.5 两条免责提示（与 ROI 列同批上）

1. 「本表不预测销量」——提价掉量模型看不见（上游设计稿 §5.3）
2. 「平台报告ROI 含自然/达人归因，达标 ≠ 赚钱」——（上游设计稿 §2.5⑧）

第 2 条在阶段 1 只放**文案**（还没有平台报告ROI 列），阶段 2 与判定一起上。

### 3.6 测试清单

| # | 用例 | 位置 |
|---|---|---|
| 1 | 保本ROI 公式精确值 | `backend/tests/test_product_roi_service.py`（新建） |
| 2 | `break_even_roi × p == 1` | 同上 |
| 3 | `suggested_roi == break_even_roi × 1.20` | 同上 |
| 4 | 封顶：`suggested_roi_clamped == 50` 且 `suggestion_note == 'above_platform_ceiling'`，且 `suggested_roi` 保留未封顶原值 | 同上 |
| 5 | 不封底：保本ROI < 1 时不 clamp，返回异常标记 | 同上 |
| 6 | 分母 ≤ 0 → 返回 None + `non_positive_cost_denominator` | 同上 |
| 7 | **分母口径**：`break_even_roi == net_revenue ÷ pre_ad_profit`（**是商家实收，不是商品金额**） | 同上 |
| 8 | **与平台标尺一致**：`net_revenue == (P − c) == B + d` | 同上 |
| 9 | **广告费率 ↔ 目标ROI 恒等**：`pre_ad_profit × s == net_revenue ÷ R` | 同上 |
| 10 | 候选响应含新增字段（**漏声明会被静默丢弃**） | `test_product_center_schema_contract.py` |
| 11 | `ProductCenterItem` 新增字段全部 `Optional` | 同上 |
| 12 | 成本不全守卫：`reference_cost_status != 'ready'` 时 ROI 字段为 None | `test_platform_sku_profit_workbench.py` |
| 13 | 三步迁移可重复 | 新建迁移契约测试 |
| 14 | 前端 3 列渲染 + 置灰 | `frontend/tests/productCenterUi.test.mjs` |

### 3.7 回滚

| 迁移 | 回滚 |
|---|---|
| A（平台配置） | `alembic -c alembic-current.ini downgrade -1` → 删 3 列 |
| B（业务列） | 同上 |

**旧代码读不到新列，不受影响**（这正是"新增可空列"的价值）。前端若列渲染异常，回退前端即可，后端数据留着无害。

---

## 4. 阶段 2 · ROI 输入与判定

### 4.1 后端

| 改动 | 位置 |
|---|---|
| `SkuOperatingProfile` + `target_roi` / `target_roi_source` | `business.py` 的 `SkuOperatingProfile` |
| `SkuProfitEstimate` + `actual_roi` / `actual_roi_source` | `business.py` 的 `SkuProfitEstimate` |
| 迁移 | `20261114_add_sku_roi_input_columns.py` |
| 请求体加 `target_roi` / `actual_roi` | `schemas` 的 `PlatformSkuProfitEstimateRequest` |
| 新增错误码 | 见下表 |
| 草稿保存（`:2715-2716`）把 `target_roi` 一起写进 profile | router |
| 利润版本落库（`:2799-2814`）把 `actual_roi` 一起写进 estimate | router |

**错误码**（走 `BusinessValidationError`，**不要用 `HTTPException(status_code=422, detail={...})`** —— 全局异常处理器会把 `detail` 拍平成字符串，前端读不到 `code`，`product_center.py:2199-2200` 有先例注释）：

| code | 触发 | 说明 |
|---|---|---|
| `below_break_even_roi` | `target_roi < break_even_roi` | 目标ROI 低于保本线 |
| `roi_cost_incomplete` | `reference_cost_status != 'ready'` | 成本不全，保本ROI 不可信 |
| `roi_out_of_platform_range` | `break_even_roi × (1+margin) > target_roi_ceiling` | 广告空间不足（**提示，不拦**） |

**护栏顺序**：保本ROI 护栏必须在「资料完整性」校验**之前**（沿用现有 `below_min_selling_price` 的顺序逻辑，见 `product_center.py:2741-2745` 的注释）。

### 4.2 前端 · 2 个手填列 + 三色判定

| 列 | 内容 | 校验 |
|---|---|---|
| 目标ROI | 手填 | `> 0`，超出合理区间给黄提示但不拦 |
| 平台报告ROI | 手填 | 同上 |

**三色判定**：

```
平台报告ROI < 保本ROI          → 🔴 亏损投放
保本ROI ≤ 平台报告ROI < 建议ROI  → 🟡 有利润但未达财务目标
平台报告ROI ≥ 建议ROI           → 🟢 达标
目标ROI < 保本ROI              → 🔴 目标ROI低于保本线，这单投了就是亏
```

**判定行必须带归因警示**（上游设计稿 §2.5⑧）：GMV Max 的归因窗口把自然流量和达人带货也算进归因 GMV，所以「🟢 达标」很可能只是归因虚高。商品中心**目前拿不到归因放大系数**（没有平台广告数据源），所以第一版**只给警示文案，不给数字** —— 给不出数字时宁可不给，不能编。

### 4.3 阶段 2 测试

在阶段 1 的用例基础上追加：

- 护栏顺序：同时「目标ROI低于保本线」且「缺物流规则」→ 返回 `below_break_even_roi`
- 错误信封：`{"success":false,"error":{"code":3001,"detail":{"code":"below_break_even_roi",...}}}`，**顶层无 `detail` 键**
- 草稿不拦截：`POST /drafts` 在目标ROI低于保本线时仍返回 201
- ROI 来源标记：`target_roi` 落 profile、`actual_roi` 落 estimate，各带 `*_roi_source`

---

## 5. 阶段 3 · 广告分成率降级 + 字段瘦身

### 5.1 广告分成率降级

**主手填输入收敛为「目标ROI」一个**（上游设计稿 §2.5⑩）。

```
广告费用 = 商家实收 ÷ 目标ROI              （与平台标尺一致）
广告分成率 = 广告费用 ÷ 广告前利润
等效目标ROI = 保本ROI ÷ 广告分成率          （手填阶段一直并排显示）
```

- **手填广告费率降级为高级逃生口**：默认折叠，需显式展开才能改，旁边永远并排显示「等效目标ROI」
- **存量 SKU 用 `等效目标ROI = 保本ROI ÷ s` 反解出 `target_roi` 初值**，源标记 `migrated_from_legacy_rate`
  （开发库现状：`sku_operating_profiles` 3 行全部 `expected_ad_rate = 0.15`，`dim_platforms` **没有广告费率默认列** → 这个 15% 是人工填的。**生产库的填充率必须先查**，见 §11 前置核查）
- 字段 `expected_ad_rate` **保留**，不删列，只改语义标注

### 5.2 列瘦身

| 动作 | 位置 |
|---|---|
| 移除「物流方式」列（与顶部筛选器重复） | `:385` |
| 「实际物流 / 实际仓储」折叠进「混合成本利润」tooltip | 阶段 0 已做一半 |
| 改名「预计售价」→「测算售价」 | `:358` |
| 改名「预计利润」→「参考成本利润」 | `:408` |
| 改名「广告费率」→「广告分成率」 | `:389` |
| 改名「平台费率」→「平台佣金率」 | `:390` |
| 改名「平台费用」→「平台佣金」 | `:391` |
| 改名「参考物流/参考仓储」→「预估物流成本/预估仓储成本」 | `:386` / `:387` |
| 改名「参考贴单费」→「贴单费」 | `:388` |
| 改名「继承货损率」→「物流货损率（SPU）」 | `:394` |
| 改名「继承退货损失率」→「退货损失率（SPU）」 | `:395` |
| 改名「当前可优惠」→「当前让利上限」 | `:347` |
| 改名「清货极限」→「清货让利上限」 | `:348` |
| 改名「参考售价」→「基准售价」 | `:345` |
| 表头分组 `标识｜定价｜参照｜成本｜广告｜结论` | 全表 |

**改名会影响的前端断言**（`frontend/tests/productCenterUi.test.mjs`）：

| 行 | 现断言 | 改后 |
|---|---|---|
| `:92` | `/重估利润/` | `/混合成本利润/`（阶段 0 已改） |
| `:165` | `/滞销可优惠/` | `/清货让利上限/` |
| `:265` | `/广告费率/` | `/广告分成率/` |

### 5.3 阶段 3 特有风险与回滚

**风险**：阶段 3 是唯一一个**语义变更**的阶段 —— 手填入口从"平级"变成"折叠的高级逃生口"，运营的操作路径变了。

**缓解**：
- 阶段 3 单独发布，**不与阶段 2 同批**
- 手填入口折叠而非删除 → 回滚只需展开
- 存量 SKU 已反解迁移 → 不会出现"突然所有 SKU 都没广告费"的断崖

**回滚**：纯前端 + 迁移降级（`target_roi` 列留着无害）。

---

## 6. 阶段 4 · 基准售价工具

**归属决策（Q6 已定）**：基准售价由**对应运营自己填**，系统侧只负责把规则和工具落地，**不推动批量补齐、不替业务判断价格**。

**风险等级：低**（无人会被系统批量改动底线）。

### 6.1 交付的四样工具

| # | 工具 | 实现 | 验收 |
|---|---|---|---|
| 1 | 来源可追溯 | `dim_erp_sku.selling_price_source` 从自由文本改枚举：`platform_listing` / `erp` / `manual`。⚠️ `platform_listing` **当前无可靠数据源**（`feishu_projection_service.py:406-408` 明示"平台 SKU 档案靠人工维护，覆盖率未知"），保留枚举位但不承诺可采集 | 枚举 CHECK 生效；历史自由文本已清洗 |
| 2 | 确认日期 | `selling_price_confirmed_at` 字段已存在（`dimensions.py:215`）。SKU 资料 tab 有「参考售价」输入框（`:255`）和「售价来源」输入框（`:260`），但**没有确认日期输入框**。补上，填基准售价时自动写当天 | 填值自动写当天 |
| 3 | **即时影响预览**（最重要） | 运营填基准售价的**当场**显示：「该 SKU 最低售价将从 **28.23** 变为 **63.00**（**+123%**）」，标明原因是纪律线生效 | 填值即时反馈，不用保存后才知道 |
| 4 | 偏差校验 + 过期巡检 | 与历史成交价中位数偏差 > 30% → 提示；`confirmed_at` 超 90 天 → 标黄 | 提示可复现，不误报 |

**工具 3 为什么最重要**：基准售价填错的**最大风险不是亏本，是货卖不动**（基准售价偏高 → 纪律线偏高 → 最低售价被顶高 → 护栏把品拦死）。这个风险**必须在填的瞬间被看见**。

**工具 4 的前置依赖**：SKU 级历史成交价目前**取不到** —— `sql/semantic/orders_atomic.sql` 已有 `platform_sku` / `product_sku` / `sku_id`（`:259-275` 从 `raw_data` 提取），但**没有 join `bridge_erp_sku_keys` 映射到 ERP SKU**。

> 这也修正了上游设计稿 §12 第 3 条的旧结论：「订单表商品键全空」不准确 —— **键是有的（平台侧），缺的是到 ERP SKU 的映射**。

### 6.2 迁移

`current_migrations/versions/20261115_selling_price_source_enum.py`

1. 清洗历史自由文本 → 映射到枚举（无法判定的统一落 `manual` 并记 `selling_price_source_cleaned_at`）
2. 加 CHECK 约束 `ck_dim_erp_sku_selling_price_source`
3. `selling_price_confirmed_at` 加条件 NOT NULL 检查（有基准售价时必须有确认日期）—— 建议用 CHECK 而非 NOT NULL，因为历史数据有缺口

### 6.3 阶段 4 测试

- 基准售价即时预览：填基准售价时返回的「补齐后最低售价」与手算一致（成本线 28.23 / 基准售价 70 → 最低售价 63.00）
- 来源枚举 CHECK 生效
- `confirmed_at` 自动写入

---

## 7. 阶段 5 · 指标口径登记

**纯文档，无代码。** 但**不做这一步就上线，等于再造一个"没有统一系统口径"的野生指标**。

1. `docs/team-skills/sea-metrics-language/references/metrics-dictionary.md` 给出「保本ROI / 建议ROI / 广告前贡献毛利率」的正式定义（公式、维度、口径声明）
2. `metric-status.md` 登记状态：建议先给 `observe` + `conditional`，待有实际投放数据后再升 `stable`
   （注意 `roas` / `mer` 当前是 `blocked`，见 `metric-status.md:28-29`，owner=marketing）
3. `platform-mapping.md` 的 blocked 列表同步

---

## 8. 跨阶段 · 改名映射总表

| 位置 | 现状 | 目标 | 阶段 |
|---|---|---|---|
| SKU 资料 tab | 参考售价 | **基准售价** | 3 |
| SKU 资料 tab | 售价来源 | **基准售价来源** | 4 |
| SKU 资料 tab | 滞销可优惠 | **清货让利上限** | 3 |
| 利润测算 tab | 参考售价 | **基准售价** | 3 |
| 利润测算 tab | 预计售价 | **测算售价** | 3 |
| 利润测算 tab | 预计利润 | **参考成本利润** | 3 |
| 利润测算 tab | 重估利润 | **混合成本利润** | 0 |
| 利润测算 tab | 重估完整度 | **混合成本完整度** | 0 |
| 利润测算 tab | 广告费率 | **广告分成率** | 3 |
| 利润测算 tab | 平台费率 | **平台佣金率** | 3 |
| 利润测算 tab | 平台费用 | **平台佣金** | 3 |
| 利润测算 tab | 参考物流 / 参考仓储 | **预估物流成本 / 预估仓储成本** | 3 |
| 利润测算 tab | 参考贴单费 | **贴单费** | 3 |
| 利润测算 tab | 继承货损率 | **物流货损率（SPU）** | 3 |
| 利润测算 tab | 继承退货损失率 | **退货损失率（SPU）** | 3 |
| 利润测算 tab | 当前可优惠 | **当前让利上限** | 3 |
| 利润测算 tab | 清货极限 | **清货让利上限** | 3 |
| 利润测算 tab | 优惠券 | **优惠券（商家承担）** | 3 |
| 利润测算 tab | 实际物流 / 实际仓储 | 折叠进「混合成本利润」tooltip | 0 / 3 |
| 利润测算 tab | 物流方式 | 移除（与顶部筛选器重复） | 3 |
| 定价设置抽屉 | 滞销30天 / 滞销60天 / 滞销60天以上 | **库龄≥60天 / 库龄≥90天 / 库龄≥120天** | 3 |
| 飞书投影 | 参考售价 | **基准售价** | 3 |

**禁用词表**（任何文档、注释、UI 文案都不得出现）：参考售价、预计利润、重估利润、实际成本利润、实际ROI、广告费率、平台费率、折扣率、滞销30天、毛利率。

---

## 9. 发布与回滚手册

### 9.1 发布顺序（不可颠倒）

```
1. 阶段 0（纯代码）        → 验证 → 发布
2. 阶段 1 迁移 A（平台配置）→ upgrade → 验证 → 发布
3. 阶段 1 迁移 B（业务列）  → upgrade → 验证 → 发布
4. 阶段 1 代码（只读列）    → 验证 → 发布
5. 阶段 2 迁移 → 阶段 2 代码
6. 阶段 3 代码（独立发布）
7. 阶段 4（与 1-3 无交集，可并行）
8. 阶段 5（纯文档）
```

### 9.2 每阶段的验证清单

```powershell
# 迁移三步可重复
alembic -c alembic-current.ini upgrade heads
alembic -c alembic-current.ini downgrade -1
alembic -c alembic-current.ini upgrade heads

# 后端契约测试
python -m pytest -q backend/tests -m "not slow and not requires_browser" --ignore=backend/tests/data_pipeline --ignore=backend/tests/archive

# 前端测试
node --test frontend/tests/productCenterUi.test.mjs

# 质量门禁
python scripts/run_lint.py
python scripts/run_typecheck.py
```

### 9.3 回滚矩阵

| 阶段 | 回滚动作 | 数据影响 |
|---|---|---|
| 0 | `git checkout` 还原代码 | 无（但 B6 若已同步过云端需重新同步） |
| 1 | `alembic -c alembic-current.ini downgrade -1`（两次，迁 A、B）+ 还原代码 | 新列删除，旧数据不受影响 |
| 2 | 同上 + 还原代码 | |
| 3 | 还原前端代码即可（保留手填入口即可回退） | 无 |
| 4 | `downgrade -1` + 还原代码 | 枚举约束退回自由文本（需保留清洗结果） |
| 5 | 文档回滚 | 无 |

---

## 10. 风险登记册

| # | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | **B6 已经在生产造成过损失** —— 云端档位表被清空过，最低售价算不出来 | 中 | 高 | 阶段 0 第一优先级；同步后校验改为硬失败 |
| R2 | 成本不全时保本ROI 偏松 → 运营真亏损 | **高** | **高** | 阶段 1 的完整度守卫是**硬前提**，没守卫不上线 |
| R3 | 存量 SKU 广告费率填充率低 → 阶段 3 迁移后大面积「无目标ROI」 | 中 | 中 | 反解迁移；**上线前先在生产库查填充率**（见 §11） |
| R4 | 改名一次性动 20+ 处，漏改导致跨 tab 对不上 | 高 | 中 | §8 映射总表 + 前端断言逐条同步 |
| R5 | 阶段 3 语义变更吓到运营 | 中 | 中 | 独立发布；手填入口折叠而非删除；配文案说明 |
| R6 | 基准售价批量补齐导致护栏把品拦死 | **低**（Q6 后无批量） | 高 | 阶段 4 只给工具不做数据；即时影响预览让运营当场看见 |
| R7 | 归因虚高被误读成"赚钱" | 高 | 中 | 判定行强制带警示文案；不给编造的放大系数 |
| R8 | `PlatformSkuProfitCandidateResponse` 漏声明新增字段 → 被静默丢弃 | 中 | 中 | 契约测试断言新增字段存在（阶段 1 用例 10） |
| R9 | `sku_pricing_policies` 进同步清单后 FK 顺序不对 → 同步失败 | 低 | 中 | 放在 `sku_operating_profiles` 之前；同步后校验 |
| R10 | 阶段 1 迁移 B 加 CHECK 约束时，存量 `cost_completeness` 有污染值 → 加约束失败 | ~~中~~ → **已解除** | ✅ **D7/D8 实测：`sku_profit_estimates` 生产 0 行**，无存量污染值 ⇒ 约束可直接加，不需要前置清洗（见 §11.1 / §11.2①） |

---

## 11. 前置数据核查清单 · **已于 2026-11-07 完成（生产库实测）**

> **执行方式**：SSH 隧道 `ssh -N -L 15433:127.0.0.1:15435 deploy@134.175.222.171`
> （注意生产 PG 容器映射在 **15435**，不是 5432 —— `docker-compose.prod.yml` 里是 `127.0.0.1:15435->5432`）
> → `CLOUD_DATABASE_URL`（`.env`）指向 `127.0.0.1:15433`。全程 `SET default_transaction_read_only = on`，
> 只跑聚合查询，**未对生产库做任何写入**。

### 11.1 D1–D8 实测结果

| # | 核查项 | 生产库实测 | 对方案的影响 |
|---|---|---|---|
| D1 | `sku_operating_profiles.expected_ad_rate` | **共 6 条，全部 = 0.15**（无 null、无 0、min=max=avg=0.15） | 阶段 3 反解迁移**只影响 6 条**，影响面极小 → **可以直接做，不需要分批策略**。同时确认：0.15 是人工填的默认值，不是真实分布 |
| D2 | `dim_erp_sku.reference_selling_price` | **4 / 1122 = 0.36%** 非空（取值 40 ~ 500） | 设计稿引用的 0.2% 实测 0.36%。**基准售价纪律线覆盖不到 99.6% 的 SKU** → 阶段 2 必须有"参考售价缺失"的降级路径，不能假设它普遍存在 |
| D3 | `dim_erp_sku.selling_price_source` | `(null)` 1117 / `'manual'` 4 / **空字符串 1** | 阶段 4 枚举清洗要处理 **1118 行**（1117 null + 1 空串）；已有取值只有 `'manual'` 一个 |
| D4 | `sku_operating_profiles.status` | `active` 6 / 其它 0 | B4 筛选器选项确认：生产上只有 active 有数据，但保留 inactive 选项仍必要（软删会累积） |
| D5 | `sku_pricing_policies` | **4 条，全部 `status=active`、`effective_to IS NULL`、且 `platform_basis` 全是 `tiktok`** | ⚠ **Shopee 一条档位规则都没有** → 见 §11.2 |
| D6 | 软删规模 | `core.dim_spu.active`：True 284 / **False 3**；`core.dim_erp_sku.status`：active 1119 / **inactive 3** | B3（软删可恢复）与 B4（状态筛选）的真实规模确认，各 3 条 |
| D7 | `sku_profit_estimates.cost_completeness` | **表 0 行 → 无任何存量值** | ✅ **R10 风险解除** |
| D8 | `sku_profit_estimates.actual_recost_completeness` | **表 0 行 → 无任何存量值** | ✅ 同上 |

### 11.2 核查带出的三个新结论

**① 阶段 1 的 CHECK 约束不再需要"先清洗"这一步（原 R10 解除）**

风险册 R10 写的是"存量 `cost_completeness` 可能被 `actual_recost` 段污染，加 CHECK 会失败"。
实测 `sku_profit_estimates` **在生产上是一条数据都没有** ⇒ 没有存量污染值 ⇒
**阶段 1 迁移 B 可以直接加 CHECK 约束，不需要前置清洗语句**。原方案里"约束推迟到 D7/D8 之后"的顾虑已消除。

**② Shopee 完全没有库龄档位规则 —— 比 B6 的"同步漏表"更根本**

D5 显示 4 条档位规则的 `platform_basis` **全是 `tiktok`**。也就是说：即使 B6 的同步清单修好了、
规则被同步到了云端，**Shopee 侧依然一条规则都没有** ⇒ Shopee 的 SKU 全部落进
`missing_pricing_policy` ⇒ **最低售价（底线）在 Shopee 上根本算不出来**。

而 Walter 拍板的目标 ROI 上限恰恰是 Shopee 50 / TikTok 20 —— 上限更高的那个平台恰好没有底线规则。
**这必须作为阶段 1 的前置任务**：Shopee 的档位规则要建（见 §13.3 待确认 Q13）。

**③ 商品中心在生产上基本没有启用 —— 这改变了阶段 1–3 的性质**

生产库实测规模：

| 表 | 生产 | 开发 | 说明 |
|---|---|---|---|
| `core.dim_erp_sku` | 1122 | 1125 | 主数据，两边早已同步过 |
| `core.dim_spu` | 287 | 286 | 同上 |
| `core.dim_users` | 390 | 16 | 差额里 **375 个是 `approval_workflow_*` 审批流临时账号**，真人用户两边基本一致 |
| `finance.sku_operating_profiles` | **6** | 3 | 6 条里覆盖的只有 **4 个不同 sku_id**（1768 / 772 / 1869 / 1456） |
| `finance.sku_profit_estimates` | **0** | 0 | **一条利润测算结果都没有** |

6 条经营档案的明细还显示：`selling_price` **全部为 NULL**、`expected_ad_rate` **全部 0.15**、
`transport_type` **全部 sea**、最后一次写入 **2026-10-08**（距今一个多月）。

⇒ **商品中心在生产上几乎没被真正使用**：1122 个 SKU 里只有 4 个有经营档案，而且连售价都没填。
⇒ 阶段 1–3 做完，生产上**也没有真实数据能验证效果**。这件事的性质决定了阶段 1 之后要不要加
「数据补录 + 铺开」这条线（见 §13.3 Q14）。

### 11.3 回答"要不要把生产库数据复制到开发库"

**结论：不复制。** 理由（均已实测，非推测）：

| # | 理由 | 证据 |
|---|---|---|
| 1 | **开发库不空** —— 主数据早就同步过 | SKU 1125/1122、SPU 286/287、平台 5/5、仓库 5/5、档位规则 4/4、仓储规则 3/3、物流规则 6/6 |
| 2 | **该空的地方两边都空** | `sku_profit_estimates` 生产 0 / 开发 0；经营档案生产的 6 条还是空壳（售价全 NULL、费率全 0.15） |
| 3 | **表结构 100% 一致**，复制没有结构风险也没有结构收益 | 商品中心域 10 张表逐列比对：30/14/12/11/22/24/48/14/14/21 列，**全部完全一致** |
| 4 | **真人用户开发库已覆盖** | 开发库 16 个用户中 15 个生产已存在（仅 `acceptance_admin` 为本地造）；生产多出的 375 个绝大多数是审批流临时账号，对商品中心开发无用 |
| 5 | **不划算的合规成本** | 复制会把 390 人的真实姓名 / 手机号 / 邮箱带进本地环境，换不来任何数据价值 |

**唯一有价值的窄复制（仍建议不做）**：`finance.sku_operating_profiles` 的 3 条差额。
但那 3 条是空壳，复制后开发库里也只有"几个售价为空、费率都是 0.15"的记录，
**不影响阶段 1 的任何设计或验证** ⇒ 不做。

**已完成的等价动作**：直接对生产库跑 D1–D8 聚合查询（只读），拿到真实分布，
比"复制一份数据到本地再慢慢看"更快也更准。

### 11.4 后续动作

| # | 动作 | 状态 |
|---|---|---|
| 1 | D1–D8 全部核查 | ✅ 完成（2026-11-07） |
| 2 | 阶段 1 迁移 B 去掉"清洗前置"，直接加 CHECK 约束 | 待阶段 1 实施时落地 |
| 3 | **补建 Shopee 库龄档位规则** | ⏳ 需 Walter 拍板档位值（§13.3 Q13） |
| 4 | 阶段 2 增加"参考售价缺失"的降级路径（D2 = 0.36%） | 待阶段 2 实施时落地 |
| 5 | 确认商品中心在生产上的铺开状态（§13.3 Q14） | ⏳ 待 Walter 回答 |
| 6 | SSH 隧道按需开启（本机 `15433`），用完可关 | 按需 |

---

## 12. 工作量估算

**假设**：一名熟悉本仓库的后端 + 一名前端并行；估算单位为人日；不含需求沟通与上线观察期。

| 阶段 | 后端 | 前端 | 迁移 | 测试 | 小计 |
|---|---|---|---|---|---|
| 0 · B1 | — | 0.5 | — | 0.3 | **0.8** |
| 0 · B2 | — | 0.5 | — | 0.2 | **0.7** |
| 0 · B3 | — | 0.3 | — | 0.1 | **0.4** |
| 0 · B4 | 0.3 | 0.3 | — | 0.2 | **0.8** |
| 0 · B5 | — | 0.2 | — | 0.2 | **0.4** |
| 0 · B6 | 0.3 | — | — | 0.3 | **0.6** |
| 0 · C2/C5/C6 | 0.8 | 0.5 | — | 0.5 | **1.8** |
| **阶段 0 小计** | **1.4** | **2.3** | **0** | **1.8** | **≈ 5.5 人日** |
| 1 · ROI 只读层 | 1.5 | 1.0 | 0.8 | 1.2 | **≈ 4.5 人日** |
| 2 · ROI 输入判定 | 1.2 | 1.0 | 0.5 | 1.0 | **≈ 3.7 人日** |
| 3 · 降级 + 瘦身 | 0.8 | 1.5 | 0 | 0.8 | **≈ 3.1 人日** |
| 4 · 基准售价工具 | 0.8 | 1.2 | 0.6 | 0.8 | **≈ 3.4 人日** |
| 5 · 指标登记 | 0.5 | — | — | — | **≈ 0.5 人日** |
| **合计** | | | | | **≈ 21 人日** |

**关键路径**：阶段 0 → 1 → 2 → 3，约 **17 人日**。阶段 4（3.4）与阶段 5（0.5）可并行。

---

## 13. 待确认（不阻塞阶段 0）

| # | 问题 | 影响 | 现状 |
|---|---|---|---|
| Q10 | 是否立项**平台广告数据采集**（消耗 + 归因）？ | 真实广告ROI 可算、达人佣金可自动回填 | 建议立项，ROI 从"人工抄"走向"自动算"的唯一路径 |
| Q11 | 是否立项**语义层 join `bridge_erp_sku_keys`**？ | SKU 级历史成交价带 → 阶段 4 工具 4 | 建议立项，改动小、复用现成别名表 |
| Q12 | 仓储费账单采集 | 「混合成本利润」能否升级为「实际成本利润」 | 暂不立项 |
| Q13 | ~~**生产库 D1–D6 核查由谁执行**~~ | 阶段 3 迁移策略、阶段 4 排期 | ✅ **已由本次会话执行完毕**（生产库只读实测，结果见 §11.1） |
| **Q14** | **Shopee 的库龄档位规则怎么建？** | **阶段 1 的前置**：没有规则 ⇒ Shopee 全部 SKU 落进 `missing_pricing_policy` ⇒ **最低售价在 Shopee 上算不出来**。而目标 ROI 上限更高的恰恰是 Shopee（50 vs 20） | 🔴 **待 Walter 拍板**（见 §11.2②）。TikTok 那 4 档是 `platform_basis=tiktok`、源 `industry_benchmark_2026` |
| **Q15** | **商品中心在生产上是"还没正式铺开"还是"铺开了但没人录数据"？** | 决定阶段 1 之后要不要加「数据补录 + 运营培训 + 铺开」这条线。实测：1122 个 SKU 只有 **4 个**有经营档案、**售价全空**、**利润测算 0 条**、最后一次操作 2026-10-08 | 🔴 **待 Walter 回答**（见 §11.2③） |

---

## 附：与上游设计稿的对应关系

本方案**不重复定义**任何业务概念。以下为阶段 → 上游设计稿章节的对照：

| 本方案 | 上游设计稿 |
|---|---|
| §2.1 B1 | §5.4 B1 |
| §2.2 B2 | §5.4 B2 |
| §2.3 B3 | §5.4 B3 |
| §2.4 B4 | §5.4 B4 |
| §2.5 B5 | §5.4 B5 |
| §2.6 B6 | §5.4 B6 |
| §2.7 C2 | §5.2 C2 + §2.4⑤ |
| §2.8 C5/C6 | §5.2 C5/C6 + §13 Q4 |
| §3 阶段 1 | §6 阶段 1 + §2.5⑦⑨⑩⑪ |
| §4 阶段 2 | §6 阶段 2 + §2.5⑧ |
| §5 阶段 3 | §6 阶段 3 + §2.5⑩ |
| §6 阶段 4 | §6 阶段 4 + §13 Q6 |
| §7 阶段 5 | §6 阶段 5 |
| §8 改名表 | §4.1 + §4.3 |
| §10 风险册 | §12 + §5.4 |

---

## 附录 B · 阶段 0 实施记录（2026-11-06 完成）

### B.1 工作分支

| 项 | 值 |
|---|---|
| 分支 | `feature/product-center-stage0` |
| worktree | `.worktrees/product-center-stage0` |
| 起点 | `d2d4e05f`（与 main 同起点） |
| 合并回 main | **已合并**（`dea7bb1e`，快进；main 与该分支同起点，无冲突） |

> 合并前主工作区保持干净（只有其它会话的 `shop-identity-alignment-remediation.md`），本会话的全部改动只存在于本分支。
> 合并时另有一个并行会话的分支 `e18e2c75`（采集运行时探测修复），与本次改动的文件**零交集**，互不影响。
> worktree 与分支保留未删：里面还有 5 份分块测试日志作为验证证据。确认不再需要时执行
> `git worktree remove .worktrees/product-center-stage0` 与 `git branch -d feature/product-center-stage0`。

### B.2 实际改动清单（7 改 + 4 增）

| 文件 | 改动 |
|---|---|
| `scripts/sync_product_center_to_cloud.py` | 清单补 `finance.sku_pricing_policies`（17 张表，规则表置于 `sku_operating_profiles` 之前）；新增 `CRITICAL_TABLES`；**破坏性操作之前**加源表非空闸门；复制后加关键表校验；`plan`/`verify` 的表数改为动态 |
| `frontend/src/domains/business/views/ProductCenter.vue` | B1 的 9 个 `@change` + `onSpuL1CategoryChange`；`formatVolume` / `hasVolume` / `volumeMissing`；`missingVolumeSkus` 提示；`spuRowClass` 灰显；仓储规则权限门禁；SKU 状态筛选器；删「实际仓储」列、「实际物流」折进 tooltip；「重估利润/重估完整度」→「混合成本利润/混合成本完整度」；去掉 `configuration_status` 兜底 |
| `backend/domains/business/routers/product_center.py` | `list_skus` 加 `status` 参数；`cost_completeness` 固定取 `preview["expected"]` |
| `backend/services/product_profit_service.py` | `expected` 段补 `completeness` 键 |
| `backend/schemas/product_center.py` | `configuration_status` / `actual_storage_cost` 加语义注释（防再被误用）；**`ProductCenterItem` 补 `active` 字段**（B3 二次修复，见 B.7） |
| `frontend/tests/productCenterUi.test.mjs` | 改 2 条既有断言 + 新增 7 个用例 |
| `backend/tests/test_product_profit_calculator.py` | 新增 3 个用例 |
| `backend/tests/test_product_center_sync_contract.py` | **新建** 6 个用例 |
| `backend/tests/test_product_center_stage0_contract.py` | **新建** 3 个用例 |

### B.3 与原方案的差异（实施中修正）

| # | 方案原写法 | 实际改成 | 为什么 |
|---|---|---|---|
| 1 | 体积未填的 SKU **归入 `unmapped`**，不静默塞进 lines | **保留行 + 提示但不阻断**（`missingVolumeSkus` + 行上黄色边框 + 抽屉顶部 warning） | `unmapped` 非空时 `saveBatch` 会直接抛错「请先完成待映射采购单 SKU 的 ERP SKU 映射」并**卡死批次流程**，而那个抽屉里没有补体积的入口；提示文案也会误导成"映射问题" |
| 2 | `cost_completeness` 落库后加 DB CHECK 约束 | **推迟到阶段 1 迁移 B** | 加约束前必须先查生产库存量值（§11 D7/D8）并清洗；生产数据未查清前不能动。阶段 0 只做 Python 层（router 分流 + 产出侧补键 + 前端去兜底） |
| 3 | 给响应模型的 `cost_completeness` 加 pattern | **不加** | 存量行可能有被 actual_recost 段污染的值（`estimated`/`mixed`/`actual`），加了 pattern 会让响应模型校验失败 → 500。风险与收益不匹配 |
| 4 | 同步后校验放在复制完成之后 | **闸门放在 TRUNCATE 之前**，复制后只做核对 | `TRUNCATE` 一旦提交就撤不回来；"复制后发现源表是空的"已经无法挽回。正确做法是**源表空就拒绝开始** |
| 5 | 仓储规则按钮 `disabled + tooltip` | **整列 `v-if`** | 与仓库既有范式一致（`:182`、`:332` 定价设置按钮都是 `v-if`）；这 4 个按钮全都要 admin/manager/finance，留一列空操作列是噪音 |
| 6 | B3 只改前端（`include_inactive` + 灰显） | **前端 + 后端响应模型同时改** | 复查发现：前端多处依赖 `row.active`，但 `ProductCenterItem` **从来没有这个字段** ⇒ `/api/spus` 响应从不下发 `active` ⇒ 灰显、`恢复` 按钮、`删除` 禁用、选中过滤**全部恒为 false**。只改前端等于什么都没修。详见 B.7 |

### B.4 实施中新查实的事实

| 事实 | 影响 |
|---|---|
| `finance.sku_pricing_policies` **没有任何外键** | B6 的失效机理不是"被清空"而是"**从未被同步过**" → 云端停在空表或旧规则。旧规则更隐蔽（表面正常但底线算错）。已回写上游设计稿 §5.4 B6 |
| `expected` 段以前**根本没有** `completeness` 键 | `section.get("completeness", "complete")` 在 estimated 版本**恒为 "complete"**，在 actual_recost 版本写 `estimated/mixed/actual` → 同列两种语义 + 违反 schema pattern。已补键 + 按 basis 分流 |
| `core.dim_erp_sku.status` 有索引（`ix_dim_erp_sku_status`），实际值 `active`(1122) / `inactive`(3) | B4 的筛选器可直接走索引；选项就这两个 |
| `core.dim_spu.active` = True 283 / **False 3** | 确认生产确有 3 个软删 SPU，B3 的「恢复不可达」是真问题不是理论风险 |
| `dim_platforms` **没有广告费率默认列** | 开发库那 3 个 `expected_ad_rate=0.15` 是**人工填的**（`created_by=4`，同一用户），不是系统默认 |
| 仓库的 lint 门禁 `scripts/run_lint.py` **只跑 ruff**（Python），CI 不跑前端 eslint | `ProductCenter.vue` 有 928 个既有 eslint 错误（双引号/分号风格与 eslint 配置冲突），不是门禁项。新增代码**保持与文件既有风格一致**，不单独改成单引号 |

### B.5 验证结果

| 检查 | 结果 |
|---|---|
| `node --test frontend/tests/productCenterUi.test.mjs` | **36 passed / 0 failed**（含新增用例） |
| `pytest` 商品中心域 **16 个相关文件** | **213 passed / 1 failed** |
| └ 那 1 条失败 | `test_product_category_contract.py::test_profit_save_uses_the_preview_version_when_the_client_does_not_supply_one` —— **pre-existing**，main 上同样失败（`product_finance_service.py` 未被本次改动触碰，`git diff` 为空）。根因：源码里该表达式被换行拆成两行，而断言要求单行 |
| `pytest backend/tests` **全量**（570 文件 / 3772 用例，5 进程并行分块） | **3638 passed / 110 failed / 7 skipped / 22 errors** |
| └ 与 main 基线逐条对比 | **失败清单完全一致**，无一条新增（详见 B.8） |
| `ruff check`（7 个改动文件） | **All checks passed** |
| `npx vite build` | **✓ built in 15.32s**，ProductCenter chunk 73.18 kB 正常产出 |
| `npx eslint` | 950（基线 928，Δ22 全部是 `quotes`/`semi`/`comma-dangle` 风格类，与文件既有风格一致，eslint 非 CI 门禁） |
| 迁移 | **无迁移**（阶段 0 是纯代码改动） |

### B.6 遗留

- ~~**§11 的 D1–D8 生产库数据核查仍未做**~~ → ✅ **已于 2026-11-07 完成**（生产库只读实测），结果见 §11.1，带出三个新结论见 §11.2。
- 阶段 1–5 的代码尚未开始。
- **新增遗留（见 §11.2）**：① Shopee 库龄档位规则缺失，需拍板档位值（Q13）；② 商品中心在生产上基本没启用，需确认是否要加"数据补录 + 铺开"这条线（Q14）；③ 阶段 2 需为"参考售价缺失"（生产仅 0.36% 覆盖）设计降级路径。

### B.7 复查阶段的二次发现：B3 的「恢复」按钮此前根本不可达

**发现路径**：最终 diff 复查时逐个核实前端每个判断的数据来源，发现前端 SPU 表格有 5 处依赖 `row.active`：

| 位置 | 用途 |
|---|---|
| `ProductCenter.vue:135` | `v-if="row.active === false"` → 显示「恢复」按钮 |
| `ProductCenter.vue:143` | `:disabled="row.__new \|\| row.active === false"` → 已软删行禁用「删除」 |
| `ProductCenter.vue:1753` | `onSpuSelectionChange` 过滤掉已软删行 |
| `ProductCenter.vue:1885` | 批量软删只取在售行 |
| `ProductCenter.vue:1821` | `handleRestoreSpu` 的前置守卫 |

**但后端从不下发这个字段**：`ProductCenterItem`（`backend/schemas/product_center.py:237`）没有 `active`，
`list_spus` 用 `ProductCenterItem.model_validate(row)` 序列化 → Pydantic 只保留 schema 里声明的字段 → `active` 被丢弃。

**后果**：即使前端请求了 `include_inactive=true` 把已软删 SPU 列出来，它们在 UI 上：

- 看起来和在售品**一模一样**（不灰显）；
- **没有「恢复」按钮**（条件恒 false）；
- 仍能被选中、仍能被再次软删。

也就是说：**软删实际上是不可逆的**——这正是 B3 要修的缺陷，但第一版只改了前端，等于没修。

**修复**：`ProductCenterItem` 增加 `active: Optional[bool] = None`。

- `from_attributes=True` 会自动从 `DimSpu.active` 取值（`modules/core/db/schema_parts/dimensions.py:176`）；
- SKU 行没有 `active` 列（SKU 用 `status`），取默认值 `None`，不影响 `list_skus`；
- `ProductCenterItem` **纯粹是响应模型**（`list_spus` / `list_skus` / `create_*` / `update_*` / `bulk_*` 的 `response_model`），
  批量保存的入参用的是独立的 `SpuBulkItem` / `SkuBulkItem` → 加字段**不会**让批量接口多接受一个可写 `active`；
- 已有护栏用例 `test_product_center_item_validates_bare_orm_row`（校验裸 `DimErpSku` 行）不受影响。

**新增回归用例**：

| 用例 | 断言 |
|---|---|
| `test_spu_response_carries_active_flag` | `DimSpu(active=False)` → `item.active is False`；`DimSpu(active=True)` → `True` |
| `test_sku_response_active_stays_none` | `DimErpSku(status="active")` → `item.active is None`（不报错、也不误取 status） |
| 前端 `SPU 列表带出已软删的行，软删可恢复` | 断言「恢复」按钮条件与 `spuRowClass` 确实以 `row.active` 为准，防止有人把条件改成 `!row.active` 之类 |

### B.8 全量验证的执行方式（并行分块）

单进程跑 `backend/tests` 全量（570 个测试文件 / 3772 个用例）速率约 **15 用例/分钟**，
且 `backend/tests/conftest.py` 在**模块导入时**就拉起一次性 PostgreSQL 容器
（`:102`），`pg_engine` 又是 session 级 fixture 会**再拉一个**（`:288`）——
两个容器常驻、`create_all` 建全套 schema，单进程墙钟 4 小时以上。

**改为 5 个 pytest 进程并行分块**（按文件名排序后等分，每块 114 个文件）：

| 关注点 | 结论 |
|---|---|
| 分块是否会互相干扰 | 不会：每块是独立进程，各自起自己的隔离库（随机端口 + ryuk 回收），`backend/tests/data_pipeline` 与 `archive` 按原口径排除 |
| 块内卡死怎么定位 | 逐块单独跑，卡住时看该块日志末尾即可定位到具体文件 |
| 为什么必须全量 | 阶段 0 改了**共享**的 `product_center` 路由与 `product_profit_service`，响应模型字段变更会影响所有引用它们的契约测试；只跑商品中心子集不足以证明没有回归 |

对照基线：分块跑出来的失败清单，回到 **main（`d2d4e05f`）** 同文件复跑，确认均为 pre-existing。

**对照结果**（分块口径一致：worktree 的分块清单直接映射到 main，只过滤掉 main 里没有的 2 个新测试文件）：

| 分块 | worktree | main 基线 | 失败清单差异 |
|---|---|---|---|
| 1 | 15 failed / 831 passed | 14 failed / 832 passed | 多 1 条 → **worktree 专属** |
| 2 | 19 failed / 615 passed | 18 failed / 616 passed | 多 1 条 → **worktree 专属** |
| 3 | 10 failed / 700 passed | 10 failed / 700 passed | 无 |
| 4 | 11 failed / 772 passed | 11 failed / 758 passed | 无（差 14 = 本次新增用例数） |
| 5 | 57 failed / 718 passed | 57 failed / 718 passed | 无 |
| **合计** | **3638 passed / 110 failed / 7 skipped / 22 errors** | **3624 passed / 110 failed / 7 skipped / 22 errors** | **0 条新增失败** |

**两条 worktree 专属失败的根因（都不是代码问题，是 worktree 不含未跟踪的本地文件）**：

| 用例 | 根因 | 处理 |
|---|---|---|
| `test_collection_frontend_contracts.py::test_utf8_editor_guardrails_are_declared` | 读 `.vscode/settings.json`（`.gitignore:109`，纯本地编辑器配置），worktree 里没有 → `FileNotFoundError` | 把 main 的该文件复制进 worktree → 30 passed |
| `test_data_sync_governance_status_consistency.py::test_governance_detailed_coverage_skips_temp_development_sample_files` | `temp/development/shopee_products_daily_20250128_case3.xlsx` 是**未跟踪**的本地样本文件（`temp/` 下 git 跟踪 0 个文件），治理覆盖率按磁盘路径存在与否判定"待处理文件数" → worktree 缺文件 ⇒ 组合被归入归档桶 ⇒ `covered` 为空 | 把该样本文件复制进 worktree → 3 passed |

**这两条补齐后，worktree 与 main 的失败清单逐条完全一致 —— 阶段 0 没有引入任何回归。**

### B.9 阶段 0 已识别的既有失败（不属于本次改动，但建议单独排期）

全量跑出来的 110 条失败里有几类是**仓库既有的结构性问题**，阶段 0 不修，但值得记一笔：

| 类别 | 例子 | 性质 |
|---|---|---|
| 断言写死了源码的**单行**排版，源码被格式化器换行后就失效 | `test_product_category_contract.py::test_profit_save_uses_the_preview_version_when_the_client_does_not_supply_one` | 测试脆弱性，源码没变也会红 |
| 断言依赖**本地未跟踪文件** | `test_collection_frontend_contracts.py`、`test_data_sync_governance_status_consistency.py` | CI 上必然与本地不一致 |
| Shopee 导出组件用例大面积失败 | `test_shopee_products_export_component.py`（约 40 条） | 组件 locator 行为与用例假设不符 |
| alembic rehearsal 失败 | `test_schema_cleanup_rehearsal.py`、`test_sync_progress_submitted_status_migration_contract.py` | `alembic upgrade head` 在隔离库上失败 |
| SQLite 建表报 `unknown database ops` | `test_task_center_*.py`（17 条 ERROR） | 仓库用 PG 命名空间，SQLite 建不出来（conftest 注释里已承认 `sqlite_session` 一直是坏的） |
| 前端契约断言中文乱码 | `test_hr_performance_adjustment_frontend_contract.py` 等 | 断言串是 GBK/mojibake，与 UTF-8 源文件不匹配 |
