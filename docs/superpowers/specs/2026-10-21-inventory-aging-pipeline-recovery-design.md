# 库存库龄管道恢复设计（Inventory Aging Pipeline Recovery）

**日期:** 2026-10-21（初稿） → **2026-10-21 修订（实测校准版）**
**状态:** 待实施
**上游依赖:** `docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md`（SKU 定价底线，已交付）
**关联 spec:** `docs/superpowers/specs/2026-10-21-sku-level-clearance-ranking-design.md`（SKU 级滞销排名，本次新增）
**定位:** 本 spec 只解决「让库龄有真实数据」。滞销预警规则、清理排序优先级、阈值筛选的业务设计**不在本 spec 范围**。

---

## 0. 修订记录（2026-10-21 实测校准）

初稿写于 2026-10-21 上午。本次在写 spec 之后又对本地库 `xihong_erp` 做了一轮完整实测（表行数 / `catalog_files` 状态 / 模板表头 / 采集配置 / 真实文件内容 / SKU 命中），**发现 4 处偏差 + 2 个此前没被识别到的坑**。下表是全部差异，后续章节以本表为准。

| # | 初稿结论 | 实测结果 | 处置 |
|---|---|---|---|
| 1 | §5.1「那 3 个新增字段待查，提示大概率是平台 SKU/SKU ID/商品 ID」 | **实际是 `次品库存`、`暂存库存`、`备注`** —— 与提示完全无关 | §5.1 已完成，结论固化 |
| 2 | §2.3 / §5.3「文件 2755 卡在 `processing`，让超时自愈机制把它退回可重试后重跑入库」 | 2755 **只有 23 字节**，磁盘上根本没有这个文件；状态已由自愈机制退回 `pending` | **2755 不可救活**，改为作废 + 重新采集（§5.3） |
| 3 | §5.5 / §6-6「管道通后 `bucket` 应出现 ≥2 个不同值」 | 唯一可用文件的 `date_from = 2026-09-14`，只有**一帧**快照 → 所有 SKU `age_days = 0`，**必然全部落 0-30 档** | 验收口径改为「管道通 ≠ 分档生效」，分档需要第二帧（§5.5、§6） |
| 4 | §5.2「同步 `core.field_mapping_template_items` / `_versions`」 | 模板 309 的 `field_mapping_template_items` **是空表**；模板内容全在 `core.field_mapping_templates` 一行里（`header_columns` / `header_bindings` / `field_parse_rules`） | 不需要动那两个表（§5.2） |
| 5 | §2.6「打开调度 = `schedule_enabled` 置 true」 | `collection_configs.id=30` 的 `date_range_type='custom'` + `custom_date_start=2026-03-23`，**会把这个死窗口原样写进新文件的 `date_from`** | **这是本 spec 最危险的一处**，必须连同日期设置一起改（§5.4） |
| 6 | §5.4 cron 用标准 crontab 语义 | 仓库用 APScheduler `CronTrigger.from_crontab`，其星期编号**比标准 crontab 偏移一天**（`0` = 周一，不是周日）；仓库现有的「每周一」预设 `0 9 * * 1` 实际跑在**周二** | cron 表达式按 APScheduler 语义写（§5.4、§10） |
| 7 | §2.6 / §5.2「`collection_configs.template_id = 15` 指向不存在的模板，要修正引用」 | **错读了表。** 该列是 **FK → `core.collection_config_templates(id)`**（采集配置的默认值模板：日期口径/执行模式/默认 cron），**id=15 存在且正确**（`miaoshou-miaoshou_real_001-weekly`）。**字段映射模板**是另一条路径：入库时由 `template_matcher.find_matching_template` 按 `(platform, data_domain, granularity) + published + version DESC` **自动选取** | **不动** `collection_configs.template_id`；发布 v3 且 version 最高即自动生效（§5.2） |

**未被推翻的部分:** §2.1 全链路 0 行、§3.4 历史 80280 行不可复用、§3.5 误诊纠正、§5.5 age_refresh 服务不重写、§7 已有资产清单 —— 全部经实测复核成立。

---

## 1. 背景与目标

SKU 定价底线功能已于 2026-10-21 交付。它的「库龄档位分层」依赖 `mart.inventory_age_current.age_days`：

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
4. 建立**可持续的采集节奏**（本次决策：**每 3 天一次，下限每周一次**），让库龄随时间自然增长

---

## 2. 现状（2026-10-21 23:00 在本地库 `xihong_erp` 复测）

### 2.1 全链路各表行数

| 表 | 行数 | 性质 |
|---|---|---|
| `b_class.fact_miaoshou_inventory_snapshot` | **0** | 采集层落地表（25 个中文扁平列） |
| `b_class.fact_shopee_inventory_snapshot` | **0** | 无采集组件，永久 0 行 |
| `b_class.fact_tiktok_inventory_snapshot` | **0** | 无采集组件，永久 0 行 |
| `b_class.staging_raw_data` | **0** | 原始暂存 |
| `semantic.fact_inventory_snapshot` | **0** | **视图**，UNION 读上面三张 b_class 表 |
| `mart.inventory_snapshot_history` / `_latest` / `_change` / `_company_daily` | **0** | 视图 |
| `mart.inventory_age_current` | **0** | **表**，由 `inventory_age_refresh_service` 维护 |
| `mart.inventory_age_history` | **0** | 同上 |
| `api.inventory_age_list_module` / `_summary_module` | **0** | 看板读模型（视图） |
| `api.clearance_ranking_module` | **0** | 滞销读模型（视图） |
| `mart.inventory_backlog_base` | **0** | 滞销底座（视图） |
| `core.staging_inventory` | 80280 | **2025-11 一次性历史导入，形态不同（见 §3.4）** |

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
         status = pending                        ← 已由超时自愈机制退回
         error  = 「自动入库任务超时，已回退等待重试」
         file_size = 23 bytes                    ← ⚠️ 空壳文件
         file_path = data/raw/2026/...xlsx       ← ⚠️ 磁盘上不存在该文件
         file_metadata.auto_ingest.last_status = stale_recovered

