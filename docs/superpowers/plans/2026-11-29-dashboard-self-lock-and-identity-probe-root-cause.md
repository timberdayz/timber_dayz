# 看板刷新自锁循环 + 采集侧 404 假冲突：根因分析与根治方案

- 日期：2026-11-29
- 范围：`backend/services/data_pipeline/dashboard_bootstrap.py`、`backend/services/data_pipeline/refresh_validation.py`、
  `backend/tasks/refresh_queue_tasks.py`、`backend/domains/business/routers/dashboard_api_postgresql.py`、
  `frontend/src/domains/business/views/BusinessOverview.vue`、
  `backend/services/platform_shop_discovery_service.py`、`modules/apps/collection_center/executor_v2.py`
- 触发：业务概览页常驻「业务概览数据刷新中 / Dashboard SQL 资产正在刷新」提示；
  业务概览页常驻「店铺身份未对齐 / 采集期探测到 1 次店铺身份异常」告警。

---

## 一、结论摘要

两个现象**都不是**「系统正在正常工作」的提示，而是两个**已经闭合的缺陷环**：

| 现象 | 真相 | 本次处置 |
| --- | --- | --- |
| 页面永远「数据刷新中」 | 状态机把**没人能修的状态**（刷新资产定义漂移）当成了「正在刷新」，而修复方又把自己制造的「正在刷新」当成失败条件 ⇒ 退避重排 ⇒ 无限自锁 | 断开闭环：状态机去死区 + 验收口径与运行期门禁同源 + 安全网熔断 + 僵尸回收 |
| 1 次店铺身份异常 | 采集器打开到平台的 **404 页**，把 404 页 URL 上残留的**上一家店编号**当成探测结果 ⇒ 判成「被别的账号占着」 ⇒ **假冲突** | 采集侧：404 / 错误页 / 登录页 ⇒ 判「探测失败」，不参与绑定判定、不计入告警 |

实测证据（开发库 `xihong_erp`）：

- `core.refresh_queue_tasks` 里 `dashboard_safety_net_repair` **failed 859 次 / skipped 193 次 / completed 32 次** —— 每一次都真的重跑了整条刷新计划（物化视图全量重算）。
- `ops.pipeline_run_log` 里 3 行永久 `running` 的 `dashboard_safety_net_repair`（最老的停了 19 小时）。
- `core.platform_shop_discoveries` 28 行里 1 行 `conflict_detected`（id=72），其 `raw_payload.current_url` =
  `https://seller.shopee.cn/404?cnsc_shop_id=1391124228` —— **404 页**。

---

## 二、看板自锁循环的根因链

### 2.1 事实核对（不是定义漂移，是**记账**漂移）

| 项 | 值 |
| --- | --- |
| `ops.dashboard_asset_state`（business_overview）写入时间 | 2026-11-05 04:38 |
| 账本里的 `refresh_fingerprint_applied` | `e63efcbd…`（= 写账本那一刻的文件哈希） |
| **当场重算**的文件哈希（`_module_refresh_plan` 8 个目标） | `fb31cb8c…` |
| 库里 `semantic.shop_identity_resolution_candidates` 的定义 | **已含新口径**（`business_role='operating_store'` + 别名不认领他人编号） |

⇒ 库里定义**已经是新的**（迁移 `20261112_realign_identity_candidates_anchor` 重建了候选集视图与物化副本），
**只有账本停在旧哈希**。`93bb5ac0`（11-07 00:01）改了两个身份候选集 SQL ⇒ 文件哈希变了 ⇒ 账本对不上。

### 2.2 四个缺陷环

```
① 迁移重建了资产（事实已新）
        ↓ 迁移不回写 ops.dashboard_asset_state（迁移不 import backend，且不该抄指纹算法）
② 账本 refresh_fingerprint_applied 停在旧哈希
        ↓ _build_module_report：refresh 指纹不一致 ⇒ status='refreshing'
③ 「refreshing」这个状态**没有任何人能消掉它**
        ├─ bootstrap_dashboard_assets_if_needed：status ∈ {ready, refreshing} ⇒ 跳过 ⇒ 不修
        ├─ 物化资产文件是「存在则 REFRESH / 不存在则 CREATE」⇒ 对已存在的对象**从不重建定义**
        │   ⇒ 安全网/刷新/重试全都只原地刷新或跳过 ⇒ 不修
        └─ 安全网看到 status != 'ready' ⇒ 每 5 分钟排一次 dashboard_safety_net_repair ⇒ 永远重试
④ 修复任务跑完 → 验收方要求模块 status == 'ready'
        ↓ refresh_validation._module_status_is_ready：'refreshing' != 'ready' ⇒ 验收失败
        ↓ error_message='dashboard_modules_not_ready:business_overview' ⇒ 任务 failed ⇒ 退避重排
        ↓ 下一轮安全网又看到「不是 ready」⇒ 再排一次 ⇒ 无限自锁
```

