# 店铺身份「保未来」与可观测性加固方案

- **日期**：2026-11-10
- **来源**：采集机交开发环境的问题单（10 项，P1×3 / P2×5 / P3×2）+ 本地主干逐项复核
- **代码基线**：`main` @ `abb599e7`（= `origin/main`）
- **复核方式**：全仓只读取证（未连数据库 / 未连容器）+ 提交历史比对 + 语义层资产走查
- **业务决策（2026-11-10，Walter）**：**沿用 11-06 决定 —— 只保未来，历史数据不修**
- **状态**：方案已定，待执行

---

## 0. 硬约束与范围

### 0.1 业务约束

| 约束 | 含义 |
|---|---|
| **只保未来** | 保证**后续采集的数据**不再错位、不再静默归错店 |
| **历史数据不修** | **不回填**历史事实行的身份戳、**不改**历史行的归属、**不重推** 11 月 |

沿用 `docs/superpowers/plans/2026-11-06-shop-identity-alignment-remediation.md` §0.2 的处置（当时把 P0-2 / P0-2b / P0-3 的历史数据部分移出范围）。

### 0.2 「历史数据不修」的边界判定（本方案唯一的口径读法）

必须区分两类东西，二者不是一回事：

| 对象 | 是什么 | 是否属「历史数据」 | 本方案处置 |
|---|---|---|---|
| `b_class.fact_*` 里已落库的历史行 | 过去采过的业务数据 | ✅ **是** | ❌ **不动**（不回填、不改归属、不重推） |
| `core.shop_accounts.platform_shop_id` | **当前**登记状态：这个账号**现在**在平台上的编号 | ❌ **不是** | ✅ **要修**（见下） |
| `core.shop_account_aliases` 里的错别名 | 错登记的**派生残留** | ❌ 不是 | ✅ **要删**（清理，低风险） |

**为什么主数据对齐必须做（这是「保未来」的必要条件，不是历史订正）**：

语义层输出的规范键是 `COALESCE(canonical.platform_shop_id, resolved.resolved_shop_id)`
（`sql/semantic/shop_identity_resolution_candidates.sql:90-94` 注释段 `:75-78` 明确锁死这个顺序）。
⇒ **语义层吐出来的 `shop_id` 本身就派生自主数据登记**。

于是：

- 主数据错位 ⇒ 采集侧导出的编号就是错的（`modules/components/export/base.py:73-85` 只认主数据）
  ⇒ 新行里带着错编号 ⇒ 推到云端后，云端用**对的**登记去解释 ⇒ 编号候选指向别的账号
  ⇒ **候选数 = 2 ⇒ 落 `unknown`** ⇒ **每一批新数据在云端都塌**；
- 主数据对齐 ⇒ 新行的编号、账号章、店名三者一致 ⇒ 云端候选数 = 1 ⇒ **归属正确**。

⇒ **不对齐主数据，「保未来」就是落空的。** 即使把入库收敛顺序改成账号章优先，新行在云端仍会因「错编号指向邻居账号」而落 `unknown`。

> ⚠️ 若业务方的「历史不修」本意是**连主数据也不动**，则本方案降级为「只做批次 1 + 批次 3」，且需接受一条明确后果：
> **云端后续每一批新数据仍会塌成 `unknown`，看板归属问题不会随时间自愈。**
> 本方案按「主数据 = 当前状态，不是历史数据」纳入对齐动作。

### 0.3 本方案**明确不做**的事

- ❌ 不回填 2195 行缺戳的历史分析数据
- ❌ 不回滚 `20261117` 已改写的 957 行
- ❌ 不逐行订正 11 月（含 products / services 批次）的行内身份
- ❌ 不回退同步检查点、不重推 11 月
- ❌ 不给 `ops.pipeline_run_log` 加 `heartbeat_at` 列（留到 V2）
- ❌ 不改语义层**计数口径**（`count(DISTINCT c.resolved_shop_id)` 保持不动 —— 仓库既有原则：歧义宁可落 `unknown` 报警，也不猜一个）

---

## 1. 问题定性（复核后）

### 1.1 任务单 10 项的逐项结论