id=2764  miaoshou_inventory_snapshot_20260915_000609.xls
         status = template_update_required
         error  = 「新增3个字段, 删除0个字段 (匹配率: 89.3%)」
         file_size = 11177284 bytes             ← 真实文件，磁盘上存在
         file_metadata.auto_ingest.last_governance_status = breaking_drift
```

**实测补充：**
- 2755 的 `date_from = 2025-09-14`，`file_size = 23` → 是个 23 字节的残file，**没有任何内容可入库**。
- 2764 的 `date_from = date_to = 2026-09-14`，`account = 18876067809`，`shop_id = xihong`。
- 2764 的伴生 `.meta.json` 显示 `business_metadata.date_from = 2026-09-14`、`collected_at = 2026-09-15T00:06:09`（采集于凌晨 0 点 6 分，日期取了前一天）。

### 2.4 对照：其它数据域的管道是通的

`public.catalog_files` 按域 × 状态：

| 域 | ingested | template_update_required | failed | pending | processing |
|---|---|---|---|---|---|
| analytics | 156 | 2 | — | — | — |
| services | 113 | — | — | — | — |
| orders | 49 | — | 2 | 1 | — |
| products | 107 | 25 | 24 | — | — |
| purchase | — | — | — | 7 | — |
| **inventory** | **0** | **1** | — | **1** | — |

→ **inventory 是掉队的那个，不是整条管道都坏了。**

### 2.5 字段映射模板状态

`core.field_mapping_templates` 里 `data_domain='inventory'` 共 12 个版本，**只有 id=309 是 `published`**：

| id | 名称 | 版本 | 状态 | 字段数 | 更新时间 |
|---|---|---|---|---|---|
| **309** | `miaoshou_inventory__snapshot_v2` | v2 | **`published`** | 25 | 2026-06-01 |
| 308 / 182 / 180 / 178 / 177 | `..._snapshot_v1` | v1~v9 | archived | 25 | 2025-11-27 / 2026-04-14 |
| 116 / 95 / 94 / 91 / 78 / 77 / 76 | `..._snapshot_v3~v7` | — | archived | 16~17 | 2025-11-09 ~ 11-27 |

**模板 309 的内容（实测）：**

- `header_columns`：25 个中文列名
- `header_bindings`：25 条绑定（`position` / `raw_name` / `required` / `confidence` / `sample_type` …）
- `deduplication_fields`：`["*商品SKU", "*商品名称", "*规格", "仓库"]`
- **`field_parse_rules`**：`[{"strict": true, "value_kind": "single_date", "date_format": "yyyy-mm-dd", "target_field": "metric_date", "source_column": "__file_date_from__"}]`
  → **`metric_date` = 文件的 `date_from`**。这一条决定了库龄锚点，见 §5.4 的坑。
- `core.field_mapping_template_items` 中 309 的行数 = **0**（模板内容不在该表）

### 2.6 采集调度没开 —— 以及两个此前没识别到的坑

```
core.collection_configs id=30
  name              = miaoshou-miaoshou_real_001-weekly-inventory-orders-v1
  data_domains      = ['orders', 'inventory']
  granularity       = weekly
  date_range_type   = custom                    ← ⚠️ 坑 1
  custom_date_start = 2026-03-23               ← ⚠️ 坑 1
  custom_date_end   = 2026-03-29               ← ⚠️ 坑 1
  is_active         = true
  schedule_enabled  = false
  schedule_cron     = null
  template_id       = 15   →  FK 到 core.collection_config_templates（采集配置默认值模板）
                            id=15 = miaoshou-miaoshou_real_001-weekly —— 存在且正确，不修
  execution_mode    = headed
