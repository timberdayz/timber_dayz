# 采集任务状态 SSOT 收敛 + 文件系统护栏 + 日/周粒度废弃重采

- 日期：2026-11-11
- 批次：店铺身份「保未来」优化 · 批次 4（代码缺陷收口）
- 上游方案：`docs/superpowers/plans/2026-11-11-shop-identity-business-plan.md`
  §十一「SSOT 三条铁律」→ 律 1「真源只能有一个，而且必须写在纸上」
- 分支：`fix/2026-11-11-task-center-status-constraint`
- base：`main`（`4f37dad7`）

---

## 1. 本批解决什么

两个**会直接让采集跑不起来 / 让排查误判**的代码缺陷，外加一条
**已声明决策与实际动作对齐**的数据处置。

### ① 任务中心状态约束漂移 ⇒ 采集真实失败原因被盖掉

**现象**：9 家 shopee 采集失败后，失败原因显示成
`This Session's transaction has been rolled back due to a previous exception during flush...`
而不是「平台要求滑块验证码，等人工处理」。

**根因**（实测到代码行）：`public.task_center_tasks` 的 `CHECK` 约束
`chk_task_center_tasks_status` 里**手抄**了一份状态清单，**漏掉了**
`verification_required` / `verification_submitted` / `manual_intervention_required`。

⇒ 采集走到「等人工处理」时（`_on_verification_required` → 写任务中心），
写库被 PostgreSQL 直接拒绝（`CheckViolationError`）
⇒ SQLAlchemy session 事务被回滚 ⇒ 上层兜底捕获到的异常变成事务回滚噪音
⇒ **真实原因被覆盖**；且任务中心里任务状态是 `failed` 而不是「等待人工处理」
⇒ **前端的人工处理入口拿不到正确状态**。

**为什么不是「加一条迁移把三个值补进去」**：那只是把第 6 份手抄再补一次，
下次真源加状态时它照样漂移。

⇒ 真源 `backend/services/collection_task_status.py` 本来就自称 SSOT，
但它**只定义了状态分组**（终态/活跃/暂停），**没定义「任务中心能写哪些状态」**
⇒ 于是「哪些状态能进任务中心」这件事在 6 个地方各抄一份，其中一份漂了。

### ② 测试把假文件写进正式数据目录

**现象**：排查数据问题时，`data/raw/2026/` 里混着 176 个假文件。

**实测**：
* 内容全是 `fake-export`（**11 字节**）—— 根本不是有效的 xlsx；
* 全部**没有** `public.catalog_files` 入库记录（孤儿文件）；
* 真实采集文件对照：**89 KB** 的有效 .xls；
* 跑一次 `tests/test_executor_v2.py`（27 个用例）就写 **8 个文件**。

⇒ 差点误判成「订单采了没入库」。

**根因**：`executor_v2._process_collected_files` 用 `get_data_raw_dir()` 决定落盘目录，
而 `get_data_raw_dir()` 读**环境变量 `DATA_DIR`**。
`backend/tests/conftest.py` 已经给**数据库 / Redis / Celery** 都加了护栏
（护栏失效就整场测试失败），**唯独漏了文件系统**。

### ③ 日/周粒度历史数据：把「不修历史」写成明确例外并执行

`modules/core/shop_identity_ssot.py` §③ 快照层原写「既定决策不修（只保未来）」。
但用户 2026-11-11 决策：日/周粒度数据问题大面积且难以分辨可信度
⇒ **整体废弃重采**（不是逐行订正 —— 删干净了就不会撞 upsert 冲突键）。

⇒ 先改声明（把例外写进纸面），再执行清理。

---

