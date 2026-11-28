# Plans Status Index

> **本文件是「当前状态索引」，不是历史流水账。**
>
> - 已完结批次的实施记录已整体归档到
>   `docs/superpowers/plans/archive/STATUS-2026-11-13-full-history.md`
>   （原始 1,659 行 / 27 个章节，**逐字节保留、零删改**；此后完结批次的发布证据
>   也按批次追加进同一份归档，STATUS.md 只留**最新一次**发布）。
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
| 3 | 4 项业务口径待拍板：`3c店` 冲突取舍 / **一个** disabled 主账号（`虾皮巴西（东朗照明主体）`，`enabled=false`）是否启用 / TikTok 三店改名归属（含疑似历史误录 `TK新加坡1店`）/ 10 个文件命中已停用账号 `shopee_sg_chenewei666_local` 是否回填 | 业务口径 | 待拍板（**原 5 项里的 `platform='验证码测试账号'` 脏行已于 2026-11-14 随迁移删除**）；**另记**：生产有 **26 条 `enabled=false` 的店铺行**挂在 3 个**启用中**的主账号下（越南 / 智利 / 秘鲁 / 泰国等站点）—— 采集侧两层都按 `enabled` 过滤 ⇒ 不会被采，但历史事实需留档 | 归档文件「批次 A / B / C」节 |
| 4 | 账号浏览器环境 SSOT 收口：**代码与规范已落地**（2026-11-14 二次方向修订：不造账号差异 + 去 `HeadlessChrome` + locale/时区跟出口）；**剩资源缺口 G1**（库里代理 0 条 ⇒ 账号仍共用出口 IP） | 资源缺口 | 待采购代理资源并写入主账号 `extra_config['proxy']`；G2–G8 见本文件「已知缺口」表 | `docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure.md` + `...-closure-execution.md` |
| 5 | `modules/apps/web_interface_manager` 健康检查持续失败（依赖的 `frontend_streamlit` 目录不存在） | 真实缺陷 | 批次 F-1 揭露；待修（本批未擅自改业务代码） | 本文件「批次 F」节 |
| 6 | `mypy` 目前**没有任何门禁**（440 条动态 ORM 基类误报需先分层/豁免才可能升门禁） | 加固方向 | 待拍板 | 本文件「批次 F」节 |
| 7 | 采集组件 lint 仍是告警模式（范围已收窄，强度未提升） | 加固方向 | 待拍板 | 本文件「批次 F」节 |
| 8 | 覆盖缺口两项：① legacy `modules/apps/{account_manager,collection_center}/contract_tests.py` 不再由 CI 执行；② **`backend/tests/` 下的 async 用例不能混进 CI 根契约清单**（CI 钉 `pytest==7.4.3` / `pytest-asyncio==0.21.1`，而 `backend/tests/conftest.py` 覆盖了 session 级 `event_loop`（1.x 忽略它）⇒ 混跑时排在 `test_celery_dispatch_event_loop_isolation.py` 之后的 async 用例拿到**已关闭**的循环，报 `RuntimeError: Event loop is closed`） | 覆盖缺口 | ①待决定是否把断言迁进 pytest；②本轮**已规避**（契约断言放进纯同步的 `tests/test_account_proxy_source_contract.py`），**根因未修** ⇒ 记账到 V2（统一事件循环策略，或 CI 升 pytest-asyncio 1.x 并同步改 conftest） | 本文件「批次 F」节 + `tests/test_account_proxy_source_contract.py` 文件头 |
| 9 | **221 个守护从不主动执行**（C 类：不在任何 CI 清单、也没有被别的文件引用 ⇒ 只在有人恰好改了该文件时才跑） | 覆盖缺口 | 待拍板是否分批提升进 CI 清单（会拉长流水线，属加固方向） | 本文件「批次 F」节 |
| 10 | **商品中心录数缺口（v7.31.x 遗留 + 批次 6/7/8 新口径）**：① 飞书三张状态镜像表 `table_id` 全 NULL，且生产 `FEISHU_PRODUCT_BASE_TOKEN` 未设 ⇒ 商品镜像投影投不出去（**2026-11-22 实测 112 条长期 pending**，最早可追到 2026-09-17、`attempt_count` 全为 0 ⇒ 从未投递）；② ~~生产 `finance.delivery_rate_rules` 0 行~~ ⇒ **已由批次 7 的迁移 `20261238` 解决**（生产 5 行 = shopee/SG-01/T01–T05，20.93/25.31/27.97/38.59/62.44 元，链头 `20261238`），**但 TikTok SG 仍只有 T02 一档**（生产 0 行 ⇒ 本地那档 14.84 元的官方出处也待确认）；③ 生产各平台 `delivery_cost_rate` 仍空 ⇒ 尾程不进成本底线（重算前置：SKU 段归类 + 订单级/单件摊口径钉死）；④ 生产 1122 个 SKU 重量段全空（**批次 6 已删除 `weight_kg`**）⇒ 发版后尾程落最轻档并标 `estimated`；⑤ 批次 6 的**包邮开关**需业务逐 SKU 勾选（默认不包邮）；⑥ 汇率 5.2077 待业务认可（生产汇率表仍是 5.2）；⑦ **残差桶**（`other_cost_rate`）仍是 1 月实测值 ⇒ 官方 2026-01/04 两次调涨后偏低约 1.1pt，待新实测重算；⑧ TikTok SG 尾程价目表未提供（现仅 1 档 T02） | 业务录数 / 配置 | 待业务录数：① 飞书后台建好三张镜像表并回填配置；②⑤ 在「定价设置」/「平台 SKU 利润测算」维护；④ 按实物批量归类重量段；⑥ 汇率更新授权；⑦ 提供 TikTok 价目表 | `CHANGELOG.md` v7.31.1 节 + 计划文档 §8.3、§9、§9.10 |

