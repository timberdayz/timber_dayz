# 商品中心优化实施方案

> 状态：**待评审** —— 阶段 0 已获批准，可立即开工
> 日期：2026-11-06
> 上游设计稿：`docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md`（**术语与口径的唯一权威**，本方案不重复定义，只负责"怎么改"）
> 范围：`frontend/src/domains/business/views/ProductCenter.vue`、`frontend/src/api/productCenter.js`、`backend/domains/business/routers/product_center.py`、`backend/schemas/product_center.py`、`backend/services/{product_profit_service,product_finance_service,product_pricing_service}.py`、`modules/core/db/schema_parts/{dimensions,business}.py`、`current_migrations/versions/`、`scripts/sync_product_center_to_cloud.py`
> 关联：`2026-10-20-sku-pricing-guardrails-design.md`（最低售价与定价纪律）、`docs/team-skills/sea-metrics-language/`（指标口径治理）

---

## 0. 执行摘要

**一句话**：商品中心从「只管价格下限」升级为「价格下限 + 广告投放边界」，分 6 个阶段落地（阶段 2 含 2.1/2.2 两小节，共 7 段工作），其中**阶段 0 零业务语义变更、可以独立上线**。

| 阶段 | 内容 | 产出 | 依赖 | 风险 | 可独立上线 |
|---|---|---|---|---|---|
| **0** | 稳定性修复 | 8 个缺陷修复（静默丢数据、崩溃、软删不可逆、同步缺表） | 无 | 低 | ✅ |
| **1** | ROI 只读层 | 保本ROI / 建议ROI / 广告前贡献毛利率 三列 | 0 | 低 | ✅（但**必须在 0 之后**） |
| **2.1** | **底线下沉到平台** | **每个平台一条底线**（新建 `finance.sku_platform_pricing` + 8 处消费方切平台口径） | 1 | **高**（数据模型变更） | ✅（可与 2.2 分别上线） |
| **2.2** | ROI 输入与判定 | 目标ROI / 平台报告ROI 两列 + 三色判定 | 2.1 | 低 | ✅ |
| **3** | 广告分成率降级 + 字段瘦身 | 手填口收敛为一个；删 3 列、折叠 2 列 | 2.2 | 中 | ✅（保留手填入口即可回退） |
| **4** | 基准售价工具 | 来源枚举 + 确认日期 + 即时影响预览 + 偏差校验 | **2.1**（纪律线的平台口径依赖底线平台化） | 低 | ✅ |
| **5** | 指标口径登记 | `sea-metrics-language` 登记 | 1 | 低 | ✅（纯文档） |

**三条铁律**：

1. **阶段 1 之前必须先修 B1/B2/B3。** 否则新列上线时运营改字段照样丢数据（`saveSpuRows`/`saveSkuRows` 只提交 dirtyRows）。
2. **阶段 3 不能一步到位。** 直接取消广告费率手填会让存量 SKU（无目标ROI）广告成本变 None → 利润空白，比现在更糟。必须经过阶段 1–2 的过渡期。
3. **新增列全部可空。** 任何阶段都不允许出现"运营不填新东西就用不了旧功能"。

> **阶段 2.1 是 2026-11-07 新增的**（Walter 拍板，见 §4.1）：生产库实测发现所有平台的底线都用
> TikTok 的费率算，Shopee 底线被低估 34.6%–74.3% ⇒ 护栏放行本该拦住的品 ⇒ 有真亏本风险。
> 它是本方案唯一的**数据模型变更**，也是唯一**必须早于阶段 4** 的新增约束。

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
    ┌─────────▼──────────────────┐
    │ 阶段 2.1  底线下沉到平台      │  ← 数据模型变更，先于 2.2
    │ 每平台一条底线 + 8 处消费方   │     （有实打实的亏本敞口）
    └─────────┬──────────────────┘
              │
    ┌─────────▼──────────┐
    │ 阶段 2.2 ROI 输入判定 │
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
⚠️ **阶段 4 依赖阶段 2.1**：基准售价是**纪律线**的基数，而纪律线属于底线体系 ⇒ 底线平台化没做完，
纪律线的平台口径仍然是错的（§11.2② 实测偏低 34.6%–74.3%）。所以阶段 4 **不能早于 2.1 发布**。

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

**迁移 A** `current_migrations/versions/20261113_add_platform_roi_config.py`

```python
revision = "current_schema_20261113_add_platform_roi_config"
down_revision = "current_schema_20261112_realign_identity_candidates_anchor"
```

> ⚠️ **实施时改了日期**（2026-11-12 → 2026-11-13 / 2026-11-14）：`20261112` 这个日期前缀
> 已被另一条会话的 `20261112_realign_identity_candidates_anchor.py` 占用（它把迁移链的
> head 推到了 `current_schema_20261112_realign_identity_candidates_anchor`）。
> 日期前缀重复不会冲突（唯一性只看 revision id），但同一目录里两个 `20261112_` 开头的
> 文件会让人以为它们是一对。**down_revision 必须指向真实 head**，所以照抄本文档会失败。

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

**迁移 B** `current_migrations/versions/20261114_add_sku_roi_columns.py`