## 2. 改动清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `backend/services/collection_task_status.py` | **真源扩展**：加 `ALL_STATUSES`（状态全集）、`TASK_CENTER_WRITABLE_STATUSES`（任务中心可写集合）、`TASK_CENTER_OWN_STATUSES`、`render_task_center_status_constraint()`（渲染 SQL 约束表达式）、`to_task_center_status()`（状态映射）。补 `INTERRUPTED` —— 它是采集侧真实写入的终态（服务重启回收），原先真源里**没有** |
| 2 | `modules/core/db/schema_parts/collection.py` | ORM 的 `CheckConstraint` **改为从真源渲染**（原先手抄 10 个值） |
| 3 | `backend/services/collection_config_run_service.py` | `TERMINAL_TASK_STATUSES` / `RECOVERABLE_TASK_STATUSES` **从真源派生**（原先手抄） |
| 4 | `backend/domains/collection/routers/collection_schedule.py` | `ACTIVE_COLLECTION_TASK_STATUSES` **从真源派生**（原先手抄）；另修 2 处 `ruff E712`（`is_active == True` → `is_(True)`，布尔 NOT NULL 列上取值集合完全相同）—— 否则 CI 的 `ruff check <changed files>` 必判红 |
| 5 | `backend/domains/collection/routers/collection_tasks.py` | `_collection_status_to_task_center` 改为调用真源的 `to_task_center_status()`（原先手抄 dict） |
| 6 | `current_migrations/versions/20261226_task_center_status_constraint.py`（新增） | 约束对齐迁移：**从真源渲染**目标表达式（不写死状态清单）；迁移前核对现状、存量行校验、fail-closed |
| 7 | `modules/core/shop_identity_ssot.py` | 快照层加「日/周整体废弃重采」例外（`DISPOSABLE_GRANULARITIES`），并写进 `IDENTITY_LAYERS` 的 `on_problem` |
| 8 | `tests/conftest.py`（新增） | **文件系统护栏**：把 `DATA_DIR` 指向临时目录 ⇒ 测试的采集产物落不到正式目录；**每个用例前重新钉一次 + 清 `path_manager` 的 lru_cache**（见 §3.6）；会话结束自检告警 |
| 9 | `backend/tests/test_collection_task_status_ssot_contract.py`（新增） | 状态 SSOT 守卫（24 条） |
| 10 | `tests/test_collection_data_dir_guard_contract.py`（新增） | 文件系统护栏守卫（7 条） |

### 2.1 依赖点收敛结果（原先 6 份手抄 → 1 份真源）

| 位置 | 原状 | 现在 |
|---|---|---|
| `collection_task_status.py` | 分组定义（无「可写集合」） | **真源**：全集 + 可写集合 + 渲染函数 + 映射函数 |
| ORM `CheckConstraint` | 手抄 10 个 ❌ 漏 3 个 | 渲染自真源 |
| `collection_config_run_service.py` | 手抄 5+7 个 | 派生自真源 |
| `collection_schedule.py` | 手抄 7 个 | 派生自真源 |
| `collection_tasks.py` 映射 | 手抄 dict | 调用真源函数 |
| 前端两个视图 | 手抄 7 个 | 由**守卫测试**断言与真源一致 |
| `collection_config_execution.py` | 已正确引用真源 | 保持 |

---

## 3. 数据处置（日/周粒度）

范围口径来自新写入的声明：`DISPOSABLE_GRANULARITIES = ('daily', 'weekly')`
⇒ **只清日/周粒度；月粒度与快照粒度完全不动**。

### 3.1 实测（干跑）

| | 本地 | 云端 |
|---|---|---|
| 待清表（总） | 41 张（9 张非空） | 39 张（9 张非空） |
| 日/周行合计 | **2211** | **2641** |
| 月/快照行 | **不动** | **不动** |

非空表的行数（两端同源）：
`fact_shopee_orders_weekly` 1298、`fact_tiktok_orders_weekly` 208、
`fact_shopee_orders_daily` 336、`fact_tiktok_orders_daily` 134、
`fact_shopee_products_daily` 110/518、`fact_tiktok_analytics_daily` 72、
`fact_tiktok_products_daily` 47、`fact_shopee_analytics_daily` 3/12、
`fact_shopee_services_agent_daily` 3/9。

### 3.2 判定依据（不靠文件名猜）

周粒度 1506 行的原始 `shop_id` **全部**是 `xihong`（采集方代号，不是店铺身份）
⇒ 与「身份归属错位」的判断一致。

### 3.3 备份

删除前把**每张被清表的全部行**（含 `raw_data`）导出成 JSONL：
`%TEMP%\mcode_granularity_backup_20261111\{LOCAL,CLOUD}_daily_weekly_fact_rows.jsonl`
⇒ 可逐行完整恢复。