| # | 任务单主张 | 结论 | 关键证据 / 修正 |
|---|---|---|---|
| P1-1 | 检查点越过批次前部的矛盾行 | **确认存在** | `backend/services/cloud_b_class_sync_service.py:1090-1131` 推进到 `last_written_index`（最后一个落库行），非「最后一个连续自洽行」 |
| P1-2 | 云端巡检在采集机永远跳过 | **确认存在**（两处表述要改） | `backend/tasks/cloud_sync_integrity_tasks.py:37-42` + `docker-compose.dev.yml:215-225`（celery-worker 无 `CLOUD_DATABASE_URL`、无 `env_file`）。**修正①**：该巡检不读 `ops.cloud_sync_receive_log`，读 `b_class.fact_*` / `core.shop_accounts` / `semantic.shop_identity_resolution_candidates`。**修正②**：`docker-compose.collection-cloud-sync.yml:38` 确实注入了 `CLOUD_DATABASE_URL`，但对象是 `backend-collector`，该文件未定义任何 celery 服务 |
| P1-3 | 采集机登记整体错位一位 | **确认存在**，但**归因已过时**（详见 §1.2） | 见 §1.2 / §1.3 |
| P2-1 | `--check --json` 因 datetime 崩 | **确认存在**（成因要改） | `backend/services/data_pipeline/dashboard_bootstrap.py:236` `dict(row)` 带 datetime → `scripts/bootstrap_postgresql_dashboard.py:57` `json.dumps` 无 `default=`。**修正**：僵尸 run 的成因不是「异常路径没收尾」（`refresh_runner.py:888/895` **有**收尾），而是**逐目标提交**（`:836`）后进程被**硬杀** ⇒ `running` 已提交、最终 UPDATE 没来得及执行 |
| P2-2 | 僵尸回收是封闭白名单 | **确认存在**（建议要改） | `backend/tasks/refresh_queue_tasks.py:521-533` SQL 与任务单逐字一致。**修正**：`ops.pipeline_run_log` 只有 9 列，**无** `heartbeat_at` ⇒ 任务单建议的「用心跳做二次判据」需要先加列（→ V2） |
| P2-3 | bootstrap 两模式互斥、refresh 写旧指纹 | **确认存在** | `scripts/bootstrap_postgresql_dashboard.py:107-119` 早返回；`dashboard_bootstrap.py:681-682` 写 `state.get(...)` 旧值 |
| P2-4 | `source_freshness_check` 永久红灯、无出口 | **确认存在**（三处口径要改） | `source_freshness_service.py:447` 只有 success/partial_failed；全仓无消费方（前端零命中）。**修正①**：`b_class.fact_*_analytics_*` / `_orders_*` **源表是覆盖的**，没覆盖的是 `semantic.fact_analytics_monthly_atomic`（`semantic` schema 的 VIEW，不在 `b_class` 且 `relkind IN ('r','p')` 排除视图）。**修正②**：代码里**根本没有「当前采集范围」这个概念**，红灯来自「**曾经采过、现已停采**」的链；「从未被采」的表判 `empty` → skipped，**不进 partial_failed**。**修正③**：阈值是粒度默认（daily/weekly=365、monthly=60、snapshot=10）+ 2 条链级例外（`shopee/tiktok products[daily]`=30）+ 环境变量覆盖 |
| P2-5 | 采集失败无主动告警 | **确认存在**（一处口径要改） | 6 条置 failed 路径全部只写库，无任何通知调用。**修正**：单域失败但其它域成功 ⇒ 终态是 `partial_success`（`executor_v2.py:5444-5448`），只有 `completed_count==0 and failed_count>0` 才判 `FAILED`（`:5426-5427`） |
| P3-1 | `clearance_ranking` 是孤儿记账行 | **确认存在** | `DASHBOARD_MODULE_TARGETS` 只有 `business_overview` / `inventory_backlog` 两个模块；`api.sku_clearance_ranking_module` 是 `inventory_backlog` 的 core target；代码里无任何 prune 逻辑 |
| P3-2 | 本地 b_class 历史不完整 | **代码层无法验证**（需连库）；文档层确认未写 | `docs/guides/LOCAL_COLLECTION_TAKEOVER.md` 通篇无「云端为基准 / 2026-07 起可比」 |

### 1.2 P1-3 的归因已过时（任务单 §2.2 / §2.8 第 1、6 条）

| 任务单说法 | 实际 |
|---|---|
| `record_runtime_discovery` 不校验归属就直接覆盖 | **主干已修**。`platform_shop_discovery_service.py:236` docstring 明写「**只记录证据，不改 `core.shop_accounts`**」；守卫 `_guard_platform_shop_id_binding(allow_rebind=False)`（`:310-316`）只做状态判定。修复提交 `e18e2c75` 时间 **2026-11-06 22:48**，采集机那批错误写入发生在 **11-06 10:22~10:32** ⇒ **在修复之前**，是历史代码欠的账 |
| 「该来源至今仍在写」 | 采集机基线 `b716efbb`（11-09 14:20）**已含**该修复 ⇒ 不再写主数据，只写探测证据 |
| 「硬编码覆盖表已不存在，需重新定位编号来源」 | **已完成定位**。`3e7b9795`（11-07）把采集侧编号收敛到主数据单一源头、删除硬编码覆盖表；现入口是 `modules/components/export/base.py:73-85` → `shop_account_identity_service.resolve_master_platform_shop_id_sync` |

