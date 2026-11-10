# 批次 4.3 —— 同步侧矛盾行台账 + 手工重发入口

> 对应方案: `docs/superpowers/plans/2026-11-10-shop-identity-future-proofing-and-observability.md` §批次 4 第 4.3 项
> 业务语言版: `docs/superpowers/plans/2026-11-11-shop-identity-business-plan.md` §收尾「同步矛盾行台账」
> 前置: `docs/superpowers/plans/2026-11-11-shop-identity-sync-dual-baseline-guard.md`（批次 3.7）
> 状态: **已实现**（本分支）

---

## 1. 要解决什么

批次 3.7 把「本地/云端登记信息不一致」的行**降级为可观测事件**，事件落在
`ops.pipeline_run_log` 的 `context->'events'` 里。那是**整批**的 jsonb **样本**
（最多 50 条）⇒ 看不出「这一行到底被跳过几次、第一次被跳过是什么时候」，
也无法**逐行**重发。

而方案 §批次 4.3 写得很明确（**硬约束**）：

> ⚠️ **在「历史不修」下不要改成「停在第一个矛盾行」** —— 那会让
> `fact_shopee_products_daily` 永久卡在那 8 行之前（它们归属永远不会被修）
> ⇒ 把「漏传」换成「堵死」。正确做法：**保持现有推进算法**（不制造永久卡死），
> 额外把被跳过的矛盾行记进台账并标注「已知历史遗留」，另提供**手工重发入口**
> （将来若决定修历史，改成停在第一个矛盾行即可）

⇒ 本批次做三件事：

| # | 做什么 | 落在哪 |
|---|---|---|
| A | 新建**行级矛盾行台账**（`ops.shop_identity_conflict_rows`） | 新表 + 新迁移 |
| B | 同步侧把**被跳过 / 被降级**的行**逐行**登记进去（**只记不阻塞**） | `backend/services/shop_identity_conflict_ledger_service.py` |
| C | 手工重发入口（**默认 `--dry-run`**） | `scripts/replay_shop_identity_conflict_rows.py` |

顺带修掉批次 3.7 留下的两条已知问题（见 §7）。

---

## 2. 台账的字段口径

一行 = **一个矛盾行**（不是一个批次）。表在 `ops` 域 —— 与
`ops.cloud_sync_receive_log`、`ops.pipeline_run_log` 同域：**运行与同步的台账**，
不是业务事实。

| 字段 | 口径 | 回答的问题 |
|---|---|---|
| `id` | bigserial 主键 | — |
| `dedup_key` | 「源表 \| 业务日期 \| 行内定位 \| 原因码」 | **去重键**（唯一约束建在它上面） |
| `source_table_name` | 同步源表名（`fact_*`） | 哪张表 |
| `platform_code` | 行内 `platform_code` | 哪个平台 |
| `data_domain` | 同步的数据域（由表名推断） | 哪个域 |
| `business_date` | 行内业务日期（`business_date` / `metric_date` / `period_end_date` / `analytics_date` **按此优先级**取第一个非空） | 哪个业务日期 |
| `row_locator` | 「源行主键 \| 冲突键摘要」 | 行内定位（人工找这一行用） |
| `source_row_id` | 源行主键（`b_class.fact_*.id`） | 源行是哪一行 |
| `identity_value` | 行内那列的值（**归一化**后，取**账号章优先**的那一路） | 行内那列的值是什么 |
| `identity_tokens` | jsonb：行内各身份键的归一化 token 全貌 | 当时行内带了哪几路身份 |
| `resolved_account_id` | 本地**唯一**认出的账号（多账号矛盾时为空） | 本地认出的账号是谁 |
| `resolved_accounts` | jsonb：本地解析出的**账号集合** | 本地认出了哪几个账号 |
| `cloud_accounts` | jsonb：云端解析出的账号集合（双基准降级时才有） | 云端认为它是谁 |
| `reason_code` | 原因码（见 §3） | 为什么判为矛盾 |
| `status` | `known_legacy` / `pending_manual` | 是「已知历史遗留」还是「待人工处理」 |
| `occurrence_count` | 累计出现次数 | 这一行被跳过几次了 |
| `first_seen_at` | 第一次见到的时间 | 什么时候开始出的问题 |
| `last_seen_at` | 最近一次见到的时间 | 最近还在出吗 |
| `resolution_status` | `open` / `in_progress` / `resolved` / `ignored` | 人工处理状态 |
| `resolved_by` / `resolved_at` / `resolution_note` | 处理人 / 处理时间 / 备注 | 谁处理的、什么时候 |
| `created_at` / `updated_at` | 审计时间 | — |