```

> 另两个 `miaoshou` 配置（id=27 monthly、id=34 daily）名字里带 `inventory-orders`，但 `data_domains` 都只有 `['orders']` —— **全库只有 id=30 真正含 `inventory` 域**。

> **⚠️ `template_id` 的正确含义（实测，2026-10-21 实施时发现）**
>
> `core.collection_configs.template_id` 的外键是
> `fk_collection_configs_template_id: FOREIGN KEY (template_id) REFERENCES collection_config_templates(id)`。
> 它指向的是**采集配置模板**（存 `default_date_range_type` / `default_execution_mode` / `default_schedule_cron` 等默认值），
> **不是字段映射模板**。config 30 的 `template_id=15` 指向 `miaoshou-miaoshou_real_001-weekly`，
> **完全有效，不需要修**。
>
> **字段映射模板走的是另一条路径**：入库时由
> `backend/services/template_matcher.py::find_matching_template` 按
> `(platform, data_domain, granularity) + status='published'` 过滤、再按 `version DESC` 取第一条。
> → **只要 v3 是 published 且 version 最大，它就会被自动选中**，不需要任何配置引用。
>
> （初稿因为只查了 `core.field_mapping_templates` 而误判 `template_id=15`「失效」，见 §0 表 #7。）

**坑 1：`date_range_type='custom'` 会把死窗口写进新文件。**

定时执行路径 `backend/services/collection_config_execution.py:151`：

```python
time_selection = normalize_time_selection(
    date_range_type=config.date_range_type,
    custom_date_start=config.custom_date_start,
    custom_date_end=config.custom_date_end,
)
normalized_date_range = build_date_range_from_time_selection(time_selection, now=time_window_now)
```

而 `build_date_range_from_time_selection`（`backend/services/collection_contracts.py:238`）在 `mode == "custom"` 时**原样返回** `start_date` / `end_date`，不参与任何「滚动」计算。这个 `date_range` 一路传到 `executor_v2.py:4335` 的 `date_from`，再写进 `.meta.json` 的 `business_metadata.date_from`，最后成为 `catalog_files.date_from`，再被模板 309 的 `field_parse_rules` 读成 `metric_date`。

→ **如果只把 `schedule_enabled` 打开而不改日期设置，每一帧新快照的 `metric_date` 都会是 2026-03-23 → 库龄锚点变成 212 天前 → 所有 SKU 一步落进 180+ 最深档 → 全线 30% 折扣。**
→ 这比现在的「全是 0 天」危险得多。**必须与 `schedule_enabled` 一起改。**

**坑 2：cron 的星期编号与标准 crontab 偏移一天。**

`backend/services/collection_scheduler.py:216` 用 `CronTrigger.from_crontab(cron_expression)`。APScheduler 3.11 的 `from_crontab` **不做星期编号换算**，直接沿用 crontab 的数字；而 APScheduler 自己的 `day_of_week` 是 **周一=0 … 周日=6**。实测（本机 apscheduler 3.11.1）：

| cron | 实际触发 |
|---|---|
| `0 9 * * 1` | **周二** |
| `0 9 * * 0` | **周一** |
| `0 9 * * 1,4` | **周二 + 周五** |
| `0 9 * * 4` | **周五** |

→ 仓库现有的「每周一 09:00 自动采集上周」预设 `GRANULARITY_SCHEDULE_PRESETS["weekly"]["cron"] = "0 9 * * 1"`（`backend/domains/collection/routers/collection_schedule.py:53`）**实际跑在周二**。这是既有缺陷，不在本次修复范围，但**本次配置不能直接复用该预设**。

### 2.7 匹配率基线（用真实采集文件实测，不是历史 staging）

**真实文件** `data/raw/2026/miaoshou_inventory_snapshot_20260915_000609.xls`（11.2 MB）：

| 指标 | 值 |
|---|---|
| 数据行数 | **1226** |
| `*商品SKU` 去重后 | **1122** |
| 精确匹配 `core.dim_erp_sku.sku_key` | **1118（99.64%）** |
| 匹配不上 | **4**：`HJJ-XH-CTD01`、`HJJ-XH-CTD02`、`HJJ-XH-CTS01`、`HJJ-XH-CTS02` |
| 一对多风险（同一 sku_key 对多个 product_sku） | **0** |
| `可用库存` 合计 | 11,184 |
| `库存总量` 合计 | 11,237 |

> 该 4 个是 ERP 主数据里没有的新品族，属主数据问题，不在本 spec 范围。
> 命中率 99.64% **高于**初稿用历史 staging 测出的 98.72%。

⚠️ **不要试图「去掉第一个空格再匹配」** —— 实测那样反而更差。空格是「基础编码 + 规格」的分隔，去掉会把不同规格的 SKU 合并。

### 2.8 定价输入的填充率（决定「管道通了之后页面上能看到什么」）

| 输入 | 填充率 | 影响 |
|---|---|---|
| `core.dim_erp_sku.default_purchase_cost` | 1084 / 1121（96.7%） | 成本线能算 |
| `core.dim_erp_sku.reference_selling_price` | **2 / 1121（0.2%）** | 纪律线基本算不出 |
| `core.dim_erp_sku.creator_commission_rate` | 1（有平台兜底 `tiktok.default_creator_commission_rate = 0.0606`） | 有效 |
| SPU 有效绑定 + 两个率齐全 | 1118 / 1118 | 成本线能算 |
| `core.dim_erp_sku` 有效 SKU 总数 | 1121（active 1118） | — |
| `finance.sku_pricing_policies` | **4 行已就位**，`effective_from = 2026-10-21`，`platform_basis = tiktok` | 档位规则已就位 |

**按 `compute_sku_pricing` 的公式对 1121 个 SKU 实算：**

| 结果 | 数量 |
|---|---|
| **能算出最低售价** | **1084（96.7%）**，全部来自成本线 |
| 缺采购成本 | 37 |
| 无 SPU 有效绑定 | 3 |
| 能算纪律线 | 2（0.2%） |
| 分母 ≤ 0 | 0 |

成本线分布：最低 ¥0.03 / 中位 ¥70.24 / 最高 ¥1041.36。

→ **结论：「当前可优惠」这一列目前并未真正参与定价**（纪律线几乎算不出）。档位现在只通过「目标利润率」影响成本线。本次按业务决策，**纪律线不作为本轮验收项**（见 §4.2）。

---

## 3. 根因

### 3.1 断点 A：字段映射模板过期（挡住 1 个文件）

- 2026-09 采集层重写（V2 canonical）后，库存表在妙手侧多了 3 个字段
- 现行 published 模板 309 是 **2026-06-01** 发布的，只有 25 个字段
- 治理层判定 `breaking_drift` → 文件挂起等模板更新，**不自动入库**

### 3.2 断点 B：文件 2755 是空壳（**修正原判**）

- 2755 只有 **23 字节**，磁盘上无此文件 → **不存在「重试入库」的可能**
- 它当初的「自动入库任务超时」记录仍然有效为历史痕迹，但文件本体已不可用
- 处置：**作废该记录，靠重新采集产生新文件**（§5.3）

### 3.3 断点 C：采集调度未开启，且配置带死窗口

- `collection_configs.id=30` 的 `schedule_enabled=false`、`schedule_cron=null`
- **且** `date_range_type='custom'` 锁在 2026-03-23~29（§2.6 坑 1）
- 即使 A、B 修好，**没有定时任务去持续采集，库龄会再次停在今天**
- （初稿还列了「`template_id=15` 指向不存在的模板」，实测是读错了表，见 §0 表 #7 与 §2.6 澄清 —— **这一条不成立**）

### 3.4 澄清：历史 80280 行 staging 数据不可直接复用

`core.staging_inventory` 的 80280 行是 2025-11-17 ~ 22 的一次性历史导入，**形态与当前链路不同**：

| | 历史 staging 行 | 当前 b_class 链路 |
|---|---|---|
| SKU 键 | `product_sku`（英） | `商品SKU`（中） |
| 在库库存 | `total_stock` | `库存总量` |
| 单价 | `price` | `*单价\n（元）` |

`sql/semantic/inventory_snapshot.sql` 的 COALESCE 清单**不包含** `total_stock` 与 `price`，所以这批历史行即使灌进去，**在库量会算成 0、库存价值也算成 0**，库龄毫无意义。

→ **历史行只能用来测 join 命中率，不能当库龄数据源。必须重新采集。**

### 3.5 澄清：一条此前的误诊（维持原判）

曾判断「同步层未同步、`stage_inventory` 只在 `field_mapping_ingest.py:869` 被调用、`data_ingestion_service.py` import 了却从不调用」。**这是错的。** 实际情况：

- `semantic.fact_inventory_snapshot` 是**视图**，直接 UNION 读三张 b_class 快照表 —— **没有"同步层"这一环**
- `data_ingestion_service.py` 里的 `stage_orders` / `stage_product_metrics` / `stage_inventory` / `upsert_*` **全部是死导入**，当前链路走的是 `raw_data_importer` + `platform_table_manager` 直写 b_class
- 但**入库服务本身是活的**：`data_sync_service.py:1076 → DataIngestionService.ingest_data()` → `raw_data_importer` 写 b_class → 末尾 `data_ingestion_service.py:1120` 发布 `DataIngestedEvent` → `event_listeners.py:139` 命中 `data_domain == "inventory"` → `sync_inventory_skus` + `InventoryAgeRefreshService.refresh()`
- 所以「调用没接上」不是断点，**断点在采集任务的产物入库环节**（§3.1–3.3）

> 下个会话请以本文档的实测为准，不要沿用旧结论。

---

## 4. 范围

### 4.1 在范围内

1. 让 inventory 采集表头与 published 字段映射模板对齐（补齐 3 个新增字段）
2. 作废 2755 空壳记录；让 2764 走完入库
3. 打开 inventory 的定时采集调度（**含修正 `date_range_type` 与 `batch_status`**）
4. 打通后的端到端验收（b_class → semantic → mart → age_refresh → 看板）
5. 确认 `product_sku` → `dim_erp_sku.sku_key` 的 join 命中率落在可接受区间
6. **建立 3 天采集节奏**（§10）

### 4.2 不在范围内

- 滞销预警规则、清理排序优先级、滞销天数阈值筛选（`docs/API_CONTRACTS_TASK_COMPLETION_STATUS.md` 里列为「未来」的那些）
- **SKU 级滞销排名** —— 本次**另立 spec**：`docs/superpowers/specs/2026-10-21-sku-level-clearance-ranking-design.md`（与本 spec 共用同一份库龄/快照底座，但读模型与前端是独立改动）
- 定价底线的任何改动（上游 spec 已交付，本次只提供数据）
- **纪律线（参考售价 × 折扣率）不作为本轮验收项** —— `reference_selling_price` 填充率 0.2%，补齐属于主数据录入工作，另开任务
- 清理 `core.staging_inventory` 的 80280 行历史数据（可另开任务；本次只标注不可用）
- 改造 `semantic` / `mart` 视图层（现有定义是对的，够用）
- Shopee / TikTok 的库存采集组件（本次只做妙手；另两个平台状态在 §8 记录）

---

## 5. 修复方案

### 5.1 步骤 1：摸清那 3 个新增字段 ✅ **已完成**

**产出（实测，2026-10-21）：**

```
模板 309（25 列）  vs  2026-09-15 采集文件（28 列）
  新增 3 列：次品库存、暂存库存、备注
  删除 0 列
  匹配率 25/28 = 89.3%   ← 与 catalog_files 里的报错完全一致