### 1.3 复核新增的三个发现（任务单未覆盖）

**发现 A —— 主干内部方向自相矛盾**

| 位置 | 主张 |
|---|---|
| `modules/core/fact_identity_columns.py:33-37`（SSOT 权威文件） | `shop_account_id` **最可靠**；`platform_shop_id` **会被采集器污染**，次之 |
| `current_migrations/versions/20261112_realign_identity_candidates_anchor.py` | `shop_account_id` → priority 1，`platform_shop_id` → priority 2 |
| `sql/semantic/shop_identity_resolution_candidates.sql:109-132`（现状资产） | 同上（`shop_account_id`=1、`platform_shop_id`=2） |
| `current_migrations/versions/20261117_remediate_shopee_row_identity_conflicts.py:25-41` | **反过来**：「编号是权威的，标签是错的」⇒ 用编号反查账号并**改写 `shop_account_id`** |

⇒ 20261117 在**错位登记**的库上执行 ⇒ 把 957 行搬到了**错的店**，且把这 957 行的四路身份全部改写成一致的错误值 ⇒ **行内自洽 ⇒ 本地看板零告警**。这正是 11-06 方案 §3.2 警告过的「静默错配」，只是当时判断对象是计数口径。

**发现 B —— 入库收敛的信号优先级与 SSOT 相反（这是「后续每批都产生同样 unknown」的代码源头）**

`backend/services/shop_identity_reconciliation_service.py:91-107`：

```python
#: 信号优先级 —— **平台店铺编号最权威**。
SIGNAL_PRIORITY = ("platform_shop_id", "shop_id", "shop_account_id", "store_name")
```

`apply_reconciliation`（`:592-633`）在收敛后会把行内四路身份键**全部改写成同一账号的登记值**。
⇒ 登记信息错位时：**编号优先 ⇒ 新行被打上错的 `shop_account_id` 且行内自洽** ⇒ 本地看不出异常 ⇒ 推到云端 ⇒ 候选数 2 ⇒ `unknown`。

⇒ 与发现 A 是同一个错误的两个副本：20261117 是**一次性批量犯**，入库收敛是**每批持续犯**。

**发现 C —— 污染来源已定位（任务单归因正确），且**已在主干修好**；但复发守卫还有最后一个缺口**

**先更正一处在复核中产生的误判**：人工巡店路径（`record_manual_discovery`）**不是**污染来源。理由：
`shop_discovery_service.run_current_discovery` 的 `_capture_runtime_snapshot`（`:106-113`）把
`dom_snapshot.store_name` 写死成 `None` ⇒ 候选集只能由「`platform_shop_id` 命中」产生 ⇒
自动绑定写回的是**同一个值**（no-op）⇒ **不会**产生错位，也**不会**产生别名。

**真正的污染来源（已用 `git show e18e2c75^` 逐行核对，与采集机实测三项特征完全吻合）**：

修复前的 `record_runtime_discovery`（`git show e18e2c75^:backend/services/platform_shop_discovery_service.py`）：

```python
shop_account.platform_shop_id = detected_platform_shop_id
shop_account.platform_shop_id_status = "auto_bound"
await retain_previous_platform_shop_id_as_alias(db, shop_account, previous_platform_shop_id)
```

⇒ 与采集机 11-06 10:22 那 9 行的实测特征**逐条对上**：编号被改写 + `platform_shop_id_status='auto_bound'` + 旧值降级成 `former_platform_shop_id` 别名。
探测值来自 `page.url` 的 `cnsc_shop_id`，而三个调用点都在**切店组件跑之前** ⇒ 读到的是上一个店 / 登录账号默认店的编号 ⇒ **整体错位一位**。

⇒ **任务单的根因归因（根因 ①）是正确的**，本方案 §1.2 的「归因已过时」只针对**这条修复已经进主干**这一点：

