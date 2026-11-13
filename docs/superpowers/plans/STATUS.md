# Plans Status Index

> **本文件是「当前状态索引」，不是历史流水账。**
>
> - 已完结批次的实施记录已整体归档到
>   `docs/superpowers/plans/archive/STATUS-2026-11-13-full-history.md`
>   （1,659 行 / 27 个章节，**逐字节保留、零删改**）。
> - 本文件只保留三样东西：**当前未结表**、**仍被外部引用因而必须留着的章节**、
>   **进行中的批次**。
> - 瘦身规则与守护见文末「台账瘦身约定」节；
>   守护文件 `backend/tests/test_status_index_slim_contract.py`（进 CI 根契约清单）。
>
> 律 1：真源只能一个，而且必须写在纸上 —— 下面每一行都指向真正的真源文件。

## 当前未结

| # | 事项 | 性质 | 状态 / 解除条件 | 真源 |
|---|---|---|---|---|
| 1 | 生产机 `/opt/xihong_erp/.env.production.passwords.txt` 旧密钥副本待删 | 生产写操作 | 待拍板：须走发版流程或人工执行 | 归档文件「安全发现」节 |
| 2 | 旧 `SECRET_KEY` / `JWT_SECRET_KEY` / `METABASE_API_KEY` 在**已下线旧环境**是否还活着 | 需业务确认 | 待确认（本次只比对了生产与本机） | 归档文件「安全发现」节 |
| 3 | 5 项业务口径待拍板：`3c店` 冲突取舍 / 两个 disabled 主账号是否启用 / TikTok 三店改名归属（含疑似历史误录 `TK新加坡1店`）/ `platform='验证码测试账号'` 脏行处理 / 10 个文件命中已停用账号 `shopee_sg_chenewei666_local` 是否回填 | 业务口径 | 待拍板 | 归档文件「批次 A / B / C」节 |
| 4 | 账号设备身份 SSOT 收口：**代码与规范已落地**（方向修订后 9 张卡全部完成）；**剩资源缺口 G1**（库里代理 0 条 ⇒ 账号仍共用出口 IP） | 资源缺口 | 待采购代理资源并写入主账号 `extra_config['proxy']`；G2–G8 见本文件「已知缺口」表 | `docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure.md` + `...-closure-execution.md` |
| 5 | `modules/apps/web_interface_manager` 健康检查持续失败（依赖的 `frontend_streamlit` 目录不存在） | 真实缺陷 | 批次 F-1 揭露；待修（本批未擅自改业务代码） | 本文件「批次 F」节 |
| 6 | `mypy` 目前**没有任何门禁**（440 条动态 ORM 基类误报需先分层/豁免才可能升门禁） | 加固方向 | 待拍板 | 本文件「批次 F」节 |
| 7 | 采集组件 lint 仍是告警模式（范围已收窄，强度未提升） | 加固方向 | 待拍板 | 本文件「批次 F」节 |
| 8 | 覆盖缺口两项：① legacy `modules/apps/{account_manager,collection_center}/contract_tests.py` 不再由 CI 执行；② **`backend/tests/` 下的 async 用例不能混进 CI 根契约清单**（CI 钉 `pytest==7.4.3` / `pytest-asyncio==0.21.1`，而 `backend/tests/conftest.py` 覆盖了 session 级 `event_loop`（1.x 忽略它）⇒ 混跑时排在 `test_celery_dispatch_event_loop_isolation.py` 之后的 async 用例拿到**已关闭**的循环，报 `RuntimeError: Event loop is closed`） | 覆盖缺口 | ①待决定是否把断言迁进 pytest；②本轮**已规避**（契约断言放进纯同步的 `tests/test_account_proxy_source_contract.py`），**根因未修** ⇒ 记账到 V2（统一事件循环策略，或 CI 升 pytest-asyncio 1.x 并同步改 conftest） | 本文件「批次 F」节 + `tests/test_account_proxy_source_contract.py` 文件头 |
| 9 | **221 个守护从不主动执行**（C 类：不在任何 CI 清单、也没有被别的文件引用 ⇒ 只在有人恰好改了该文件时才跑） | 覆盖缺口 | 待拍板是否分批提升进 CI 清单（会拉长流水线，属加固方向） | 本文件「批次 F」节 |
| 10 | `CHANGELOG.md:952` 写「新增三个 CI 坑」，原标题写「两个」（内容确实是 3 条） | 文档不一致 | 已在本文件修正标题；**已发布的 CHANGELOG 不改** | 本文件「新增三个 CI 坑」节 |

