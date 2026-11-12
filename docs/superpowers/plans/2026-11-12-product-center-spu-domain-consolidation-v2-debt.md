# 商品中心「款 / 货 / 归属」概念收敛 · V2 债（**已全部结清**）

> 状态：**已结清** —— 2026-11-12 这一天把 V2 债清单上的 4 项 + 过程中新发现的 5 项
> **全部做完**，本文件保留为「做了什么 / 为什么这么做」的记录。
>
> 本轮的业务概念、SSOT 审查结论与实现，见 §3。
>
> ⚠️ **仍未做**的是「款 → 货」的**页面层级重排**（IA）——
>    那是**产品演进**，不是技术债：它要重做整个商品中心的页面结构，
>    按 pre-launch 约束不该混进 launch 期改动。见 §4。

---

## 1. 背景：2026-11-12 查清的三个问题

起因是运营反馈「SKU 资料」页的「所属 SPU」筛选框输入编码后只显示「无匹配数据」，
且回车不生效。审查后确认**根因不是分页，而是概念问题**：

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| A | 「可选的款」被做成「SPU 管理 tab 那一页」 | 阻塞运营 | ✅ 已修 |
| B | 「这个款还在不在」有两个真相来源（`active` / `biz_status`） | 数据一致性 | ✅ 已修（建模 A） |
| C | 「查」与「挂」被做成同一件事，共用一份候选集 | 概念错误 | ✅ 已修（两种口径分开） |

---

## 2. V2 债清单（4 项 + 5 项新发现）· 全部已做

### 2.1 批次 A · 范围参数三义 + 品类双真相 ✅

**原问题**：同一个参数名 `include_inactive` 在三个端点上语义不同；
品类的「不可选」在前端**硬编码**了一份清单。

| 端点 | 改前 | 改后 |
|---|---|---|
| `GET /api/spus` | `include_inactive`（= `active IS TRUE`） | **`include_soft_deleted`**（= 含不含已删除的款） |
| `GET /api/product-categories` | `include_inactive`（混了停用 + 不可选两件事） | **`include_inactive`**（只管 `status`）+ **`include_unselectable`**（只管 `is_selectable`） |
| `GET /api/warehouse-storage-rules` | `include_inactive`（= `status == 'active'`） | 不动（语义本就明确 = 停用） |

「不可选品类」改为**只以 DB `is_selectable` 为准**，删掉前端硬编码的
`legacyUnselectableCodes = new Set(["PET_DAILY"])`
（实测 DB 里 `PET_DAILY.is_selectable=false`，是全表唯一一条 ⇒ 前端那份是重复定义）。

守护测试：`backend/tests/test_product_center_listing_scope_contract.py`

### 2.2 批次 B · 归属的时态露出水面 ✅

**原问题**：`core.bridge_spu_sku` 是**带生效区间**的关联
（`effective_from` / `effective_to` / `binding_status`），
但 SKU 列表只投影了「今天的落点」一个字符串 ⇒
运营看不到「这个货是什么时候挂到这个款上的」「换过几次款」。

⇒ 新增真源 `backend/services/product_spu_binding.py`，
   `SkuItem.spu_effective_from` 把生效日露出来，前端在 SPU 单元格下方显示「自 YYYY-MM-DD」。

**顺带收敛（新发现第 1 项）**：「什么关系算当前有效」这个判定
（`binding_status == 'active' AND effective_to IS NULL`）
原本被**手抄在 13 个文件**里（路由 20 处 + 4 个业务服务 + 种子脚本 + 测试与冒烟脚本）
⇒ 全部改为引用真源，并加一条**全仓扫描**的守护测试：
`backend/tests/test_product_center_binding_projection.py`

### 2.3 批次 C · `ProductCenterItem` 一模两用 ✅

**原问题**：同一个模型同时表示「SPU 行」与「SKU 行」——
`spu` 一会儿是**标识**、一会儿是**引用**，`active` 在 SKU 行里恒为 None，
调用方拿到它无法判断自己拿的是哪一种。