| 项 | 状态 |
|---|---|
| 污染来源 | `record_runtime_discovery`（修复前）—— **已修**（`e18e2c75`，2026-11-06 22:48） |
| 采集机是否还在跑旧代码 | 否。采集机基线 `b716efbb`（11-09 14:20）**已含**该修复 |
| 复发守卫 | **已有且完整**：`backend/tests/test_shop_platform_id_rebind_alias.py` 的 `test_runtime_discovery_never_writes_master_data`（`:263`）、`test_runtime_discovery_marks_stale_url_when_id_differs`（`:295`）、`test_runtime_discovery_marks_conflict_when_id_owned_by_another`（`:319`）、`test_every_master_data_writing_path_calls_the_shared_ownership_guard`（`:248`） |
| `confirm_discovery` 的人工换绑 | **有意设计且有测试保护**（`test_manual_rebind_keeps_previous_platform_shop_id_as_alias` `:460`）—— **不改** |
| ⚠️ **剩下的缺口** | **采集导出路径缺一条反向守护**：SSOT（`shop_account_identity_service.py:11-12`）要求「**绝不**回退到账号上下文里的来路不明的编号（`cnsc_shop_id` …）」，但 `backend/tests/test_collection_output_path_unification.py` 只有**正向**测试（主数据编号被用上），**没有**反向测试（主数据取不到 ⇒ 编号必须留空、绝不能回退到 `cnsc_shop_id`）。⇒ 见批次 1.2 |

---

## 2. 方向裁定

### 2.1 裁定结论

**以行内 `shop_account_id`（账号章）为权威锚点；`platform_shop_id` 是派生值，必须服从账号章。**

这**不是新立规矩**，而是把仓库已经做过两次的决定补齐到第三处漏抄的地方：

1. `modules/core/fact_identity_columns.py:33-37`（SSOT 权威文件）
2. `current_migrations/versions/20261112_realign_identity_candidates_anchor.py`（语义层已落地的锚点倒置）
3. ⛔ `backend/services/shop_identity_reconciliation_service.py:102`（入库侧，**漏抄**） ← 本次修
4. ⛔ `current_migrations/versions/20261117_remediate_shopee_row_identity_conflicts.py`（历史订正迁移，**方向相反**） ← 本次**不动**（历史不修），但要留痕说明

### 2.2 这个裁定带来的直接好处

- **入库侧**：新行保住**正确的账号归属**（账号章是文件级盖章，采集时就知道正确归属）⇒ 即使主数据暂时未对齐，新行也不会被焊上错账号 ⇒ **登记信息对齐后自动归位，不需要逐行订正归属**。
- **历史行**：不需要碰 ⇒ 完全符合「历史不修」。
- **云端**：新行的 `shop_account_id` + 对齐后的 `platform_shop_id` 一致 ⇒ 候选数 1 ⇒ 归属正确 ⇒ **「保未来」成立**。

### 2.3 裁定带来的代价（明写，不藏）

- 11 月及更早的历史行仍带着错编号 ⇒ **云端这几个月的 `unknown` 不会归零**（这是「历史不修」的既定代价）。
- ⇒ **必须配套一条「历史遗留 vs 新增」分档的巡检**（批次 3 的 3.2），否则告警会永远红，机制就废了。

---

## 3. 批次划分与执行顺序

```
批次 0（只读对账，采集机）  →  批次 2（主数据对齐，采集机）  →  下一轮采集  →  验收
                                    ↑ 需要先有批次 1 的代码
批次 1（代码加固，走 PR）    ─────────────────────────────────────┘
批次 3（巡检与告警）        ── 与批次 1 并行
批次 4（清理与文档）        ── 最后
```

> **关键时序**：批次 2 的主数据对齐必须在**下一轮采集之前**完成。否则下一轮采集仍会用旧（错位）登记写编号。
> **批次 1 的入库收敛改动必须在批次 2 之前上线**，否则对齐后新进来的第一批数据仍会按旧顺序被焊上错账号。

### 批次 0：只读对账脚本（采集机执行，不写任何数据）

**为什么先做**：所有数据动作的正确性都建立在「云端登记就是基准」这个前提上，而这个前提目前是任务单的**断言**，不是验过的事实。同时，因为不做历史订正，**没有第二次数据订正机会**，对账脚本从「订正前的准备」升级为「**常驻守护**」。

**产出**：一条可重复执行的只读脚本，输出四张对比表：

| 表 | 内容 |
|---|---|
| T1 登记信息逐条比对 | `core.shop_accounts` 本地 vs 云端：`platform_shop_id` / `platform_shop_id_status` / `store_name` / `enabled` / `business_role` / `updated_by` |
| T2 错别名清单 | 本地 `core.shop_account_aliases` 中 `alias_type='former_platform_shop_id'` 全量，标注「值 == 拥有者自己的 platform_shop_id」（自别名）与「值 == 别的账号的 platform_shop_id」（跨账号认领） |
| T3 双认领检查 | `identity_value → >1 个账号` 的清单（两边各出一份） |
| T4 探测记录近 30 天分布 | `core.platform_shop_discoveries` 按 status / created_at 分布，确认「把正确编号降级为别名」的写入已绝迹 |

