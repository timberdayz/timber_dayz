# 库存库龄管道恢复设计（Inventory Aging Pipeline Recovery）

**日期:** 2026-10-21
**状态:** 待实施（下一个会话）
**上游依赖:** `docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md`（SKU 定价底线）
**定位:** 本 spec 只解决「让库龄有真实数据」。滞销预警、清理排序、阈值筛选等业务设计**不在本 spec 范围**。

---

## 1. 背景与目标

SKU 定价底线功能已于 2026-10-21 交付（见上游 spec）。它的「库龄档位分层」依赖 `mart.inventory_age_current.age_days`：

| 库龄 | 命中档位 | 当前档折扣率 | 目标利润率 |
|---|---|---|---|
| 0 天 | 日常 | 10% | 25% |
| 60 天 | 滞销30天 | 15% | 22% |
| 90 天 | 滞销60天 | 20% | 18% |
| 120 天 | 滞销60天以上 | 30% | 10% |

但**库龄表至今 0 行** → 所有 SKU 一律回落到「日常」档 → 界面上「当前可优惠」恒为 10%，「滞销可优惠」恒为 30%。**档位分层从未真正生效过。**

本 spec 的目标：

1. 让 `mart.inventory_age_current` / `mart.inventory_age_history` 拿到**真实、持续更新**的库龄数据
2. 保证 `product_sku` 能高比例匹配到 `core.dim_erp_sku.sku_key`（商品中心 join 的前提）
3. 打通后**不改任何定价底线代码**，同一套界面自动按真实库龄分档

---

## 2. 现状（2026-10-21 在本地库 `xihong_erp` 实测）

### 2.1 全链路各表行数

| 表 | 行数 | 性质 |
|---|---|---|
| `b_class.fact_miaoshou_inventory_snapshot` | **0** | 采集层落地表（有 `商品SKU` 等扁平列） |
| `b_class.fact_shopee_inventory_snapshot` | **0** | 同上 |
| `b_class.fact_tiktok_inventory_snapshot` | **0** | 同上 |
| `b_class.staging_raw_data` | **0** | 原始暂存 |
| `semantic.fact_inventory_snapshot` | **0** | **视图**，直接 UNION 读上面三张 b_class 表 |
| `mart.inventory_snapshot_history` | **0** | 视图，读 semantic |
| `mart.inventory_snapshot_latest` / `_change` / `_company_daily` | **0** | 视图 |
| `mart.inventory_age_current` | **0** | **表**，由 `inventory_age_refresh_service` 维护 |
| `mart.inventory_age_history` | **0** | 同上 |
| `core.staging_inventory` | 80280 | **2025-11 一次性历史导入，形态不同（见 §3.4）** |
| `api.inventory_age_list_module` / `_summary_module` | **0** | 看板读模型 |

### 2.2 采集中心确实跑过 inventory

`core.collection_tasks` 里 `data_domains` 含 `inventory` 的任务（最近的）：

| id | 状态 | 时间 | 说明 |
|---|---|---|---|
| 622 | `completed` | 2026-09-14 | 「采集完成,共采集 **1 个文件**」 |
| 621 | `failed` | 2026-09-14 | 0/1 域成功 |
| 456 | `failed` | 2026-06-07 | 等待验证码回填 |
| 293 / 313 / 327 / 199 / 196 / 197 / 211 / 198 / 238 / 232 / 233 | completed / partial_success | 2026-04-13 ~ 04-16 | 4 月那批 |

**采集不是没跑，是跑了但数据没进 b_class。**

### 2.3 卡在 `public.catalog_files` 的两个文件（断点现场）

```
id=2755  miaoshou_inventory_snapshot_20250914_134915.xlsx
         status = processing
         error  = 「自动入库任务超时，已回退等待重试」
         first_seen = 2026-09-14

id=2764  miaoshou_inventory_snapshot_20260915_000609.xls
         status = template_update_required
         error  = 「新增3个字段, 删除0个字段 (匹配率: 89.3%)」
         file_metadata.auto_ingest.claimed_by = scheduled_tasks.auto_ingest_pending_files
         file_metadata.auto_ingest.last_governance_status = breaking_drift
         first_seen = 2026-09-15
```

### 2.4 对照：其它数据域的管道是通的

`public.catalog_files` 按域 × 状态：