⚠️ **只登记，不修**：本表**不回填、不改写**任何历史事实行（`b_class.fact_*`）
—— 「只保未来、历史不修」是既定决策。表里也**不存行体**，只存定位信息。

### 归一化口径从哪来

`identity_value` / `identity_tokens` 用的是
`backend/services/shop_identity_reconciliation_service.py::row_identity_tokens`
的产物（与语义层候选池同口径），**取哪一个身份键**用
`modules/core/shop_identity_ssot.py::IDENTITY_SIGNAL_PRIORITY`
（**账号章优先**）—— 与入库侧、语义层、批次 3.7 的守卫**完全同源**。

⇒ **认人优先级仍然只有一处定义**（仓库唯一台账声明），本批次没有另写一份
「什么算认得出」。

---

## 3. 原因码清单

**唯一定义处**：`backend/services/shop_identity_conflict_ledger_service.py`
（批次 3.7 的 `cloud_sync_identity_guard_service` 只做**转出**，不另写一份）。

| 原因码 | 含义 | 什么情况下出现 | 行会写云端吗 |
|---|---|---|---|
| `local_registry_ambiguous` | 本地台账把行内身份解析出 **>1 个**账号（真矛盾） | 行内两个身份键指向不同的店 | ❌ 不写 |
| `local_identity_token_mismatch` | 拿不到本地台账时的降级判据：行内**同形态**的身份键互相不一致 | 本地没有 `core.shop_accounts`（降级判据） | ❌ 不写 |
| `cloud_registry_unresolved` | 本地认出的账号，**云端认不出** | 两边登记信息不一致 | ❌ 不写 |
| `cloud_registry_ambiguous` | **云端自己**都认不唯一 | 两边登记信息不一致 | ❌ 不写 |
| `cloud_registry_different_account` | 云端把它**指向了另一个账号** | 两边登记信息不一致 | ❌ 不写 |

⚠️ **未归属行（本地认不出任何账号）不进台账** —— 它们**照常落库**（不是坏数据），
只是计数并告警 ⇒ 不属于「被跳过 / 被降级」。

---

## 4. 去重口径

**同一「(源表, 业务日期, 行内定位, 原因码)」再遇到时，更新累计次数与最近见到
时间，不插新行。**

实现方式：

* 四项拼成一个稳定串 → `dedup_key`；
* `dedup_key` 上建**唯一索引** `ix_shop_identity_conflict_rows_dedup_key`；
* 写入用 `INSERT ... ON CONFLICT (dedup_key) DO UPDATE`，
  `occurrence_count = occurrence_count + 1`、`last_seen_at = now()`。

⇒ **幂等由数据库兜底**，应用层不先查后写（先查后写在并发下会插重复行）。

⚠️ **这一套去重口径同时也是批次 3.7「事件重复写」的修复口径**（见 §7.1）——
**不要**再写第二套。

---

## 5. 「已知历史遗留」的判定依据

与**批次 3.2**（报表可解析性分档巡检）**同口径**：以「店铺身份登记信息
**对齐生效日**」（环境变量 `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE`）为界。

| 条件 | 结论 | 含义 |
|---|---|---|
| **未配置**对齐生效日 | `known_legacy` | 没有基准就分不出「历史」与「新增」⇒ 一律按历史遗留（与批次 3.2 同口径：**宁可不报也不误报**） |
| 业务日期 **早于**对齐生效日 | `known_legacy` | 那些行的归属**永远不会被修**（历史不修）⇒ 不重发、不报警 |
| 业务日期 **不早于**对齐生效日 | `pending_manual` | 台账修好后**可以**手工重发 |
| 业务日期**为空**（已配置生效日） | `pending_manual` | 无法证明它早于生效日 ⇒ 交给人工判断 |

判定实现在 `classify_conflict_status()`，对齐生效日的读取**复用批次 3.2 的
那一份**（`backend/services/data_pipeline/cloud_sync_integrity_service.py::
resolve_alignment_effective_date`）⇒ 两处分档不会分叉。

⚠️ **对齐生效日必须配**。没配时所有矛盾行都归「历史遗留」，手工重发入口会
挑不出候选行（脚本会提示）。批次 2（台账对齐）执行完就该配。

---

## 6. 手工重发入口

`scripts/replay_shop_identity_conflict_rows.py`

### 用法

```powershell
# ① 只看要重发什么（**默认行为**，不改动任何东西）
python scripts/replay_shop_identity_conflict_rows.py --dry-run

# ② 按源表 / 日期范围筛
python scripts/replay_shop_identity_conflict_rows.py --dry-run `
    --source-table fact_shopee_products_daily `
    --date-from 2026-11-01 --date-to 2026-11-30 --limit 50

# ③ 确认无误后真执行
python scripts/replay_shop_identity_conflict_rows.py --execute
```