**已关闭、不再是未结项**（留一行指针，避免又被当成待办）：

- 店铺账号密码轮换 —— Walter 决定**不轮换**（取证结论不变，但是否轮换是业务负责人的决定）⇒ 关闭。
- `git filter-repo` 历史清理 —— 按约定**不做**（会作废全部已发布 tag，含 `v7.24.0`）。

---

## 已知未落地项

（2026-11-11 复核新增，**必须留档** —— `CHANGELOG.md` 有两处引用本章节）

### 律 3（派生层口径收回）在**库里**还没真正生效

- **仓库侧已到位**：PR #11 把物化副本 `sql/semantic/shop_identity_resolution_candidates_v2_mv.sql`
  改成 `SELECT <8 列显式清单> FROM semantic.shop_identity_resolution_candidates`（不用 `SELECT *`），
  并同步改了 `current_migrations/versions/20261105_create_identity_candidates_mv.py`
  ⇒ **全新库**从 baseline 建出来的副本就是「从正本取数」。
- **存量库没变**：本地库（15432）与云端库（15433）的 `semantic.shop_identity_resolution_candidates_v2_mv`
  **仍是旧定义**（自带 4 路 UNION、独立算）——
  实测 `pg_get_viewdef` 两端都是 3 个 `UNION`、都不引用正本视图。
  原因：**改迁移文件不会重跑已应用的迁移**（两端 `core.current_schema_alembic_version`
  都已是链头 `current_schema_20261223_collection_source_identifiers`），
  而 `REFRESH` 只刷数据、**不改定义** ⇒ 存量 MV 的定义不会自己变。
- **当前无功能影响**（已实测）：两端正本与副本都 **72 行**，本地实测内容指纹
  `md5 = cf586d9c8e27911ed762855025a1b57b` **完全一致** ⇒ 报表口径今天是对的。
- **为什么本轮不做**：要让存量库也改成「从正本取数」，只能 **DROP + CREATE** 副本；
  而该副本下游挂着 `semantic.fact_orders_atomic` / `fact_analytics_atomic` / `semantic.shop_identity_resolver`
  （都是 `LANGUAGE sql`，**依赖被跟踪**）⇒ 不带连带删除的重建会**直接失败**；
  带连带删除的重建要先把这些对象的正文临时换掉 ⇒ 那正是方案里判定的「口径变更手术」，
  方案明确要求它不在批次 2 里做（且不应在发版窗口里做）。
- **解除条件**：① 需要一个**独立维护窗口**（低峰、不带其他业务变更）；
  ② 走既有的「临时换下游正文 → DROP 副本 → CREATE 新副本 → 换回下游正文 → 连带刷新」路径；
  ③ 前后各跑一次正本/副本指纹比对，**必须仍然一致**（72 行 / 同 md5）；
  ④ 全程**不碰历史事实行**（`b_class.fact_*` 行数与 `data_hash` 必须不变）。

### 业务语言决策版（2026-11-11）

- Plan: `docs/superpowers/plans/2026-11-11-shop-identity-business-plan.md`
- 定位：同一方案的**决策人视角**（业务语言，零代码术语）。技术口径仍以
  `2026-11-10-shop-identity-future-proofing-and-observability.md` 为准。
