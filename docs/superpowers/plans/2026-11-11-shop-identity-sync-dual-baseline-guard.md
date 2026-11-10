# 批次 3.7 —— 同步侧双基准守卫

> 对应方案: `docs/superpowers/plans/2026-11-10-shop-identity-future-proofing-and-observability.md` §批次 3 第 3.7 项
> 业务语言版: `docs/superpowers/plans/2026-11-11-shop-identity-business-plan.md` §第三步「同步侧双基准守卫」
> 状态: **已实现**（本分支）; 批次 4.3（矛盾行台账）另做。

---

## 1. 要解决什么

同步侧推送前的身份判定只看**本地**那份登记信息
（`core.shop_accounts` + `core.shop_account_aliases`），
把待推送的行分成三类：**自洽 / 未归属 / 真矛盾**（>1 个账号 ⇒ 不写云端）。

但**云端也有一份登记信息**。两边不同步时（采集机本地台账与云端台账不一致）：

```
采集机本地台账                     云端台账
─────────────                    ──────────
行 → 账号 A  ✔ 自洽              行 → 账号 B   ⇒ 归属塌陷(unknown)
```

本地判「自洽」的行推到云端后，云端会用**云端**的登记去解释它 ⇒ 可能指向别的店
⇒ 云端出现**归属塌陷**（语义层落 `unknown`）。
**2026-11-07 事故就是这么发生的**：两边各自自洽，只有跨端比对才暴露。

⇒ 本批次：**推送前再比一次**。两边不一致 ⇒ 该行**降级为可观测事件**，
**不再当自洽行直接放行**。

---

## 2. 「两边不一致」的判定口径

设 `L` = 本地台账把这一行解析出的账号集合，`C` = 云端台账解析出的账号集合。
两边用**同一份**解析实现
（`backend/services/shop_identity_reconciliation_service.row_identity_accounts`），
口径不会分叉；反查索引由仓库唯一台账声明
（`modules/core/shop_identity_ssot.py`）派生 ⇒ **与「账号章优先」方向一致**。

| 本地 `L` | 云端 `C` | 结论 | 原因码 |
|---|---|---|---|
| 恰好 1 个 | 与 `L` 相同 | **一致** ⇒ 行为与改造前**完全相同** | — |
| 恰好 1 个 | 空 | **不一致**（云端认不出） | `cloud_registry_unresolved` |
| 恰好 1 个 | 恰好 1 个但不同 | **不一致**（云端指向另一个账号） | `cloud_registry_different_account` |
| 恰好 1 个 | >1 个 | **不一致**（云端自己都认不唯一） | `cloud_registry_ambiguous` |
| 0 个（未归属） | — | **不比较** ⇒ 行为不变（照常落库 + 计数 + 告警） | — |

**为什么这样定**

1. **只比「这一行推到云端后会被算到谁头上」**，不逐字段比台账 ——
   逐字段比只能发现「编号登记错了」，发现不了「别名指错了」「本地停用店云端还在」。
   直接问云端那一份登记信息，问的正是真正要防的那件事。
2. **云端认不出 / 云端歧义都算不一致** —— 两种情况下推上去的结果都不是
   「一个确定的店」：前者会落 `unknown`，后者同样会落 `unknown`。
3. **未归属行不比较** —— 本地没唯一认出来时没有「本地认出的账号」可比对，
   强行比较会把「待人工补主数据」的**好数据**当成坏数据丢掉
   （2026-11-07 事故的形态）。行为保持不变。

---

## 3. 降级与降级路径

| 情形 | 行为 |
|---|---|
| 两边一致 | **与改造前完全相同**：自洽行照常放行 |
| 两边不一致 | 该行**不写云端**，降级成**可观测事件**（记下来 / 可查 / 可计数） |
| **云端不可达** | **退回本地单基准判定**（行为与改造前完全相同）+ 记一条「**双基准不可用**」事件 |

> **绝不能因为云端连不上就把同步搞挂。**

### 检查点算法**不变**

批次 4.3 的硬约束：**保持现有推进算法**（推进到 `last_written_index`，即最后一个落库行），
**不要**改成「停在第一个矛盾行」—— 那会让 `fact_shopee_products_daily` 永久卡在那 8 行之前
（历史不修 ⇒ 那些行的归属永远不会被修）。

降级行与真矛盾行**同样**不参与 `written_indexes` ⇒ 检查点照样按现有算法推进。
「本批一行都没落库 ⇒ 检查点停在当前水位」这条既有语义也保持不变
（此时状态为 `partial_success`，并明确报错 ⇒ 人工对齐台账后再同步）。

---

## 4. 可观测事件落在哪

**不新建表、不加迁移链**（那要迁移链，成本高）。落点是既有的
`ops.pipeline_run_log`（已有 `context` jsonb 这一列，云端巡检与新鲜度巡检都在用它）。

| 事件 | `pipeline_name` | `status` | `context` 关键字段 |
|---|---|---|---|
| 双基准**不一致** | `cloud_sync_identity_guard` | `partial_failed` | `dual_baseline_status=mismatch`、`degraded_rows`、`events[]` |
| 双基准**不可用** | `cloud_sync_identity_guard` | `partial_failed` | `dual_baseline_status=unavailable`、`reason`、`fallback=local_single_baseline` |

**为什么落**本地**库**：云端连不上时，那条「双基准不可用」事件**根本写不到云端**
⇒ 落点必须在采集机本地库（同步 worker 本来就在那儿）。两边的事件落在同一个地方，
计数口径才统一。

### 怎么计数 / 怎么查