**已关闭、不再是未结项**（留一行指针，避免又被当成待办）：

- 店铺账号密码轮换 —— Walter 决定**不轮换**；`git filter-repo` 历史清理 —— 按约定**不做**（会作废全部已发布 tag，含 `v7.24.0`）⇒ 均关闭。
- `CHANGELOG.md:952`「新增三个 CI 坑」标题笔误 —— 已在本文件修正标题（**已发布的 CHANGELOG 不改**）⇒ 关闭。

## 上一发布：v7.40.0（2026-11-26）

- **人力管理页假报错修复 + 归属「角色」退休 + 批量能力**。
  - 假报错根因：2026-11-20 的重构（`dd04894e`，员工管理拆独立组件）把 `loadEmployees`
    搬进子组件 `EmployeeTab.vue`，父容器 `HumanResources.vue` 忘了删那一行调用
    ⇒ 运行时 `ReferenceError` ⇒ 弹「加载数据失败，请刷新重试」；**数据其实全部加载成功**
    （生产只读核验：报错时刻 HR 接口全部 200）。
  - **归属「角色」整条退休**（业务拍板）：现实是一家店可有主管 + 多个总经理 + 操作员同时吃提成，
    「主管/操作员」二分法装不下；该字段早已是遗留（看板分摊前端已不消费；唯一还活着的
    「每月成本录入任务派给店主管」自 2026-06-18 起已静默停摆）⇒ 连同该任务链路一并删除。
    层级改显示员工档案的**职位名**（只读、不落库、不勾选）。
    ⚠️ **访问权限角色体系（admin/manager/operator/finance）一行未动**，只是中文名撞车。
  - **批量能力**：批量挂靠 / 批量调整比例 / 批量移除 + 批量保存改并行汇总（失败不中断）；
    后端新增 `POST /hr/employee-shop-assignments/batch`（单事务、逐项成败、逐店比例上限校验）。
  - **门禁补强**：`ci.yml` 新增「人力域 lint（显式 `no-undef`）」+「前端测试全量」两步
    （此前前端测试从未在 CI 里跑过）；新增 3 条契约守护 + 6 个功能守护。
  - **迁移**：`current_schema_20261244_drop_employee_shop_assignment_role`（删两列，可降级）；
    生产归属表 0 行、绩效快照表 0 行、`role` 列可空 ⇒ 零数据损失。
  - **口径零改动**：提成仍是「可分配利润 × 归属提成比」零系数，**工资单金额不受影响**。
  - 计划与实施记录：`docs/superpowers/plans/2026-11-26-hr-assignment-role-retirement-and-batch-operations.md`。
  - ⚠️ **仍需业务侧补录**：11 名员工仅 1 人有岗位 ⇒ 需给负责人挂 SUPV 主管岗位（职位表现成 10 个职位够用）。
  - **已发版并部署生产**（2026-11-26）：流水线 run `45832287245` 全绿（数据流发布门禁 ✓ 1m28s /
    镜像构建推送 ✓ 5m14s / 生产部署 ✓ 11m7s）；tag `v7.40.0` 双镜像同对象 `b854ea31`（未回填）。
    生产实测：应用容器全部 **v7.40.0**、7 容器 healthy（批次 `20261126_215446`）；
    外网 `/api/healthz/ready` = ready / **v7.40.0** / database=connected / dashboard=ready；
    **迁移已应用**（归属表 `role` 列已不存在）；生产镜像内部确认 schema 无 `role`、两个派发函数已不存在、
    任务策略只剩 `performance_confirmation`、批量路由已注册；生产前端产物 `loadEmployees` / `supervisor`
    **零命中**；归属表 0 行、`monthly_cost_entry` 任务未新增；部署后 nginx 最近 3000 条日志 **0 个 5xx**。
    ⚠️ 未做浏览器登录态验收（需业务账号）：业务侧登录后确认人力管理页不再弹「加载数据失败」，并重配归属。