- 内容：10 项问题单逐项业务结论 + **4 个复核新发现**（含「身份唯一台账从未被成文声明」
  与「输出键口径仍是平台编号优先」两处裂缝）、「历史不修」边界判定、
  三步走（堵口子 → 对齐台账 → 装雷达）、两条硬性时序、风险与回滚、
  **两项待业务拍板**（采集范围口径 / 告警通道）、业务口径验收清单。

---

## 新增三个 CI 坑

（2026-11-11 踩到，均非当次方案引入 —— `CHANGELOG.md` 有一处引用本章节）

1. **`Detect changed Python files` 在「run 期间 base 分支前进」时会失败。**
   `actions/checkout` 给 PR 检出的 `refs/pull/N/merge` 是用**事件发生时的 base tip** 生成的；
   而 `scripts/ci_changed_python_files.py:43-44` 会再 `git fetch origin <base> --depth=1` 拿**当前**的 base tip。
   两者不是同一个 commit ⇒ shallow 仓库里 `merge-base` 算不出来 ⇒ 脚本报 `CalledProcessError` ⇒ 整个 job 挂。
   实测：PR #3 合并进 main 的**第 19 秒**启动的 run 就撞上了这个坑。
   ⇒ **对策**：把 PR 分支 rebase 到**最新** main 再推（让 merge ref 与 fetch 的 base 一致），
   或至少在 base 前进后推一个新 commit 触发全新 run。
2. **`Safety diff gate` 可能报「PR 引入了新漏洞」而实际是抖动。**
   该门禁用 base 与 head 两份 `safety check` 报告做差集；PR 未改任何 requirements 文件时，
   两份报告本应完全一致。实测 PR #8 出现 `head=81 base=77 new=4`（black / pyjwt / starlette），
   而 `git diff <head> <base> -- requirements*.txt` **为空** ⇒ 是 safety 解析依赖时的非确定性抖动。
   ⇒ **对策**：同样靠 rebase 到最新 main + 推新 commit 重新触发；不要 rerun。
3. **`test (3.11)` 只跑「本次改动到的测试文件」⇒ 改了生产代码但没改对应 fake 时，红了没人看见。**
   实测（2026-11-11）：批次 3.5 把僵尸 run 回收器的结果消费方式从 `result.fetchall()` 改成
   `result.mappings().all()`（SQLAlchemy 2.0 的标准用法），但
   `backend/tests/data_pipeline/test_dashboard_asset_self_lock_guardrails.py` 里的 fake 仍返回 list
   ⇒ 该守护测试直接红（`AttributeError: 'list' object has no attribute 'all'`）。
   而 PR #6 改的是 `backend/tasks/refresh_queue_tasks.py` + 新增 `backend/tests/test_refresh_queue_stale_run_reaping.py`，
   **没碰**那个文件 ⇒ CI 压根没跑到它 ⇒ **从 PR #6 合并起一直红着**（已由 PR #14 修复）。
   ⇒ **对策**：① 改结果消费方式时，**必须同步改所有用到的 fake**；
   ② 守护测试的 fake 必须**忠实于被测代码依赖的那份 API 契约**（`mappings()` 要返回带 `.all()` 的对象，不是 list）；
   ③ 发版前跑一次**全量** `backend/tests`，而不是只信 CI 的增量结果。

---

## 账号设备身份 SSOT 收口（2026-11-13 起 / 2026-11-14 方向修订后落地）

- 计划：`docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure.md` — **done**
- 执行规格：`docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure-execution.md` — **done**
  （9 张执行卡：新1 画像模块 / 新2 machine_id 隔离 / 新3 顺序注入 / 新4 并行注入 /
  新5 巡店 CDP 注入 / 新6 主账号级代理位 / 新7 规范修订 / 新8 前置体检脚本 / 新9 面板就绪可见）
- 规范真源：`docs/guides/COLLECTION_SESSION_LIFECYCLE.md` 的 **R8 及其小节**（R8.0–R8.4）

### 方向修订（重要，勿回滚成旧口径）

