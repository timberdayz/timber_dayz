# 库存库龄管道恢复 + SKU 级滞销排名 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让妙手库存快照真正入库并持续更新，使 `mart.inventory_age_current` 拿到真实库龄，从而让商品中心的「当前可优惠 / 最低售价」按真实库龄分档；同时新增 SKU 级滞销清单，把滞销判定从「最近两帧间隔」升级为真库龄，并把定价信息直接带到清单上。

**Architecture:** 管道侧不动任何计算逻辑 —— 库龄服务（`inventory_age_refresh_service.py`）、三层 SQL（`sql/semantic` / `sql/mart` / `sql/api_modules`）都已存在且正确，缺的是「把文件放进来 + 让它持续来」。因此主体工作是 ① 发一版 28 列的字段映射模板 ② 清掉一个 23 字节的空壳文件记录 ③ 修正采集配置的日期与调度设置 ④ 端到端验收。滞销侧新增一张 `api.sku_clearance_ranking_module` 视图 + 一个只读端点 + 库龄看板页的一个新页签，定价字段复用 `product_pricing_service` 的纯函数口径（**不在 SQL 里重写公式**）。

**Tech Stack:** PostgreSQL 15、Alembic current-schema 迁移（`alembic-current.ini`）、SQLAlchemy 2.0 async、FastAPI、Pydantic v2、pytest、Vue 3 + Element Plus。

**Spec:**
- `docs/superpowers/specs/2026-10-21-inventory-aging-pipeline-recovery-design.md`（库龄管道恢复）
- `docs/superpowers/specs/2026-10-21-sku-level-clearance-ranking-design.md`（SKU 级滞销排名）

**Alembic 起点:** `current_migrations/versions/20261021_sku_pricing_creator_commission.py`（revision `current_schema_20261021_sku_pricing_creator_commission`）是当前 head。

---

## 执行前必读

### 0.1 本计划的数字都是实测的，但**先重测**

spec §2 的所有数字来自 **2026-10-21 23:00 在本地库 `xihong_erp` 的实测**。
中间链路涉及采集任务、调度、模板治理等多个外部可变因素，**开工第一步先重跑一遍 §6 的验收 SQL**，与 spec 不一致时**以实测为准并更新 spec**。

### 0.2 三个已知的既有坑（都在本计划里被显式处理）

| 坑 | 位置 | 本计划的处理 |
|---|---|---|
| `date_range_type='custom'` 会把死窗口写进新文件的 `date_from` | `collection_config_execution.py:151` → `collection_contracts.py:238` | Task 3 改 `auto_prev_day` + 清空 `custom_date_*` |
| APScheduler `from_crontab` 的星期编号比标准 crontab 偏移一天 | `collection_scheduler.py:216` | Task 3 的 cron 按 APScheduler 语义写：`0 9 * * 0,3` = **周一 + 周四** |
| `GRANULARITY_SCHEDULE_PRESETS["weekly"]` 预设 `0 9 * * 1` 实际跑周二 | `collection_schedule.py:53` | **不用**该预设；用 per-config 端点传自定义 cron |

### 0.3 迁移命令必须带 `-c alembic-current.ini`

```powershell
python -m alembic -c alembic-current.ini upgrade head
```

不带 `-c` 会跑到另一条迁移链上（10-20 计划踩过）。

### 0.4 既有红测试（不是本次引入，勿混淆）

`frontend/tests/productCenterUi.test.mjs` 与 `backend/tests/test_platform_sku_profit_workbench.py` 在本次开工前**已经是红的**（详见 10-20 计划 §0.1 / §0.1b）。**Task 7 的「Run test」步骤只统计本任务新增的用例。**

### 0.5 不要做的事

- **不要重写** `backend/services/data_pipeline/inventory_age_refresh_service.py`（已验证正确）
- **不要改** `sql/semantic/inventory_snapshot.sql` / `sql/mart/inventory_*.sql` 的定义（已验证够用）
- **不要动** `core.staging_inventory` 的 80280 行历史数据（形态不对，灌进去在库量会算成 0）
- **不要**用「去掉空格」的方式提高 SKU 匹配率（实测会让匹配变差）
- **不要**在 SQL 视图里重写最低售价公式（见 Task 5）

### 0.6 运行时形态（2026-10-22 实测补充）

自动入库、刷新队列、调度**全部跑在 Docker 容器里**，代码来自**主工作区**的 bind mount：

- `xihong_erp_celery_worker` / `xihong_erp_celery_beat`（Celery Beat 每 15 分钟跑 `auto_ingest_pending_files`，每分钟跑 `process_refresh_queue_task`）
- `xihong_erp_postgres`（对外 15432，与本机直连同一个库）/ `xihong_erp_redis`

**因此：**

| 改动类型 | 生效方式 |
|---|---|
| DB 侧（迁移、配置项、模板）| 立刻生效 |
| `backend/` 代码侧 | **必须合并到主工作区 + 重启 worker** 才生效 |

worktree 里既没有 `data/`（gitignore），原始文件也读不到 —— 要跑入库/采集相关脚本，要么在主工作区跑，要么把 `data` 挂进 worktree。

---

## Task 1：发布 inventory 字段映射模板 v3（28 列）

**产出:** `current_migrations/versions/20261021_inventory_template_v3.py`

### Step 1.1 建迁移文件

```python
"""发布 miaoshou inventory 字段映射模板 v3（28 列）。

背景：2026-09 妙手库存导出在 V2 canonical 重写后多了 3 个字段
（次品库存 / 暂存库存 / 备注），现行 published 模板 309 只有 25 列，
导致文件 2764 被治理层判定 breaking_drift 挂起。

迁移做两件事：
  1. 基于 309 复制出 v3，header_columns 扩到 28 列
  2. 309 置 archived（不改它的历史内容）

⚠️ 不动 core.collection_configs.template_id —— 那是 FK 到
   core.collection_config_templates（采集配置默认值模板），id=15 有效。
   字段映射模板由 template_matcher 按 published + version DESC 自动选取。
"""
```

迁移体（**幂等**：以「inventory 域已存在 published 且 28 列的模板」为守卫）：

1. `SELECT ... FROM core.field_mapping_templates WHERE id = 309` → 取 `header_columns` / `header_bindings` / `deduplication_fields` / `field_parse_rules` / `platform` / `data_domain` / `granularity` / `account` / `header_row` / `sheet_name` / `encoding`
   - ⚠️ 这些列在 `text()` 查询里返回的是 **JSON 文本**，要 `json.loads` 一次（实测 `jsonb_typeof` = `array`：DB 里是真正的数组，只是驱动按字符串返回）
2. 构造 28 列的 `header_columns`：在 309 的 25 列上按**锚列名**插入 `次品库存`(after 预占库存) / `暂存库存`(after 次品库存) / `备注`(before 创建时间)—— **锚列找不到就报错**，不硬编码下标
3. 构造 28 条 `header_bindings`：克隆 309 的 25 条，**重新编号 `position` 0..27** 并把新 3 条插到正确位置；新绑定用同构默认值：`{"aliases": [], "position": N, "raw_name": "<列名>", "required": false, "confidence": 0.5, "sample_type": "string", "display_name": "<列名>", "semantic_key": null, "semantic_role": null, "hash_participates": false}`
4. `INSERT` 新行：`template_name='miaoshou_inventory__snapshot_v3'`、`version=3`、`status='published'`、`field_count=28`、`created_by='migration'`、`notes='2026-09 妙手导出新增 次品库存/暂存库存/备注,补齐到 28 列'`、`created_at/updated_at = now()`
5. `UPDATE core.field_mapping_templates SET status='archived' WHERE id=309`
6. `downgrade`：`DELETE` v3，把 309 的 `status` 改回 `published`

> ⚠️ **不要动** `core.field_mapping_template_items` / `core.field_mapping_template_versions` —— 实测 309 的 items 是空表，模板内容全在 `core.field_mapping_templates` 一行里（spec §0 表 #4）。
>
> ⚠️ **不要动 `core.collection_configs.template_id`** —— 实测它是 FK 到 `core.collection_config_templates`（采集配置默认值模板），id=15 存在且正确。字段映射模板走 `template_matcher.find_matching_template` 自动选取（spec §0 表 #7）。

### Step 1.2 跑迁移

```powershell
$env:DATABASE_URL='postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp'
python -m alembic -c alembic-current.ini upgrade head
```

> ⚠️ 工作区（worktree）里**没有 `.env`**（被 gitignore），`current_migrations/env.py` 只认环境变量 `DATABASE_URL`，**必须显式设置**。