| 域 | ingested | template_update_required | failed | processing |
|---|---|---|---|---|
| analytics | 156 | 2 | — | — |
| services | 113 | — | — | — |
| orders | 49 | — | 2 | 1 |
| products | 107 | 25 | 24 | — |
| purchase | — | — | — | 7 |
| **inventory** | **0** | **1** | — | **1** |

→ **inventory 是掉队的那个，不是整条管道都坏了。** 这决定了修复方向是「补齐三处具体缺口」，而不是「重写管道」。

### 2.5 字段映射模板状态

`core.field_mapping_templates` 里 `data_domain='inventory'` 共 12 个版本：

| id | 名称 | 版本 | 状态 | 字段数 | 更新时间 |
|---|---|---|---|---|---|
| **309** | `miaoshou_inventory__snapshot_v2` | v2 | **`published`** | 25 | 2026-06-01 |
| 308 / 182 / 180 / 178 / 177 | `..._snapshot_v1` | v1~v9 | archived | 25 | 2025-11-27 / 2026-04-14 |
| 116 / 95 / 94 / 91 / 78 / 77 / 76 | `..._snapshot_v3~v7` | — | archived | 16~17 | 2025-11-09 ~ 11-27 |

**只有 id=309 是 published。** 它的 `header_columns`（25 个）：

```
*商品SKU, 商品图片, *商品名称, *规格, 商品分组, *单价\n（元）, *总价\n（元）,
库存总量, 可用库存, 预占库存, 活动预留库存, 在途库存, 计划库存, 安全库存,
仓库, 仓位1, 库存数量\n可用库存\n预占库存,
近7天销量数据, 近30天销量数据, 近60天销量数据, 近90天销量数据,
创建时间, 更新时间, 创建人员, 更新人员
```

而 2026-09-15 采集到的新文件表头有 **28 个**（25 + 3 个新增，匹配率 25/28 = 89.3% ✓ 与报错一致）。

### 2.6 采集调度没开

```
core.collection_configs id=30
  name              = miaoshou-miaoshou_real_001-weekly-inventory-orders-v1
  data_domains      = ['orders', 'inventory']
  is_active         = true
  schedule_enabled  = false     ← 定时采集未开启
  template_id       = 15
```

（`template_id=15` 在 `core.field_mapping_templates` 里**不存在**——inventory 的 published 模板是 309。模板引用也是坏的。）

### 2.7 匹配率基线（用唯一能取到的真实数据实测）

`core.staging_inventory` 的 80280 行是**唯一**带真实 SKU 的库存数据：

| 指标 | 值 |
|---|---|
| `inventory_data->>'product_sku'` 去重后 | **1094** |
| 精确匹配 `core.dim_erp_sku.sku_key` | **1080（98.72%）** |
| 匹配不上 | 14 |
| 一对多风险（同一 sku_key 对多个 product_sku） | **0** |

匹配不上的 14 个是 ERP 主数据里没有的新品族：
`A-00003-BLACK`、`A-00001-ACU camouflage`、`HJJ-XH-CTD01`、`HJJ-XH-CTS01`、`HJJ-XH-CTS02`、`SG-JWGLH-A`、`SG-JWG-A`、`SBF006B-ZSLBB-S-035` 等。

⚠️ **不要试图「去掉第一个空格再匹配」**——实测那样反而更差（1094→1071 去重，1080→1010 匹配）。空格是「基础编码 + 规格」的分隔，去掉会把不同规格的 SKU 合并。

---

## 3. 根因

### 3.1 断点 A：字段映射模板过期（挡住 1 个文件）

- 采集到的库存表在 2026-09 采集层重写（V2 canonical）后**多了 3 个字段**
- 现行 published 模板 309 是 **2026-06-01** 发布的，只有 25 个字段
- 治理层判定 `breaking_drift` → 文件挂起等模板更新，**不自动入库**

### 3.2 断点 B：自动入库任务超时（挡住 1 个文件）

- `scheduled_tasks.auto_ingest_pending_files` 领取文件 2755 后**超时回退**，状态卡在 `processing`
- 该文件从此再没被重试成功

### 3.3 断点 C：采集调度未开启

- `collection_configs.id=30` 的 `schedule_enabled=false`
- 即使 A、B 修好，**没有定时任务去持续采集**，库龄会再次停在今天

### 3.4 澄清：历史 80280 行 staging 数据不可直接复用

`core.staging_inventory` 的 80280 行是 2025-11-17 ~ 22 的一次性历史导入，**形态与当前链路不同**：