**原方向是错的**（2026-11-13 计划写的「让所有账号像**同一台电脑**的多个店」）。
Walter 澄清后的业务目标是：

> **不同账号 = 不同浏览器指纹 + 不同出口 IP，
> 目的就是不让电商平台发现"一台电脑管理多个账号"。**

⇒ 任何"让所有账号像同一台电脑"的方案都是**错方向**。
原方向产出的 6 个文件改动已全部 `git checkout --` 回滚，
方向错误时新建的 `modules/utils/sessions/device_profile_manifest.py` 已**可恢复删除**。
详见执行文档「回滚记录（方向纠偏）」节。

### 已落地（业务语言）

| 能力 | 落地物 | 真源 |
|---|---|---|
| 每个主账号一套**自洽**设备画像（浏览器/版本/视口/时区/语言互相匹配），账号间必然不同、账号内永久稳定；**OS 与地区锁宿主**（Playwright 改不了 `navigator.platform`，且地区必须与出口 IP 一致） | `modules/utils/sessions/account_device_profile.py`（462 行） | R8.0 / R8.2 |
| `machine_id` 按 account_id 确定性隔离（同机 6 个 profile 原本**全部相同** `11608241`） | 同上模块 `derive_machine_id` / `ensure_profile_machine_id` | R8.1 |
| 人工巡店 / 顺序采集 / 并行采集**三条路径同一套画像**；并行路径缺画像**必须 WARN** | `pwcli_native.py` / `runtime_session.py` / `executor_v2.py` | R8.3 |
| 代理权威位上移**主账号级**，巡店与采集同源；配置坏了**显式失败**不静默直连 | 3 个 loader + `pwcli_account_inventory.py` | R8.4 |
| 新增账号**前置体检**（7 项，只读） | `scripts/check_account_readiness.py`（353 行） | — |
| 巡店面板**就绪可见**：15 秒轮询、就绪徽标、白名单排除账号**显式列出并写明原因** | `modules/utils/sessions/account_readiness.py` + 面板 `/api/accounts/readiness` + 前端 | — |

### 验收（实测）

| 范围 | 结果 |
|---|---|
| `tests/test_account_device_isolation_contract.py` | **23 passed** |
| `tests/test_account_readiness_contract.py` | **11 passed** |
| 采集相关 5 个测试文件 | **174 passed** |
| 面板与运行时回归 | **76 passed** |

三份新守护**已进 CI 根契约清单**（`ci.yml` 根契约条目 57 → **60**），
`scripts/audit_guard_tests.py` 分类确认均为 **A 类（CI 硬门禁）**。

⚠️ 代理契约**刻意做成纯同步文件**（`tests/test_account_proxy_source_contract.py`）：
`backend/tests/test_account_proxy_config.py` 含 9 个 async 用例，在 CI 钉的
`pytest==7.4.3` / `pytest-asyncio==0.21.1` 下混进根契约清单会拿到**已关闭**的 session
事件循环（`RuntimeError: Event loop is closed`，2026-11-14 实测 CI run 43485663421）。
根因未修，已并入「当前未结」#8 记账到 V2。

### 已知缺口（**未结，必须留档**）