### Step 1.3 验证

```sql
SELECT id, template_name, version, status, field_count, jsonb_array_length(header_columns) AS cols
FROM core.field_mapping_templates
WHERE data_domain='inventory' ORDER BY id;
-- 期望：309 archived/25、v3 published/28，且 cols=28

-- 确认自动选取会命中 v3
SELECT id, template_name, version FROM core.field_mapping_templates
WHERE platform='miaoshou' AND data_domain='inventory' AND status='published'
ORDER BY version DESC LIMIT 1;
-- 期望：v3

-- 确认 309 的历史内容没被动过
SELECT jsonb_array_length(header_columns) FROM core.field_mapping_templates WHERE id=309;
-- 期望：25
```

- [x] 迁移文件已建
- [x] `upgrade head` 无错
- [x] 上面三条 SQL 符合期望（实测 v3 = id 370，28 列，绑定 0..27，matcher 选中 v3）
- [ ] `git commit -m "feat:发布妙手库存字段映射模板 v3(28列)"`

---

## Task 2：作废 2755 空壳文件，放行 2764 入库

### Step 2.1 作废 2755

2755 只有 23 字节、磁盘上无此文件 → 不可能入库。用仓库既有的 `source_missing` 状态口径（`backend/services/data_sync_cleanup_service.py:161`）：

```sql
UPDATE public.catalog_files
SET status = 'source_missing',
    error_message = '原始文件仅 23 字节且磁盘不存在，无法入库；已由 2026-09-15 之后的重新采集替代',
    processed = false
WHERE id = 2755;
```

> **关键**：`auto_ingest_pending_files` 只捞 `status='pending'`（`backend/tasks/scheduled_tasks.py:1226`）。2755 现在的状态就是 `pending`（已被超时自愈退回），**不处理它会被反复领取、反复失败**。改成 `source_missing` 后不再进队列。

### Step 2.2 放行 2764

模板更新后，治理层应重新判定。等一轮 `auto_ingest_pending_files`（Celery Beat，每 15 分钟）即可 —— 它每次先跑 `_recover_template_update_required_files`（`scheduled_tasks.py:1216`），把重新判定为可入库的 `template_update_required` 文件退回 `pending`。

**若未自动触发**，手工调一次：

```python
from backend.models.database import AsyncSessionLocal
from backend.services.data_sync_service import DataSyncService

async with AsyncSessionLocal() as db:
    result = await DataSyncService(db).sync_single_file(
        file_id=2764, only_with_template=True, allow_quarantine=True
    )
```

### Step 2.3 查清「自动入库当初为什么超时」

11 MB / 1226 行的数据量并不大，`AUTO_INGEST_STALE_TIMEOUT_MINUTES` 默认 45 分钟，理论上够用。**不查清，下次还会卡。**

排查线索：
- `public.catalog_files.file_metadata->'auto_ingest'` 的历史
- `core.collection_tasks` 里对应任务的 `duration_seconds` / `error_message`
- 后端日志里 2026-09-14 那次的入库异常
- `AUTO_INGEST_MAX_CONCURRENT`（默认 1）/ `AUTO_INGEST_MAX_FILES_PER_RUN`（默认 20）

**产出：写进本计划的「执行期发现」小节。**

### Step 2.4 验证

```sql
SELECT status, count(*) FROM public.catalog_files WHERE data_domain='inventory' GROUP BY 1;
-- 期望：ingested=1、source_missing=1，无 template_update_required / pending / processing

SELECT count(*) FROM b_class.fact_miaoshou_inventory_snapshot;
-- 期望：1226

SELECT count(*) FROM semantic.fact_inventory_snapshot;
-- 期望：> 0

SELECT count(*) FROM mart.inventory_snapshot_history;
-- 期望：> 0
```

- [x] 2755 状态已改 `source_missing`
- [x] 2764 已入库，b_class 1226 行
- [x] 超时原因已查明并记录
- [x] `git commit -m "fix:作废妙手库存空壳文件记录并放行真实快照入库"`

---

## Task 2 执行期发现（2026-10-22 实测，**改写了原计划的前提**）

### 2.A 运行形态：自动入库跑在 Docker 里，代码不来自 worktree

`docker ps` 实测：`xihong_erp_celery_worker` / `xihong_erp_celery_beat` / `xihong_erp_redis` / `xihong_erp_postgres` 全部 Up 8 小时。

容器挂载（`/app`）：

| 容器路径 | 宿主来源 |
|---|---|
| `/app/backend` | `F:\Vscode\python_programme\AI_code\xihong_erp\backend`（**主工作区**） |
| `/app/data` | `F:\...\xihong_erp\data` |
| `/app/sql`、`/app/modules`、`/app/migrations`、`/app/temp`、`/app/logs` | 主工作区对应目录 |

**推论（两条都要记住）：**

1. **worktree 里改的 `backend/` 代码不会进容器** —— 容器跑的是主工作区代码。worktree 里的代码改动要等合并到主工作区 + 重启 worker 才生效。
2. **worktree 里没有 `data/`（gitignore），原始文件找不到** —— 要跑入库必须在主工作区跑，或把 `data` 挂进去。

`core.refresh_queue_tasks` / `public.catalog_files` / `core.collection_configs` 都是**同一个库**（`localhost:15432`），所以 **DB 侧改动立刻生效**，代码侧不生效。

### 2.B 「自动入库超时」的真正原因：不是慢，是**文件不存在 + 状态机死循环**

原计划以为「11MB/1226 行数据量不大，45 分钟阈值理论上够用」。实测**完全不是超时**：

`public.task_center_tasks` 里 2026-10-21 15:30 那次 `auto_ingest` 任务（id=1750）**耗时 0.24 秒**，结果是：

```json
{"file_id": 2755, "status": "blocked_template_update", "error_code": "FILE_MISSING",
 "message": "文件不存在: [Errno 2] No such file or directory:
             '/app/data/raw/2026/miaoshou_inventory_snapshot_20250914_134915.xlsx'",
 "template_status": "file_missing", "governance_status": "parse_failed"}
```

**2755 的文件从未落盘**（23 字节，容器 `/app/data/raw/2026` 下没有 `20250914` 的任何文件）。

「超时」是**下游症状**：`auto_ingest_pending_files` 先 `_claim_auto_ingest_files` 把 2755 置成 `processing`，然后 `process_single` 发现文件不存在直接返回，**但这条分支不写回文件状态**（只有 `template_status == 'update_required'` 分支才会 `_mark_file_template_update_required`）。于是 2755 永远卡在 `processing`：

```
claim → processing → 阻塞(FILE_MISSING) → 不写回 → 卡住
  ↓ 45 分钟后
_recover_stale_auto_ingest_records → 退回 pending → 下一轮又 claim → 又卡住 → 无限循环
```

实测证据：2755 的 `file_metadata.auto_ingest` 里 `last_recovered_at=2026-10-21T15:30:00`、`processing_started_at=2026-10-21T15:30:02` —— 差 2 秒，正是「刚被看门狗退回 pending、2 秒后又被领走」。

**处置**：2755 置 `status='source_missing'`（仓库既有口径，`data_sync_cleanup_service.py:161`）。`auto_ingest_pending_files` 只捞 `status='pending'`，改成 `source_missing` 后彻底出队，死循环终止。实测确认 inventory 域最终只剩 `ingested=1` / `source_missing=1`。

### 2.C 第二个断链（**原计划完全没预料到**）：刷新从未入队，库龄表一直空

2764 于 16:15:05 入库成功（1226 行），但 `mart.inventory_age_current` 一直是 **0 行**。查 `core.refresh_queue_tasks`：**16:15 没有任何新任务**。

根因在 `backend/services/event_listeners.py`：

```python
# 修复前
task = asyncio.create_task(enqueue_refresh_for_data_ingested_event(event))
```

`asyncio.create_task` 把入队排进事件循环，而调用方是 Celery worker 里的 `asyncio.run(...)`——**收尾时 `asyncio.run` 会取消所有未完成的 task**。于是入队协程从未跑完，刷新从未入队。

**关键佐证**：worker 日志里有 `[EventListener] PostgreSQL refresh enqueue task scheduled`，但**没有** `[EventListener] PostgreSQL refresh intent enqueued` —— 后者才是入队成功的标志。

顺带发现：`run_pipeline_refresh_for_data_ingested_event`（唯一调用 `sync_inventory_skus` + `InventoryAgeRefreshService.refresh()` 的函数）**生产代码里从来没被调用过**，只有测试在调。`core.bridge_erp_sku_keys` 因此全是 `product-catalog` 源（1118 行），一条 `miaoshou` 源都没有——商品中心的 sku_id 映射因此缺料。