④ 是**最关键的一环**：运行期门禁（API）把 `refreshing` 当**可用**（放行 + 提示），
验收方却要求 `ready` —— **两套口径**。于是修复方永远通不过自己的验收。

补充：`refresh_missing`（刷新资产缺失）旧口径也只判 `refreshing`（页面照常展示、实际数据是空的），
而修复路径对「已存在的普通视图」是跳过的 ⇒ **同样修不掉**，是第二个死区。

### 2.3 为什么「重启服务/重新部署」治不好

账本漂移会在**下一次改 `sql/` 资产文件**时再次产生，而刷新路径永远不会回写它
⇒ 这是**结构性问题**，不是一次性事故。同类历史证据：仓库根 `api_ready.json`（2026-06-08）
已记录同类 drift/refresh 指纹不一致。

---

## 三、根治方案（本次已实施）

原则：**把「可自愈」与「不可自愈」分开；把「事实」与「记账」分开；修复方不得给自己当法官。**

### 断点 1：状态机去死区

`backend/services/data_pipeline/dashboard_bootstrap.py::_build_module_report`

- 移除「`refresh_applied != refresh_expected` ⇒ `refreshing`」这条判据。
  该差值**没有任何自愈路径能消掉**（物化资产文件对已存在的对象从不重建定义），
  拿它当状态判据 = 制造一个「没人能修、却被无限重试」的死区。
- 降级为**纯可见性字段** `refresh_fingerprint_drift`（运维可在 `/assets/status` 查到），
  **不参与状态判定、不驱动修复**。资产定义的最终对齐由**部署/迁移**负责。
- `refreshing` 现在**只**由「确实有一趟刷新 run 在跑」触发（有意义的提示）。
- `refresh_missing`（刷新资产缺失）从 `refreshing` 提升为 **`drift`**：
  对象缺失是硬伤（页面直接读不到），且修复任务能自愈（「不存在则 CREATE」）。

### 断点 2：验收口径与运行期门禁同源

新增 `DASHBOARD_ASSET_AVAILABLE_STATUSES = {"ready", "refreshing"}`（`dashboard_bootstrap`），
`refresh_validation._module_status_is_ready` 与
`dashboard_api_postgresql._require_dashboard_assets_ready` **共用同一份定义**：

- 只有 `drift`（对象缺失 / 定义漂移 = 数据不可信）算不可用；
- `refreshing` 是**可用**状态 —— 修复方不再把自己制造的 `refreshing` 当失败条件。

守护测试断言两个模块引用的是**同一个对象**（`is` 比较），杜绝再次分叉。

### 断点 3：安全网只修可自愈的状态 + 熔断

`backend/tasks/refresh_queue_tasks.py::_async_dashboard_refresh_safety_net`

- 只对 `status == 'drift'` 排 `dashboard_safety_net_repair`；
  `refreshing`（正有刷新在跑）不再排（否则只会并发）。
- **熔断**：同一模块连续 3 次修复失败 ⇒ 熔断，暂停自动重试并打 `ERROR` 日志
  （含模块名、失败次数、上次失败时间、冷却截止时间）；
  冷却 30 分钟后放一次「半开」尝试；一旦出现一次成功，连续计数归零、熔断自动解除。

### 断点 4：僵尸 run 回收

新增 `_reap_stale_dashboard_refresh_runs`：`ops.pipeline_run_log` 里超过 30 分钟仍是 `running`
的看板刷新 run 标记为 `failed`。匹配条件与 `_load_active_dashboard_refresh_runs` **逐字一致**
（只有被状态机读进去的行才需要回收）。否则一条僵尸 run 就能把模块**永久**钉在 `refreshing`。

### 断点 5：前端提示分级

`frontend/src/domains/business/views/BusinessOverview.vue`

- 改用后端给的 `ready` 字段判断「不可用」，不再硬编码状态名；
- `refreshing` 单独处理：它是**可用**状态，提示一句即可（真在刷）。

### 效果

- 本机 `business_overview` 立刻从 `refreshing` 变 `ready` ⇒ 页面提示消失（**无需改库**）。
- 账本里的 `refresh_fingerprint_applied` 仍是旧值 —— 这是**事实**（迁移确实重建了资产但没回写账本），
  现在只作为可见性字段存在，不再驱动任何判定与重试。

---

## 四、采集侧：404 判「探测失败」，不制造假冲突

### 4.1 事故链

```
采集器登录后打开的第一个页面 = https://seller.shopee.cn/404?cnsc_shop_id=1391124228
        ↓ 404 页 URL 照样带 cnsc_shop_id（还是「上一家店」的编号）
旧代码把它当正常探测 ⇒ 1391124228 被 shopee_sg_hx_home_local 占着
        ↓ 判成 conflict_detected（不是 stale_url，因为目标账号也有编号）
业务概览页：「采集期探测到 1 次店铺身份异常」
```

**页面上压根没有店铺身份信息**，拿 URL 参数做绑定判定 = 制造假冲突。

### 4.2 处置