| # | 缺口 | 性质 | 解除条件 |
|---|---|---|---|
| G1 | **IP 层无资源**：库里代理配置 **0 条** ⇒ 所有账号仍共用宿主出口 IP，平台仍可用"同一出口多账号"做关联；**且画像的 locale/时区因此锁在宿主地区**（出口即宿主 IP ⇒ 地区必须跟着出口走，否则自己制造"中国 IP + 德国时区"三重矛盾） | **资源缺口**（当前最大缺口） | 采购代理资源并写入主账号 `extra_config['proxy']`；到位后再按账号放开地区维度 |
| G2 | **深度指纹未覆盖**（canvas / WebGL / 字体 / GPU / 音频栈） | 技术债 | V2 专项评估 |
| G3 | 同一主账号下多店铺**共享画像与出口** | **刻意折中**（业务已确认接受） | 写进文档，不隐藏 |
| G4 | 存量 9 个主账号 `machine_id` 仍是 `11608241` | 生效延迟 | 下次巡店/采集自动改写（幂等） |
| G5 | `profile_color_seed` 6 个相同 | 技术债 | 与 G2 一并 |
| G6 | 存量账号 ID 不合规（`hongxikeji:main` / `shopee KR` / `Tiktok 1店` / `chenzeweinbnb@163.com` / 含全角括号） | 历史事实 | 体检脚本记为 **WARN**；**不主动改名**（改名会换 profile 目录 ⇒ 换登录态） |
| G7 | 测试残留账号 `accept_main_1775126941575`、`验证码测试账号` | 数据脏 | 待业务拍板（见「当前未结」#3） |
| G8 | 旧指纹机制与 `data/device_fingerprints/` 26 文件仍在 | 已决策 | 保留给非 profile 路径，暂不清理 |

**新增账号即时自查**（不等开发）：ID 只用小写字母/数字/下划线；对照现有 6 个 profile 目录确认不撞
（尤其别写成 `shopeeKR` / `Tiktok1店` / `hongxikejimain`）；ID 不可改；platform 必须在白名单内；
店铺 `platform_shop_id` 必填；首次采集前先人工巡店一次。

### 发布证据（v7.27.0，2026-11-14）

| 项 | 证据 |
|---|---|
| tag | `v7.27.0`（附注标签，对象 `fa99bf48`）→ 提交 `cc523a97`；**双镜像 tag 对象一致**（`git ls-remote --tags`） |
| main | `e9a8eecc`；**双镜像 main SHA 一致** |
| 部署流水线 | `Deploy to Production` run 43484496122 —— Tag Release 13m50s，全部步骤 ✓ |
| CI 流水线 | run 43487329740 **success**（中间两次红：43484395368 black+bandit、43485663421 根契约事件循环污染，均已修） |
| 生产镜像 | `xihong_erp_backend_api` / `frontend` / `celery_worker` / `celery_beat` 全部 **v7.27.0** 且 healthy |
| 版本号 | `GET /healthz/ready` → `{"status":"ready","version":"v7.27.0","database":"connected","dashboard":"ready"}` |
| 公网 | `http://www.xihong.site` 200；`/healthz/ready` 200 且 version=v7.27.0 |
| 迁移 | 迁移前备份已建并校验（pg_restore --list）；`Current-schema migration action completed: upgrade`；**schema gate 通过**（`up_to_date`，current == head == `current_schema_20261229_template_format_signature`，缺表/缺列均为空） |
| 视图重建 | 成功 39 个 / 失败 0 个，自愈重建物化视图 1 个 |
| nginx | 部署后 error log 仅 restart notice/warn，**无 5xx** |
| 生产库 | postgres / redis 容器未重启（Up 4 days）⇒ 本次**无生产写操作** |

> ⚠️ **tag 未移动**：v7.27.0 指向 `cc523a97`（含 black/bandit 未修的原始提交），
> 后两个提交 `a077f7cf`（black+bandit）与 `e9a8eecc`（根契约清单）是**主干**上的修复。
> 按双镜像纪律，已发布的 tag 永不回填/重写；
> 两次提交都只改排版与测试文件组织方式，**运行时行为完全相同**
> （MD5/SHA1 摘要值不变 ⇒ 已分配的设备画像与线上完全一致，无画像漂移）。


---

## 批次 F：减重批（2026-11-13）

**方向（Walter 拍板）**：做减重批 —— 关告警门禁 + 台账瘦身 + 守护分类。
**本批只做减法**：不擅自把只告警步骤升成硬门禁（升门禁属加固方向，另记待办由 Walter 决定）。