### 安全边界（**逐条都是硬约束**）

1. **默认 `--dry-run`** —— 只预览「将要重发什么」，**不改动任何东西**；
   真执行必须显式 `--execute`；
2. **只处理「待人工处理」的行** —— `--status` 默认就是 `pending_manual`；
3. **默认不动「已知历史遗留」** —— 要动必须**同时**给
   `--status known_legacy` **和** `--include-known-legacy`；
4. **不回退同步检查点、不重推整表** —— 只**逐行**补发台账里点名的那些行，
   检查点一个字都不动（既定决策：❌ 不回退同步检查点、不重推 11 月）；
5. **不修历史** —— 只重发**行**，不碰任何事实行的身份戳；
6. **连接串只从环境变量读**（`DATABASE_URL` / `CLOUD_DATABASE_URL`），
   源码里**零字面量**；解析用 `sqlalchemy.engine.make_url()`；
7. **重发仍走既有的身份闸门** —— 补发的行会**再过一次**本地/云端双基准判定；
   台账还没修好的行**照样被拒**（宁可不补发，也不写错归属）。

### 执行成功后

台账行的 `resolution_status` 置 `resolved`，并记 `resolved_by` / `resolved_at` /
`resolution_note`（脚本名 + 数据域）。

---

## 7. 批次 3.7 遗留的两条问题

### 7.1 事件台账重复写（**已修**）

**现象**：批次 3.7 把降级事件写在 `ops.pipeline_run_log`
（`pipeline_name='cloud_sync_identity_guard'`）。当整批被降级时检查点停在当前
水位 ⇒ 下一轮会读到**同一批** ⇒ **同样的事件被重复记一条**。

**修法**：事件**只在本批出现了台账里没有的新行时才记**
（`ledger_summary['new_rows'] > 0`）。去重口径 = §4 的台账口径 ⇒ **同一套**。

> ⚠️ 台账**没配**或**写失败**时事件**照记** —— 宁可多记一条，也不丢可观测性。

### 7.2 告警通道未接（**已接，默认关**）

批次 3.7 只有「台账 + 结构化日志」，没接通知出口。

**修法**：把通知出口做成**显式可选项** ——
环境变量 `SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED`，**默认关**
（只有显式为 `1` / `true` / `on` / `yes` 才开）。

**复用批次 3.4 已有的两条通道，不另造一套**：

| 通道 | 复用谁 |
|---|---|
| 站内信（管理员） | `backend/domains/platform/routers/notifications.py::create_notifications_for_admins` |
| webhook / 钉钉 | `backend/services/alert_service.py::send_resource_alert` |

⇒ 默认关 ⇒ **上线后行为与现在完全一致**；且**不在同步链路里引入新的外部网络
调用**（批次 3.7 作者标注的风险）。

---

## 8. 只记不阻塞

* 台账写入走**独立**的 `begin()` 块 ⇒ **不参与**同步的写入事务；
* 任何异常（表不存在 / 连不上 / 约束冲突 / 字段不对）都被**吞掉**，只记 warning；
* ⇒ **同步照跑，写入结果不变**（守护测试：
  `test_ledger_write_failure_does_not_block_the_sync`、
  `test_ledger_table_missing_does_not_block_the_sync`）。

---

## 9. 验收与守护测试

守护测试：`backend/tests/test_shop_identity_conflict_ledger.py`

| # | 验收口径 | 对应用例 |
|---|---|---|
| 1 | 矛盾行进台账，带正确的标注与原因码 | `test_conflict_row_is_recorded_with_reason_code_and_status` / `test_new_rows_after_the_alignment_date_are_pending_manual` / `test_degraded_row_is_recorded_with_the_cloud_reason_code` |
| 2 | 台账写失败**同步照跑** | `test_ledger_write_failure_does_not_block_the_sync` / `test_ledger_recorder_exception_is_swallowed` / `test_ledger_table_missing_does_not_block_the_sync` |
| 3 | 台账**去重**（同一行、次数 +1） | `test_the_same_conflict_row_is_deduped_in_the_ledger` / `test_the_upsert_uses_the_database_unique_constraint` |
| 4 | 批次 3.7 的事件**不再重复写** | `test_guard_event_is_not_written_twice_for_the_same_batch` / `test_guard_event_is_still_written_when_the_ledger_is_not_configured` / `test_guard_event_is_still_written_when_the_ledger_write_fails` |
| 5 | **推进算法没变**（不许卡死） | `test_rows_after_a_conflicting_row_are_still_written` / `test_the_checkpoint_advance_algorithm_is_unchanged` / `test_a_batch_where_everything_conflicts_keeps_the_old_behaviour` |
| 6 | 重发脚本：dry-run 不改动 / 只处理待人工 / 默认不动历史遗留 | `test_replay_dry_run_changes_nothing` / `test_replay_defaults_to_pending_manual_only` / `test_replay_refuses_known_legacy_without_the_explicit_flag` / `test_replay_execute_only_processes_pending_manual` |
| 7 | 原因码**只有一处定义** / 认人优先级复用 SSOT | `test_reason_codes_have_a_single_definition` / `test_identity_value_follows_the_ssot_priority` |
| 8 | 通知出口**默认关** | `test_conflict_notify_is_disabled_by_default` |
| 9 | 迁移链指向正确 + ORM 与迁移列名一致 | `test_the_ledger_migration_points_at_the_current_chain_head` / `test_the_orm_model_and_the_migration_agree_on_the_columns` |