## 最新发布：v7.41.0（2026-11-29）

- **费用管理页 + 人员店铺归属页数据密度改造**（用户侧「备注」字段同时退役）。
  - **密度 SSOT 真正进构建**：密度三档规则原寄居 `frontend/src/assets/erp-layout.css`，
    而该文件**从未被任何入口 import** ⇒ 页面写上 `erp-compact` 也只是挂了个类名，
    实测 td 内边距仍是默认 8px、行高 41px、字号 14px ⇒ **一条密度规则都没命中**。
    现独立成 `frontend/src/assets/erp-density.css` 并由 `main.js` 全局引入；
    规则全部被三个密度类闸住，未声明密度类的页面**零影响**（抽查库存/目标/用户页均 `compact:false`）。
  - **真机实测行高**：费用页 33–44px（均值 38，原 ~50）、表头 33px、7 张指标卡一行排完；
    归属页 34–44px（均值 38，原 ~110）、表头 38px、成本明细压成一行摘要 + tooltip。
  - **「+ 添加人员」入口移到固定左侧的店铺列**：人员列在横向滚动区之外（表宽 2446px > 视口），
    入口原先落在滚动区里，整行看起来是空的。
  - **用户侧「备注」字段退役**：`operating_costs.remark` 实测 233 行里 113 行有值、**全是批次标记**、
    人工录入 0 条、附件 0 行 ⇒ UI 列删除、DB 列保留转系统所有（后端不再用客户端 `note` 覆盖它）；
    普通保存命中软删行返回 400（复活只走 `/restore`）。
  - **费用口径优化（同批合并）**：店铺范围口径 + 分摊维度接口化；
    占位行软删迁移 `current_schema_20261246_cleanup_expense_placeholder_rows`（113 行，可降级）。
  - **门禁补强**：新增 `erpDensityContract.test.mjs`（10 例）+ `shopAssignmentDensity.test.mjs`（7 例），
    其中「密度文件必须被 main.js 引入」「规则只有一份出处」两条专门挡「规范进不了构建」；
    新增真机测量脚本 `frontend/scripts/erpDensityMeasure.mjs`（会话在 httpOnly cookie 里）。
  - **台账瘦身**：本次把已完结段落整体归档，STATUS.md 回到 400 行上限内
    （CI 根契约清单里那条守护此前是红的）。
  - **回滚** = 重新部署上一个 tag（v7.40.0）+ 执行降级迁移；
    费用数据的软删按批次标记精确还原。
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

### 人力资源 + 用户管理模块优化（2026-11-20 **已落地 v7.35.1，已部署生产并验收通过**）