**起因**：Walter 问「我们是不是越做越重了」。实测下来确实如此 —— CI 的 `test` job 里有
45 个硬门禁 + 14 个「只告警」步骤（`continue-on-error: true` 或命令自带 `|| true` / `|| echo`
⇒ **无论成败都不改变流水线结果**）；守卫/契约类测试文件 258 个（占测试文件 30%、39,166 行）；
本台账 1,659 行、27 个章节。

### F-1：关掉 6 个纯噪音步骤 + 收窄采集组件 lint（已落地，提交 `cb953b59`）

逐个**实测**过的处置依据（不是推断）：

| 被移除的只告警步骤 | 实测结论 |
|---|---|
| `Type checking (critical modules only)` | `mypy modules/core/` 实测 440 errors / 13 个文件，全部是动态 ORM 基类误报（`Invalid base class Base`）；命令自带 `\|\| true`，从不让流水线红 |
| `Database Design Rules Validation` | `scripts/validate_code_compliance.py` 是空壳：只打印一段说明文字，退出码 0，不做任何实际检查 |
| `Run contract tests` | legacy `contract_tests.py` 三选一循环：`web_interface_manager` 持续失败（依赖已不存在的 `frontend_streamlit`），失败被 `\|\| echo` 吞掉 |
| `Run unified health check` | 自报「健康检查失败的应用: `['web_interface_manager']`」却仍然报通过 —— 既不挡错，又制造「检查过了」的错觉 |
| `Check for known vulnerabilities` | `safety check` 上游已废弃（CI 自己的注释就写着 deprecated），输出被 `continue-on-error` 吞掉 |
| `Check for large files` | 命中的 65 个大文件全在本地产物目录（`backups/` `temp/` `docker_volume_backup/` `.playwright-mcp/`），**不在 git 跟踪范围** ⇒ CI 上必然 0 命中；且 `find` 的输出被 `while` 吞成 echo，退出码恒为 0 |

**明确保留**（减重 ≠ 放松）：

- 真硬门禁：`Check for secrets in code` / `Safety diff gate (PR only, fail on new vulns)` /
  `Check project structure` / `Run Bandit security scan`
- 故意保留的只告警步骤：`Clean up leftover test containers`（批次 E-2 设计决定：清理失败不得掩盖真实失败）/
  `Install Playwright browsers` / `Validate configurations`

**收窄（不是删）**：`Collection component lint` 之前把「本次改动的全部 Python 文件」喂给
采集组件规则 ⇒ backend/ tests/ 里的普通业务代码被套上采集组件规则，全仓报出 454 行告警，
而那些告警既不属于规则本意范围、也从不改变结果。现在改为 `--scope platforms`
（只扫 `modules/platforms/**`，路径真源在 `scripts/lint_collection_components.py`，不在 workflow 里另写一份）。
**门禁强度不变**：仍是 `--fail-on none` 告警模式。

**守护**：`backend/tests/test_ci_weight_reduction_contract.py`（已进 CI 根契约清单）
—— 锁住「6 个噪音步骤不许再回来」「真硬门禁不许被顺手删」「lint 范围必须收窄且强度不变」
「书面记录必须逐条齐全」「这份守护自己必须在 CI 清单里」。

### F-1 顺带揭露的真实缺陷（不再被 `|| echo` 吞掉）

`modules/apps/web_interface_manager` 的健康检查**持续失败** —— 它依赖的
`frontend_streamlit` 目录**不存在**。原先这个失败被 CI 的 `|| echo` 吞掉，
现在浮出水面。⇒ **待修**（不在本批范围，未擅自改业务代码）。

### F-1 留下的待办（加固方向，待 Walter 拍板）

- `mypy` 类型检查目前**没有任何门禁**（440 条误报需要先分层/豁免才可能升门禁）。
- 采集组件 lint 仍是告警模式（`--fail-on none`），范围已收窄但**强度未提升**。
- legacy `modules/apps/{account_manager,collection_center}/contract_tests.py` 不再由 CI 执行
  （其断言与 pytest 套件部分重叠）；若要保留这层覆盖，需把断言迁进 pytest。