```

完整表头（28 列，采集文件实际顺序）：

```
*商品SKU, 商品图片, *商品名称, *规格, 商品分组, *单价\n（元）, *总价\n（元）,
库存总量, 可用库存, 预占库存, 次品库存, 暂存库存, 活动预留库存, 在途库存,
计划库存, 安全库存, 仓库, 仓位1, 库存数量\n可用库存\n预占库存,
近7天销量数据, 近30天销量数据, 近60天销量数据, 近90天销量数据,
备注, 创建时间, 更新时间, 创建人员, 更新人员
```

模板 309 的 25 列（去掉上表中的 `次品库存`、`暂存库存`、`备注` 即可，**顺序不变**）。

**复现命令：**

```python
import pandas as pd
df = pd.read_excel(
    "data/raw/2026/miaoshou_inventory_snapshot_20260915_000609.xls", nrows=0
)
actual = [str(c) for c in df.columns]
```

**语义影响：** 这 3 列**对库龄计算无影响**（库龄只用 `可用库存` / `库存总量` / `*单价（元）` / `*总价（元）`，全部已存在）。入库时 `raw_data_importer` 的动态列机制会把它们物化成 `b_class.fact_miaoshou_inventory_snapshot` 上的真实 text 列，原样留档，供后续做次品/暂存库存分析。

### 5.2 步骤 2：发布新版本模板

基于 309 复制出 v3：

| 字段 | 新值 |
|---|---|
| `template_name` | `miaoshou_inventory__snapshot_v3` |
| `version` | 3 |
| `status` | `published` |
| `field_count` | **28** |
| `header_columns` | 28 列（§5.1 顺序） |
| `header_bindings` | 28 条（3 条新增绑定，位置 10/11/23，`required=false`、`confidence=0.5`、`sample_type="string"`，与既有 25 条同构） |
| `deduplication_fields` | 不变 |
| `field_parse_rules` | **不变**（`metric_date = __file_date_from__`） |
| 309 | `status` 改 `archived`（**不改它的历史内容**） |

> **不需要动 `core.field_mapping_template_items` / `core.field_mapping_template_versions`** —— 实测 309 的 items 是空的，模板内容全在 `core.field_mapping_templates` 一行里。

> **不需要动 `core.collection_configs.template_id`** —— 见 §2.6 的澄清：那是 FK 到
> `core.collection_config_templates`（采集配置默认值模板），id=15 有效；字段映射模板由
> `template_matcher.find_matching_template` 按 published + version DESC 自动选取。
> **v3 一旦发布并 version 最高，立刻自动生效。**

**验收：**

```sql
SELECT id, template_name, version, status, field_count
FROM core.field_mapping_templates
WHERE data_domain='inventory' AND status='published';
-- 期望：恰好 1 行，field_count = 28，version = 3