| | 历史 staging 行 | 当前 b_class 链路 |
|---|---|---|
| SKU 键 | `product_sku`（英） | `商品SKU`（中） |
| 在库库存 | `total_stock` | `库存总量` |
| 单价 | `price` | `*单价\n（元）` |

`sql/semantic/inventory_snapshot.sql` 的 COALESCE 清单**不包含** `total_stock` 与 `price`
（只有 `在库库存` / `库存总量` / `on_hand_stock` 与 `成本` / `单价` / `unit_cost`），
所以这批历史行即使灌进去，**在库量会算成 0、库存价值也算成 0**，库龄毫无意义。

→ **历史行只能用来测 join 命中率，不能当库龄数据源。必须重新采集。**

### 3.5 一条此前的误诊需要纠正

曾判断「同步层未同步、`stage_inventory` 只在 `field_mapping_ingest.py:869` 被调用、
`data_ingestion_service.py` import 了却从不调用」。

**这是错的。** 实际情况：

- `semantic.fact_inventory_snapshot` 是**视图**，直接 UNION 读三张 b_class 快照表 —— **没有"同步层"这一环**
- `data_ingestion_service.py` 里的 `stage_orders` / `stage_product_metrics` / `stage_inventory` / `upsert_*`
  **全部是死导入**，当前链路走的是 `raw_data_importer` + `platform_table_manager` 直写 b_class
- 所以「调用没接上」不是断点，**断点在采集任务的产物入库环节**（§3.1–3.3）

> 下个会话请以本文档的实测为准，不要沿用旧结论。

---

## 4. 范围

### 4.1 在范围内

1. 让 inventory 采集表头与 published 字段映射模板对齐（补齐 3 个新增字段）
2. 让卡住的两个文件走完入库
3. 打开 inventory 的定时采集调度
4. 打通后的端到端验收（b_class → semantic → mart → age_refresh → 看板）
5. 确认 `product_sku` → `dim_erp_sku.sku_key` 的 join 命中率落在可接受区间

### 4.2 不在范围内

- 滞销预警规则、清理排序、滞销天数阈值筛选（`docs/API_CONTRACTS_TASK_COMPLETION_STATUS.md` 里列为「未来」的那些）
- 定价底线的任何改动（上游 spec 已交付，本次只提供数据）
- 清理 `core.staging_inventory` 的 80280 行历史数据（可另开任务；本次只标注不可用）
- 改造 `semantic` / `mart` 视图层（现有定义是对的，够用）

---

## 5. 修复方案

### 5.1 步骤 1：摸清那 3 个新增字段

模板 309（25 列）与 2026-09-15 采集文件（28 列）的差集：

```sql
-- 模板表头（25 列）
SELECT header_columns FROM core.field_mapping_templates WHERE id = 309;
-- 采集文件实际表头：文件在磁盘上，路径
SELECT id, file_name, file_path FROM public.catalog_files WHERE id = 2764;
```

用 `pandas.read_excel(file_path, nrows=0)` 取实际表头，与模板 `header_columns` 求差集。
**得到的 3 个字段名就是本步骤的产出。**

> 提示：2026-09 的 V2 canonical 重写引入的字段大概率与「平台 SKU / SKU ID / 商品 ID」这类标识列有关
> （`semantic.fact_inventory_snapshot` 的 COALESCE 清单里有 `平台SKU` / `SKU ID` / `商品ID` / `product_id`），
> 但**必须以实际差集为准**，不要照猜。

### 5.2 步骤 2：发布新版本模板

基于 309 复制出 v3（或在治理流程里走「模板更新」），把 3 个新增字段纳入 `header_columns`，
并同步 `core.field_mapping_template_items` / `core.field_mapping_template_versions`。
发布后把 `collection_configs.template_id` 从失效的 `15` 指向新的 published 模板。

验收：
```sql
SELECT id, template_name, version, status, field_count
FROM core.field_mapping_templates
WHERE data_domain='inventory' AND status='published';
-- 期望：恰好 1 行 published，且 field_count = 28
```

### 5.3 步骤 3：让两个卡住的文件走完入库

- 文件 2764（`template_update_required`）：模板更新后，治理层应重新判定 → 触发自动入库
- 文件 2755（`processing` / 超时回退）：把状态改回可重试（`auto_ingest_pending_files` 的认领逻辑），
  或直接对该文件重跑一次入库任务