### F-2：台账瘦身（已落地，提交 `8d2d75d5`）

本文件由 **1,659 行 / 27 个章节** 瘦身到 **约 250 行**，历史整体归档到
`docs/superpowers/plans/archive/STATUS-2026-11-13-full-history.md`（逐字节保留，零删改）。

- **就地瘦身，路径不变** —— `CHANGELOG.md` 有三处引用 `docs/superpowers/plans/STATUS.md`。
- **保留**：当前未结表（≤10 行）、`已知未落地项`、`新增三个 CI 坑`（CHANGELOG 引用，
  标题从「两个」纠正为「三个」—— 内容本来就是 3 条）、`账号设备身份 SSOT 收口`、`批次 F`、Audit。
- **归档**：23 个已完结批次的实施记录（`Project Simplification` … `批次 E`）。
- **守护**：`backend/tests/test_status_index_slim_contract.py`（进 CI 根契约清单）——
  锁住行数上限（≤400）、未结表行数上限（≤10）、归档完整性（逐条含 23 个章节标题 +
  保留原文首尾）、**同一段历史只能有一处真源**（归档过的标题不许再回到本文件）。

### F-3：守护分类 + 重复簇聚类 + 合并最大一簇（已落地，提交 `974901d9`）

**为什么做**：259 个守护里，没有一份清单说明「哪些每次 CI 都跑、哪些只在被改动时才跑」。

**可复跑的审计脚本**：`scripts/audit_guard_tests.py`（1.5 秒，口径真源在脚本里）

- 判定口径：文件名含 `_contract` / `_guard` / `_guardrails` / `_invariant` / `_policy` /
  `_hygiene` / `_rule` / `_ssot` / `_gate` 任一标记
- 实测：全部测试文件 **839**、守护/契约类 **259（30.9%）**
- **A 类（CI 会主动跑）：24**
- **B 类（被其它文件引用，会连带跑）：14**
- **C 类（无引用，只在被改动时跑）：221（85%）**

⇒ **C 类的 221 个是最该记住的数字**：它们「守着一条规则，但从不被主动执行」——
与 2026-11-13 清理脚本事故**同款形状**（东西在仓库里、守护也在，但没人调用它）。

**重复簇**：按 AST 形状（函数角色 + 断言/glob/read 的存在性）聚类，≥5 个成员的簇有 **9 个**
（最大一簇 22 个文件，最小的 5 个）。完整清单跑 `python scripts/audit_guard_tests.py` 即可复现。

**已合并一簇（零争议、可验证）**：11 个同构 `timestamp_defaults` 守护 → 1 个参数化文件。

| 项 | 合并前 | 合并后 |
|---|---|---|
| 文件数 | 11 | 1 |
| 用例数 | 23 | 23（等价） |
| 断言组数 | 97 | 97（等价） |

- **逐条等价核对**：用 AST 解析原 11 个文件，逐个比对 glob / 断言组 / **顺序** / extra 用例 ⇒
  全部一致（`must` + `any_of` 两种形态，`public_system` 的「created_at 或 updated_at」
  保持原位置）。
- **红侧两轮验证**：① 临时改名 `migrations/versions/20260415_c_class_timestamp_defaults.py`
  ⇒ 3 条变红；② 临时抽掉迁移里的 `SET DEFAULT now()` ⇒ 1 条变红、报错精确点名。
- 旧 11 个文件已删；**合并锁**在 `backend/tests/test_guard_test_classification_contract.py` 里
  （旧文件复活 = 同一份规则维护两遍）。
- 形态不同的 `test_field_mapping_template_timestamp_defaults_migration_contract.py`
  （220 行 / 5 用例，要连真库）**原样保留**。
- **净增覆盖**：合并后的文件**加进了 CI 根契约清单** —— 原先那 11 个旧守护**都不在**任何
  CI 清单里（只在被改动时才跑）⇒ 这次是覆盖变多，不是变少。