-- 确认自动选取会命中 v3
SELECT id, template_name, version FROM core.field_mapping_templates
WHERE platform='miaoshou' AND data_domain='inventory' AND status='published'
ORDER BY version DESC LIMIT 1;
-- 期望：v3
```

### 5.3 步骤 3：作废 2755，放行 2764

- **2755（23 字节空壳）**：把 `public.catalog_files` 记录标记为不可用（`status` 置为 `source_missing` 或按仓库既有的作废口径），并在 `error_message` 写明「原始文件仅 23 字节，磁盘不存在，无法入库；由 2026-09-15 之后的重新采集替代」。
  - 仓库已有 `data_sync_cleanup_service` 的 `source_missing` 状态口径（`backend/services/data_sync_cleanup_service.py:161`），优先复用既有状态而不是新造。
  - **同时要防止它继续占着 `pending` 队列**：`auto_ingest_pending_files` 只捞 `status='pending'`（`backend/tasks/scheduled_tasks.py:1226`），作废状态后它不会再被反复领取。
- **2764（真实文件）**：模板更新后，治理层应重新判定 → 触发自动入库。
  - 自愈机制会做这件事：`auto_ingest_pending_files` 每次先跑 `_recover_template_update_required_files`（`scheduled_tasks.py:1216`），把 `template_update_required` 且重新判定为可入库的文件退回 `pending`。
  - 若未自动触发，改为手工调 `DataSyncService.sync_single_file(file_id=2764, only_with_template=True)`。
- **查清自动入库当初为什么超时** —— 11 MB / 1226 行的数据量并不大，`AUTO_INGEST_STALE_TIMEOUT_MINUTES` 默认 45 分钟，理论上够用。要么是当时环境问题，要么是别的原因。**不查清，下次还会卡。**

**验收：**

```sql
SELECT status, count(*) FROM public.catalog_files WHERE data_domain='inventory' GROUP BY 1;
-- 期望：ingested = 1，无 template_update_required / pending / processing
SELECT count(*) FROM b_class.fact_miaoshou_inventory_snapshot;
-- 期望：1226
```

### 5.4 步骤 4：打开调度（**三处必须一起改**）

**改动清单（缺一不可）：**

| # | 字段 | 从 | 到 | 理由 |
|---|---|---|---|---|
| 1 | `date_range_type` | `custom` | **`auto_prev_day`** | 消除 §2.6 坑 1。`auto_prev_day` 是 dynamic 策略，`resolve_collection_time_window` 按运行时刻算出 `available_day`（`now >= 06:00` 取今天，否则取昨天，时区 `Asia/Hong_Kong`）→ `date_from = date_to = 实际采集日`，**永远跟随真实日期**。且 dynamic 分支在 `normalize_time_selection` 里**先于** custom 字段检查返回（`collection_contracts.py:132`），残留的 `custom_date_start/end` 不会导致报错。 |
| 2 | `custom_date_start` / `custom_date_end` | `2026-03-23` / `2026-03-29` | `NULL` | 卫生清理。dynamic 模式下不生效，但留着会误导下一个看配置的人，也让 `_get_config_time_selection` 走 `custom` 分支。 |
| 3 | `schedule_enabled` | `false` | `true` | 真正打开采集 |
| 4 | `schedule_cron` | `null` | **`0 9 * * 0,3`** | 见 §10 频次决策。**注意 APScheduler 语义**：`0`=周一、`3`=周四（§2.6 坑 2）→ 实际是**周一 09:00 + 周四 09:00**，间隔 3~4 天。 |
| 5 | `batch_status` | `draft` | `active` | `draft` 的配置不会被正常调度执行 |
| 6 | `execution_mode` | `headed` | 待定 | 见 §8 风险：headed 需要可见浏览器。无人值守调度前必须确认妙手账号能免验证码登录；不能则保留 headed 并接受人工触发。 |

> **`template_id` 不用改** —— 它是 FK 到 `core.collection_config_templates`（采集配置默认值模板），id=15 有效（§2.6 澄清）。

**改动方式：** 优先走 API `POST /api/collection/configs/30/schedule`（`backend/domains/collection/routers/collection_schedule.py:309`）—— 它会同时 `scheduler.add_schedule()` 注册 APScheduler 作业。
**不要用** `POST /api/collection/schedule/granularity/weekly` —— 那个接口会把该粒度的**所有**配置统一刷成预设 cron（`0 9 * * 1` = 实际周二），既覆盖不到我们想要的 3 天节奏，也带上了 §2.6 坑 2 的星期偏移。

**手动触发路径（验证用）：** `POST /api/collection/configs/30/run`（`collection_config.py:1464` 一带同样走 `build_date_range_from_time_selection`）。

**验收：**

```sql
SELECT id, date_range_type, custom_date_start, custom_date_end,
       schedule_enabled, schedule_cron, execution_mode, batch_status