- 同时要查**为什么超时**（入库任务超时阈值太短？还是这批文件确实大/字段多？），
  否则下次照样卡住

验收：
```sql
SELECT status, count(*) FROM public.catalog_files WHERE data_domain='inventory' GROUP BY 1;
-- 期望：ingested = 2，无 template_update_required / processing
SELECT count(*) FROM b_class.fact_miaoshou_inventory_snapshot;
-- 期望：> 0
```

### 5.4 步骤 4：打开调度

`core.collection_configs.id=30` 的 `schedule_enabled` 置 true（并确认 `schedule_cron` 合理、
`is_active=true`、`main_account_id` 指向可用账号）。

验收：等一个调度周期，或手工触发一次任务，确认 `catalog_files` 出现**新的** inventory 文件
且 `first_seen_at` 是当天。

### 5.5 步骤 5：端到端跑通 age_refresh

`backend/services/data_pipeline/inventory_age_refresh_service.py` 是**已存在且正确**的库龄计算服务
（锚点重置 / 分档 / 补货归零 / 卖空重现归零），**不要重写**。管道通后确认它被触发：

```sql
SELECT count(*) FROM mart.inventory_age_current;            -- 期望 > 0
SELECT bucket, count(*) FROM mart.inventory_age_current GROUP BY 1;
-- 期望：出现多个分档（0-30/31-60/61-90/91-180/180+），而不是全部落在一个档
```

**若所有 SKU 都落在同一档**，说明 `age_days` 全是 0 或全等于同一个值 → 锚点逻辑没吃到真实快照，
这时要回查 `mart.inventory_age_current.age_anchor_date` 与 `reset_reason`。

### 5.6 步骤 6：join 命中率验收

```sql
-- 库龄表的 product_sku 能否对上 ERP 主数据
SELECT count(*) AS 总数,
       count(*) FILTER (WHERE s.sku_id IS NOT NULL) AS 命中
FROM mart.inventory_age_current a
LEFT JOIN core.dim_erp_sku s ON s.sku_key = a.product_sku;
-- 期望：命中率 ≥ 95%（基线 98.72%）
```

若命中率明显低于 98.72%，先看 `product_sku` 是不是被截断/带规格后缀，
**不要用「去空格」的方式凑命中**（实测会让匹配变差）。

### 5.7 步骤 7：回看定价底线

管道通后，商品中心 SKU 资料页的「当前可优惠」应随真实库龄分档（不再是恒 10%）。

**验收方式**：在本地库造一个库龄不同的 SKU（或用真实快照），刷新商品中心，
确认「当前可优惠」出现 10% / 15% / 20% / 30% 多种值。

> 定价底线**不需要改任何代码**——`backend/domains/business/routers/product_center.py` 里
> `_load_age_days_by_sku` 已经是「表不存在就回落日常档」的安全实现
> （`SELECT to_regclass('mart.inventory_age_current')` 探测 + SAVEPOINT 兜底），
> 表有数据后自动生效。

---

## 6. 验收标准（全部可执行）

| # | 断言 | 查询 / 方式 |
|---|---|---|
| 1 | 采集有真实产物 | `SELECT count(*) FROM public.catalog_files WHERE data_domain='inventory' AND first_seen_at >= CURRENT_DATE` > 0 |
| 2 | 没有卡住的文件 | `SELECT status, count(*) FROM public.catalog_files WHERE data_domain='inventory' GROUP BY 1` → 只有 `ingested` |
| 3 | b_class 有数据 | `SELECT count(*) FROM b_class.fact_miaoshou_inventory_snapshot` > 0 |
| 4 | semantic 有数据 | `SELECT count(*) FROM semantic.fact_inventory_snapshot` > 0 |
| 5 | mart 快照链有数据 | `SELECT count(*) FROM mart.inventory_snapshot_history` > 0 |
| 6 | 库龄表有数据且分档多样 | `mart.inventory_age_current` 行数 > 0，且 `bucket` 出现 ≥ 2 个不同值 |
| 7 | 只有一个 published 模板 | `core.field_mapping_templates` inventory 的 published 恰好 1 行，field_count = 28 |
| 8 | join 命中率 ≥ 95% | 见 §5.6 |
| 9 | 调度已开 | `collection_configs.id=30` 的 `schedule_enabled = true` |
| 10 | 定价底线自动分档 | 商品中心「当前可优惠」出现多种值 |