### 3.4 连带处理：物化视图必须重刷

`semantic.fact_orders_atomic_mv` / `fact_analytics_atomic_mv` / `fact_products_atomic_mv`
都读日/周事实表 ⇒ **删了事实行不重刷视图 = 白删**（看板读到的还是旧数据）。

⚠️ **第一次尝试踩到了真问题**：直接 `REFRESH MATERIALIZED VIEW` 全部
`statement_timeout` 超时失败（连接池默认 120s，而 `fact_orders_atomic_mv`
生产实测就要 **115 秒** —— 只差 5 秒就被掐断）。

⇒ 改走仓库正主路径 `refresh_runner.execute_sql_target()`：它已封装
临时抬高超时（10 分钟预算）、MV 锁、索引补齐、MV 不存在时自愈。

### 3.5 ⚠️ 第二次踩到的真问题：刷了「报成功」但数据没变

第一次走 `execute_sql_target()` 时，**6 个目标（本地 3 + 云端 3）全部报 ok**，
复查却发现 MV 里的 daily/weekly 行**一行没少**。

**根因**：`execute_sql_target()` **自己不提交事务** —— 提交是上层
`execute_refresh_plan()` 的活（它每个目标后调 `await _commit_if_possible(db)`）。
而 PostgreSQL 的 `REFRESH MATERIALIZED VIEW` 是**事务性**的：
没提交就关会话 ⇒ 整个事务回滚 ⇒ 物化视图内容**原样保留**。

⇒ **不是仓库的 bug，是我那次探针脚本的锅**（直接调 `execute_sql_target` 而没 commit）。
⇒ 补上 `await db.commit()` 后重刷，验收通过：

| | `fact_orders_atomic_mv` | `fact_analytics_atomic_mv` | `fact_products_atomic_mv` | 正本 `semantic.fact_orders_atomic` |
|---|---|---|---|---|
| 本地 | 34883（daily/weekly **0**） | 3728（**0**） | 4761（**0**） | 只剩 monthly 34883 |
| 云端 | 37516（daily/weekly **0**） | 5418（**0**） | 5890（**0**） | 只剩 monthly 37516 |

### 3.6 ⚠️ 第三次踩到的真问题：护栏「设了环境变量」但**护不住**

护栏第一版只在 `tests/conftest.py` 顶层设 `DATA_DIR` ⇒ 主工作树实测
`new = 0`，看着是好的。**但在 worktree 里跑，又往正式目录写了 8 个文件。**

**根因**（实测 + 代码行）：
1. 仓库根 `.env` 里有 **`DATA_DIR=./data`**（相对路径 ⇒ 相对 cwd ⇒ 就是正式目录）；
2. `backend/main.py` / `run.py` 在 **import 时**就调 `load_project_env(project_root)`，
   它的 `load_dotenv(..., override=True)` 会把 `DATA_DIR` **覆盖回** `./data`
   （仓库自己的方案文档 `2026-11-07-consolidated-execution-plan.md` 就记着这条：
   「import 时 `load_project_env(override=True)` ⇒ 用例变成顺序依赖」）；
3. 再叠加 `modules/core/path_manager.py::get_data_dir()` 是 `@lru_cache(maxsize=1)`
   ⇒ 第一次调用就把 `./data` **冻住**，之后改环境变量也无效。

⇒ 护栏必须两件事都做（`tests/conftest.py`）：
* **每个用例前**（`pytest_runtest_setup`）重新写回 `DATA_DIR`
  —— 因为 `.env` 是在**收集期**（import 测试模块时）被加载的，
  `pytest_configure` 跑在收集**之前**，那时覆盖还没发生；
* 同时 `cache_clear()` 掉 `get_data_dir` / `get_data_raw_dir` /
  `get_data_processed_dir` / `get_data_input_dir` 的缓存。

⚠️ **没有**改用仓库的 `XIHONG_TEST_ENV_GUARD` 全局护栏：
那个开关会让 `backend/utils/config.py` 把 `Settings.DATABASE_URL` 强制切到
隔离库地址 —— 而**根 `tests/` 本来就是要连真实本地库**的
（`tests/test_v4_3_2_complete_system.py` 直接读 `os.getenv("DATABASE_URL")`），
开了会把它切到一个不存在的服务 ⇒ 根测试反而全红。**爆炸半径太大，不采用。**