**本批不做（待拍板）**：221 个 C 类守护要不要分批提升进 CI 清单。提升会直接拉长流水线
（当前 test job 约 188 秒），属**加固方向**，不在本批「只做减法」的范围内。

### F-4：验收（CI 三线全绿 + 双镜像一致 + 生产未受影响）

**本地全量回归**

| 范围 | 结果 |
|---|---|
| 后端（排除 data_pipeline / archive） | **4697 passed / 7 skipped**（247.60s） |
| `backend/tests/data_pipeline` | **1274 passed / 1 skipped**（53.91s） |
| 根 `tests/` | **801 passed / 5 skipped** |
| 前端 `node --test` | **207 passed** |
| 5 个新守护文件合计 | **119 passed** |
| ruff / black / UTF-8 卫生 / 规则完整性 / 架构 SSOT | 全绿 |

**CI 三线全绿**（`974901d9`）：CI Pipeline `43467986461`（**8 个 job 全 success**）/
Validate Data Flow `43467986640` / Docker Build and Push `43467986403`。

**CI 上的决定性证据**

- 根契约清单：**593 passed / 11 skipped**（上一批是 481 passed ⇒ **+112**，
  正好等于本次新增的 4 个守护文件：23 + 57 + 7 + 25）
- 「Run pytest (if test files exist)」：**119 passed**（本次改动的 5 个测试文件）
- 采集组件 lint：**「扫描范围: platforms（范围外文件 7 个已过滤）」+ error 0 / warning 0**
  ⇒ 收窄真实生效，且**没有把任何真问题过滤掉**
- `test (3.11)` 的步骤列表里**已看不到**被移除的 6 个步骤 ⇒ 移除确实落地

**双镜像**：`git ls-remote` 权威核对 —— GitHub(SSH-443) / CNB(HTTPS) / 本地
**三处同为 `974901d9`**；`v7.26.0` tag 两端仍是同一对象 `009a2867` → commit `05a359a1`，
**未被回填**。

**生产未受影响**：本批是测试/工具层改动，**不打 tag、不发版** ⇒ 不触发部署。
`/api/healthz/ready` → HTTP 200、`version=v7.26.0`、`database=connected`、
`dashboard=ready`、`runtime_mode=production`（与部署前一致）。

**一处如实说明**：`scripts/sync_main_mirrors.ps1` 的「工作树必须干净」守卫**跑不起来** ——
工作树里有**另一条工作流**的未跟踪文件
（`docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure.md`，
不是本批产物，**未动**）。已手工复核该脚本要检查的每一项，全部通过：
分支 = `main`；无 `MERGE_HEAD`；**无任何已跟踪文件改动**（唯一脏项是那个未跟踪文件）；
本地 `main` 与两端同 SHA、无分叉。

---

## 台账瘦身约定

1. **STATUS.md 只放「当前状态」，不放历史流水账。**
   一个批次完结 ⇒ 它的实施记录整体进 `docs/superpowers/plans/archive/`，
   本文件只留一行指针（通常在「当前未结」表里，或干脆不留）。
2. **未完结 ≠ 永远挂着。** 「当前未结」表上限 10 行；超过就把已完结项移进归档。
3. **归档必须逐字节保留。** 归档文件 = 原文副本 + 一段说明头；不许「顺手重写」「提炼摘要」。
   （律 1：真源只能一个 —— 摘要是第二份真源。）
4. **外部引用必须仍然可达。** `CHANGELOG.md` 引用到的章节名不许改名、不许移走。
5. **瘦身由守护锁住**，不许靠自觉：
   `backend/tests/test_status_index_slim_contract.py`（进 CI 根契约清单）。

## Audit

- The completion state above reflects the work merged into `main` (latest closure commit around 2026-05-06).
- Parallel/specialized tracks should keep their own plan documents and be referenced from here when they are merged.
- Plans closure audit (documentation-only): `docs/superpowers/findings/2026-05-06-plans-closure-audit.md`