---

## 7. 已有资产（**不要重写**）

| 资产 | 位置 | 说明 |
|---|---|---|
| 库龄计算 + 分档 | `backend/services/data_pipeline/inventory_age_refresh_service.py` | 锚点重置 / 补货归零 / 卖空重现归零 / 0-30·31-60·61-90·91-180·180+ 分档，**已验证正确** |
| 库龄看板（前端） | `frontend/src/domains/business/views/inventory/InventoryAging.vue` | 已存在 |
| 库龄预警（前端） | `frontend/src/domains/business/views/inventory/InventoryAlerts.vue` | 已存在 |
| mart 层 SQL | `sql/mart/inventory_age_current.sql`、`inventory_age_history.sql`、`inventory_snapshot_*.sql` | 已存在 |
| semantic 层 SQL | `sql/semantic/inventory_snapshot.sql` | 已存在（是视图，直接读 b_class） |
| 采集组件（V2 canonical） | `modules/platforms/miaoshou/components/inventory_export.py` | `MiaoshouInventoryExport`，Playwright 抓妙手 ERP 导出表 |
| 数据域导出映射 | `modules/apps/collection_center/python_component_adapter.py` | `"miaoshou": {"inventory": "MiaoshouInventoryExport"}` |
| 滞销清理排名 API | `GET /api/dashboard/clearance-ranking` | 已存在 |

---

## 8. 风险与未知项

| 风险 | 说明 | 应对 |
|---|---|---|
| **采集需要活的妙手 ERP 会话** | 采集组件是 Playwright 驱动 ERP 界面导出，可能要登录/验证码/账号授权 | 动手前先确认有可用账号与会话；否则只能修到「配置就绪」，无法端到端验收 |
| **模板 309 之外还有 11 个 archived 版本** | 直接改 309 可能破坏历史回溯 | 走治理流程发新版本，不改历史版本 |
| **`collection_configs.template_id = 15` 指向不存在的模板** | 可能是 inventory 域另有模板体系 | 步骤 2 一并修正引用 |
| **自动入库为什么会超时** | 未知（文件大？字段多？） | 步骤 3 必须查清，否则修完还会卡 |
| **shopee / tiktok 的 inventory 域** | 采集映射里只有 `miaoshou.inventory`，另两个平台的快照表也是 0 行 | 本次可只做 miaoshou，但要在 §6 之外明确记录另两个平台的状态与原因 |
| **14 个 SKU 匹配不上** | ERP 主数据缺这些新品族 | 属主数据问题，不在本 spec 范围；命中率 98.72% 已足够 |
| **历史 80280 行** | 形态不同，价值为 0 | 不要灌进库；可另开任务清理 |

---

## 9. 参考文档

| 文档 | 用途 | 备注 |
|---|---|---|
| `docs/superpowers/specs/2026-04-09-snapshot-continuous-inventory-aging-design.md` | **主设计**：快照连续库龄 | 与当前架构一致（snapshot-first） |
| `docs/superpowers/plans/2026-04-09-snapshot-continuous-inventory-aging.md` | 04-09 的实施计划 | |
| `docs/superpowers/specs/2026-04-04-real-inventory-aging-design.md` | 早期版（ledger/FIFO 方向） | **已被 04-09 修正**，只当历史背景 |
| `docs/superpowers/plans/2026-04-04-real-inventory-aging-implementation.md` | 04-04 的实施计划 | |
| `docs/superpowers/plans/2026-10-20-sku-pricing-guardrails.md` | 定价底线计划（文末有移交说明） | 本 spec 是它的下游 |
| `docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md` | 定价底线设计 | §4.1 库龄口径、§5.5 护栏 |
| `docs/API_CONTRACTS_TASK_COMPLETION_STATUS.md` | 滞销相关 API 的完成状态 | 「滞销天数阈值筛选」标为未来 |

---

## 10. 开工前请先做的一件事

**核对 §2 的实测数字是否仍然成立**（表行数、`catalog_files` 状态、模板状态、配置开关）。
本 spec 的所有数字都是 **2026-10-21 在本地库 `xihong_erp` 上实测**的，
但中间链路涉及采集任务、调度、模板治理等多个外部可变因素，**下一会话开场应先重测**。

若与 §2 不一致，**以实测为准并更新本 spec**，不要按旧数字施工。