⇒ 拆成 `SpuItem`（`spu` 是标识，必填）/ `SkuItem`（`spu` 是引用，可空）；
   `ProductCenterListResponse` → `SpuListResponse` / `SkuListResponse`；
   `BulkMutationResponse` → `SpuBulkMutationResponse` / `SkuBulkMutationResponse`；
   **旧的三个模型一律删除**（留着就是留后门）。
   `SkuItem` 上不再有 `active`（货用 `status`）；
   `SkuItem.spu_name` 改为**真的**从当前归属的款投影出来（以前恒为 None）。

守护测试：`backend/tests/test_product_center_item_split_contract.py`

### 2.4 批次 D · 归属双向可达 ✅

**原问题**：SKU 资料页里存量行的 SPU 列是**只读**的，
改归属只能从「SPU 管理」tab 的「SKU 归属」抽屉**单向**进入。

⇒ 存量行的 SPU 单元格改为可编辑的下拉（候选集 = **可绑定口径** ∪ 各行当前挂着的款），
   改动走**已有的** `bulk_save_skus` 通道（不另开写入路径 ——
   归属有生效区间、有归档、有审计，另写一条必然漏掉一半）。

守护测试：`backend/tests/test_product_center_binding_write_path_contract.py`（后端）
+ `frontend/tests/productCenterUi.test.mjs`（前端）

### 2.5 过程中新发现的 5 项（也一并做掉）

| # | 问题 | 做法 |
|---|---|---|
| 1 | 「当前有效」的判定被手抄在 13 个文件里 | 全部收敛到真源 + 全仓扫描守护测试（见 2.2） |
| 2 | 前端硬编码「不可选品类」清单 | 只以 DB `is_selectable` 为准（见 2.1） |
| 3 | 4 个遗留测试 fixture 用 `biz_status="active"`（该值 API pattern 早已拒绝、真实库 0 行、备份表也无） | 改为 `"candidate"` |
| 4 | **归属状态取值域没有任何约束**：三个语义各异的值（`active` 当前有效 / `inactive` 软删封存可复活 / `historical` 换款归档不可复活）散落各处，且 `binding_status` 上**没有 CHECK** ⇒ 第四个值会静默写进库 | 真源补齐三值 + 两个判定条件（当前有效 / 可复活）+ 两个渲染函数（取值域约束、部分索引谓词）；ORM 加 `chk_bridge_spu_sku_binding_status`，并让 `uq_bridge_spu_sku_current` 的索引谓词也从真源渲染；迁移 `current_migrations/versions/20261228_bridge_spu_sku_binding_status_constraint.py` |
| 5 | **写入路径**：`_apply_bulk_sku_spu_binding` 在**归属没换**时也校验新款能不能挂货 ⇒ 一个挂在**已淘汰款**下的 SKU，运营只想改个重量，保存时却收到 422「不能绑定新 SKU」（与他做的事毫无关系，且无从绕过） | 先看归属有没有变；没变就原样返回。**换款时**仍然校验 |

**另外两处顺手修掉的**（都是「不留技术债」范围内的真实缺陷）：

* **同日换款被硬拒**：`starts_on <= binding.effective_from` ⇒ 今天刚建的绑定今天改不了，
  运营只看到一句「effective_from must be later than…」，也不知道该怎么办。
  ⇒ 改成**只有改到过去**才拒绝；同一天 = 当天纠正，允许。
* **typecheck 门禁静默失效**：`scripts/run_typecheck.py` 的目标里写着
  `backend/routers/dashboard_api.py`，而那个文件**早已不存在**
  ⇒ mypy 每次都报错 ⇒ 这道门禁**从来没有真正跑过**。
  ⇒ 指向改成 `dashboard_api_postgresql.py`，并把商品中心的运行时面纳入门禁；
    加 `backend/tests/test_runtime_surface_integrity.py` 守着目标必须存在，
    同时**静态**断言路由不引用未定义的全局名
    （实测踩过：漏导入 `archived_binding_condition` ⇒ `restore_spu` / `restore_sku`
    运行到那行才 `NameError`，而**全量测试照样全绿**）。