**验收**：
1. 连续跑两次输出**完全一致**（纯只读、无副作用）
2. T1 逐条给出「一致 / 不一致（附两端取值）」
3. T2 直接产出批次 2 的删除清单
4. 脚本本身入库（`scripts/`），连接串一律从 `.env` 读、无硬编码口令

### 批次 1：代码加固（走 PR，含测试）——「保未来」的主体

| # | 改动 | 文件 | 为什么 |
|---|---|---|---|
| 1.1 | 入库收敛信号优先级 → `shop_account_id` 优先 | `backend/services/shop_identity_reconciliation_service.py:102` + `:91-101` 注释块 + `reconcile_identity` docstring「编号权威」那句 | 发现 B：**唯一能让后续每批数据不再重复犯错**的动作。改完新行保住正确账号归属 |
| 1.2 | **采集导出路径的编号来源反向守护** | `backend/tests/test_collection_output_path_unification.py`（新增反向用例）+ `modules/components/export/base.py:69-85`（注释点名 SSOT 出处） | 发现 C 的**最后缺口**：SSOT 要求「绝不回退到账号上下文里的来路不明的编号」，但现在**只有正向测试**。补上反向测试 ⇒ 下次有人把 `cnsc_shop_id` 兜底加回来时会被立刻抓住 |
| 1.3 | `--check --json` 序列化加固 | `backend/services/data_pipeline/dashboard_bootstrap.py:191-238`（`_normalize_json_value` 扩成递归归一化，处理 `datetime` / `date` / `Decimal`；`runs[module_name] = dict(row)` 前先转 ISO） | P2-1：运维最需要结论的时刻命令不可用。归一化收敛到**已有的** `_normalize_json_value`，不在调用点各写一份 |
| 1.4 | celery 注入 `CLOUD_DATABASE_URL` | `docker-compose.dev.yml` 的 `celery-worker` / `celery-beat`（host 用 `host.docker.internal`，端口 15433）+ 守护测试 | P1-2：唯一能提前发现云端停摆的信号，在采集机上是哑的。**注意**：`docker-compose.collection-cloud-sync.yml:38` 已给 `backend-collector` 注入并配好了 `CLOUD_SYNC_TUNNEL_*`，本次只是把同样的配置**补到 celery 服务**上 |

**验收**：
1. 1.1：新增测试 —— 行内编号指向别的账号、但行内账号章正确时，收敛结果取**账号章**那个账号
2. 1.2：新增**反向**测试 —— 主数据取不到编号时，shopee 导出路径的编号**必须留空**，绝不能回退到 `cfg["cnsc_shop_id"]` / `account["cnsc_shop_id"]` / `account["platform_shop_id"]`
3. 1.3：新增测试 —— 存在 `status='running'` 的 run 时 `--check --json` 正常输出 JSON，不抛 `TypeError`
4. 1.4：新增守护测试 —— 采集环境 compose 的 `celery-worker` / `celery-beat` 必须带 `CLOUD_DATABASE_URL`，且其 host **不得**是 `127.0.0.1` / `localhost`（容器回环 ≠ 宿主）
5. 回归：`python scripts/diff_pytest_junit.py <before.xml> <after.xml>` ⇒ **无 NEW failure**（仓库有既有失败基线，按失败集 diff 判定，不按计数）

### 批次 2：主数据对齐（采集机执行；出迁移 + 回滚方案）

**只做「当前状态」，不动任何历史事实行。**

| 步骤 | 动作 | 说明 |
|---|---|---|
| 2.1 | 按 T1 对齐 `core.shop_accounts.platform_shop_id`（9 个 shopee 店） | 目标：与云端**逐条相等**。默认**只动这一个字段** —— T1 另外 5 个字段只报告不改（改名是业务决定、停用是运营开关） |
| 2.2 | `platform_shop_id_status` 回 `confirmed` / `manual_confirmed`；`updated_by` 记为**人工修复**（不是 `system`） | 避免再被自动流程覆盖。`updated_by` 由工具统一写，**不接受**来自云端的对齐值 |
| 2.3 | 按 T2 删除错 `former_platform_shop_id` 别名 | ⚠️ 阻断条件是「该别名值是某账号**唯一**的身份来源」；事实行里出现同值**不阻断**（历史行归属早已固化、语义层别名路不认领平台编号，删别名不改变其解析结果），只作提示 |
| 2.4 | **REFRESH**（不是 DROP 重建）`semantic.shop_identity_resolution_candidates_v2_mv`，随后跑正本/副本内容指纹比对 | **本步骤已按仓库既有事实修正**（见下方「2.4 的修正」） |
| 2.5 | 连带刷新下游 | 原子层 → 物化副本 → 看板（走既有 `refresh_registry` 依赖链 + `bootstrap_postgresql_dashboard.py --refresh-materializations`） |