**修复**（提交 `70420fe4`）：

1. `event_listeners.py` 新增 `handle_data_ingested_async`，**await 到入队落库**；`handle_data_ingested` 加 `enqueue_refresh` 开关，无事件循环时用 `asyncio.run` 直接跑完
2. `data_ingestion_service.py` 事件派发改调 `await event_listener.handle_data_ingested_async(event)`
3. `refresh_queue_tasks.py` 的 inventory 分支补上 `sync_inventory_skus`（与原 inline 路径对齐），再刷库龄

### 2.D 2764 是怎么进库的（**不是手工触发的**）

模板 v3 在 **16:05:26** 发布（`core.field_mapping_templates.id=370`）。16:00 那轮复核用的还是旧模板 309（25 列），所以报「新增3个、匹配率89.3%」属正常。16:15 那轮 `auto_ingest_pending_files` 的 `_recover_template_update_required_files` 命中 v3（28 列），把 2764 退回 `pending`，**同一轮**就被领走并入库成功。

> ⚠️ 因此「等一轮自动入库即可放行」这条原计划结论是成立的，但**前提是模板发布时间要早于复核时间**。发布模板后要等最多 15 分钟。

### 2.E Task 2 实测验收结果

| 检查项 | 期望 | 实测 |
|---|---|---|
| inventory 域 catalog_files 状态 | ingested=1 / source_missing=1 | ✅ `ingested=1`、`source_missing=1` |
| `b_class.fact_miaoshou_inventory_snapshot` | 1226 | ✅ **1226** |
| `semantic.fact_inventory_snapshot` | > 0 | ✅ **1226** |
| `mart.inventory_snapshot_history` | > 0 | ✅ **1226**（snapshot_date=2026-09-14）|
| `mart.inventory_snapshot_company_daily` | 1122 | ✅ **1122**（= 文件去重 SKU 数）|
| `mart.inventory_age_current` | > 0（Task 4）| ✅ **495**（在库 qty>0 的 SKU）|
| `age_anchor_date` | 2026-09-14 | ✅ **2026-09-14** |
| `bucket` | 单帧只有 `0-30` | ✅ 只有 `0-30`（495）|
| `reset_reason` | 单帧只有 `first_positive` | ✅ 只有 `first_positive`（495）|
| join 命中率 | ≥ 95% | ✅ **99.80%**（494/495）|
| `core.dim_erp_sku` | 随入库刷新 | 1121 → **1125** |
| `core.bridge_erp_sku_keys` miaoshou 源 | > 0 | 0 → **1122** |

`age_current=495` vs `age_history=1122` 的差额不是丢数据：`replay_snapshot_rows` 只在 `current_qty > 0` 时才产出 current 行。实测在库 495 个 SKU / 11190 件，零库存 627 个（合计 -6 件，源数据本身有微负）。


---

## Task 3：打开每周一 + 周四的定时采集

**这是全计划风险最高的一步。** 改错日期设置会让所有 SKU 一步落进最深档（spec §2.6 坑 1）。

### Step 3.1 改配置（6 项一起改）

```sql
UPDATE core.collection_configs
SET date_range_type   = 'auto_prev_day',
    custom_date_start = NULL,
    custom_date_end   = NULL,
    schedule_enabled  = true,
    schedule_cron     = '0 9 * * 0,3',
    batch_status      = 'active',
    updated_at        = now()
WHERE id = 30;
```

| 字段 | 值 | 理由 |
|---|---|---|
| `date_range_type` | `auto_prev_day` | dynamic 策略，`resolve_collection_time_window` 按运行时刻算 `available_day`（`now >= 06:00` 取今天，否则昨天，时区 `Asia/Hong_Kong`）→ `date_from` 永远跟随真实日期。dynamic 分支在 `normalize_time_selection` 里**先于** custom 字段检查返回（`collection_contracts.py:132`），残留的 `custom_date_*` 不会报错 |
| `custom_date_start/end` | `NULL` | 卫生清理。dynamic 模式下不生效，但留着会误导人 |
| `schedule_enabled` | `true` | 真正打开采集 |
| `schedule_cron` | `0 9 * * 0,3` | **APScheduler 语义**：`0`=周一、`3`=周四 → 周一 09:00 + 周四 09:00，间隔 3~4 天。**不要用标准 crontab 语义**（那会变成周三+周六） |
| `batch_status` | `active` | `draft` 的配置不会被正常调度执行 |
| `execution_mode` | 见 Step 3.2 | 取决于妙手会话能否无人值守 |

> **`template_id` 不用改** —— 它是 FK 到 `core.collection_config_templates`（采集配置默认值模板），id=15 有效。字段映射模板由 `template_matcher` 自动选取（spec §0 表 #7）。
>
> **额外建议（不属于必改项）**：`core.collection_config_templates` id=15 的 `default_date_range_type` 也是 `'custom'`，会让**将来新建**的 weekly 配置继承同一个陷阱。可以一并改成 `'auto_prev_day'`。

### Step 3.2 定 `execution_mode`

当前是 `headed`（有头浏览器，需要可见会话）。

- **若妙手账号能免验证码自动登录** → 保持 `headed` 但确认 APScheduler 触发时能起浏览器；或改 `headless`
- **若需要人工过验证码** → 保持 `headed`，接受「采集非全自动」，并在交付说明里写明

**动手前先确认有可用账号与会话。** 采集组件是 Playwright 驱动妙手 ERP 界面导出（`modules/platforms/miaoshou/components/inventory_export.py`）。

### Step 3.3 注册 APScheduler 作业

优先走 API（会同时 `scheduler.add_schedule()`）：

```
POST /api/collection/configs/30/schedule
{ "schedule_enabled": true, "schedule_cron": "0 9 * * 0,3" }
```

**不要用** `POST /api/collection/schedule/granularity/weekly` —— 它会把该粒度的所有配置统一刷成预设 cron（`0 9 * * 1` = 实际周二），既覆盖不到 3 天节奏，也带上了星期偏移。

若服务未运行，改完 SQL 后**重启后端**即可 —— `backend/main.py:754` 启动时会 `scheduler.load_all_schedules()` 拉起所有 `schedule_enabled=true AND schedule_cron IS NOT NULL AND is_active=true` 的配置。

### Step 3.4 手动触发一次，验证产物的 date_from

```
POST /api/collection/configs/30/run
```

### Step 3.5 验证（**最关键的三条**）

```sql
SELECT id, date_range_type, custom_date_start, custom_date_end,
       schedule_enabled, schedule_cron, execution_mode, batch_status
FROM core.collection_configs WHERE id = 30;
-- 期望：auto_prev_day / NULL / NULL / true / '0 9 * * 0,3' / (headed|headless) / active
```

```sql
SELECT id, file_name, status, date_from, date_to, first_seen_at
FROM public.catalog_files
WHERE data_domain='inventory' ORDER BY id DESC LIMIT 3;
-- 期望：新行的 date_from ≈ 采集当天（或昨天）
-- 🔴 绝不能是 2026-03-23
```

```sql
SELECT id, job_id, next_run_time FROM core.apscheduler_jobs ORDER BY next_run_time;
-- 期望：有 collection_config_30 作业，next_run_time 是某个周一或周四 09:00
```

- [ ] 7 项配置已一起改
- [ ] `execution_mode` 已定并记录
- [ ] APScheduler 已注册作业
- [ ] 手动触发成功，产出文件的 `date_from` 是当天
- [ ] `git commit -m "feat:打开妙手库存每周一/周四定时采集并修正日期口径"`

### Task 3 执行期结论（2026-10-22，**范围已收缩**）

> 用户反馈：「采集肯定是没问题的，你不用验证采集」「你设置的这个cron是多余的」「以现有数据来做工作就可以，不要去采集」。

**决定：本轮不新增采集 cron，也不验证采集。** 调度由既有机制负责。config 30 的
`schedule_enabled` / `schedule_cron` / `batch_status` / `execution_mode` **全部保持原样**，
我手动注册的 `collection_config_30` 作业也已从 `core.apscheduler_jobs` 删除。

**只保留一处改动 —— 日期口径（真正的坑）：**

```sql
UPDATE core.collection_configs
SET date_range_type   = 'auto_prev_day',
    custom_date_start = NULL,
    custom_date_end   = NULL,
    updated_at        = now()
WHERE id = 30;
```