---

## 3. 本轮已落地（2026-11-12）

### 3.1 建模决策：建模 A

`active=false` 必然是 `biz_status='retired'`；但 `retired` 可以不删
（逻辑淘汰 —— 业务上不再经营，历史仍要留）。

⇒ 不变量 `active=false ⟹ biz_status='retired'`
⇒ 「可绑定」= `biz_status` 不是 `retired` ⇒ 判定**只需一个条件**。

### 3.2 值的域独立成两个端点

| 端点 | 口径 | 用途 |
|---|---|---|
| `GET /api/spus/options` | 浏览口径：在售（`active IS TRUE`） | 工具栏「所属 SPU」**筛选** |
| `GET /api/spus/assignable-options` | 可绑定口径：`biz_status ∈ {candidate, testing, promoted}` | SKU 行**赋值 / 换款** |

口径**固化在端点里**，不暴露给调用方自由拼装 —— 前端无法组合出
「已删除但状态还是候选」这种自相矛盾的候选集。

筛选器是**查询条件**（可输入任意编码回车生效，`allow-create`）；
赋值选择器是**外键**（不允许造出库里不存在的 SPU）。

### 3.3 两个真源（律 1「真源只能一个，而且必须写在纸上」）

| 真源 | 管什么 | 派生点 |
|---|---|---|
| `backend/services/product_spu_lifecycle.py` | SPU **自身**的状态与「能不能挂货」 | ORM 约束、路由判定、迁移 `20261227`、守护测试 |
| `backend/services/product_spu_binding.py` | SKU ↔ SPU **归属关系**的状态与投影 | ORM 约束、路由判定、4 个业务服务、种子脚本、迁移 `20261228`、守护测试 |

守护测试断言「ORM 约束 == 真源 == 迁移渲染结果」，
外加**全仓扫描**：任何人再手抄一份判定，测试立刻变红。

### 3.4 写入路径收敛

* `SpuBulkItem` / `SpuUpdateRequest` **不再接受 `active`** ——
  `active` 只能由删除 / 恢复这三个专用端点写。
* 归属的写入：**只有真的换款**才校验新款能不能挂货。
* 归属状态的三个语义各自独立：换款归档（`historical`）**不可**复活，
  软删封存（`inactive`）**可**复活。

### 3.5 数据库层兜底

三条 CHECK 约束（均从真源渲染）：

| 约束 | 表 | 作用 |
|---|---|---|
| `chk_dim_spu_biz_status` | `core.dim_spu` | 经营状态取值域 |
| `chk_dim_spu_lifecycle` | `core.dim_spu` | 建模 A 的不变量 |
| `chk_bridge_spu_sku_binding_status` | `core.bridge_spu_sku` | 归属状态取值域 |

存量行**一行未改**（只保未来、历史不修），迁移前 fail-closed 校验存量行。

---

## 4. 仍未做（**产品演进**，不是技术债）

### 款 → 货的层级视图（IA）

**现状**：商品中心是四个平级 tab ——「SPU 管理」「SKU 资料」「平台 SKU 利润测算」
「物流仓储管理」。

**问题**：业务上款（SPU）是头、货（SKU）是脚，二者不是平级实体。
款上定义的货损率 / 退货率会下发给它的货；定价底线也是「款 × 平台」的量。
运营要理解「货挂在哪个款下」仍然要跨 tab 拼接
（虽然**归属关系本身已经双向可达**了，见 §2.4）。

**建议形态**：以「款」为聚合根的层级视图（款 → 它的货），SKU 资料变成款的展开区。

**为什么本轮不做**：属于页面结构重排，触及面远超一个功能缺陷，
按 pre-launch 约束不应混进 launch 期改动。
**这是一件产品决策，需要先定 IA，再动手。**