```sql
-- 发生过多少次不一致
SELECT count(*) AS degraded_batches
FROM ops.pipeline_run_log
WHERE pipeline_name = 'cloud_sync_identity_guard'
  AND status = 'partial_failed';

-- 一共降级了多少行（计数是全量的，events 只是截断的样本）
SELECT sum((context->>'degraded_rows')::int) AS degraded_rows
FROM ops.pipeline_run_log
WHERE pipeline_name = 'cloud_sync_identity_guard';

-- 看某一次降级了哪些行（事件样本，最多 50 条）
SELECT created_at, context->>'source_table_name', context->'events'
FROM ops.pipeline_run_log
WHERE pipeline_name = 'cloud_sync_identity_guard'
ORDER BY created_at DESC;
```

事件**绝不阻塞同步**：台账写入失败只记日志，同步照常进行。

---

## 5. 云端登记信息怎么读

* 连接串**只从环境变量读**（`CLOUD_DATABASE_URL`）—— 源码里**没有任何连接串字面量**；
* 解析用 `sqlalchemy.engine.make_url()`（**自动解码**百分号编码的口令）——
  **不要**用 `urlparse` 读口令：它不解码，脱敏会漏；
* 连接**只读**、**短命**：建引擎 → 查两张表 → `finally` 里 `dispose()`；
* ⚠️ **不做主机名重写**：采集机的云端同步 worker 跑在**宿主进程**
  （`scripts\start_collection_formal.ps1`），那里 `127.0.0.1` 就是宿主自己
  ⇒ 换成 `host.docker.internal` 反而连不上。现有同步链路也是原样使用
  `CLOUD_DATABASE_URL`，这里与它保持一致；
* 读的是 `core.shop_accounts`（`id` / `shop_account_id` / `platform` /
  `platform_shop_id` / `store_name` / `shop_region` / `enabled` / `business_role`）
  与 `core.shop_account_aliases`；
* ⚠️ **别名表的 FK 是整数主键**：`core.shop_account_aliases.shop_account_id`
  → `core.shop_accounts.id` ⇒ JOIN 必须写 `ON a.shop_account_id = s.id`。

---

## 6. 已知风险 / 遗留

1. **台账会重复写**：一批被降级后检查点不推进（若整批都没落库），下一轮会读到同一批
   ⇒ 同样的事件再记一条。批次 4.3 的「矛盾行台账 + `--dry-run` + 归档口径」要一并解决。
2. **本地台账整体错位时，同步会停在该表**：所有自洽行都被降级 ⇒ 一行都不落库
   ⇒ 检查点停在当前水位（状态 `partial_success` + 明确报错 + 事件台账）。
   这是**有意的**：宁可停下让人对齐台账，也不要把行按错的归属推进去。
   ⚠️ 修法：对齐本地台账（批次 2）后自动恢复。
3. **未归属行不做跨端比较** —— 本地认不出就没有可比对的基准（见 §2）。
4. **告警通道未接**：目前只有「台账 + 结构化日志」，还没接
   `create_notifications_for_admins` / `alert_service.send_resource_alert`
   （批次 3.4 的三通道）。留给批次 4.3 一并做，避免在同步链路里引入外部调用风险。

---

## 7. 验收与守护测试

守护测试：`backend/tests/test_cloud_sync_dual_baseline_guard.py`

| # | 验收口径 | 对应用例 |
|---|---|---|
| 1 | 两边不一致 ⇒ 该行降级，不再当自洽行放行 | `test_registry_mismatch_degrades_the_row` / `test_registry_mismatch_does_not_write_the_row_to_cloud` |
| 2 | 云端认不出 / 云端歧义 ⇒ 同样是不一致 | `test_cloud_cannot_resolve_the_account_is_also_a_mismatch` / `test_cloud_ambiguous_account_is_a_mismatch` |
| 3 | 云端连不上 ⇒ 退回本地单基准 + 记「双基准不可用」，同步不挂 | `test_unreachable_cloud_falls_back_to_local_single_baseline` / `test_unreachable_cloud_records_unavailable_event_and_keeps_syncing` |
| 4 | 两边一致 ⇒ 行为与改造前相同 | `test_identical_registries_keep_the_previous_behavior` / `test_identical_registries_write_every_row` |
| 5 | 降级事件可查询/计数，且不阻塞同步 | `test_guard_event_is_written_to_pipeline_run_log` / `test_guard_event_context_carries_countable_numbers` / `test_event_recording_failure_does_not_block_the_sync` |
| 6 | 连接建立与关闭不泄漏 | `test_cloud_registry_connection_is_disposed_on_success` / `test_cloud_registry_connection_is_disposed_on_failure` |
| 7 | 源码里没有连接串字面量；用 `make_url` 不用 `urlparse` | `test_guard_module_has_no_connection_string_literal` / `test_guard_module_uses_make_url_not_urlparse` |

---

## 8. 硬约束自查

| 约束 | 自查 |
|---|---|
| 不许改语义层计数口径 | ✅ 未触碰 `count(DISTINCT c.resolved_shop_id)` 与 `sql/semantic/*` |
| 不许动历史事实行 | ✅ 未写任何针对 `b_class.fact_*` 的数据迁移/回填/订正 |
| 不许改别的 PR 的文件 | ✅ 只改 `cloud_b_class_sync_service.py` / `cloud_b_class_auto_sync_factory.py`，新增 `cloud_sync_identity_guard_service.py` |
| 不许新增第三方依赖 | ✅ 只用仓库已有的 SQLAlchemy / psycopg |
| 不许硬编码连接串 | ✅ 连接串只从 `CLOUD_DATABASE_URL` 读；守护测试守死 |
| 不许直推 main | ✅ 独立分支 + PR |
| 文本统一 LF | ✅ `.gitattributes` 已强制 `*.py text eol=lf` |
| 不许在仓库根新增临时报告 | ✅ 方案产物落在 `docs/superpowers/plans/` |