#### 2.4 的修正（2026-11-10，实施时按仓库既有事实纠正）

方案初稿写的是「DROP + 重建（不带 CASCADE）」，**这是错的**，按仓库自己的既有事实应改为**只 REFRESH**：

- 副本资产 `sql/semantic/shop_identity_resolution_candidates_v2_mv.sql` 的刷新语义是
  「存在则 REFRESH / 不存在则 CREATE」，**绝不 DROP ... CASCADE** ——
  资产自己的注释（`:69-73`）与守护测试
  `backend/tests/data_pipeline/test_identity_candidates_materialization.py::test_materialized_view_asset_never_drops_cascade`
  都在守这条。
- DROP 重建只在**口径变更**时需要：迁移
  `current_migrations/versions/20261112_realign_identity_candidates_anchor.py:41-60` 写明
  「REFRESH 只重算**数据**, 不换**定义**；口径改了之后, 光 REFRESH 刷出来的还是旧口径 ⇒ 必须 DROP 重建」。
  批次 2 只改 `core.shop_accounts` 的**数据**、口径一个字不动 ⇒ REFRESH 即可。
- 而且**不带 CASCADE 的 DROP 会直接失败**：副本下游挂着
  `semantic.fact_orders_atomic` / `fact_analytics_atomic` / `semantic.shop_identity_resolver`
  （都是 `LANGUAGE sql`，依赖被跟踪），要 DROP 得先把这些对象的正文临时换成正本 ——
  那是口径变更才需要的手术，批次 2 不该做。

⇒ 落地工具：`scripts/refresh_shop_identity_candidates.py`（REFRESH + 指纹比对，
指纹口径与迁移 `20261105_create_identity_candidates_mv.py` 的 `_fingerprint` 一致：
行数 + 全量内容 md5）。

**明确不做**：不回滚 957 行、不逐行订正 11 月、不重推 11 月。

**验收**：
1. `core.shop_accounts` 的 9 个 shopee 店 `platform_shop_id` 与云端**逐条相等**
2. `platform_shop_id_status` 全部为 `confirmed` / `manual_confirmed`
3. `former_platform_shop_id` 错别名 0 条；双认领 0
4. 候选池正本与副本**内容指纹一致**
5. **历史行未被动过**：`b_class.fact_*` 的行数、`data_hash`、`_pre_remediation_identity` 留痕计数**全部不变**
6. 总 UV / PV **不变**（15,357 / 33,346）—— 修身份不得改总量

### 批次 3：巡检与告警（与批次 1 并行）

| # | 项 | 要点 |
|---|---|---|
| 3.1 | **云端巡检生效**（P1-2） | 批次 1.4 落地后，采集机上不再 `skipped`；巡检能读到云端 `b_class.fact_*` 的真实水位 |
| 3.2 | **语义层可解析性巡检**（新增，任务单 §2.8 第 8 条） | 检查云端 `semantic.fact_analytics_monthly_atomic` 的 `shop_id='unknown'` 行数 / UV 占比。**必须按 `metric_date` 分档**：登记信息对齐生效日之前的历史月份归入「已知历史遗留」不报警；之后的月份占比超阈值 ⇒ 报警。**这是「历史不修」策略的必要配套** |
| 3.3 | **数据新鲜度分档**（P2-4） | ① 阈值按「这条链是否在当前采集范围内」分档 —— 范围来源必须是**采集器自己用的那一份**（`core.collection_configs.data_domains` / `core.collection_config_shop_scopes.data_domains`），不得另立第三份定义；② 加 `partial_success` 分级；③ 补通知出口 |
| 3.4 | **采集失败主动告警**（P2-5） | 复用现成的 `create_notifications_for_admins`（站内信）+ `alert_service.send_resource_alert`（webhook / 钉钉 / 邮件）+ 飞书投影；`NotificationType.SYSTEM_ALERT` 枚举已预留但零调用。**同一轮内错误聚类**（如「7 个店都挂在 `date option was not clicked`」）；**「等待验证码回填」单独归类**，不与步骤失败混在一起。⚠️ `AlertRule` 那套**只有 CRUD、无求值器**，不能当现成通道用 |
| 3.5 | **僵尸回收扩面**（P2-2） | 回收条件从封闭白名单改为「全族 `status='running'` + 超阈值」，**留痕**（被回收的 `run_id` / `pipeline_name` / 滞留时长写进 `error_message`）。⚠️ **暂不加 `heartbeat_at` 列**；阈值维持 45 分钟（> `time_limit=1800`），且必须同步复查 P2-1 依赖的「活跃行」判定 —— 它会把**任何** `status='running'` 的行当成「正在刷新」 |
| 3.6 | **指纹收敛 + 顺序链**（P2-3） | `refresh_dashboard_materialization_assets` 回写**本次实算**的指纹（`:681-682` 改成重算 `core_expected`）；CLI 把早返回改成顺序链：核心 bootstrap（算指纹并回写）→ 刷新物化资产 → 再回写指纹 ⇒「跑一次就一定收敛」。回写入口收敛到一处 + 断言「写入的 applied == 本次算出的 expected」 |
| 3.7 | **同步侧双基准守卫**（任务单 §2.8 第 7 条） | 推送前除本地登记信息外，还要与**云端登记信息**比对；不一致 ⇒ 降级为**可观测事件**（不再当自洽行放行）。依赖 1.4 的云端连接 |