FROM core.collection_configs WHERE id = 30;
-- 期望：auto_prev_day / NULL / NULL / true / '0 9 * * 0,3' / (headed|headless) / active
```

```sql
SELECT id, file_name, status, date_from, date_to, first_seen_at
FROM public.catalog_files
WHERE data_domain='inventory' AND first_seen_at >= CURRENT_DATE;
-- 期望：≥1 行，且 date_from == 当天（或昨天），绝不能是 2026-03-23
```

### 5.5 步骤 5：端到端跑通 age_refresh（**验收口径已修正**）

`backend/services/data_pipeline/inventory_age_refresh_service.py` 是**已存在且正确**的库龄计算服务（锚点重置 / 分档 / 补货归零 / 卖空重现归零），**不要重写**。管道通后确认它被触发：

```sql
SELECT count(*) FROM mart.inventory_age_current;
-- 期望 > 0
SELECT bucket, count(*) FROM mart.inventory_age_current GROUP BY 1;
```

> **⚠️ 修正后的验收口径：刚打通管道时，`bucket` 只有 `0-30` 一个值是「正确结果」，不是 bug。**
>
> 原因：库龄的起算点是「该 SKU 第一次有库存的那天」（`age_anchor_date` = 第一帧快照的 `snapshot_date`，`reset_reason='first_positive'`）。只有一帧快照时，所有 SKU 的 `age_days` 都是 0。
>
> 分档要生效需要**第二帧**：
>
> | 帧 | `snapshot_date` | `age_days` | 库龄看板 bucket | 定价档位 |
> |---|---|---|---|---|
> | 锚点帧（2764） | 2026-09-14 | 0 | 0-30 | 日常 |
> | 第二帧 | 采集日 | 与锚点的天数差 | 随天数 | 随天数 |
>
> 因此本步骤的验收是「**管道通、库龄表有数据、`age_anchor_date` 正确落在 2026-09-14**」，**分档多样性的验收放在第二帧之后**（见 §6）。

**若 `age_days` 全是 0 之外的异常值**（例如全是同一个非 0 值），回查 `mart.inventory_age_current.age_anchor_date` 与 `reset_reason`。

### 5.6 步骤 6：join 命中率验收

```sql
SELECT count(*) AS 总数,
       count(*) FILTER (WHERE s.sku_id IS NOT NULL) AS 命中