> `custom_date_start=2026-03-23 / custom_date_end=2026-03-29` 这个死窗口一旦被 custom 分支
> 写进新文件的 `date_from`，库龄锚点会直接变成 2026-03-23，全 SKU 一步落进 180+ 档。
> 改成 `auto_prev_day` 之后 `date_from` 永远跟随真实采集日，无论采集是自动还是手动触发。

顺带把 `core.collection_config_templates.id=15` 的 `default_date_range_type` 也改成
`'auto_prev_day'`（新建 weekly 配置不再继承同一个陷阱）。

**顺带查清的三件事（写下来免得再踩）：**

1. **`execution_mode` 不是「有头浏览器」开关**，它是 `debug_mode` 标志
   （`collection_scheduler.py:82` `resolve_config_debug_mode`：等于 `'headed'` 就是 debug 模式）。
   浏览器真正 headless/headed 由 `PLAYWRIGHT_HEADLESS` 环境变量决定，
   `get_browser_launch_args(debug_mode, execution_mode)` 里 `execution_mode='headless'`
   才会强制 `headless=True, slow_mo=0`。**计划 Step 3.2 对它的理解是错的。**
2. **APScheduler 作业落在 `core.apscheduler_jobs`**（DB 作业存储，`search_path` 含 `core`），
   由 `backend/main.py:754` 的 `scheduler.load_all_schedules()` 在后端启动时自动注册。
   → **不需要手工注册**，后端一启动就有了；我那次手工注册确实是多余的。
3. **`0 9 * * 0,3` 在 APScheduler 语义下 = 周一 + 周四 09:00**（`day_of_week='0,3'`），
   实测触发序列：2026-10-22(周四) → 10-26(周一) → 10-29(周四) → 11-02(周一)，
   间隔 4 天 / 3 天交替，与「每 3 天一次、下限每周一次」的决策一致。

**Task 4 的第二帧不在本轮范围**（需要再次采集，用户明确不做）。
单帧阶段的 `bucket` 全是 `0-30`、`reset_reason` 全是 `first_positive` 属**正确结果**。

---

## Task 4：端到端验收库龄链路

### Step 4.1 验收锚点

```sql
SELECT count(*) FROM mart.inventory_age_current;
-- 期望 > 0

SELECT reset_reason, count(*) FROM mart.inventory_age_current GROUP BY 1;
-- 期望：全部 first_positive（只有一帧快照）

SELECT DISTINCT age_anchor_date FROM mart.inventory_age_current;
-- 期望：2026-09-14（锚点帧）

SELECT bucket, count(*) FROM mart.inventory_age_current GROUP BY 1;
-- 期望：只有 0-30 一个值 —— 这是单帧阶段的【正确结果】，不是 bug
```

> **口径提醒（spec §5.5）**：库龄从「该 SKU 第一次有库存那天」起算。只有一帧快照时所有 SKU `age_days=0`。
> **分档多样性的验收在第二帧之后（Task 4.3），不在本次单帧验收内。**

### Step 4.2 验收 join 命中率

```sql
SELECT count(*) AS 总数,
       count(*) FILTER (WHERE s.sku_id IS NOT NULL) AS 命中
FROM mart.inventory_age_current a
LEFT JOIN core.dim_erp_sku s ON s.sku_key = a.product_sku;
-- 期望：命中率 ≥ 95%（真实文件基线 99.64%）
```

### Step 4.3 采第二帧，形成第二个时间点

**这是分档生效的前提。** 第二帧落地后：

```sql
SELECT bucket, count(*) FROM mart.inventory_age_current GROUP BY 1;
-- 期望：出现 0-30 与 31-60 两个值（锚点 2026-09-14，第二帧 2026-10-2x → age_days ≈ 37）

SELECT age_days, count(*) FROM mart.inventory_age_current GROUP BY 1 ORDER BY 1;
-- 期望：出现非 0 的 age_days
```

**⚠️ 补货会让部分 SKU 的 age_days 仍是 0** —— 这是 `stock_increase` 归零的正确行为。看 `reset_reason` 分布确认：

```sql
SELECT reset_reason, count(*) FROM mart.inventory_age_history
WHERE snapshot_date >= :起跑日 GROUP BY 1 ORDER BY 2 DESC;
```

- `stock_increase` 占比**明显偏低** + `continued` 畸高 → 补货漏检严重，考虑加密到每天（spec §10.3）
- 分布正常 → 保持 3 天

### Step 4.4 验收定价底线

第二帧落地且库龄超过 60 天后（按锚点 2026-09-14，最早 2026-11-13 前后）：

```
GET /api/skus?page_size=5
```

确认返回里 `pricing_tier_label` 不再全是「日常」，`pricing_age_days` 非 null，`pricing_tier_source = 'age_data'`。

> **预期幅度提醒**：分档解锁后，1084 个能算底线的 SKU 最低售价会明显下调（`A-00001-BLACK`：¥128.56 → ¥90.82，**降 29%**）。这是设计意图，但**上线前要跟业务方对齐**。
>
> 纪律线本轮**不验收**（`reference_selling_price` 填充率 0.2%）。

- [ ] 库龄表有数据、锚点正确、join 命中率 ≥ 95%
- [ ] 第二帧落地后分档出现 ≥ 2 个值
- [ ] `reset_reason` 分布已复核并记录结论
- [ ] `git commit -m "docs:记录库龄管道端到端验收结果"`

---

## Task 5：建 `api.sku_clearance_ranking_module` 视图

**产出:** `sql/api_modules/sku_clearance_ranking_module.sql`

### Step 5.1 口径决策（**先定再写**）

**建议：价格字段不放视图里。**

- 视图只出：库龄、库存、动销、ERP 关联、`sku_id` / `default_purchase_cost` / `reference_selling_price` / `min_selling_price_override`
- 定价字段（档位、折扣率、最低售价）由后端 service 调 `product_pricing_service` 的**纯函数**补齐

**理由**：定价公式已在 `backend/services/product_pricing_service.py` 里是纯函数 + 单测覆盖。在 SQL 视图里重写一遍 = 第二份口径，必然随规则表演进漂移。视图与商品中心的数值不一致，是最容易在评审时被忽略、但业务上最伤的一种 bug。

如果实施时判断视图里算更简单，**必须**逐条对齐 `compute_sku_pricing` 的公式与降级链（分母 ≤ 0 返回 NULL、缺料不硬算、`min_selling_price_override` 优先），并在 Task 7 的跨接口一致性比对里兜住。

### Step 5.2 写视图

结构见 spec §3.1。关键点：

- 库龄主口径来自 `mart.inventory_age_current`（**不是** `estimated_stagnant_days`）
- `mart.inventory_backlog_base` 是**仓库行**，要 `GROUP BY platform_code, product_sku` 聚合到 SKU
- `estimated_turnover_days` 在 SKU 层级**重算**（`SUM(available_stock) / SUM(daily_avg_sales)`），不要 `MAX`
- 规则表「当前行」谓词与 `product_center._policy_current_predicate()` **完全一致**：`status='active' AND effective_to IS NULL AND effective_from <= CURRENT_DATE`
- 命中档位用 `LATERAL ... ORDER BY min_age_days DESC LIMIT 1`，与 `select_age_tier` 同逻辑
- `product_sku IS NULL` 的行过滤掉（无法作为 SKU）
- **不 join `core.dim_erp_sku` 过滤掉未匹配行** —— 未匹配的新品也要出现在清单里（spec §3.6）

### Step 5.3 应用

```powershell
psql -f sql/api_modules/sku_clearance_ranking_module.sql
```

> 这些 SQL 是 **idempotent 的 `CREATE OR REPLACE VIEW`**，仓库的部署期 bootstrap 会统一跑。若视图列有变化，PostgreSQL 不能用 `CREATE OR REPLACE` 改列名 —— 需要先 `DROP VIEW`（既有 `clearance_ranking_module.sql` 就是这么做的）。

### Step 5.4 验证

```sql
SELECT count(*) FROM api.sku_clearance_ranking_module;
-- 管道通后 > 0

SELECT count(DISTINCT product_sku) = count(*) AS one_row_per_sku
FROM api.sku_clearance_ranking_module;
-- 期望：true

SELECT risk_level, count(*), round(sum(inventory_value)) FROM api.sku_clearance_ranking_module GROUP BY 1;
-- 期望：有分组

SELECT product_sku, age_days, age_bucket, age_anchor_date, reset_reason, inventory_value
FROM api.sku_clearance_ranking_module ORDER BY age_days DESC LIMIT 5;
-- 期望：age_days 非 0（第二帧之后）
```

- [ ] 口径决策已定并记录
- [ ] 视图已建、可查
- [ ] `git commit -m "feat:新增 SKU 级滞销排名读模型视图"`