### 批次 4：清理与文档

| # | 项 | 要点 |
|---|---|---|
| 4.1 | 孤儿记账行 prune（P3-1） | 在写记账的同一事务里 prune 掉不在 `DASHBOARD_MODULE_TARGETS` 里的旧行；**只删记账行，不碰任何物化对象 / 视图 / 模块定义**；删除前写日志。⚠️ 默认不自动删，先提供 `--dry-run` 预览命令 |
| 4.2 | 文档口径（P3-2） | `docs/guides/LOCAL_COLLECTION_TAKEOVER.md` 写明「**以云端为历史基准**，采集机本地只负责增量；跨环境对账仅在 2026-07 之后可比」 |
| 4.3 | 同步检查点 + 矛盾行台账（P1-1） | ⚠️ **在「历史不修」下不要改成「停在第一个矛盾行」** —— 那会让 `fact_shopee_products_daily` 永久卡在那 8 行之前（它们归属永远不会被修）⇒ 把「漏传」换成「堵死」。正确做法：**保持现有推进算法**（不制造永久卡死），额外把被跳过的矛盾行记进台账并标注「已知历史遗留」，另提供**手工重发入口**（将来若决定修历史，改成停在第一个矛盾行即可） |

---

## 4. SSOT 符合性

| 改动 | 判定 |
|---|---|
| 1.1 入库优先级 → 账号章优先 | ✅ **符合**：SSOT 文件（`fact_identity_columns.py:33-37`）已如此定义，入库侧是**漏抄**。是补齐，不是新立 |
| 1.2 堵人工巡店取号 | ✅ **符合**：`shop_account_identity_service.py:11-12` 明令「绝不回退到 `cnsc_shop_id`」，现状违反它。改完是服从已有定义 |
| 1.3 时间戳归一化 | ✅ **符合**：收敛到**已有的** `_normalize_json_value` 这一个归一化入口 |
| 1.4 / 3.7 云端连接 | ✅ **符合**：`CLOUD_SYNC_TUNNEL_*` 已在 `docker-compose.collection-cloud-sync.yml:39-41` 定义过，本次只是把同一份配置补给 celery 服务 |
| 2.1~2.4 主数据对齐 | ✅ **符合**：对齐 SSOT 本身（`core.shop_accounts.platform_shop_id` 是 `shop_account_identity_service` 的「唯一权威源」），别名是派生副本 |
| 3.3 新鲜度分档 | ⚠️ **有现成 SSOT 缺口**：采集范围现在有**两份**定义（代码里的「可选域全集」`DEFAULT_CONFIG_DATA_DOMAINS` vs 数据库里实际生效的 `data_domains`）。分档**必须读采集器自己用的那一份** |
| 3.4 通知出口 | ⚠️ **有现成 SSOT 缺口**：出口现在有 4 条（站内信 / 邮件钉钉 / 飞书 / `AlertRule`），其中 **`AlertRule` 是空壳**（只有 CRUD、无求值器，前端写「开发中」）。要么给它接上求值器，要么明确废弃它 —— **别让它继续冒充 SSOT** |

### 4.1 待补的 SSOT 缺口（本方案不在本轮做，记入 V2）

1. **认人优先级目前写在三个地方**：SSOT 文件的散文、Python 的 `SIGNAL_PRIORITY`、两份 SQL 资产（含指纹守护）。
   ⇒ 本轮只把 Python 侧对齐到 SSOT 的**结论**；**建议 V2 做「优先级收敛到一处」**：让 SSOT 文件导出一个可执行的优先级元组，Python 直接引用它，SQL 侧加一条守护测试断言三者一致。
   **否则我们只是把矛盾从「两个 Python 文件」挪到了「三个地方」，下次照样打架。**
2. **采集范围的两份定义**（见 3.3）。
3. **`AlertRule` 空壳**（见 3.4）。

---

## 5. 为什么之前一直没发现