FROM mart.inventory_age_current a
LEFT JOIN core.dim_erp_sku s ON s.sku_key = a.product_sku;
-- 期望：命中率 ≥ 95%（真实文件基线 99.64%）
```

若命中率明显低于 99.64%，先看 `product_sku` 是不是被截断/带规格后缀，
**不要用「去空格」的方式凑命中**（实测会让匹配变差）。

### 5.7 步骤 7：回看定价底线

管道通后，商品中心 SKU 资料页的「当前可优惠」应随真实库龄分档（不再是恒 10%）。

**验收方式：** 在本地库造一个库龄不同的 SKU（或等第二帧落地），刷新商品中心，
确认「当前可优惠」出现 10% / 15% / 20% / 30% 多种值。

> 定价底线**不需要改任何代码**——`backend/domains/business/routers/product_center.py` 里
> `_load_age_days_by_sku` 已经是「表不存在就回落日常档」的安全实现
> （`SELECT to_regclass('mart.inventory_age_current')` 探测 + SAVEPOINT 兜底），
> 表有数据后自动生效。
>
> **预期幅度提醒（业务侧要提前知道）：** 分档一旦解锁，1084 个能算底线的 SKU 的最低售价会明显下调。以 `A-00001-BLACK`（采购成本 ¥46.5）为例：日常档（目标利润率 25%）底线 ¥128.56 → 最深档（目标利润率 10%）底线 ¥90.82，**降 29%**。这是设计意图（滞销品该降价清），但上线前要跟业务方对齐这个幅度。
>
> 纪律线（参考售价 × 折扣率）本轮**不验收**（填充率 0.2%，见 §2.8、§4.2）。

---

## 6. 验收标准（全部可执行）

| # | 断言 | 查询 / 方式 | 状态 |
|---|---|---|---|
| 1 | 只有一个 published 模板 | `core.field_mapping_templates` inventory 的 published 恰好 1 行，`field_count = 28`、`version = 3` | ✅ **已完成**（id=370） |
| 2 | 没有卡住的文件 | `public.catalog_files` inventory 的 status 只有 `ingested`（2755 为已作废） | 待做 |
| 3 | b_class 有数据 | `SELECT count(*) FROM b_class.fact_miaoshou_inventory_snapshot` = 1226 | 待做 |
| 4 | semantic 有数据 | `SELECT count(*) FROM semantic.fact_inventory_snapshot` > 0 | 待做 |
| 5 | mart 快照链有数据 | `SELECT count(*) FROM mart.inventory_snapshot_history` > 0 | 待做 |
| 6 | **库龄表有数据且锚点正确** | `mart.inventory_age_current` 行数 > 0，且 `age_anchor_date` = 2026-09-14（锚点帧），`reset_reason = 'first_positive'` | 待做 |
| 7 | **分档多样（第二帧后）** | `bucket` 出现 ≥ 2 个不同值 | **待第二帧**，不在本次单帧验收内 |
| 8 | join 命中率 ≥ 95% | 见 §5.6（真实文件基线 99.64%） | 待做 |
| 9 | **调度已开且日期设置正确** | `collection_configs.id=30`：`schedule_enabled = true`、`schedule_cron = '0 9 * * 0,3'`、`date_range_type = 'auto_prev_day'`、`custom_date_start IS NULL`、`batch_status = 'active'` | 待做 |
| 10 | **新采集产物日期正确** | `catalog_files` inventory 出现 `first_seen_at >= CURRENT_DATE` 的新行，且 `date_from` ≈ 当天（**绝不能是 2026-03-23**） | 待做 |
| 11 | 定价底线自动分档 | 第二帧落地后，商品中心「当前可优惠」出现多种值 | **待第二帧** |
| 12 | 纪律线生效 | — | **不在本轮范围** |

---

## 7. 已有资产（**不要重写**）

| 资产 | 位置 | 说明 |
|---|---|---|
| 库龄计算 + 分档 | `backend/services/data_pipeline/inventory_age_refresh_service.py` | 锚点重置 / 补货归零 / 卖空重现归零 / 0-30·31-60·61-90·91-180·180+ 分档，**已验证正确** |
| 库龄重算触发 | `backend/services/event_listeners.py:139` | `DATA_INGESTED` 事件命中 `data_domain == "inventory"` 时自动 `refresh()` |
| SKU 主数据同步 | `backend/services/product_center_service.py:40` | `sync_inventory_skus` 同步 `dim_erp_sku` + `bridge_erp_sku_keys` 别名 |
| 库龄看板（前端） | `frontend/src/domains/business/views/inventory/InventoryAging.vue` | 已存在 |
| 库龄预警（前端） | `frontend/src/domains/business/views/inventory/InventoryAlerts.vue` | 已存在 |
| mart 层 SQL | `sql/mart/inventory_age_current.sql`、`inventory_age_history.sql`、`inventory_snapshot_*.sql` | 已存在 |
| semantic 层 SQL | `sql/semantic/inventory_snapshot.sql` | 已存在（是视图，直接读 b_class） |
| api 读模型 | `sql/api_modules/inventory_age_list_module.sql`、`inventory_age_summary_module.sql` | 已存在 |
| 采集组件（V2 canonical） | `modules/platforms/miaoshou/components/inventory_export.py` | `MiaoshouInventoryExport`，Playwright 抓妙手 ERP 导出表 |
| 数据域导出映射 | `modules/apps/collection_center/python_component_adapter.py` | `"miaoshou": {"inventory": "MiaoshouInventoryExport"}` |
| 定价档位规则表 | `finance.sku_pricing_policies` | 4 行已就位 |
| 定价底线计算 | `backend/services/product_pricing_service.py` | 纯函数，已交付 |
| 自动入库 + 超时自愈 | `backend/tasks/scheduled_tasks.py` | `auto_ingest_pending_files` / `_recover_stale_auto_ingest_records` / `_recover_template_update_required_files` |

---

## 8. 风险与未知项

| 风险 | 说明 | 应对 |
|---|---|---|
| **🔴 配置日期写错会直接毁掉库龄** | §2.6 坑 1。只开 `schedule_enabled` 不改 `date_range_type`，每帧 `metric_date` 都是 2026-03-23 → 全 SKU 直接落 180+ 档 | §5.4 七项改动**一起做**；验收项 9 + 10 专门盯这个 |
| **🔴 妙手 ERP 会话可能无法无人值守** | 采集组件是 Playwright 驱动 ERP 界面导出，要登录/验证码；`execution_mode = headed` 需要可见浏览器 | 动手前确认有可用账号与会话；不能则保留 headed + 人工触发，并在交付说明里写明「采集非全自动」 |
| **自动入库为什么会超时** | 未知（文件大？字段多？当时环境异常？） | §5.3 必须查清，否则修完还会卡 |
| **补货漏检导致库龄虚高** | `compute_age_transition` 靠 `current_qty > previous_qty` 判补货；一周内补货又卖光则检不出，库龄继续累加 | 3 天采集把漏检窗口压到 ≤3 天；上线后用 `reset_reason` 分布复核（见 §10） |
| **`mart.inventory_snapshot_change` 的 `estimated_stagnant_days` 会随采集变密而变小** | 该字段只取**最近两帧的间隔**（3 天采 → ≤3），不是累计；而 `api.clearance_ranking_module` 要求 `GREATEST(estimated_stagnant_days, estimated_turnover_days) >= 30` | 已知并接受；这是滞销模块的口径特性，SKU 级滞销另立 spec 时单独处理 |
| 模板 309 之外还有 11 个 archived 版本 | 直接改 309 可能破坏历史回溯 | 走治理流程发新版本，不改历史版本 |
| **`GRANULARITY_SCHEDULE_PRESETS["weekly"]` 星期偏移一天** | 预设 `0 9 * * 1` 实际跑周二（§2.6 坑 2） | 本次不用该预设；缺陷记录在案，另开任务修 |
| **Shopee / TikTok 的 inventory 域** | 采集映射里只有 `miaoshou.inventory`，另两个平台的快照表必然 0 行 | 本次只做妙手；另两个平台状态与原因在交付说明里明确记录 |
| 4 个 SKU 匹配不上 | ERP 主数据缺这些新品族（`HJJ-XH-CTD01/02`、`CTS01/02`） | 属主数据问题，不在本 spec 范围；命中率 99.64% 已足够 |
| 历史 80280 行 | 形态不同，价值为 0 | 不要灌进库；可另开任务清理 |
| **纪律线不生效** | `reference_selling_price` 填充率 0.2% | 本轮不验收（§4.2）；「当前可优惠」目前只通过目标利润率影响底线 |

---

## 9. 参考文档

| 文档 | 用途 | 备注 |
|---|---|---|
| `docs/superpowers/specs/2026-10-21-sku-level-clearance-ranking-design.md` | **同批新增**：SKU 级滞销排名 | 与本 spec 共用库龄/快照底座 |
| `docs/superpowers/specs/2026-04-09-snapshot-continuous-inventory-aging-design.md` | **主设计**：快照连续库龄 | 与当前架构一致（snapshot-first） |
| `docs/superpowers/plans/2026-04-09-snapshot-continuous-inventory-aging.md` | 04-09 的实施计划 | |
| `docs/superpowers/specs/2026-04-04-real-inventory-aging-design.md` | 早期版（ledger/FIFO 方向） | **已被 04-09 修正**，只当历史背景 |
| `docs/superpowers/plans/2026-10-20-sku-pricing-guardrails.md` | 定价底线计划（文末有移交说明） | 本 spec 是它的下游 |
| `docs/superpowers/specs/2026-10-20-sku-pricing-guardrails-design.md` | 定价底线设计 | §4.1 库龄口径、§5.5 护栏 |
| `docs/API_CONTRACTS_TASK_COMPLETION_STATUS.md` | 滞销相关 API 的完成状态 | 「滞销天数阈值筛选」标为未来 |
| `docs/guides/PRE_LAUNCH_RULES.md` | 上线前变更边界 | 本次改动以最小面为主 |

---

## 10. 采集频次与档位时间线

### 10.1 决策

**每 3 天采集一次（周一 + 周四 09:00），下限每周一次。**

cron = `0 9 * * 0,3`（**APScheduler 语义**：`0`=周一、`3`=周四）。

**为什么不用 `*/3` 的 day-of-month 写法：** `0 9 */3 * *` 会按「1/4/7/.../28 号」触发，跨月时 28 号到 1 号只隔 1~4 天，节奏不稳定，还会制造近乎重复的快照。周一/周四固定节奏，间隔恒为 3~4 天，无跨月问题。

**为什么下限是每周：** 妙手 ERP 会话是稀缺资源，采集频次直接等于登录/验证码失败概率。cron 是一个字段，随时可改（`0 9 * * 0` = 每周一）。

### 10.2 档位解锁时间线（锚点 = 2026-09-14）

| 库龄档位 | 翻转日（锚点 + N 天） | 3 天采集实际生效 | 每周采集实际生效 |
|---|---|---|---|
| 60 天档（滞销30天，15%） | 2026-11-13 | 11-15 前后 | 11-16 前后 |
| 90 天档（滞销60天，20%） | 2026-12-13 | 12-14 前后 | 12-14 前后 |
| 120 天档（滞销60天以上，30%） | 2027-01-12 | 2027-01-14 前后 | 2027-01-18 前后 |

> **档位翻转日由锚点固定，与采集频次无关。** 频次只影响「翻转被观测到」的延迟：3 天采集 ≤3 天，每周 ≤7 天。档位带宽 30 天，7 天抖动可接受。

### 10.3 上线后的持续观测

跑满 2~3 帧后，用库龄重置原因分布复核「补货漏检」是否严重：

```sql
SELECT reset_reason, count(*)
FROM mart.inventory_age_history
WHERE snapshot_date >= :起跑日
GROUP BY 1 ORDER BY 2 DESC;
```

- `stock_increase`（补货归零）占比**明显偏低** + `continued`（持续累加）占比畸高 → 补货漏检严重，考虑加密到每天
- 分布正常 → 保持 3 天

---

## 11. 开工前请先做的一件事

**核对 §2 的实测数字是否仍然成立**（表行数、`catalog_files` 状态、模板状态、配置开关）。

本文档 §2 的所有数字都是 **2026-10-21 在本地库 `xihong_erp` 上实测**的，
但中间链路涉及采集任务、调度、模板治理等多个外部可变因素，**下一会话开场应先重测**。

若与 §2 不一致，**以实测为准并更新本 spec**，不要按旧数字施工。