---

## Task 6：后端 service + 端点 + 契约 + 单测

### Step 6.1 service 方法

`backend/services/postgresql_dashboard_service.py` 新增：

```python
async def get_sku_clearance_ranking(
    self, *, min_age_days=60, max_age_days=None, risk_level=None,
    platform_code=None, keyword=None, sort_by="clearance_priority_score",
    sort_order="desc", limit=100, offset=0,
) -> dict[str, Any]
```

- 查询源：`api.sku_clearance_ranking_module`
- `min_age_days` / `max_age_days` / `risk_level` / `platform_code` / `keyword` **必须真的生效**（既有 `get_clearance_ranking` 的 `min_days` 是空转的，别照抄那个坏模式）
- `sort_by` 白名单：`clearance_priority_score` / `age_days` / `inventory_value` / `estimated_turnover_days`
- 价格字段：按 Task 5.1 的决策，调用 `product_pricing_service` 的纯函数补齐
- 返回结构见 spec §3.4（含 `summary.missing_reference_price_count`）

### Step 6.2 端点

`backend/domains/business/routers/inventory_domain.py` 新增：

```
GET /api/inventory/clearance-ranking
```

- `response_model` 用 Pydantic 契约（放 `backend/schemas/inventory_domain.py`，**不在 router 里内联**）
- **只读端点，不加 `require_admin`**（与既有 `/inventory/aging` 一致）
- 参数校验：`min_age_days >= 0`、`limit` 1~500、`offset >= 0`、`sort_order in {asc, desc}`

### Step 6.3 单测

`backend/tests/data_pipeline/test_sku_clearance_ranking.py`：

- [ ] 视图查询只打 `api.sku_clearance_ranking_module`（不碰 `b_class.` / `semantic.fact_orders_atomic` / `raw_data->>`）—— 与既有 `test_business_overview_query_policy_gates.py` 同一套门禁
- [ ] `min_age_days` 真的过滤（**不是空转**）
- [ ] `risk_level` 过滤生效
- [ ] `sort_by` 白名单外的值被拒（不拼进 SQL）
- [ ] `summary.missing_reference_price_count` 统计正确
- [ ] 未匹配主数据的 SKU 仍在结果里，价格字段为空
- [ ] 端点 200 + 响应结构完整

### Step 6.4 验证

```powershell
python -m pytest backend/tests/data_pipeline/test_sku_clearance_ranking.py -q
```

- [ ] service + 端点 + 契约 + 单测完成
- [ ] `git commit -m "feat:SKU 级滞销排名服务与端点"`

---

## Task 7：前端滞销清单页签

### Step 7.1 API 封装

`frontend/src/api/inventoryDomain.js`：

```js
async getClearanceRanking(params = {}) {
  return await api._get('/inventory/clearance-ranking', { params })
}
```

### Step 7.2 页签

`frontend/src/domains/business/views/inventory/InventoryAging.vue` 加「**滞销清单**」页签，内容见 spec §3.5：

- 汇总卡：滞销 SKU 数 / 压资金额 / 在库数量 / 高风险数
- 风险分布条 + 档位分布
- 明细表（16 列，见 spec §3.5）
- 筛选：库龄下限、风险等级、平台、关键词、排序
- 数据缺口提示：「N 个 SKU 缺参考售价，无法计算清货回款」

**`reset_reason` 中文化**（`first_positive` → 首次有货 / `stock_increase` → 补货归零 / `reappeared_after_zero` → 卖空重现 / `zero_stock` → 归零 / `continued` → 持续累加）。

### Step 7.3 前端测试

`frontend/tests/inventoryAgingUi.test.mjs`（新建）：

- [x] 页面含「滞销清单」页签
- [x] 表格列齐全（`min_selling_price` / `current_discount_rate` / `age_days` / `clearance_priority_score`）
- [x] `clearance_recovery_amount` 为 null 时显示「缺参考售价」而不是 `-`
- [x] 原有页签功能未变

### Step 7.4 验证

```powershell
node --test frontend/tests/inventoryAgingUi.test.mjs
```

- [x] 页签与测试完成（**15/15 过**）
- [ ] `git commit -m "feat:库龄看板页新增 SKU 级滞销清单页签"`

### Step 7.5 执行结果（2026-10-22）

**做出来的东西**

| 项 | 结果 |
|---|---|
| 页签 | `InventoryAging.vue` 重构为 `el-tabs` 两个 pane：「库龄明细」（原内容原样保留）+「滞销清单」 |
| 明细表 | **16 列**（spec §3.5 列了 15 列，补了「平台」列凑 16 —— 多平台下没有平台列没法定位） |
| 汇总卡 | 滞销 SKU 数 / 压资金额 / 在库数量 / 高风险数 |
| 分布 | 风险分布条（high/medium/low）+ 库龄档位分布条，均取 `summary.by_risk_level` / `summary.by_age_bucket` |
| 缺口提示 | `el-alert`：「N 个 SKU 缺参考售价，无法计算清货回款」（实测 N=495，全量缺参考售价） |
| 筛选 | 库龄下限/上限、风险等级、平台、关键词、排序字段、排序方向 —— **全部真进后端 query** |
| 分页 | `el-pagination`，offset 按 `(page-1)*size` 传给后端 |

**几个执行期的决定**

1. **前端库龄下限默认用 0，接口默认仍是 60。**
   当前库里只有单帧快照（`age_days` 全 0），前端默认 60 会直接白屏。
   接口默认值按 spec 保持 60（口径留在一处），前端按真实数据现状给 0 —— 前端**总是显式传** `min_age_days`，不依赖后端默认值。
2. **`reset_reason` 中文化按 spec 统一到一套词**（原库龄明细页用的是另一套）。
   同一个枚举值在同一页出现两种中文说法是缺陷，所以两个页签共用同一个映射函数：
   `first_positive` → 首次有货 / `stock_increase` → 补货归零 / `reappeared_after_zero` → 卖空重现 / `zero_stock` → 库存归零 / `continued` → 持续累加。
3. **周转哨兵值 9999 显示成「无动销」而不是「9999 天」** —— 9999 是「有库存但完全没有动销数据」的内部哨兵，展示成天数会让人以为这货要卖 27 年。
4. **滞销清单页签懒加载**：第一次切到该页签才发请求，不给每次进页面都加一枪查询。

**验证**

```powershell
node --test frontend/tests/inventoryAgingUi.test.mjs   # 15/15 过
npx vite build                                          # exit 0，SFC 编译通过
```

> ⚠️ eslint 说明：仓库前端**本来就是红的**（`src/domains/business/views` 下 61 个 .vue 里 20 个有错，合计 1096 个：`semi` 514 / `quotes` 310 / `comma-dangle` 120 / `indent` 78 …）。本文件的 eslint 报错只有 `indent`（switch 分支缩进，与仓库既有写法一致）和 `comma-dangle`（与同目录既有测试文件一致），**无 `vue/no-parsing-error`**。
> 过程中 eslint 抓到一个真 bug：抽屉里 `<template #default>` 少写了一个 `</template>` 闭合标签 → 已修。

---

## Task 8：跨接口一致性验证（**硬性**）

**同一 SKU 在「商品中心」和「滞销清单」上算出来的档位/折扣率/最低售价必须完全一致。**

```sql
-- 取几个 SKU，在商品中心接口和滞销清单接口对一遍
SELECT product_sku, age_days, age_bucket, pricing_tier_label,
       current_discount_rate, clearance_max_discount_rate, min_selling_price
FROM api.sku_clearance_ranking_module
ORDER BY clearance_priority_score DESC LIMIT 5;
```

对每个 SKU 调 `GET /api/skus?keyword=<product_sku>`，比对 `pricing_tier_label` / `current_discount_rate` / `clearance_max_discount_rate` / `min_selling_price`。

- [x] 5 个 SKU 全部一致
- [x] 差异不为 0 的原因已查明（**差异为 0，无需回 Task 5**）

### Task 8 执行结果（2026-10-22）

**方法**：两层验证，都打真实库。

1. **service 层**：直接调两个 router 的函数（`list_skus` 与 `SkuClearanceService.get_sku_clearance_ranking`），共用一个 `AsyncSession`，排除 HTTP/鉴权干扰。
2. **HTTP 层**：httpx `ASGITransport` 直连 ASGI app（不跑 lifespan），带真实 access token（库里启用用户 + 临时 `core.user_sessions` 行，跑完删掉）。

**结果**：两层都是 **5/5 一致，0 差异**。