---

## 4. 边界（不做的事）

- ❌ 不改语义层**计数口径**（`count(DISTINCT resolved_shop_id)` 保持不动；歧义仍落 `unknown`）；
- ❌ 不动**月粒度 / 快照粒度**的历史行；
- ❌ 不动**台账层**（`core.shop_accounts` / `core.shop_account_aliases`）；
- ❌ 不改候选集正本/副本口径（那是 PR #20 已落地的部分）；
- ❌ 不自动重试任何**店铺账号**的登录/验证（用户风控要求）；
- ❌ 不改 `sql/semantic/*.sql` 的**定义**（本批只做数据清理 + 视图重刷）；
- ❌ 不新增根级临时报告（本文档落 `docs/superpowers/plans/`）。

---

## 5. 验证

### 5.1 基线（改动前，`main` = `4f37dad7`）

| 范围 | 结果 |
|---|---|
| 根 `tests/` | 738 passed / 5 skipped / **0 failed** |
| `backend/tests/` | 5664 passed / 8 skipped / **0 failed** |

### 5.2 本批新增守卫

| 文件 | 条数 | 结果 |
|---|---|---|
| `backend/tests/test_collection_task_status_ssot_contract.py` | 24 | 全绿 |
| `tests/test_collection_data_dir_guard_contract.py` | 7 | 全绿 |

### 5.3 真库演练（迁移）

`20261226_task_center_status_constraint` 在**本地开发库**上实跑 `upgrade` → `downgrade`：

* 升级前：`manual_intervention_required` 写入 → **被拒**（复现 bug）；
* 升级后：13 个状态全部可写；`bogus_status` 仍被拒（约束没被放开成 unrestricted）；
* 降级后：约束**逐字恢复**成迁移前的定义。

### 5.4 护栏实测

主工作树跑 `tests/test_executor_v2.py`：
* 修复前：每次必写 **8 个文件**进 `data/raw/2026/`；
* 修复后：**new = 0**（一个都不写），且会话自检正确告警出历史遗留的极小文件。

### 5.5 污染清理

按「无入库记录 + <64 字节 + 内容含 `fake-export`」三条**同时**满足才删：
删 **176** 个；保留「孤儿但大小正常」663 个 + 已登记 487 个
⇒ 清理后 `data/raw` 里 <64 字节的文件 **0 个**。

### 5.6 格式

`black==25.1.0` 侧校验通过（本地 3.13 + CI 侧 3.11 复验）。
断言消息按 **3.11 侧**排版（不用 `assert 条件, (消息)` 的括号换行写法）。

---

## 6. 后续（不在本批）

- **C1 失败隔离**：`_process_run` 的任务循环里，`await self._execute_task(...)`
  **没有** try/except 包裹 ⇒ 单个任务抛 `CancelledError` 之类异常会跳出整轮，
  剩下的店铺**不再执行**。（任务级的普通异常已被 `_execute_collection_task_background_v2`
  内部的 `except Exception` 捕获，所以日常失败不会拖垮整轮 —— 但取消/超时类异常仍会。）
  ⇒ 建议单独一批：给任务循环加 per-task 兜底。
- **C2 人工验证续跑**：现在的 `resume` 依赖 **Redis + 执行器仍在同一 page 内等待**
  （`VERIFICATION_WAIT_TIMEOUT=300` 秒）⇒ 超时后浏览器已关，**只能重跑，不能续跑**。
  这是「等待窗口」的设计，不是 bug；要改成「可续跑」需要改成断点续采（重成本）。
- **采集无自动运行机制**：14 个配置 `schedule_enabled=false`，调度器在跑但没注册
  任何采集任务 ⇒ 新鲜度全靠人记得点。（配置/运维决策，非代码缺陷。）
- **粒度级开关有风控陷阱**：daily 档覆盖 6 个配置（含 5 个店铺采集），
  打开 = 每天 07:00 全店登录 ⇒ 必须改用「按配置设 cron」。