```python
revision = "current_schema_20261114_add_sku_roi_columns"
down_revision = "current_schema_20261113_add_platform_roi_config"
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

## 4. 阶段 2 · 底线下沉到平台 + ROI 输入与判定

> **阶段 2 在 2026-11-07 扩为两小节**：4.1 是 Walter 拍板的**底线下沉到「SKU × 平台」**（数据模型变更），
> 4.2–4.4 是原有的 ROI 输入与判定。两小节**可分别上线**（4.1 先上，因为它有实打实的亏本敞口）。
> 章节号与既有交叉引用**不变**（阶段 2 的三小节编号顺延即可）。

### 4.1 底线下沉到「SKU × 平台」（Walter 2026-11-07 拍板）

**为什么必须做**（证据见 §11.2② 的生产库实测）：

- 底线 / 成本线 / 纪律线是 **SKU 级**概念，但底线公式里的**平台成本率按平台不同**
  （`other_cost_rate`：Shopee 41.65% vs TikTok 27.27%；达人佣金：TikTok 6.06% vs Shopee 1.11%）。
- 现在 `product_pricing_query_service.py:49-50` 取**规则表固定 basis 平台**（当前 `tiktok`）的费率
  ⇒ **所有平台的底线都用 TikTok 的成本结构算**。
- 实测后果：同一个 SKU `166851422928` 在 Shopee 与 TikTok 上底线完全一样（59.29），
  而按 Shopee 真实费率应是 **103.36**，**偏低 44 元（74.3%）**。
- 方向是**偏松** ⇒ 护栏「预计售价低于最低售价」在 Shopee 上**放行本该拦住的品 ⇒ 真亏本风险**。
- 且**底线与利润测算两边口径不一致**（利润测算按所选平台取费率，见 `product_center.py:2592-2597`）。

**目标**：底线从 SKU 级下沉到 **SKU × 平台**级，每个平台按自己的费率算自己的底线。

#### 4.1.1 数据模型

**① 新建 `finance.sku_platform_pricing`**（SKU × 平台）

⚠️ **不要**塞进 `finance.sku_operating_profiles`：它的唯一键是
`(sku_id, platform_code, warehouse_code)`（`business.py:1205-1217`），
**同一平台多个仓会有多条档案**，底线放进去会重复。

| 列 | 类型 | 说明 |
|---|---|---|
| `pricing_id` | int PK | |
| `sku_id` | int FK → `core.dim_erp_sku` | NOT NULL |
| `platform_code` | str FK → `core.dim_platforms` | NOT NULL |
| `min_selling_price_override` | Numeric(18,2) null | **人工覆盖**（从 `dim_erp_sku` 下沉而来） |
| `min_selling_price_source` | str(32) null | 最后一次写入的来源标记 |
| `pricing_tier_label` / `pricing_days_since_restock` / `pricing_tier_source` | | 派生快照 |
| `created_at` / `updated_at` / `updated_by` | | |

约束：`UNIQUE (sku_id, platform_code)`。

> **注意**：系统算出的 `min_selling_price` **不入库** —— 现在 `core.dim_erp_sku` 也没有这一列
> （只有 `min_selling_price_override`，`dimensions.py:220`），底线是查询时派生的。
> 新表与现状对称：**只存人工覆盖 + 派生快照**。

**② `core.dim_erp_sku.min_selling_price_override` 保留一个版本周期（deprecated）**

- 读路径：**全部切到新表**；新表无行时回落到旧列（兼容历史数据）。
- 写路径：新表优先。
- 迁移回填：把旧列的值**复制到该 SKU 所有经营档案出现过的平台**。
- 下个大版本删列（删列单独一个迁移，不与本阶段混在一起）。

> ⚠️ **实施调整（2026-11-07）**：**写路径没有在本阶段下沉**，拆到**阶段 2.1b**
> （覆盖值按平台分行 + SKU 资料页按平台分行 + 删 SKU 级旧列）。
> 理由：生产库与开发库的 `min_selling_price_override` **均为 0 条** ⇒ 没有运营在用 ⇒
> 本阶段先只做读路径 + 回落链（新表 → 旧列），行为对运营**完全不变**，
> 风险最小；等真有人开始按平台调价时再动写入路径。
> 详见附录 D.2。

**③ `ops.price_adjust_baselines` 主键下沉**

现主键是 `sku_id`（`collection.py:1220`）⇒ 改成 `(sku_id, platform_code)` 复合主键。
迁移：加列 `platform_code` → 老行按该 SKU 的经营档案回填（无经营档案的 SKU 落 `platform_basis`）→
建复合唯一约束。

#### 4.1.2 取数与计算层

| 改动 | 位置 | 说明 |
|---|---|---|
| `load_pricing_context` 返回 `platforms: {platform_code: DimPlatform}` | `product_pricing_query_service.py:34-60` | 现在只返回一个 `platform`；改为按需取多行。**不再有"basis 平台"这个概念** |
| `_compute_pricing_for_sku` 增 `platform_code` 参数 | `product_pricing_query_service.py:100-130` | 按该平台的 `other_cost_rate` / `default_creator_commission_rate` 算 |
| 纯函数 `compute_sku_pricing` **不改** | `product_pricing_service.py:120-147` | 它本来就吃标量费率（`other_cost_rate` / `platform_creator_commission_rate`），**这层天然平台无关** —— 这是本改法成本低的关键 |

#### 4.1.3 消费方（全部要跟着改，共 8 处）

| # | 消费方 | 位置 | 怎么改 |
|---|---|---|---|
| 1 | SKU 列表的定价字段 | `product_center.py` `list_skus` | SKU 资料 tab 是 SKU 级的，**底线的展示移到利润测算 tab**（那里已经是平台级）；SKU 资料 tab 只留"人工覆盖"，按平台分行 |
| 2 | 利润测算候选列表的 `min_selling_price_below` | `product_center.py:2629-2634` | 候选列表本就带 `platform_code` ⇒ 直接用该平台的底线 |
| 3 | 保存拦截的护栏 | `product_center.py:1176-1192` `_compute_sku_min_selling_price` | 签名加 `platform_code` |
| 4 | 草稿/版本落库的护栏 | `product_center.py:2749-2760` | 同上，请求体已带平台 |
| 5 | 最低售价变更通知 | `price_adjust_notify_service.py` + `price_adjust_notify_tasks.py` | 基线粒度 → `(sku_id, platform_code)`；归因上下文加 `platform_code` |
| 6 | 飞书投影 | `feishu_projection_service.py:388-430` | 调价记录加"平台"列 |
| 7 | 库存清货排名 | `sku_clearance_service.py`（12 处引用）+ `sql/api_modules/sku_clearance_ranking_module.sql` | 清货是"这个 SKU 在这个平台降多少" ⇒ 按平台出 |
| 8 | 前端 | `ProductCenter.vue`（31 处）+ `InventoryAging.vue`（2 处） | 最低售价列移到利润测算 tab；人工覆盖按平台 |

> ⚠️ **实施调整（2026-11-07）**：第 1、8 项的「把最低售价列移走」**没有照做** ——
> SKU 资料页保留「最低售价」列，改为**加一个「底线按平台」选择器**（列表按所选平台取底线）。
> 理由：运营现在就在这一页看底线并做人工覆盖，把列搬走等于砍掉他们已有的工作流；
> 加选择器同样能把「平台口径」显式化，成本更低、风险更小。详见附录 D.2。
>
> ⚠️ **实施调整（2026-11-07）**：第 7 项「清货按平台出」的**前提不成立** ——
> 清货视图的 `platform_code` 来自 `mart.inventory_state`，生产库 1232 行**恒为** `'miaoshou'`
> （库存来源平台），**不是销售渠道** ⇒ 按行平台查销售平台费率查不到 ⇒
> 成本线算不出 ⇒ **底线整个消失**（只剩纪律线）。
> 底线比口径不一致更危险，所以改成两级取费率（行平台是销售平台就用它自己的，
> 否则回落公司级费率 ⇒ 与改造前**完全一致**）。详见附录 D.2。


**Schema**：`backend/schemas/product_center.py`（14 处）、`backend/schemas/inventory.py`（3 处）要加平台维度字段。

#### 4.1.4 迁移

`current_migrations/versions/20261115_add_sku_platform_pricing.py`（幂等范式：`_has_table` / `_has_column` / `_has_index` 守卫，
`upgrade` 与 `downgrade` 都写）。**本阶段有 DDL 变更** —— 仓库规矩是 ORM SSOT 在
`modules/core/db/schema_parts/`，迁移只负责把库里已有的表对齐到 SSOT。

#### 4.1.5 阶段 2.1 测试清单

- 同一 SKU 在两个平台 ⇒ **两条底线**，按各自费率算
- `load_pricing_context` 返回两个平台的费率
- 人工覆盖：SKU 级旧列 → 新表读写回退路径
- 通知基线：`(sku_id, platform_code)` 粒度；一个平台变价**不**触发另一个平台的变更通知
- 迁移幂等：跑两次不报错；`downgrade` 能回退
- 护栏：Shopee 底线 > TikTok 底线（回归 §11.2② 的实测偏差）

#### 4.1.6 阶段 2.1 回滚

| 项 | 回滚动作 |
|---|---|
| 新表 | `DROP TABLE finance.sku_platform_pricing`（幂等） |
| `dim_erp_sku.min_selling_price_override` | **不动**（本阶段只读不删）⇒ 回滚零风险 |
| `ops.price_adjust_baselines` | 复合主键改回 `sku_id`（迁移的 `downgrade`） |
| 读/写路径 | 靠开关或直接回退代码（读路径有"新表无行 → 回落旧列"的兼容分支） |

### 4.2 后端（ROI 输入与判定）

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

### 4.3 前端 · 2 个手填列 + 三色判定

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

### 4.4 阶段 2 测试（ROI 输入与判定部分）

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
5. 阶段 2.1 迁移（平台定价表 + 基线复合主键）→ upgrade → 验证 → 发布
6. 阶段 2.1 代码（8 处消费方切平台口径）  → 验证 → 发布
7. 阶段 2.2 迁移 → 阶段 2.2 代码
8. 阶段 3 代码（独立发布）
9. 阶段 4（**必须在阶段 2.1 之后**，见 §1.1 的依赖说明）
10. 阶段 5（纯文档）
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

**② 底线计算的平台成本率取自「规则表的单一 basis 平台」，不是 SKU 实际在卖的平台**（B7）

> ⚠️ **本节最初写成「Shopee 完全没有库龄档位规则」，那是错的，已撤回。**
> Walter 指出库龄档位规则是公司级的 —— 查证属实：
> `SkuPricingPolicyBase` 的 docstring 就写着「库龄档位定价纪律规则（**公司级**）」；
> `load_current_policies` 的谓词（`sku_pricing_policy_service.py:31-35`）只有
> `status='active' AND effective_to IS NULL AND effective_from <= today`，**没有任何平台过滤**。
> ⇒ 4 条规则对所有平台生效，**Shopee 并不缺规则**。

**但同一层核查翻出另一个真缺陷：平台费率被写死成单一 basis 平台。**

`backend/services/product_pricing_query_service.py:49-50`：

```python
basis = policy_rows[0]["platform_basis"] if policy_rows else "tiktok"
platform = await db.get(DimPlatform, basis)
```

⇒ 规则虽然是公司级的，但**底线计算用的平台成本率**，一律取 `policy_rows[0]` 那一行的
`platform_basis` 所指平台。生产库 4 条规则的 `platform_basis` **全是 `tiktok`** ⇒
**所有平台（含 Shopee）的底线都用 TikTok 的费率算。**

生产库 `core.dim_platforms` 实测费率差异：

| 平台 | `other_cost_rate`（已含平台佣金） | 达人佣金率 | `default_fee_rate` |
|---|---|---|---|
| **tiktok**（= 当前 basis） | 0.2727 | 6.06% | 7.37% |
| **shopee** | **0.4165** | **1.11%** | 14.87% |
| amazon | NULL | NULL | NULL |
| miaoshou（source 角色） | NULL | NULL | NULL |

成本线公式（`product_pricing_service.py:52-62`，模块头注释明确「平台佣金率已包含在
`other_cost_rate` 内，不得单独进入分母」）：

```
成本线 = 采购成本 ÷ (1 − other_cost_rate − 达人佣金率 − 货损率 − 破损率 − 目标利润率)
```

⇒ 用生产真实数据算出来的偏差（`sku_operating_profiles` 6 条逐条）：

| 平台 | SKU | 采购成本 | 当前底线（用 TikTok 费率） | 应得底线（用本平台费率） | 差额 | 偏差 |
|---|---|---|---|---|---|---|
| **shopee** | `HJJ-XH-DM-004` | 11.00 | 30.00 | **40.38** | +10.38 | **+34.6%** |
| **shopee** | `166851422928` | 20.00 | 59.29 | **103.36** | +44.07 | **+74.3%** |
| tiktok | `166851422928`（同一 SKU） | 20.00 | 59.29 | 59.29 | 0.00 | 0% |

**最刺眼的一条：同一个 SKU `166851422928`，在 Shopee 和 TikTok 上算出的最低售价一模一样（59.29）** ——
因为费率根本没跟着平台走。Shopee 的真实成本结构更重（`other_cost_rate` 高 14.38 个百分点），
底线本该是 103.36，**现在被低估了 44 元（44%）**。

**方向是偏低（过松）⇒ Shopee 商品按一个偏松的底线放行，存在真亏本的风险。**
同时这套系统里**两边口径还不一致**：

| 路径 | 费率来源 | 是否按实际平台 |
|---|---|---|
| 利润测算（ROI / 利润试算） | 请求里的 `platform_code` → `dim_platforms`（`product_center.py:2592-2597`） | ✅ 是 |
| 最低售价 / 成本线 / 纪律线 | 规则表的 `policy_rows[0]["platform_basis"]` | ❌ **否** |

⇒ **同一个 SKU，底线按 TikTok 算、利润按 Shopee 算，两边数字对不上。**

**处置**：这是阶段 1 的前置（阶段 1 的 ROI 层直接建立在成本线与底线之上，费率口径不对，
ROI 算出来的保本 ROI 也会跟着错）。改法有两个方向，见 §13.3 Q14。

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

**Walter 的说明（2026-11-07）**：「我们最近一直在测试，一直发现问题在优化」——
⇒ 这**不是**"没铺开"，而是**还在测试迭代期**，数据少是必然结果，不是运营不用。
⇒ 结论：**不追加「数据补录 + 培训 + 铺开」这条线**（那是正式投用后的事）；
阶段 1–3 的目标就是**把功能修对，让测试能继续往下推进**。Q15 关闭。

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
| **2.1 · 底线下沉到平台** | **3.0** | **2.5** | **1.5** | **2.5** | **≈ 9.5 人日** |
| 2.2 · ROI 输入判定 | 1.2 | 1.0 | 0.5 | 1.0 | **≈ 3.7 人日** |
| 3 · 降级 + 瘦身 | 0.8 | 1.5 | 0 | 0.8 | **≈ 3.1 人日** |
| 4 · 基准售价工具 | 0.8 | 1.2 | 0.6 | 0.8 | **≈ 3.4 人日** |
| 5 · 指标登记 | 0.5 | — | — | — | **≈ 0.5 人日** |
| **合计** | | | | | **≈ 30.5 人日** |

**关键路径**：阶段 0 → 1 → **2.1** → 2.2 → 3，约 **26 人日**。阶段 4（3.4）与阶段 5（0.5）可并行，
但**阶段 4 不能早于 2.1 发布**（纪律线的平台口径依赖底线平台化，见 §1.1）。

> **阶段 2.1 为什么这么贵**：它是本方案里唯一的**数据模型变更**，牵动 8 处消费方
> （护栏 / SKU 列表 / 候选列表 / 变更通知 / 飞书投影 / 库存清货 / 两个前端页面），
> 外加 `ops.price_adjust_baselines` 的**复合主键变更**。

---

## 13. 待确认（不阻塞阶段 0）

| # | 问题 | 影响 | 现状 |
|---|---|---|---|
| Q10 | 是否立项**平台广告数据采集**（消耗 + 归因）？ | 真实广告ROI 可算、达人佣金可自动回填 | 建议立项，ROI 从"人工抄"走向"自动算"的唯一路径 |
| Q11 | 是否立项**语义层 join `bridge_erp_sku_keys`**？ | SKU 级历史成交价带 → 阶段 4 工具 4 | 建议立项，改动小、复用现成别名表 |
| Q12 | 仓储费账单采集 | 「混合成本利润」能否升级为「实际成本利润」 | 暂不立项 |
| Q13 | ~~**生产库 D1–D6 核查由谁执行**~~ | 阶段 3 迁移策略、阶段 4 排期 | ✅ **已由本次会话执行完毕**（生产库只读实测，结果见 §11.1） |
| **Q14** | ~~底线计算的平台成本率要不要改成「按 SKU 实际平台取」？~~ | 阶段 2.1 的范围 | ✅ **已由 Walter 拍板（2026-11-07）**：选**最彻底**的方案 —— **底线下沉到「SKU × 平台」，每个平台一条底线**。方案见 §4.1（新建 `finance.sku_platform_pricing` + 8 处消费方切平台口径 + `ops.price_adjust_baselines` 复合主键）。⚠️ 原设计的「阶段 2」因此**扩为 2.1（底线下沉）+ 2.2（ROI 输入判定）**，工作量由 ≈21 人日增至 **≈30.5 人日** |
| ~~Q15~~ | ~~商品中心在生产的铺开状态~~ | — | ✅ **已由 Walter 答复关闭**（2026-11-07：「一直在测试，一直发现问题在优化」）⇒ 不追加「数据补录 + 铺开」这条线，阶段 1–3 专注把功能修对 |

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
| **§4.1 阶段 2.1 底线下沉** | **§5.4 B7**（底线取单一 basis 平台费率）+ §11.2② 的生产库实测 |
| §4.2–4.4 阶段 2.2 | §6 阶段 2 + §2.5⑧ |
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
- **新增遗留（见 §11.2）**：① **底线计算的平台成本率取自单一 basis 平台**（B7），Shopee 底线被低估 34.6%–74.3%，改法待拍板（Q14）；② 阶段 2 需为"参考售价缺失"（生产仅 0.36% 覆盖）设计降级路径。
- **已关闭**：~~商品中心在生产上基本没启用，需确认是否要加"数据补录 + 铺开"这条线~~ → Walter 答复「一直在测试、一直发现问题在优化」⇒ 不追加该线（§11.2③）。

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

---

## 附录 C · 阶段 1 实施记录（2026-11-07 完成）

### C.1 改动清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `backend/services/product_roi_service.py` | **新建**：纯函数模块 `compute_roi_metrics` |
| 2 | `backend/services/product_profit_service.py` | `_ad_cost_and_profit` 多返回 `pre_ad_profit`；`build_platform_profit_preview` 新增 `roi_safety_margin`/`target_roi_ceiling` 入参并**在内部算 ROI**；`expected`/`actual_recost` 段各带一份 ROI 指标 |
| 3 | `backend/services/product_finance_service.py` | `preview_platform_sku_profit` 传平台 ROI 配置、带出 `expected_selling_price_source` / `roi_safety_margin` / `target_roi_ceiling` |
| 4 | `backend/domains/business/routers/product_center.py` | 候选列表同样传平台 ROI 配置并带出三个顶层字段 |
| 5 | `backend/schemas/product_center.py` | `PlatformSkuProfitCandidateResponse` 增 3 个顶层字段（**漏声明会被 `extra='ignore'` 静默丢弃**） |
| 6 | `modules/core/db/schema_parts/dimensions.py` | `core.dim_platforms` 增 `roi_safety_margin` / `target_roi_ceiling` / `target_roi_floor` + 3 个 CHECK |
| 7 | `modules/core/db/schema_parts/business.py` | `finance.sku_operating_profiles` 增 `expected_selling_price_source`；`finance.sku_profit_estimates` 增 `expected_selling_price_source` + 4 个 ROI 列；**C2 的 2 个完整度 CHECK 收口** |
| 8 | `current_migrations/versions/20261113_add_platform_roi_config.py` | **新建**：平台 ROI 配置 + 回填 TikTok 20 / Shopee 50 |
| 9 | `current_migrations/versions/20261114_add_sku_roi_columns.py` | **新建**：业务列 + C2 约束（先清洗存量再加约束） |
| 10 | `frontend/src/domains/business/views/ProductCenter.vue` | 3 个只读列 + 成本完整度守卫 + 2 条免责提示 + 缺资料标签抽成共用 map |
| 11 | `backend/domains/business/routers/product_center.py`（保存路径） | 利润版本落库时写入 4 个 ROI 列 + `expected_selling_price_source`；经营档案记 `expected_selling_price_source`；利润版本查询接口回读 |

### C.1.1 列加了还不够，得有人写

第 7/9 项加的列如果只有 schema 没有写入路径，就是**空壳** —— 运营投的那个 ROI
事后仍然无从解释。所以：

- `POST /api/platform-sku-profit/estimates` 保存利润版本时，把 **本 section 自己的**
  ROI 写进 `finance.sku_profit_estimates`（estimated 段与 actual_recost 段各算各的 ——
  两段成本口径不同，ROI 也不该混）。
- `finance.sku_operating_profiles` 记 `expected_selling_price_source`
  （`user_input` / `sku_reference`）：运营自己填的价和 SKU 参考售价兜底的价，
  在利润表里长得一样，在 ROI 判定里可信度不同，必须留痕。
- `GET /api/platform-sku-profit/estimates` 回读这 4 个 ROI 字段与来源。

`expected_selling_price_source` 在候选列表里的取值优先级：
**经营档案里记下来的来源** → 老档案没记过时退化成 `profile` → 都没有时按 SKU 参考售价记 `sku_reference`。

### C.2 三处与原方案不同的地方（实施时修正）

1. **ROI 在 `build_platform_profit_preview` 内部算，不在路由里算。**
   原方案说接入点是 `preview_platform_sku_profit`（`product_finance_service.py:1053`），
   但**前端表格读的是候选列表的行**（`row.preview.expected.*`），而候选列表在
   `product_center.py` 里**自己调** `build_platform_profit_preview`。
   两处分头算必然漂移，所以把计算下沉到共同的那一层，两个调用点自动一致。

2. **`suggested_roi_clamped` 是「两位小数的可执行值」，不是 `min(原值, 上限)` 的原样结果。**
   理由：运营填进平台后台的是**两位小数**的数；表上保本 ROI 显示 1.97，
   运营自己算 1.97 × 1.2 = 2.36，表上写的必须是 **2.36** 才对得上账。
   等效单均广告费/净利也由这个数推出 ⇒ 68 ÷ 2.36 = **28.81**、净利 **5.68**、净利率 **8.35%**，
   与上游设计稿 §2.5⑪ 的示例**完全一致**。
   全精度的未封顶原值保留在 `suggested_roi`（超上限时在 tooltip 里显示真实差距）。

3. **迁移日期从 20261112/20261113 顺延到 20261113/20261114**（见 §3.3 的说明）。

### C.3 口径核对（开发库实测）

| 平台 | `target_roi_ceiling` | `break_even_roi` | `suggested_roi_clamped` | 等效单均广告费 |
|---|---|---|---|---|
| tiktok | 20.00 | 2.6371308016877637 | **3.17** | 15.77 |
| shopee | 50.00 | 2.9380341880341883 | **3.53** | 15.58 |

同一 SKU 在两个平台的 ROI 不同 —— 因为费率不同，利润链不同，**ROI 必须跟着平台走**
（这正是阶段 2.1「底线下沉到平台」要修的同一个病根：底线取的是单一 basis 平台的费率）。

成本不全的行：`reference_cost_status = "incomplete"` ⇒ `pre_ad_profit` 算不出来 ⇒
**ROI 三个数全部为 None** + `roi_missing_reasons = ["non_positive_revenue"]`（或
`non_positive_cost_denominator`），前端同时置灰。

### C.4 测试

| 文件 | 条数 | 说明 |
|---|---|---|
| `backend/tests/test_product_roi_service.py` | 12（新增） | 方案 §3.6 用例 1–9 + 口径补充 |
| `backend/tests/test_product_roi_migration_contract.py` | 4（新增） | 源码契约 3 条 + **真实 PG 上跑 upgrade×2 → downgrade → upgrade** 1 条 |
| `backend/tests/test_product_center_schema_contract.py` | +3 | 用例 10、11 + ORM 列与约束 |
| `backend/tests/test_platform_sku_profit_workbench.py` | +3 | 用例 12 + `pre_ad_profit` 暴露 + 平台配置生效 |
| `frontend/tests/productCenterUi.test.mjs` | +5（41 条全绿） | 用例 14：3 列渲染 / 列序 / 置灰守卫 / 免责提示 / 封顶提示 |

### C.5 顺手修掉的既有失败（1 条）

`test_product_category_contract.py::test_profit_save_uses_the_preview_version_when_the_client_does_not_supply_one`
—— 断言要求 `assumption_version=data.get("assumption_version") or preview["assumption_version"]`
**写在同一行**，而源码被换行拆成两行（`product_finance_service.py`），于是永远找不到。
行为本身是对的。把两处表达式合回一行即可，**零行为变更**。
（该用例原本被记在 §B.9「阶段 0 已识别的既有失败」里，现已消除。）

### C.6 全量回归对比（worktree vs main，同一份文件清单）

单进程跑全量太慢（`conftest.py:102` 在**模块导入时**就拉一次性 PG 容器，
`pg_engine`（`:288`）session 级 fixture 再拉一个），所以按文件清单 **5 进程并行分块**跑。
文件清单：`backend/tests` 下 **rglob `test_*.py` 共 671 个**（main 基线 669 个 —— 扣掉本次新增的 2 个测试文件）。

| | worktree（本次） | main 基线（`e69a29e3`） |
|---|---|---|
| 用例总数 | **4474** | 4450 |
| 通过 | **4293** | 4281 |
| 失败 | **161** | 162 |
| 错误 | 22 | 22 |
| 跳过 | 7 | 7 |
| 失败/错误用例数（去重） | **183** | 184 |

**逐条对比失败清单**：

| 差异 | 条数 | 明细 |
|---|---|---|
| worktree **新增**的失败（本次引入的回归） | **0** | —— |
| main 有、worktree 没有（**被修好**） | **1** | `test_product_category_contract::test_profit_save_uses_the_preview_version_when_the_client_does_not_supply_one`（见 C.5） |

其余 183 条失败**全部落在商品中心域之外**（Shopee 导出组件约 40 条、SQLite 建表
`unknown database ops` 17 条、HR 前端契约断言乱码、legacy 启动入口、alembic rehearsal
等），与阶段 0 的基线一致，属于仓库既有问题（见 §B.9），阶段 1 不处理。

**商品中心域 + ROI 相关的测试文件：0 失败**（`test_product_roi_service.py` 12、
`test_product_roi_migration_contract.py` 4、`test_product_center_schema_contract.py`、
`test_platform_sku_profit_workbench.py` 14、`test_product_profit_calculator.py`、
`test_product_pricing_guardrails.py` 全绿）。

前端：`node --test frontend/tests/productCenterUi.test.mjs` **41 passed**（新增 5 条）；
`vite build` ✓（ProductCenter chunk 75.76 kB，较阶段 0 的 73.18 kB +2.58 kB）；
`ruff` 全绿。

---

## 附录 D · 阶段 2.1 实施记录（2026-11-07 完成）

> 本附录记录**阶段 2.1（底线下沉到「SKU × 平台」）**的实际改动、与原方案的偏离、
> 实测数据与验证结果。方案正文（§4.1）里对应位置都加了「实施调整」提示，
> 两边不重复展开，以本附录为准。

### D.1 改动清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `backend/services/product_pricing_query_service.py` | 取数层新增 `load_pricing_platforms` / `load_platform_pricing_overrides` / `resolve_pricing_platform` / `resolve_pricing_platform_code` / `resolve_pricing_override`；`load_pricing_context` 增 `platform_codes` 参数，返回 `platforms` 字典 + `priceable_platform_codes` + `overrides`；`compute_pricing_state` / `compute_pricing_for_sku` / `resolve_effective_creator_rate` 增 `platform_code` 参数；人工覆盖回落链 = **新表 → SKU 级旧列** |
| 2 | `modules/core/db/schema_parts/business.py` | **新建** `SkuPlatformPricing`（`finance.sku_platform_pricing`，12 列，`UNIQUE (sku_id, platform_code)`） |
| 3 | `modules/core/db/schema.py` | 导出 `SkuPlatformPricing` |
| 4 | `modules/core/db/schema_parts/collection.py` | `PriceAdjustBaseline` 主键改复合 `(sku_id, platform_code)` |
| 5 | `current_migrations/versions/20261115_add_sku_platform_pricing.py` | **新建**：建新表 + 基线表加 `platform_code` 并回填 + 换复合主键；`downgrade` 反向（同一 SKU 多平台行只保留平台字典序最小的一条，否则建主键撞重复行） |
| 6 | `backend/domains/business/routers/product_center.py` | `_compute_sku_min_selling_price` 增 `platform_code`；`list_skus` 增 `platform_code` 查询参数；**候选列表 / 保存护栏 / 落库护栏**全部按请求里的平台算底线；响应带出 `min_selling_price_platform` |
| 7 | `backend/schemas/product_center.py` | `ProductCenterItem` 与 `PlatformSkuProfitCandidateResponse` 增 `min_selling_price_platform`（**漏声明会被 `extra='ignore'` 静默丢弃**） |
| 8 | `backend/services/price_adjust_notify_service.py` | `build_context` 增 `platform_code`；`collect_pricing_states` / `load_baselines` 的键改 `(sku_id, platform_code)`；`detect_changes` / `advance_baselines` / `advance_baseline_for_sku` 跟着改 |
| 9 | `backend/tasks/price_adjust_notify_tasks.py` | 去重键改 `sku_id:platform_code`（`_business_key`）；payload 带 `platform_code` |
| 10 | `backend/services/feishu_projection_service.py` | 调价记录表加「平台」列；回写基线传 `platform_code` |
| 11 | `backend/services/inventory/sku_clearance_service.py` | `_load_platform` → `_load_pricing_platforms`（返回「各销售平台费率 + 公司级兜底平台」）；`_build_item` 按行自己的平台取费率，取不到回落兜底（见 D.2-①） |
| 12 | `frontend/src/domains/business/views/ProductCenter.vue` | SKU 资料页加「底线按平台」选择器；`listSkus` 传 `platform_code`；两处最低售价口径提示改为按平台 |
| 13 | `backend/tests/test_sku_platform_pricing.py` | **新建** 17 条（§4.1.5 六条 + 口径补充 + 迁移幂等 + 护栏端到端） |
| 14 | `backend/tests/test_price_adjust_notification.py` | 基线键改 `(1, "tiktok")`；`_state` 带 `platform_code`；SQLite fixture 补 `finance.sku_platform_pricing` |
| 15 | `backend/tests/data_pipeline/test_sku_clearance_ranking.py` | 打桩改新接口；**+2 条**（行平台回落公司级 / 行平台用自己的费率） |
| 16 | `backend/tests/conftest.py` | 定价种子清理清单加 `shopee` 平台（PG 容器是 session 级，不清理会撞下一条用例） |
| 17 | `frontend/tests/productCenterUi.test.mjs` | **+4 条**（45 条全绿） |

### D.2 与原方案不同的四处（实施时修正）

**① 清货排名：视图粒度是「库存来源平台」，不是销售渠道**

原方案 §4.1.3 第 7 项写的是「清货是『这个 SKU 在这个平台降多少』⇒ 按平台出」。
**这个前提在数据上不成立**：

- 清货视图 `api.sku_clearance_ranking_module` 的 `platform_code` 来自
  `mart.inventory_state.platform_code`；
- 生产库该表 1232 行**恒为** `'miaoshou'`（库存来源平台 = 妙手 ERP），**不是** tiktok / shopee；
- `core.dim_platforms` 里 `'miaoshou'` 的 `platform_role = 'source'`、`other_cost_rate` 为 NULL。

所以「按行平台查销售平台费率」会**查不到** ⇒ 没有 `other_cost_rate` ⇒ 成本线算不出来 ⇒
**底线整个消失**（只剩纪律线）。而**底线比口径不一致更危险**：口径不一致只是数字难看，
底线消失是护栏形同虚设 —— 正好是本阶段要修的那个病（方向是偏松 ⇒ 放行本该拦住的品）。

**改法**：两级取费率（`sku_clearance_service._build_item`）

1. 行里的 `platform_code` **是销售平台** ⇒ 用它自己的费率；
2. 行里是**库存来源平台**（今天的生产数据）⇒ 回落**公司级**费率
   （规则表 basis 平台，与本阶段改造前**完全一致** ⇒ 零行为变化）。

SQL 视图**不用改**。新增 2 条用例把这条钉死
（`test_row_platform_falls_back_to_company_rates_for_inventory_source_rows` /
`test_row_platform_uses_its_own_rates_when_it_is_a_sales_platform`）。

> 这条也说明：**「底线按平台」不是一个能一刀切的口径**。
> 凡是数据粒度里**没有销售渠道**的报表，底线只能是公司级的 ——
> 硬套平台口径只会把底线算没。

**② SKU 资料页保留「最低售价」列，改加「底线按平台」选择器**

原方案说「底线的展示移到利润测算 tab，SKU 资料 tab 只留人工覆盖，按平台分行」。
实际做的是：SKU 资料页**保留**最低售价列，加一个平台选择器（列表按所选平台取底线），
并在列下方明写「底线按 X 的成本率计算」「人工覆盖是公司级的，对所有平台生效」。

理由：运营现在就在这一页看底线并做人工覆盖，把列搬走等于砍掉他们已有的工作流；
而「让平台口径显式化」这个目的，用一个选择器就能达到，成本更低、风险更小。

**③ 人工覆盖的「写路径」没有在本阶段下沉**（拆到阶段 2.1b）

本阶段只做了**读路径 + 回落链**：新表有行就用新表，没有就回落 SKU 级旧列。
写入仍然写旧列。理由：

- 生产库与开发库的 `core.dim_erp_sku.min_selling_price_override` **均为 0 条** ⇒
  现在没有运营在用这一列 ⇒ 本阶段不碰写入路径，对运营**行为完全不变**；
- 等真有人开始按平台调价时再动写入路径（阶段 2.1b：覆盖值按平台分行 +
  SKU 资料页按平台分行 + 删 SKU 级旧列）。

> ⚠️ 代价要说清楚：这样一来，**人工覆盖仍然是公司级的**（对所有平台生效），
> 只有**系统算出来的底线**是平台级的。界面上已明写这一点，避免误读。

**④ 「可定价平台」的定义** = `platform_role = 'sales'` **AND** `other_cost_rate IS NOT NULL`

`amazon` 是销售平台但三个费率全 NULL（生产库实测）⇒ 算不出底线（成本线分母里缺
`other_cost_rate`）⇒ 建了基线也是一列 NULL ⇒ **不跟踪**，等它配了费率再进来。
`source` / `test` 平台（妙手、验证码测试账号）没有对外售价，不参与。

### D.3 核心修复实测（开发库）

SKU `751`「XH-MC-吸鼻器」（采购成本 40.00，SPU `XH-BABY-MC` 退货损失 3.5% / 货损 1.5%，
日常档 目标利润率 25% / 折扣 10%），开发库迁移已生效：

| | 底线 | 来源 |
|---|---|---|
| **修复后** · TikTok（other 27.27% / 达人 6.06%） | **109.08** | cost_floor |
| **修复后** · Shopee（other 41.65% / 达人 1.11%） | **146.84** | cost_floor |
| **修复前**（两个平台都用 basis 平台 tiktok 的费率） | 109.08 / 109.08 | cost_floor |

⇒ 同一个 SKU 在两个平台**终于有两条不同的底线**；
Shopee 的底线修复前被低估 **(146.84 − 109.08) / 146.84 = 25.7%**。

生产库的偏差更大（§11.2② 实测）：SKU `166851422928` 的 Shopee 底线
59.29 vs 应有的 103.36，**偏低 74.3%**。

### D.4 测试

| 文件 | 条数 | 对应 §4.1.5 |
|---|---|---|
| `backend/tests/test_sku_platform_pricing.py` | **17（新建）** | 六条全覆盖 + 口径补充 |
| `backend/tests/data_pipeline/test_sku_clearance_ranking.py` | +2 | D.2-① 的两条钉死用例 |
| `backend/tests/test_price_adjust_notification.py` | 38（改基线键） | 第 4 条（基线粒度） |
| `frontend/tests/productCenterUi.test.mjs` | **45**（+4） | 平台选择器 / 列表传参 / 口径提示 / 删掉过时文案 |

`test_sku_platform_pricing.py` 的六条对应：

| §4.1.5 | 用例 |
|---|---|
| ① 同一 SKU 两平台两条底线 | `test_same_sku_has_one_floor_per_platform`、`test_each_platform_uses_its_own_rate`（**逐条手算验算**，不只比大小） |
| ② 取数层返回两个平台费率 | `test_pricing_context_exposes_both_platforms_rates`、`test_floor_no_longer_follows_the_policy_basis_platform`（**改规则表 basis 平台，底线一条都不变** —— 钉死「basis 平台不再决定费率」） |
| ③ 人工覆盖新表读写 + 回落旧列 | `test_new_table_override_is_scoped_to_its_platform`、`test_new_table_override_wins_over_the_legacy_sku_column`、`test_legacy_sku_level_override_is_the_fallback_for_every_platform`、`test_override_is_flagged_as_manual_override` |
| ④ 基线 `(sku_id, platform_code)` 粒度 | `test_baselines_are_keyed_by_sku_and_platform`、`test_price_change_on_one_platform_does_not_notify_the_other`（**Shopee 变价只报 Shopee**）、`test_platform_is_recorded_in_the_attribution_context` |
| ⑤ 迁移幂等 + downgrade | `test_migration_is_chained_on_the_current_head`、`test_migration_guards_every_object`、`test_migration_is_repeatable_and_rolls_back_cleanly`（**真实 PG 上跑 upgrade×2 → downgrade → upgrade**）、`test_migration_backfills_the_baseline_platform` |
| ⑥ 护栏按平台 | `test_guardrail_uses_the_floor_of_the_requested_platform`（**同一个价格 35.00：TikTok 放行 201、Shopee 拦下 422**）、`test_candidate_list_reports_the_floor_of_the_selected_platform` |

### D.5 全量回归对比（worktree vs main，同一份文件清单）

| | worktree（阶段 2.1） | main 基线（`1e61a3c9`） |
|---|---|---|
| 测试文件数 | **672** | 671（差 1 = 本阶段新增的 `test_sku_platform_pricing.py`） |
| 覆盖到的测试模块 | **705** | 704（差 1 同上） |
| 用例总数 | **4783** | 4765（差 18 = 新增 17 条 + 1 条抖动用例） |
| 通过 | **4629** | 4612 |
| 失败 | **125** | 124 |
| 错误 | **22** | 22 |
| 跳过 | **7** | 7 |
| 失败/错误去重条数 | **147** | 146 |

**逐条对比失败清单**：

| 差异 | 条数 | 明细 |
|---|---|---|
| worktree **新增**的失败（本次引入的回归） | **0** | —— |
| main 有、worktree 没有 | **1** | `test_field_mapping_template_timestamp_defaults_migration_contract::test_field_mapping_template_timestamp_migration_repairs_drifted_postgres_table` —— **抖动，不是修复**：单独复跑该文件在 worktree 上 **3/3 通过**（连跑两次都是），失败只在「同进程里跟着别的迁移契约测试一起跑」时出现 |

> **两侧剩余的 147 / 146 条失败全部落在商品中心域之外**（Shopee 导出组件约 40 条、
> HR/绩效/任务中心、SQLite 建表 `unknown database ops`、迁移契约的 PG 漂移用例、
> legacy 启动入口等），与阶段 0 / 阶段 1 的基线一致，属于仓库既有问题（见 §B.9）。

**商品中心域相关：0 失败** —— `test_sku_platform_pricing.py` 17、`test_price_adjust_notification.py` 38、
`test_product_pricing_guardrails.py`、`test_platform_sku_profit_workbench.py` 14、
`test_product_profit_calculator.py`、`test_product_center_schema_contract.py`、
`test_sku_clearance_ranking.py` 26、`test_product_center_sync_contract.py` 6、
`test_profit_basis_schema_contract.py` 2 全绿。

前端：`node --test frontend/tests/productCenterUi.test.mjs` **45 passed**（新增 4 条）；
`vite build` ✓（ProductCenter chunk 76.30 kB，较阶段 1 的 75.76 kB +0.54 kB）；
`python scripts/run_lint.py` 退出码 0。

#### D.5.1 这次的全量回归为什么换了跑法（阶段 1 是「5 块并行」）

阶段 1 用「5 个大块并行」跑完全量，本阶段**同样的跑法会卡死**：
某个 67 文件的块跑到 `test_hr_performance_input_routes.py` 时，
`starlette.testclient` 的阻塞 portal 一直不返回 —— 线程挂着、CPU 不动、**不报错**。

排查结论（py-spy dump 线程栈）：

- 卡住的位置在 **HR 绩效输入路由的 TestClient POST**，与商品中心**完全无关**；
- **main（不含阶段 2.1 的任何改动）跑同一组文件会以同样方式卡住** ⇒ 不是本次引入；
- 该文件**单独跑 23 秒通过**；二分到 4 个文件一组也都能过 ⇒ 触发条件是
  **同进程内若干文件的组合状态**，不是单个文件的问题；
- 同时还有**另一个会话在跑同一套全量回归**，两边互相拖慢会放大这个现象。

所以本阶段把跑法换成：**10 个子块（每块带超时）→ 超时的块再逐文件跑（每文件带超时）**
→ 两侧**逐个测试 ID 对比**，而不是只比聚合计数。逐文件跑时 57 + 17 个文件
全部正常跑完、**0 超时**。

> 顺带记一笔：这属于**仓库既有的测试隔离问题**（共享 PG 容器 + 同进程状态残留），
> 与商品中心无关，但会让「全量回归」在多会话并发时变得不可靠。建议单独立项修，
> 不要挂在阶段 2.1 上。


### D.6 合并 main 的产物：迁移链修复（发布级）

阶段 2.1 合并 main（`74a32a53` 店铺身份治理）时暴露了**两处迁移链缺陷**，
都不是阶段 2.1 的业务代码问题，但**都会卡住发布**，必须在这一轮修掉。

#### D.6.① 两个 head ⇒ `alembic upgrade head` 直接报错

两个分支各自在 `20261114_add_sku_roi_columns` 后面挂了一个新迁移：

| 迁移 | 来源 | 原 `down_revision` |
|---|---|---|
| `current_schema_20261115_add_sku_platform_pricing` | 阶段 2.1（本分支） | `20261114_add_sku_roi_columns` |
| `current_schema_20261116_add_tiktok_export_store_name_aliases` | main（店铺身份治理） | `20261114_add_sku_roi_columns` |

⇒ 合并后是**兄弟节点** ⇒ **两个 head** ⇒ `alembic upgrade head` 报
`Multiple head revisions` ⇒ **迁移链必须是单 head**（仓库规则），发布阻塞。

**改法**：把 `20261116` 的 `down_revision` 改挂到 `20261115` 后面，
恢复**日期序单链** `11 → 12 → 13 → 14 → 15 → 16 → 17`。

**为什么安全**（生产库 2026-11-07 只读核查实测）：
生产库的 `public.current_schema_alembic_version` 仍停在
`current_schema_20261111_add_refresh_queue_domain_and_retry`
⇒ **12 / 13 / 14 / 16 / 17 都还没上过生产**
⇒ 生产升级时按新链序依次执行 ⇒ 不会出现「已经是 17 却漏掉 15」的情况。

#### D.6.② `alembic downgrade` 不可用（`IndexError`）

`20261117_remediate_shopee_row_identity_conflicts.py` 的 `_UPDATE_SQL` /
`_ROLLBACK_SQL` 在**模块加载时**已经 `.format(table="{table}", audit_key=...)` 过一次
⇒ 模板里的 `{{}}` 已经变成**字面 `{}`**（JSONB 空对象）。
运行期再走一次 `.format(table=table)`，那个裸 `{}` 会被当成**自动编号字段**：

```
IndexError: Replacement index 0 out of range for positional args tuple
```

⇒ **`alembic downgrade` 直接炸、回滚不可用**（已实测复现）。
仓库规则要求 `upgrade` / `downgrade` 都写，§9.2 验证清单要求「迁移三步可重复」。

**改法**：运行期一律用 `.replace("{table}", table)`，
与守护测试 `backend/tests/data_pipeline/test_shopee_row_identity_remediation.py`
的 `_update_sql` / `_rollback_sql` 本来就有的口径**一致**（`upgrade()` / `downgrade()` 两处）。

> ⚠️ 这两处改的是**另一个会话的迁移文件**，但属于**发布级阻塞**，已在本阶段一并修掉。
> 修法是「让运行期格式化方式与模块加载期对齐」，不改任何业务语义。

#### D.6.③ 修完后的验证结果

| 项 | 结果 |
|---|---|
| `alembic heads` | **单 head**：`current_schema_20261117_remediate_shopee_row_identity_conflicts` |
| `downgrade -1` → `upgrade head` | ✅ 还原 1,946 行（18 + 1,909 + 19）→ 重订正 1,946 行 |
| 整链往返 `downgrade → 20261114` → `upgrade head` | ✅ `17→16→15→14→15→16→17` 全绿，退出码 0 |
| 开发库结构 | `finance.sku_platform_pricing` 12 列 / 0 行；`ops.price_adjust_baselines` PK = `(sku_id, platform_code)`；基线 tiktok 1121 + shopee 1，`platform_code` 无 NULL；`core.dim_erp_sku.min_selling_price_override` 非空 0 条 |
| 商品中心域定向测试 | 15 文件 **259 passed** |
| 店铺身份域定向测试 | 23 文件 **194 passed** |
| 合计 | **453 passed / 0 failed**（上一次是 299 passed / 1 failed，那 1 条就是 D.6.② 的缺陷） |
| `python scripts/run_lint.py` | 退出码 0 |

### D.7 遗留

| 项 | 说明 |
|---|---|
| **阶段 2.1b** | 人工覆盖写入路径下沉到平台级 + SKU 资料页按平台分行 + 删 `core.dim_erp_sku.min_selling_price_override` |
| 清货排名的平台粒度 | 视图粒度是库存来源平台 ⇒ 底线仍是公司级。要做「按渠道出清货排名」，得先给视图加销售渠道维度（join `finance.sku_operating_profiles`）—— 生产库该表只有 6 行，覆盖率不足以支撑，**暂不做** |
| `amazon` 无费率 | 销售平台但三个费率全 NULL ⇒ 不可定价、不跟踪。等配了费率自动进 `priceable_platform_codes` |
| 旧列删列 | `core.dim_erp_sku.min_selling_price_override` 保留一个版本周期，删列单独一个迁移（不与本阶段混） |