---

## 10. 迁移

* 文件：`current_migrations/versions/20261224_shop_identity_conflict_rows.py`
* `revision = "current_schema_20261224_shop_identity_conflict_rows"`
* `down_revision = "current_schema_20261223_collection_source_identifiers"`（链头）
* 只**新建一张表 + 四个索引**，不改任何既有表 / 列 / 数据；
* `downgrade()` 删表 + 删索引。

---

## 11. 硬约束自查

| 约束 | 自查 |
|---|---|
| 只保未来、历史数据不修 | ✅ 不回填身份戳、不改历史行归属、不重推 11 月；重发脚本**不回退检查点**、只逐行补发 |
| 不改语义层计数口径 | ✅ 未触碰 `count(DISTINCT c.resolved_shop_id)` 与 `sql/semantic/*` |
| 不改语义层 SQL 资产 / `dashboard_bootstrap.py` / `shop_identity_reconciliation_service.py` / `fact_identity_columns.py` / `shop_identity_ssot.py` / `source_freshness_*` / `cloud_sync_integrity_*` | ✅ 这些文件**一个都没改**（只**读** `cloud_sync_integrity_service` 的 `resolve_alignment_effective_date`） |
| 认人优先级只有一处定义 | ✅ 复用 `modules/core/shop_identity_ssot.py::IDENTITY_SIGNAL_PRIORITY` 与 `row_identity_tokens` |
| 推进算法不变 | ✅ `last_written_index` 逻辑**一个字没动**；新增的只是台账登记 |
| 连接串只从环境变量读 | ✅ `DATABASE_URL` / `CLOUD_DATABASE_URL`；源码零字面量；用 `make_url` 解析 |
| 文本统一 LF | ✅ `.gitattributes` 保证 `*.py text eol=lf`；提交前核对 0 个 CR 字节 |
| 不新增第三方依赖 | ✅ 只用仓库已有的 SQLAlchemy |
| 不直推 main | ✅ 独立分支 + PR |

---

## 12. 已知风险 / 遗留

1. **「双基准不可用」事件仍会跨轮重复**（批次 3.7 的 per-run 去重只管**同一轮**）。
   本批次**没有**把它纳入台账去重口径 —— 它的去重单位是「条件」而不是「行」，
   硬塞进行级台账会让台账语义变浑。⇒ **残留**：云端长期不可达时，每轮仍会记一条
   「不可用」事件。影响有限（每轮一条，不是每行一条）。
2. **台账行不记行体** —— 想知道「当时那行长什么样」要回源表按 `source_row_id` 查。
   这是刻意的：行体可能很大，且台账会被运维看到。
3. **单批最多记 1000 条**（`MAX_LEDGER_RECORDS_PER_BATCH`）—— 超出部分被丢弃并记
   warning。极端情况下（一批几千行全冲突）台账会**少记**，但 `occurrence_count`
   口径仍成立。
4. **「对齐生效日」未配置 ⇒ 全部归「已知历史遗留」** ⇒ 手工重发入口挑不出候选行。
   ⇒ **必须配** `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE`（批次 2 之后）。
5. **通知出口默认关** ⇒ 上线后**没有人**会收到矛盾行告警，除非显式打开
   `SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED`。这是「上线后行为与现在完全一致」的
   代价 —— 要告警就显式打开。
6. **重发脚本不做幂等保证的并发保护** —— 两个人同时跑 `--execute` 可能重复补发
   同一行。补发用的是 upsert（同一冲突键）⇒ **结果幂等**（不会产生重复行），
   只是台账的 `resolution_status` 会被写两次。