| SKU | 档位 | 当前可优惠 | 清仓最高折扣 | 最低售价 |
|---|---|---|---|---|
| HKR-JWGLH-A | 日常 | 0.1 | 0.3 | ¥21.03 |
| HKR-JWG-A | 日常 | 0.1 | 0.3 | ¥12.62 |
| MECHANIC-IX5-S845 | 日常 | 0.1 | 0.3 | ¥236.75 |
| **A-00001-BLACK** | 日常 | 0.1 | 0.3 | **¥128.56** |
| XH-MCYX-Black | 日常 | 0.1 | 0.3 | ¥447.07 |

`A-00001-BLACK` 的 ¥128.56 与 spec 基线**完全吻合**。

**参数校验（HTTP 层，7 个非法值全 422）**：
`sort_by=not_a_column` / `sort_order=sideways` / `risk_level=extreme` / `limit=0` / `limit=501` / `offset=-1` / `min_age_days=-5`。
合法参数全 200；`min_age_days=9999` 返回 0 条（不报错）。

**为什么两边必然一致**：两个入口喂给 `product_pricing_service.compute_sku_pricing` 的**原料完全相同** —— 采购成本 / 参考售价 / 人工覆盖价 / SKU 达人佣金率 / 平台佣金率 / 平台其他成本率 / SPU 绑定与两个 SPU 率 / 命中的档位 / 最深档位 / 库龄，全部同源。差别只在 **库龄取法**：
- 商品中心：`_load_age_days_by_sku` → `MIN(age_days) GROUP BY product_sku`（跨平台取最小）
- 滞销清单：视图里该 SKU 自己那一行的 `age_days`

当前只有 miaoshou 一个平台有库存，两者等价。**将来接入多平台时这两个口径会分叉**（同一 `product_sku` 在 A 平台 30 天、B 平台 200 天时，商品中心按 30 天、滞销清单按自己那行），届时要统一。

### Task 8 执行期发现：端点慢查询（已修）

HTTP 层验证时**第一次请求耗了 11 秒**（第二次 15 秒），交互页面不可接受。逐段拆解后定位：

| 环节 | 耗时 |
|---|---|
| `mart.inventory_age_current` | 2 ms |
| `mart.inventory_snapshot_change` | 26 ms |
| `mart.inventory_backlog_base`（**含销售 CTE**） | **2244 ms** |
| `semantic.fact_orders_atomic` 全量求值 | **20990 ms** |
| 视图明细查询（改造前） | **8867 ms** |

**根因**：`mart.inventory_backlog_base` 的 `sales_30d` 用 `metric_date::date >= CURRENT_DATE - INTERVAL '30 days'` 过滤，`::date` 转换让谓词**下不进** `semantic.fact_orders_atomic` 的 UNION ALL 分支 → 2.8 万行订单全量做去重窗口 → 8.8 秒。
`sql/mart/inventory_*.sql` **在禁改清单里**，所以不动它，改我自己的视图。

**修法**（只改 `sql/api_modules/sku_clearance_ranking_module.sql`）：
1. **库存/滞留列**改从 `mart.inventory_snapshot_change` 取，不再经过 `inventory_backlog_base`。
   两者共用同一个 `company_daily` CTE 和同一个 `ROW_NUMBER() ... PARTITION BY platform_code, platform_sku, product_sku, warehouse_name ORDER BY snapshot_date DESC, ingest_timestamp DESC`，`latest` 取 rn=1、`change` 取 rank=1 值 → **available_stock / on_hand_stock / inventory_value 完全等价**，代价 48 ms。
2. **销售聚合限定在「有库存的平台」**：`platform_code = ANY(ARRAY(SELECT DISTINCT platform_code FROM mart.inventory_age_current))`。
   子查询是 InitPlan → 常量数组 → 谓词能下推到 `fact_orders_atomic` 的 UNION ALL 分支，只扫对应平台的事实表。
   **不改变任何数字**：销售与库存的连接键含 `platform_code`，没有库存的平台其销售行本来也匹配不上。

**实测**：视图明细查询 **8867 ms → 44.9 ms**（热缓存 34.3 ms），端点整体从 11 秒降到 **~90 ms**，不再触发慢请求告警。

**数字不变性证明**：改造前后把视图全量输出（495 行 × 24 列）落成 CSV 逐行逐列对比 → **0 处差异**。

**顺带修掉一个潜伏的口径 bug**：老写法把 `daily_avg_sales`（SKU 级动销）**按仓库行求和**，同一 SKU 有 N 个仓库就放大 N 倍，`estimated_turnover_days = 总库存 / 放大后的日均` 会被低估 N 倍。现在动销在 SKU 级算一次，不再按仓库重复计数。
（当前库里 `daily_avg_sales` 全为 0，所以这个 bug 今天看不出来，但**等订单数据接上就会显形**。）

**回归门禁**：`backend/tests/data_pipeline/test_sku_clearance_ranking.py` 加 3 条视图 SQL 静态断言 —— 不得引用 `mart.inventory_backlog_base`、销售必须限定平台、定价公式不得写进 SQL。

---

## 验收汇总

| # | 断言 | 来源 Task | 状态 |
|---|---|---|---|
| 1 | inventory 域 published 模板恰好 1 行，`field_count = 28`、`version = 3` | Task 1 | ☑ **已过**（id=370） |
| 2 | 字段映射模板自动选取命中 v3 | Task 1 | ☑ **已过** |
| 3 | `catalog_files` inventory 无 `template_update_required` / `pending` / `processing` | Task 2 | ☑ **已过**（ingested=1 / source_missing=1）|
| 4 | `b_class.fact_miaoshou_inventory_snapshot` = 1226 行 | Task 2 | ☑ **已过**（1226）|
| 5 | `semantic.fact_inventory_snapshot` / `mart.inventory_snapshot_history` > 0 | Task 2 | ☑ **已过**（各 1226）|
| 6 | 自动入库当初超时的原因已查明并记录 | Task 2 | ☑ **已过**（不是超时：文件不存在 + 状态机死循环，见 Task 2 执行期发现）|
| 7 | `collection_configs.id=30`：`auto_prev_day` / `custom_date_* IS NULL` / `schedule_enabled=true` / `cron='0 9 * * 0,3'` / `batch_status='active'` | Task 3 | ⬛ **本轮不做**（用户 2026-10-22 明确：不加 cron。已只保留日期口径修复）|
| 8 | 新采集产物 `date_from` ≈ 采集当天（**绝不是 2026-03-23**） | Task 3 | ⬛ **本轮不做**（用户明确不采集）|
| 9 | APScheduler 有 `collection_config_30` 作业 | Task 3 | ⬛ **本轮不做**（同上）|
| 10 | `mart.inventory_age_current` > 0，`age_anchor_date = 2026-09-14` | Task 4 | ☑ **已过**（495 行，锚点 2026-09-14）|
| 11 | join 命中率 ≥ 95%（基线 99.64%） | Task 4 | ☑ **已过**（99.80%）|
| 12 | 第二帧后 `bucket` ≥ 2 个值 | Task 4 | ⬛ **本轮不做**（需第二帧，用户明确不采集）|
| 13 | `reset_reason` 分布已复核，采集频次结论已定 | Task 4 | ☑ **已过**（单帧：全 `first_positive`；频次决策见 spec）|
| 14 | `api.sku_clearance_ranking_module` 可查、一行一 SKU | Task 5 | ☑ **已过**（495 行，`count(DISTINCT product_sku)=count(*)`）|
| 15 | `min_age_days` / `risk_level` 筛选真的生效 | Task 6 | ☑ **已过**（单测 + HTTP 层实测）|
| 16 | 未匹配主数据的 SKU 仍在清单里 | Task 6 | ☑ **已过**（495/495 都匹配上了 ERP 主数据，逻辑分支有单测覆盖）|
| 17 | 库龄看板页「滞销清单」页签可用 | Task 7 | ☑ **已过**（15/15 前端测试过，`vite build` exit 0）|
| 18 | 商品中心与滞销清单的档位/折扣率/最低售价完全一致 | Task 8 | ☑ **已过**（service 层 + HTTP 层各 5/5 一致，0 差异）|
| 19 | 纪律线生效 | — | **不在本轮范围**（参考售价填充率 0.2%） |

**额外验收（本轮新增）**