`modules/apps/collection_center/executor_v2.py`

- 新增 `_is_platform_error_page(url)`：看 path **最后一段**是否命中
  `404 / 404error / error / notfound / signin / login` 等（只看最后一段，
  避免把 `/datacenter/error_report` 这类正常业务路径误判）。
- `_extract_platform_shop_context` 新增 `is_error_page` 字段（证据仍留在 `current_url` 等字段里）。
- `_record_platform_shop_discovery_async` 命中错误页 ⇒ 传 `probe_failed=True`。

`backend/services/platform_shop_discovery_service.py`

- 新增状态 `PLATFORM_SHOP_DISCOVERY_STATUS_FAILED = "failed"`；
  **刻意不在** `PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES` 里 ⇒ **不计入身份异常告警**
  （2026-04 已有 3 条同口径历史记录，当时命中的是登录页）。
- `record_runtime_discovery(..., probe_failed=True)`：
  **不做绑定判定、不写候选账号、不把 URL 上的编号当成探测值**（主字段置 NULL），
  证据（URL）留在 `raw_payload` 里。
- 正常页面上的同一个编号**仍然**判 `conflict_detected`（改动只作用于错误页路径）。

---

## 五、历史那条假冲突怎么处理

`core.platform_shop_discoveries` id=72 保留原样（**不删历史**）。
它的 `raw_payload.current_url` 里就是 404 证据，属于「当时的错误判定」。

- **不删**：历史记录是证据。
- 若要让运营侧的告警归零，需要**人工确认**后把它改判为 `failed`（与 2026-04 那 3 条同口径）；
  这是**改历史判定**，必须由人拍板，不由代码自动做。

---

## 六、遗留与 V2

| 项 | 状态 | 说明 |
| --- | --- | --- |
| `ops.dashboard_asset_state` 的记账仍可能落后于文件 | **已知，不再影响判定** | 资产定义的最终对齐由部署/迁移负责；若要彻底消除，需要让「落库」只有一个入口并由它回写账本（V2） |
| 物化视图定义变更的落库路径 | **V2** | 资产文件是「存在则 REFRESH」，已存在的 MV 改定义只能靠迁移 DROP+CREATE；下游里有**不是 refresh registry 可重建目标**的对象（`mart.hr_shop_monthly_profit`、`mart.inventory_backlog_base_mv`），重建清单需要补齐 |
| 部署脚本的重建清单不含 MV | **V2** | `DEFAULT_REBUILD_VIEW_TARGETS` 只含普通视图；MV 定义变更要靠迁移 |
| 入库身份字段口径（模板 dedup 字段 vs 域默认字段）不一致 | **V2（既存缺陷，非 A~G 引入）** | orders / inventory 上不一致；翻 `SYNC_CORE_FIELDS_HASH_ENABLED` 前必须按实跑路径重做 hash 回放 |

---

## 七、验证

- 守护测试：`backend/tests/data_pipeline/test_dashboard_asset_self_lock_guardrails.py`（15 个）
  —— 守住四个断点；`backend/tests/test_platform_shop_discovery_error_page.py`（14 个）
  —— 守住 404 判探测失败。
- 相关回归：`backend/tests/data_pipeline/` 全量 + 刷新队列 / 安全网 / 探测状态机 / 采集执行器。
- 全量后端回归（junit 失败用例 id 集合差，不是失败计数）：
  before（`da2a2a2a`）137 失败 / 4655 通过 / 22 错误 / 4821 收集
  → after 134 失败 / 4687 通过 / 22 错误 / 4850 收集；
  **NEW = 0 ／ FIXED = 3 ／ COMMON = 156**，diff 脚本退出码 0。
  （FIXED 的 3 条是 `test_dashboard_bootstrap_locking.py` 的陈旧桩，与本次改动同属一条路径。）
- 前端守卫测试：失败名单与基线**逐条一致**（8 个历史遗留，均不在本模块内）；`npx vite build` ✓。
- 真实库验证（开发库，**未改业务数据**）：
  `python scripts/bootstrap_postgresql_dashboard.py --check --module business_overview --json`
  ⇒ `business_overview.status` 由 `refreshing` 变 **`ready`**、`ready=true`、`assets_drift=false`；
  `refresh_fingerprint_drift=true` 作为可见性字段保留。
- 僵尸回收在真实库上实跑通过：3 行永久 `running` 的 `dashboard_safety_net_repair` 被标记为 `failed`。

## 八、落地后还需要做的一步

**重启本地服务**（`local_console`）。修复在代码里，但**正在跑的 celery worker / 后端进程仍加载旧代码**：
旧代码里 `business_overview` 仍被判成 `refreshing` ⇒ 安全网仍会每 5 分钟排一次修复任务。
重启后：新代码判定为 `ready` ⇒ 安全网**不再排修复任务** ⇒ 循环就此终止。

已积压的 860 条 `failed` 修复任务**保留为历史证据**，不清理（清理属于改历史记录，需人工拍板）。