不是运气问题，是六个结构性原因：

1. **同一件事有三份「权威」，每一份单独看都合理。** 采集侧说「编号只认主数据」，入库侧说「编号最权威」，语义层说「账号章最权威」，20261117 迁移说「编号是权威的标签是错的」。任何一次评审只看到其中一份，都挑不出毛病。
2. **验收只看「总量对不对」，不看「归属对不对」。** 11-07 事故后补推，账本行数与云端增量**精确相等**，验收全绿。但归属塌成一个 `unknown` 桶时，**总量一个字节都不会变**。这类故障天生逃过「对总数」的验收。
3. **两端各自自洽，只有跨端比对才暴露。** 采集机用自己的错登记解释自己的数据 → 一切正常；云端用对登记解释 → 72/80 行崩掉。**「两边逐店比对」是这次任务单里第一次被做**（那批 `output/diag_*.py`）。
4. **守护测试把错误方向「焊」成了通过条件。** `test_remediation_follows_the_platform_number:244-259` 明确断言「订正方向 = 编号权威」，还写着「方向反了会把业务数据搬到别的店下面」—— 该测试在当时是对的（在登记正确的库上），但它**保护的是当时那个前提**。「正本 vs 副本指纹一致」的守护保证两份 SQL 一致，**但不保证它们与 SSOT 文件、与 Python 侧一致**。
5. **「不报错」被当成「没问题」。** 巡检永远 skipped、新鲜度永远 partial_failed、运维命令直接崩 —— 都是**持续性的哑 / 红**，不产生任何告警，所以能存在很久。
6. **责任链断了一环。** 采集机「只承接运行、不改业务代码」；开发环境不连云端库、看不到采集机真实数据。发现问题的（采集机）与有权修代码的（开发环境）之间**没有自动通道**。11-06 那份对齐方案是在开发环境写的、并明确决定「历史数据不修」—— 于是「已经写坏的数据」无人认领，直到今天。

---

## 6. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 1.1 改优先级后，部分行的归属结论变化 | 历史行可能被重新解释 | 本轮**只影响新入库的行**；历史行不动。回归用 junit diff 证明无新增失败 |
| 1.2 巡店不再自动绑定 | 运营需要多一次人工确认 | 守卫**不抛异常**，只跳过自动绑定 + 落证据 + 日志；巡店结果页提示「探测值与登记不一致，已记录待确认」 |
| 批次 2 改登记信息 | 若云端登记本身也不对 ⇒ 越改越错 | 批次 0 的 T1 先出逐条比对；**改前导出 `core.shop_accounts` 快照**；改后跑 T1 复跑确认一致；异常时按快照回滚 |
| 批次 2 重建 MV | 下游视图短暂空窗 | 走 `scripts/bootstrap_postgresql_dashboard.py --module all` 全量重建；选低峰执行 |
| 批次 3 扩面回收 | 误杀正在跑的长任务 | 阈值维持 45 分钟（> `time_limit=1800`）；回收留痕；**同批复查「活跃行」判定**（`dashboard_bootstrap.py:213-222` 的白名单比回收器**更窄**，扩面后必须同步） |
| 批次 3.2 新增巡检 | 历史遗留 unknown 让告警永远红 | 巡检**按 `metric_date` 分档**，历史月份归「已知历史遗留」不报警（见 §2.3） |
| 批次 4.3 台账 | 台账变成新的僵尸表 | 台账只记录不阻塞；提供 `--dry-run` 与归档口径 |
| 采集机本地适配误入 commit | 污染主干的 `.ps1` BOM 等 30 项本地适配 | **改动走 PR，不直推 main**；采集机侧用 `skip-worktree` + `.git/info/exclude` 隔离 |

---

## 7. 执行清单（勾选用）

- [ ] 批次 0：写只读对账脚本 → 采集机跑 → 回 T1~T4
- [ ] 批次 1.1：入库优先级 → 账号章优先（+ 注释 + 测试）
- [ ] 批次 1.2：堵人工巡店写主数据（+ 测试）
- [ ] 批次 1.3：`--check --json` 序列化加固（+ 测试）
- [ ] 批次 1.4：celery 注入 `CLOUD_DATABASE_URL`（+ 守护测试）
- [ ] 批次 1 回归：junit diff 无 NEW failure
- [ ] 批次 2：主数据对齐（出迁移 + 回滚）→ 采集机执行 → 回验收数据
- [ ] 下一轮采集 → 验收「新增月份 unknown = 0、逐店归属与云端一致、总量不变」
- [ ] 批次 3.1~3.7
- [ ] 批次 4.1~4.3
- [ ] 更新 `docs/superpowers/plans/STATUS.md`