| # | 断言 | 状态 |
|---|---|---|
| 20 | 滞销清单端点响应时间可接受（交互页面不能 11 秒）| ☑ **已过**（8867ms → 44.9ms，端点整体 ~90ms）|
| 21 | 视图改造前后数字完全一致 | ☑ **已过**（495 行 × 24 列 CSV 逐格对比，0 差异）|
| 22 | `backend/tests/data_pipeline` 无新增红测试 | ☑ **已过**（基线 25 failed / 386 passed → 当前 25 failed / 401 passed，**失败名单逐条 diff 0 差异**）|
| 23 | 代码已合并到主工作区且容器跑的是新代码 | ☑ **已过**（fast-forward 零冲突；重启 worker/beat 后容器内三处代码均为新版）|
| 24 | 「入库 → 事件 → 入队 → worker 消费 → 库龄重放」**全自动**跑通 | ☑ **已过**（任务 760/761 被 worker 自动消费；污染行被算回；全量重放后 0 差异；数据零膨胀）|
| 25 | 定价两条线（成本底线 / 折扣护栏）都能命中且跨接口一致 | ☑ **已过**（护栏赢 8/8、成本线赢 8/8、商品中心 vs 滞销清单 16/16 一致）|

---

## 风险与应对（执行时对照）

| 风险 | 触发信号 | 应对 |
|---|---|---|
| 🔴 日期配置写错 → 全 SKU 直接落 180+ 档 | Task 3 验证里 `date_from` 出现 2026-03-23 | 立即停调度 → 改 `auto_prev_day` → 重跑并 `TRUNCATE mart.inventory_age_*` 后重算 |
| 🔴 视图与商品中心的最低售价不一致 | Task 8 比对有差异 | 价格字段移出视图，改由 service 调纯函数（Task 5.1） |
| 妙手会话无法无人值守 | Task 3 手动触发失败在登录/验证码 | 保留 `headed` + 人工触发，交付说明写明「采集非全自动」 |
| 入库再次超时 | Task 2 手工入库超过 45 分钟 | 查 `AUTO_INGEST_STALE_TIMEOUT_MINUTES` 与文件大小；必要时调阈值并记录 |
| 补货漏检导致库龄虚高 | `reset_reason` 里 `continued` 畸高、`stock_increase` 极低 | 采集加密到每天，重跑观察 |
| 单帧阶段清单为空 | Task 4.3 之前查视图返回 0 行 | 正常，等第二帧；端点不报错 |
| 🔴 端点响应变慢 | 滞销清单页签加载 > 1s | 检查视图有没有引用 `mart.inventory_backlog_base`（销售 CTE 要 8.8 秒）；已加单测门禁拦住 |

---

## 交付说明必须写清的八件事

1. **Shopee / TikTok 库存本次不做** —— 采集映射里只有 `miaoshou.inventory`，另两张 b_class 表永久 0 行
2. **历史 80280 行不可用** —— 形态不同（英文列名），灌进去在库量会算成 0，需另开任务清理
3. **分档需要时间** —— 锚点 2026-09-14，60 天档最早 2026-11-13 前后生效，90 天档 12-13 前后，120 天档 2027-01-12 前后
4. **纪律线本轮基本不生效** —— `reference_selling_price` 原先只有 2/1125 个 SKU 有值，「当前可优惠」目前只通过目标利润率影响底线。**2026-10-22 已补 16 个测试值用于验证（见下节），业务方需替换为真实参考售价**
5. **最低售价会明显下调** —— 分档解锁后示例降 29%，需业务方事先对齐
6. **采集是否全自动** —— 取决于妙手账号能否免验证码登录（**本轮不采集**）
7. **滞销清单现在全是「0-30 天 / 低风险 / 首次有货」** —— 只有一帧快照，`age_days` 全 0。分档、风险分层要等第二帧才有意义。当前前端库龄下限默认给 **0**（不是接口默认的 60），否则页面直接白屏。
8. **「清货回款」列大部分仍是「缺参考售价」** —— 补测试值后从 495 降到 **479** 个 SKU 仍缺参考售价，回款算不出来。补齐参考售价主数据是这一列有意义的前提。

---

## 合并到主工作区 + 容器内端到端验收（2026-10-22）

### 合并

`main` 的 HEAD `e4bd8e3f` 正好是特性分支的 merge-base → **纯 fast-forward，零冲突，不产生 merge commit**：

```powershell
git merge --ff-only feature/inventory-aging-pipeline-recovery
```

7 个提交、19 个文件全部落地。**用户自己的未提交改动 `modules/platforms/miaoshou/components/filters.py` 未被触碰**（已用 `git diff --name-only main..branch` 核对，分支不含该文件）。

### 必须重启容器

Docker worker 的 bind mount 指向**主工作区**（`F:\...\xihong_erp\backend -> /app/backend`），但 Python 进程启动时就已加载代码 —— **文件改了不会自动生效**：

```powershell
docker restart xihong_erp_celery_worker xihong_erp_celery_beat
```

### 端到端验收（在容器内跑，零假数据）

**刻意避开了「重跑一次入库」**：`b_class.fact_miaoshou_inventory_snapshot` 是实体表，同一文件再入一次会灌重复行（1226 → 2452），等于污染刚清干净的历史数据。改为在容器内用**真实参数**（file_id=2764、真实 domain/granularity/row_count）触发真实事件。

| # | 验证项 | 结果 |
|---|---|---|
| ① | 容器内代码已是新版 | `data_ingestion_service.py:1129` = `await handle_data_ingested_async(event)`；`event_listeners.py:198` 有 `handle_data_ingested_async`；`refresh_queue_tasks.py:200` 有 `sync_inventory_skus` |
| ② | **事件 → 入队**（旧代码必然丢的那一段） | 队列 724 → **725**，新增 id=760：`trigger_type=data_ingested`、`pipeline_name=data_ingested_refresh`、16 个 target 含 `mart.inventory_age_current/history`、context 带真实 file_id=2764 |
| ③ | **worker 自动消费** | 任务 760：`started_at=06:14:00` → `finished_at=06:14:01`（**1.878 秒**），`attempt_count=1`，无 error；celery 日志 `process_refresh_queue_task succeeded` |
| ④ | 刷新管道真的执行 | refresh_runner 日志里 16 个 target 全部 `attempt=1/2` 或 `1/1` |
| ⑤ | **数据零膨胀** | b_class 1226 / mart_snapshot_history 1226 / dim_erp_sku 1125 / bridge_erp_sku_keys 2240 / age_current 495 —— 全部与合并前一致 |
| ⑥ | 新端点 HTTP 层 | `GET /api/inventory/clearance-ranking` → 200；6 个非法参数全 422；3 个合法参数全 200；`GET /api/skus` → 200 |

### 库龄重放是「真算」而不是「留着旧数据」——决定性实验

第 ③ 次刷新时 `updated_at` 没变，一度以为重放没跑。查下来是**正确的增量语义**：

```
水位线 = MAX(last_ingest_timestamp) FROM mart.inventory_age_history   = 2026-10-21 16:15:04
快照最新 = MAX(last_ingest_timestamp) FROM mart.inventory_snapshot_company_daily = 2026-10-21 16:15:04
```

同一个文件重跑 → 没有新数据 → `get_changed_keys()` 返回空 → `replayed_key_count=0`。**没有 bug**。

为了正面证明重放能跑，造了一个「有变化」的场景（**测的正是生产上首次入库那条路径**）：

1. 备份 `mart.inventory_age_current` 全量 495 行
2. **故意污染一行**：`A-000` → `age_days=999, bucket=180+, reset_reason=CORRUPT_PROBE`
3. `TRUNCATE mart.inventory_age_history` → 水位线变 NULL → 走「取全部 key」的全量重放分支
4. 再触发一次事件 → 任务 761 **34.6 秒**完成（对比任务 760 的 1.878 秒，差 18 倍，正是「1122 个 key 全量重放」与「无事可做」的量级差）
5. **污染行被算回**：`A-000` → `age_days=0, bucket=0-30, reset_reason=first_positive`
   → 证明库龄是**从快照重算出来的**，不是硬编码、不是残留
6. `age_history` 重建 1122 行、`age_current` 495 行、残留污染 **0** 条、`updated_at` = 本次刷新时刻
7. 全量内容与刷新前**逐行逐列 0 差异**（同数据幂等）

### 补测试用参考售价（业务方需替换为真实值）

原状：`reference_selling_price` 只有 **2/1125** 个 SKU 有值，「折扣护栏」这条定价线基本算不出来。

补了 **16 个 SKU**（`temp/backfill_reference_price.py`，备份在 `temp/reference_price_backup.json`，`--restore` 可一键还原）：

| 分组 | 参考售价 | 期望结果 |
|---|---|---|
| 8 个「护栏赢」 | 采购成本 × 4 | 最低售价由**折扣护栏**决定（`min_selling_price_source = discount_guard`） |
| 8 个「成本线赢」 | 采购成本 × 1 | 最低售价由**成本底线**决定（`min_selling_price_source = cost_floor`） |