- Plan: `docs/superpowers/plans/2026-11-19-hr-user-management-optimization.md`
- 实施记录 + 发布证据 + 部署后验收：已归档到 `docs/superpowers/plans/archive/STATUS-2026-11-13-full-history.md` 的「发布证据（v7.35.0 + v7.35.1，2026-11-19 ~ 11-20）· 批次 10」段。
- **仍待业务侧补录（未结）**：11 名员工入职日期、2 名离职员工离职日期、张三最后发薪月；**人员店铺归属 0 行**须在「人员店铺归属」页面重配，否则工资单确认链路仍会 409 —— 第五批无法由代码闭环。

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

### 二次方向修订（2026-11-14，**实测证伪了"按账号派生指纹"**）

Walter 实际用了巡店面板后追问："既然硬件指纹改不了，那其他修改是不是都没必要了？"
本机实测给出三个结论，**直接推翻了"每个账号一套指纹"的实现路径**：

| 实测 | 结论 |
|---|---|
| 同一台机器开两个**独立 profile**，14 项指纹（canvas / WebGL 像素 / 字体集合 / UA / platform / 核数 / 内存 / 屏幕 / 时区 / 语言 / 插件 …）**完全相同**；同一 profile 重开则稳定 | **独立 profile 不产生任何指纹隔离** —— 它隔开的是**账号状态层**（cookie / localStorage / 缓存 / 登录态 / 平台设备令牌） |
| 同型号同配置的电脑，硬件指纹**大量重复**（全球几百万台） | 硬件指纹是**群体特征**不是个体特征 ⇒ 平台**不会**拿"指纹相同"判"同一台电脑"（否则误杀几百万正常卖家） |
| 网页 JS 读得到 UA / platform / 核数 / 内存 / 语言 / 屏幕 / 时区 / WebGL 渲染器 / 插件，但**读不到** `machine_id` / `client_id` / `guid` | `machine_id` **平台看不见** ⇒ 改它对电商平台零价值；且 `Local State` 由 Chromium **首次启动时**创建 ⇒ 每个账号第一次巡店必然漏改 |

⇒ 修订后的口径：**账号之间只隔离「状态」，不造「指纹差异」。**
真正能分开账号的是 **① 每个账号独立 profile（状态层）** + **② 不同出口 IP**；
软件层只负责**不露馅**（去 `HeadlessChrome`）与**跟出口自洽**（locale / 时区）。
主动差异化（每人一个分辨率 / 浏览器版本 / 语言）**没有关联收益**，反而造出
「分布外」的异常特征（真实用户不会 12 个账号 12 个不重复分辨率）。

### 已落地（业务语言）

| 能力 | 落地物 | 真源 |
|---|---|---|
| 浏览器运行环境**不按账号派生**：同一台机器上所有账号拿到**完全相同**的 UA / locale / 时区 | `modules/utils/sessions/account_browser_identity.py` | R8.0 |
| **不露馅**：UA 去掉 `HeadlessChrome`（采集跑 headless），版本号与 OS token 取自真实二进制、一字不动 | 同上 `browser_user_agent` / `strip_headless_marker` | R8.1 |
| **跟出口自洽**：locale / 时区 / Accept-Language 跟随出口 IP 所在地区（现在 = 宿主；代理到位后按账号查） | 同上 `region_profile` | R8.2 |
| 人工巡店 / 顺序采集 / 并行采集**三条路径同一套环境**；顺序路径沿用 profile 原生环境，并行路径视口统一 | `pwcli_native.py` / `runtime_session.py` / `executor_v2.py` | R8.3 |
| 代理权威位上移**主账号级**，巡店与采集同源；配置坏了**显式失败**不静默直连 | 3 个 loader + `pwcli_account_inventory.py` | R8.4 |
| 新增账号**前置体检**（6 项，只读：ID 规范 / 目录不撞车 / 平台白名单 / 已首登 / 已配出口 / 主账号启用状态） | `scripts/check_account_readiness.py` | — |
| 体检脚本与巡店面板**取同一批账号**（都只含启用中的）：**停用账号不再被报「请先首登」**（假警报）；但**目录撞车检查仍保留停用账号**（它的 profile 目录还在磁盘上，新号撞上照样共用登录态） | `scripts/check_account_readiness.py` + 3 条守护 | R8.4 |
| 巡店面板**就绪可见**：15 秒轮询、**2 个**徽标（已首登 / 出口）、白名单排除账号**显式列出并写明原因** | `modules/utils/sessions/account_readiness.py` + 面板 `/api/accounts/readiness` + 前端 | — |
| 面板**状态真源是浏览器进程**：窗口一关，状态立刻回写（此前只放锁、不改状态 ⇒ 永远显示 OPEN） | `scripts/pwcli_inspection_panel.py` `_watch_browser_process` | — |
| **测试残留账号已删除**（主账号 9 → 7），走迁移、生产可执行 | `current_migrations/versions/20261230_drop_residual_test_accounts.py` | — |