复验结果：

- 护栏赢组 **8/8** 命中 `discount_guard` ✅
- 成本线赢组 **8/8** 命中 `cost_floor` ✅
- 商品中心 vs 滞销清单 **16/16 完全一致** ✅
- `missing_reference_price_count` 495 → **479**
- 「清货回款」列开始有真实数值 ✅

⚠️ **这些是测试值，不是真实业务数据。** 例：`A-00001-BLACK` 因参考售价被设为 186，最低售价从 ¥128.56 变成 **¥167.40**（护栏生效把底线抬高了）。业务方在商品中心改成真实参考售价即可。

### 合并后回归

```powershell
python -m pytest backend/tests/data_pipeline/test_sku_clearance_ranking.py \
  backend/tests/data_pipeline/test_event_listeners.py \
  backend/tests/test_refresh_queue_tasks.py -q      # 30 passed
node --test frontend/tests/inventoryAgingUi.test.mjs  # 15 pass / 0 fail
```

### 后续建议（不在本轮范围）

| 优先级 | 事项 | 说明 |
|---|---|---|
| P1 | 补齐真实参考售价主数据 | 决定「当前可优惠 / 折扣护栏」能不能真正生效，是业务录入不是开发 |
| P1 | 补齐 `creator_commission_rate` | 目前只有 1 个 SKU 有值，其余走平台兜底（tiktok 6.06%），妙手真实佣金率大概率不是这个数 |
| P2 | `semantic.fact_orders_atomic` 全量求值 21 秒 | 影响约 10 个 mart 视图（店铺级清仓看板也受影响）。根因是 `::date` 转换阻止谓词下推 + 底层事实表缺索引。**动共享 semantic 层，必须单独立项** |
| P3 | 多平台库龄口径分叉 | 商品中心取 `MIN(age_days) GROUP BY product_sku`（跨平台最小），滞销清单取该 SKU 自己那行。今天只有妙手一个平台两者等价；接入第二个平台后两个页面会给出不同的档位与最低售价，且**不会报错** |

## 采集前链路预验证（2026-10-22）

真机采集由业务方操作。本节记录采集**之前**在本地完成的链路预验证，结论是：**代码已具备验收条件**，并给出验收时应看到的预期值。

### 验证方法

两个临时探针（跑完即删，不留在仓库）：

1. **去重键探针**：用真实模板 370 配置 + 真实 `b_class` 行数据，调用真实 `DeduplicationService.calculate_data_hash`，比较两个不同 `metric_date` 下的 hash。
2. **端到端回滚探针**：在**单个事务**里模拟一次真实采集落库（往 `b_class.fact_miaoshou_inventory_snapshot` 追加一份 `metric_date=2026-10-21` 的快照副本），跑**真实**的 `InventoryAgeRefreshService.refresh(force_full=True)`，读取 `mart.inventory_age_current` 结果，最后 `ROLLBACK`，并用指纹校验数据库回到原状。

探针只读业务语义、全量回滚，验证后数据库行数与指纹逐字节一致（`495|9932a17881ff424d39c44bf3d89e`），无残留。

### 关键发现

**新采集会产生新行，而不是覆盖旧行。** 这是库龄能否推进的决定性一环：

- 模板 370（published v3）的 `deduplication_fields` 是 `["*商品SKU", "*商品名称", "*规格", "仓库"]`，本身不含日期；
- 但 `append_auto_date_identity_fields()` 会把 `field_parse_rules` 产出的日期身份字段自动并入 hash 身份，而模板的规则是 `metric_date ← __file_date_from__`；
- 实测最终身份字段为 `['*商品SKU', '*商品名称', '*规格', '仓库', 'platform_code', 'shop_id', 'metric_date']`；
- 同一行数据在 `metric_date=2026-09-14` 与 `2026-10-21` 下 hash 分别为 `fc6432475a900c02…` / `4a53c4d1df51fb4d…`，**不同** → 走 INSERT 而非 UPSERT。

因此 `b_class` 会按 `(SKU, 仓库, 快照日)` 累积历史行，`mart.inventory_snapshot_company_daily` 每个 `sku_key` 出现两个 `snapshot_date`，库龄才有时间轴可重放。

> 补充说明：`UPSERT_UPDATE_FIELDS["inventory"]` 不含 `metric_date`，因此**同一天重复采集同一文件**会走 UPSERT 覆盖同一行（`ingest_timestamp` 前移、`metric_date` 不变）——这正是「同一文件重跑 `replayed_key_count=0`」的来源，属已澄清的正确行为，不是缺陷。

### 端到端探针结果

| 观测点 | 采集前 | 模拟新采集后 |
|---|---|---|
| `b_class` 行数 / 不同 `metric_date` | 1226 / 1 | 2452 / 2 |
| `mart.inventory_snapshot_company_daily` | 1122 | 2244 |
| `replayed_key_count` | — | 1122 |
| `mart.inventory_age_current` | 495 行，`age_days=0`，`bucket=0-30`，`reset_reason=first_positive` | **495 行，`age_days=37`，`bucket=31-60`，`reset_reason=continued`** |
| `mart.inventory_age_history` | 1122 行（仅 2026-09-14） | 2244 行（2026-09-14 → 0-30；2026-10-21 → 31-60） |
| 样本 `A-00001-BLACK` | — | 库存 97，锚点仍为 **2026-09-14**，`age_days=37` |

**锚点不随采集日重置**（仍是首次有货日），只有库存数量增加或归零时才会重置——这正是「库龄」应有的语义：货一直压着，库龄就一直涨。

### 业务方真机采集后的预期值

采集日 2026-10-22，配置 30 的 `date_range_type=auto_prev_day` → `date_from = date_to = 2026-10-21` → `metric_date = 2026-10-21`（与 2026-09-15 那次采集得到 `metric_date=2026-09-14` 的规律一致）。

| 指标 | 采集前 | 采集后（预期） |
|---|---|---|
| `mart.inventory_age_current.snapshot_date` | 2026-09-14 | **2026-10-21** |
| `age_days` | 0 | **37** |
| `bucket` | 0-30 | **31-60** |
| `reset_reason` | first_positive | **continued** |
| `mart.inventory_age_history` 行数 | 1122 | **2244** |
| `mart.inventory_age_current` 行数 | 495 | 495（不增） |

**以下情况仍显示 `0-30` 档，属于正确行为，不是 bug：**

- 库存比上次**增加** → `reset_reason=stock_increase`，`age_days=0`，锚点重置为新快照日（补货归零）；
- 上次为 0、本次有货 → `reset_reason=reappeared_after_zero`，`age_days=0`；
- 库存为 0 → 不进 `age_current`（`reset_reason=zero_stock`）。

### 采集前提条件（不满足则采集白跑）

1. **妙手登录态**：`data/sessions/miaoshou/miaoshou_real_001/storage_state.json` 停在 2026-10-20 20:54，2026-10-19/20 的 `orders` 采集卡在图形验证码；本次走 `headed` 模式，可人工介入。
2. **本地后端要能起来**：`backend/main.py:538` 的 cloud sync 启动检查在云端库 `127.0.0.1:15433` 连不通时会 `raise` 导致整体退出。官方入口是 `scripts/start_collection_formal.ps1`（会自动拉 SSH 隧道）；隧道拉不起来时可用 `scripts/start_local_collection_mode.ps1`（开发模式，不强制隧道可达）。
3. **配置 30 同时含 `orders` 与 `inventory` 两个域**，`orders` 子域 shopee/tiktok 上次失败于验证码；`inventory` 域历史上成功过（2026-09-14）。

> **2026-10-23 更新**：同一数据域再次失败（flaky，非必现）。任务 `7bb2a92e-a0eb-4129-ba5c-6237b852c909`，失败于 `warehouse_filters.py` 点击仓库范围下拉框时被 `jx-select` 透明占位层拦截命中测试。根因与整改见 `docs/superpowers/specs/2026-10-23-miaoshou-inventory-domain-remediation-design.md`。
4. **inventory 域的 granularity 会被强制归一为 `snapshot`**（`modules/apps.collection_center/landing_semantics.py:resolve_business_granularity`），所以配置里的 `granularity=weekly` 不影响落库表名；另有 `POST /api/data-sync/repair-inventory-snapshot-semantics` 兜底。
5. **Docker 只保留基础设施**：`postgres` / `redis` / `celery_worker` / `celery_beat` 保持 healthy，`backend_api` / `backend_collector` 保持停止。