### 已下线

- `modules/utils/sessions/account_device_profile.py`（按账号派生画像 + `machine_id` 隔离）—— **可恢复删除**。
- `.device_profile.json` 载体与"占用校验 / 槽位顺延"机制 —— 一并不再生成（存量文件留在磁盘上，不影响运行）。
- 面板上的「画像已分配 / machine_id 已隔离 / 画像明细」三个徽标 —— 减法项，避免"没隔离 = 有风险"的假警报。

### 已知缺口（**未结，必须留档**）

| # | 缺口 | 性质 | 解除条件 |
|---|---|---|---|
| G1 | **IP 层无资源**：库里代理配置 **0 条** ⇒ 所有账号仍共用宿主出口 IP，平台仍可用"同一出口多账号"做关联；**且浏览器环境的 locale/时区因此锁在宿主地区**（出口即宿主 IP ⇒ 地区必须跟着出口走，否则自己制造"中国 IP + 德国时区"三重矛盾） | **资源缺口**（当前最大缺口） | 采购代理资源并写入主账号 `extra_config['proxy']`；到位后再按账号放开地区维度 |
| G2 | **深度指纹不覆盖**（canvas / WebGL / 字体 / GPU / 音频栈） | **刻意不做**（2026-11-14 修订） | 实测：同型号同配置机器这些值**本就完全相同**（全球几百万台）⇒ 平台不会拿它判同机；主动注入噪声反而露馅 |
| G3 | 同一主账号下多店铺**共享出口**（不再有"共享画像"这层） | **刻意折中**（业务已确认接受） | 写进文档，不隐藏 |
| G4 | `machine_id` 隔离**已整体撤销** | **已关闭**（2026-11-14） | 实测：网页读不到 `machine_id`（平台看不到）；且 `Local State` 由 Chromium 首次启动时创建 ⇒ 首次巡店必然漏改。**不再列为缺口** |
| G5 | `profile_color_seed` 6 个相同 | 技术债（属旧指纹机制） | 与 G2 一并 |
| G6 | 存量账号 ID 不合规（`hongxikeji:main` / `shopee KR` / `Tiktok 1店` / `chenzeweinbnb@163.com` / 含全角括号） | 历史事实 | 体检脚本记为 **WARN**；**不主动改名**（改名会换 profile 目录 ⇒ 换登录态） |
| G7 | 测试残留账号 `accept_main_1775126941575`、`验证码测试账号` | **已关闭**（2026-11-14） | 业务确认删除，已由迁移 `current_schema_20261230_drop_residual_test_accounts` 删除（主账号 9 → 7） |
| G8 | 旧指纹机制与 `data/device_fingerprints/` 26 文件仍在 | 已决策 | 保留给非 profile 路径，暂不清理 |

**新增账号即时自查**（不等开发）：ID 只用小写字母/数字/下划线；对照现有 6 个 profile 目录确认不撞
（尤其别写成 `shopeeKR` / `Tiktok1店` / `hongxikejimain`）；ID 不可改；platform 必须在白名单内；
店铺 `platform_shop_id` 必填；首次采集前先人工巡店一次。

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

F-4 的实施与验收记录已整体移入 `docs/superpowers/plans/archive/STATUS-2026-11-13-full-history.md`
（逐字节保留、零删改）⇒ 本节只留指针。

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
