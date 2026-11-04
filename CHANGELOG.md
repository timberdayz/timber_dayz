# Changelog - 西虹 ERP 系统

## [v7.13.4] - 2026-11-05 - 员工薪资/提成/绩效链路打通 + 店铺显示名统一

### 薪资链路：口径不再各说各话

- **工资单「锁定」只有一个定义源**：新增 `backend/services/payroll_period_lock_service.py` 的
  `PAYROLL_LOCKED_STATUSES`（`approved` / `confirmed` / `paid`）。
  以前**四处各写各的**：锁定服务只认 confirmed+paid，而工资单界面和「我的收入」把
  `approved` 也显示成「已锁定」⇒ **界面显示已锁定、后台却允许整月重算**，
  重算会悄悄改掉用户以为锁住的工资单。现在全部引用同一份常量。
- **人力成本不再算两遍**：`finance.employee_labor_cost_allocations` 里同一行可能有
  历史 V1 与现行 V2 两个版本（V1→V2 是「原地改标签」的历史迁移，遇到受保护工资月会跳过
  ⇒ 那些月份仍是 V1；随后 `refresh_month` 又会新建 V2 行 ⇒ 同月双份）。
  以前 `mart.shop_month_labor_cost` 与几处直接查 base 表的读路径**都不过滤版本**
  ⇒ 看板「人力成本」最多虚高一倍；而利润基数侧（`profit_basis_service`）**是**按版本过滤的
  ⇒ 看板与利润基数两套口径。
  - 现在视图（迁移 `20261108`）与全部读路径（看板服务、费用管理、月结服务）统一**只认 V2**。
  - 看板「用投影人力成本还是手工人力费用」不再看 `system_config` 里那个**没人维护的开关**，
    改成**看数据本身**：这个月有 V2 投影行就用投影口径（扣掉手工人力费用、加上投影金额），
    没有就保留手工人力费用 —— 两种情况都不会重复计，也不会凭空少算。
- **换店/归属变更后的人力成本不再重复计入**：`LaborCostProjectionService.refresh_month`
  以前**只 upsert、从不删除** ⇒ 员工换店、归属比例调整、工资单被删之后，
  那些已经不成立的分摊行**永久留在表里**，而看板/利润基数是把整张表 SUM 起来用的。
  现在会清掉「这次算不出来但表里还在」的行；**已锁定（已结账）的行不删、直接报错** ——
  删了等于偷偷改已结账的钱。
- **「没提成」不再是没有记录**：以前员工如果**没配提成比例**，计算会直接跳过
  ⇒ 根本不产生提成记录 ⇒ 工资单提成恒 0，界面却看不出任何异常。
  - 现在照样落一条记录（金额 0）+ `calculation_status='no_ratio'`，
    并把**比例来源**写进新增的审计字段 `c_class.employee_commissions.calculation_details`
    （迁移 `20261109`）：是「店铺归属行填的」还是「薪资结构兜底的」，一目了然。
- **提成比例只有一个权威来源**：店铺归属行 `employee_shop_assignments.commission_ratio`；
  薪资结构 `salary_structures.commission_ratio` 明确降级为**员工级兜底**。
  这段「先取归属行、取不到再取薪资结构」的逻辑以前被**抄了三遍**（金额聚合/系数加权/店铺分摊），
  改一处必漏两处 ⇒ 收敛成 `_resolve_commission_ratio()` 一个方法。
- **提成比例上限校验不再被绕过**：NULL 与负数以前被 `or 0` 抹平，
  负数会让总和变小 ⇒ **绕过 100% 上限**。现在负数直接报错，NULL（这个店不给这个人算提成）
  在报错文案里单独说明。
- **绩效「配了不生效」被堵住**：`key_product_weight`（重点产品维度）**根本没实现**
  （打分时硬编码 0），但配置校验只查「四个权重加起来 = 100」⇒ 管理员把它调成 >0 也能保存成功，
  然后这个权重**永远不生效**。现在新建/修改配置时直接拒绝并说清楚原因。
  同时修掉 `c_class.performance_scores` 上写死的「30%/25%/25%/20%」注释
  （实际默认是 40/40/0/20，而且权重是可配置的）。

### 店铺显示名统一：全站不再直接甩键值给用户

- **主名 = 内部编号**（`internal_code`，如 `XHKJ11_SG`），**副显 = 店名**（`xhkj11.sg`）。
  平台上能看到的是店名，但**店名会改、别名也会改**；内部编号唯一且稳定 ——
  报表、截图、对账都以它为准。生产上 52 个店铺账号的 `internal_code` **覆盖率 100%**。
- `/api/reference/shop-directory` 现在返回 `internal_code` 与 `secondary_name`
  （以前只给 `display_name`，前端想按内部编号显示也拿不到）；
  顺带把它**每个店查一次别名**的 N+1 查询改成一次批量查。
- 新增 `frontend/src/composables/useShopDisplay.js`：**目录只请求一次**（模块级缓存），
  加载失败**不拖垮页面**（退回显示原始键值），口径只有一份。
- 新增 `frontend/src/components/common/ShopDisplayText.vue`：统一的「主名 + 副显」单元格。
- **接入 20 个文件**：A 类 15 个（原来直接渲染 `shop_id` 的表格：
  库存余额/告警/流水/期初/对账/总览、订单管理、按商品看销售、B 成本分析、
  费用管理、销售目标、目标执行工作台、收入审计、跟投收益、员工工资）
  + B 类 5 个（原来渲染 `shop_name` 的表格：销售看板、库存健康看板、产品质量看板、
  活动管理、目标人员管理）。
  另外把**下拉选项、删除确认弹窗、详情页**里裸露的 `shop_id` 换成显示名 ——
  确认弹窗里出现 `1308200825` 这种串，管理员根本不知道自己在删哪家的数据。
- **修掉「重复装饰导致原始店名失真」**：`decorateShopEntity` 会把 `shop_name` 覆写成显示名，
  再装饰一次时原始店名就被显示名顶替 ⇒ `canonical_name` 变成显示名。
  现在优先用 `raw_shop_name` / `canonical_name` 解析，并把装饰前的原始店名留在 `raw_shop_name`。
- **搜索文本补齐所有键值**：以前只放第一个非空 ID ⇒ 拿平台店铺ID 搜就搜不到
  （「看得见、搜不到」）。现在内部编号、别名、店名、平台店铺ID、店铺账号ID 全部进搜索文本。
- **员工归属接口的店铺名不再依赖派生表**：`/api/hr/employee-shop-assignments` 的 `shop_name`
  以前查 `core.dim_shops`（派生展示维度表，曾经长期 0 行 ⇒ 名称恒空），
  现在直查权威主数据 `core.shop_accounts`，键派生与语义层一致。
- 新增前端单测 `frontend/scripts/shopDisplay.test.mjs`（8 个用例：
  主名优先级、搜索文本、跨平台同名不串店、重复不失真等）。

### 工程

- 清掉两处「被同名覆盖的死代码」：
  `payroll_generation_service.py` 里 4 个被覆盖的旧版方法（带中文列 fallback 的旧实现）、
  `hr_commission.py` 里两个未被引用的 legacy loader，以及**重复注册的绩效模板路由**
  （同一路径注册了两次）。
- 清掉一条**悬空登记**：`mart.hr_shop_monthly_profit` 登记在刷新依赖表里，
  但这个视图**从来没有建过**（仓库无资产文件、生产库查不到、无任何代码引用）
  ⇒ 已删除，并把「登记的每个目标都必须能被资产文件重建」固化成断言，防止同类悬空登记再出现。
- 收口本次改动文件上的既有格式/lint 欠账（black / ruff），避免 CI 红灯。
- 新增迁移 `current_schema_20261108_align_labor_cost_allocation_version`、
  `current_schema_20261109_add_commission_calculation_audit`。

## [v7.13.3] - 2026-11-04 - 看板超时降级兜底 + 数据地基（dim_shops 对齐 / 改名占用预检 / 状态服务端派生）

### 可靠性：看板查询超时不再「空白页」

- **看板不再「超时即空白页」**：数据库语句超时时，后端不再直接返回 500，而是返回**上一次成功算出来的结果**，并在响应里明确标出「这份数据是截至什么时候的」。
  - 降级只发生在**超时**这一种故障上。语法错、权限不足、连接断开照常 500 —— 把它们伪装成「数据有点旧」会把真 bug 藏起来。
  - 超时**且**没有可用快照时，仍然返回 500 —— 不能凭空造数。
  - 客户端断开（`asyncio.CancelledError`）不算超时：那是用户走了或服务在停机，不该拿旧数据糊弄过去。
- **快照按端点分桶**（`<端点>:last_success`）：不同端点的查询参数可能完全一样（kpi 与 operational-metrics 都是 `granularity/period_key/platform_code/shop_id`），共用一个键会把 A 端点的数字当成 B 端点的发出去。
- **快照活 24 小时**（普通看板缓存只有 180 秒）：快照的用途正是「现在算不出来时还能给用户看点什么」，活得比普通缓存短就没意义了。
- 响应里新增 `meta.data_status="degraded"`、`meta.data_as_of`（那次成功结果的时间）、`meta.degraded_reason`，以及一条人话 warning；响应头 `X-Cache: DEGRADED`。前端业务概览页顶部弹出黄色提示条，明说「当前展示的是上一次成功的结果，不是最新数据」。
- 降级记录挂在 `request.state` 上而不是 ContextVar：bootstrap 端点用 `asyncio.gather` 并发跑 7 个模块，而 **Task 会复制一份 contextvars 上下文** —— 子任务里 `ContextVar.set()` 传不回父任务。

### 数据地基

- **`core.dim_shops` 全量对齐（生产此前是 0 行）**：看板的显示名 JOIN 读这张表，而它**一行都没有** ⇒ JOIN 永远落空，显示名只能靠 `core.shop_accounts.store_name` 兜底；绩效/提成/告警等 10 张业务表也以它为外键目标，等于全在裸奔。
  - 根因：这张表的唯一写入方从**旧模型** `core.platform_accounts` 同步，而旧模型早已被 `core.shop_accounts` 取代（生产：旧模型 11 行残留，新模型 52 行才是权威）；那个同步只在「建提成配置/建目标」时顺带被调用 ⇒ 从没跑过。
  - 修法：迁移 `20261107` 把 `core.dim_shops` 变成 **`core.shop_accounts` 的派生表**，键派生与语义层**逐字一致**（`resolved_shop_id = COALESCE(platform_shop_id, shop_account_id, id::text)`）—— 派生不一致 ⇒ JOIN 落空 ⇒ 这次修复等于没做。
  - **可重跑**：upsert + 清掉源里已不存在的派生行 ⇒ P3 改键后重跑一次即可全量对齐。清理**不带 CASCADE**：历史业务表有外键指向它，真有引用就让迁移失败（fail-closed），不会悄悄删数据。
  - 写入路径同步补齐：新建/编辑店铺账号立刻 upsert 维度行（并按需补平台维度），不再靠「碰巧走到某个接口」才写进去。
  - 安全边界：`dim_shops` 主键就是 `(platform_code, shop_id)` ⇒ 看板 JOIN 最多命中一行 ⇒ **不会把金额翻倍**。
- **改名新名的跨主账号占用预检**：店名是身份解析的**第 4 路匹配键**（`store_name_match`），语义层按 `(platform, 规范化店名)` 找候选、**不区分主账号** ⇒ 两个不同主账号的店铺用了同一个店名 ⇒ 候选数 = 2 ⇒ 原子层判为 `ambiguous_shop_label` ⇒ 这些行的 `shop_id` 落进 `'unknown'` ⇒ **这家店的钱在看板上直接消失**。原来的校验只覆盖「同一个主账号」，跨主账号撞车要到语义层才炸 —— 那时已经在算钱、已经算错了。现在提前拦在写入侧（409，人话说明占用方）。
  - 规范化口径与语义层一致（`normalize_alias_key`：剥平台前缀 → 小写 → 折叠分隔符），否则「看着不一样、匹配时一样」。
  - 区域语义与别名表唯一约束一致：同名 + **不同**区域 ⇒ 允许（区域消歧就是为了让同平台同名在不同区域并存）；一方区域为空（不限区域）⇒ 与另一方也为空才算冲突。
- **`platform_shop_id_status` 改为服务端派生**：它回答「这个平台店铺ID是什么来路、靠不靠谱」，必须与数据一致 —— 没有平台店铺ID却标成 `manual_confirmed` 就是在骗下游（看板身份健康度、采集对账都拿它当依据）。
  - 没有平台店铺ID ⇒ `missing`（客户端说什么都不作数）；
  - 平台店铺ID 变了（人工填的）⇒ `manual_confirmed`；
  - 平台店铺ID 没变 ⇒ **保留原状态**（`auto_bound` / `confirmed` 不被一次无关字段的编辑改写掉）。
  - 「变化了没有」按**派生结果**判定，不按客户端声称 ⇒ 派生结果没变就不触发归属重算（避免无谓的刷新风暴）。

### 工程

- 新增 `backend/utils/query_timeout.py`：沿异常链（`__cause__` / `__context__` / SQLAlchemy 的 `orig`）识别超时 —— asyncpg 的 `QueryCanceledError`、psycopg2 的 `QueryCanceled`、`sqlalchemy.exc.TimeoutError` 都能认，同时不会把普通异常误判成超时。
- 新增 `backend/tests/data_pipeline/test_dashboard_timeout_fallback.py`（10 个用例）与 `backend/tests/test_dim_shops_alignment.py`（11 个用例）。
- 顺手修掉 `shop_accounts.py` 里一处既有 ruff 违规（`is_active == True` → `.is_(True)`）：该文件这次被改动 ⇒ CI 会检查它 ⇒ 不修就是一条新红灯。


## [v7.13.2] - 2026-11-04 - 物化店铺身份候选集 + 修 analytics 数值转换脏数据

### 修复

- **`fact_analytics_atomic` 的数值转换会崩**（v7.13.1 发布时暴露）：清洗正则 `'[^0-9.-]'` 会**保留** `.` 与 `-`，所以脏值 `"-"` 清洗后仍是 `"-"`，`NULLIF` 挡不住 → `'.'::numeric` 直接抛 `invalid input syntax for type numeric`。
  - 这个缺陷平时被 PostgreSQL 的**列裁剪**掩盖了 —— `SELECT count(*)` 不计算这些列，所以查询看着正常；直到 `CREATE MATERIALIZED VIEW` 要物化**全部列**才炸出来。
  - 修法：给 analytics 层 12 处数值转换补上与 `orders_atomic.sql` **完全一致**的正则合法性校验（`^-?(?:\d+(?:\.\d*)?|\.\d+)$`，不合法 → NULL）。订单层本来就有，analytics 层漏了 ⇒ 现在两层对齐。
  - 口径影响：命中脏值的行，**原来整个查询报错**（什么都看不到），现在该字段为 NULL、其余字段正常 —— 是从「崩」变成「空」，不是改口径。

### 性能

- **根因**：`semantic.shop_identity_resolution_candidates` 这个候选集只有 **136 行**（52 个账号 + 21 条别名派生），却是**普通视图**；而订单/流量原子层是**每行**都要做一次身份解析（`LEFT JOIN LATERAL`）⇒ 每一行订单事实都把候选集重新展开、把 `regexp_replace` 之类的规范化表达式重算一遍、再排序一次。生产 `EXPLAIN ANALYZE` 实测全量重算 38,607 行要 **119 秒**，计划里 `shop_account_aliases`（只有 21 行的小表）被扫了 **148 万次**（38,607 行 × 38 次）—— 典型的 N+1：小表被当成逐行计算的表达式。
- **修法**：新增物化副本 `semantic.shop_identity_resolution_candidates_v2_mv`，原子层的两个**普通视图**（`fact_orders_atomic` / `fact_analytics_atomic`）改读它。
  - **正本（普通视图）一个字都没改** —— 它仍从 core 表现算（已用 git diff 逐字节核对），既有的断言全部继续有效。
  - 副本正文是**自包含的一份定义**（从 core 表现算），不是 `SELECT * FROM 正本`。原因：正本在不同环境里列数不同（生产 8 列、含区域消歧列；全新库 baseline 建的是 7 列旧版）⇒ 引用正本在全新库根本建不出副本。代价是两份定义，用契约测试（4 路 UNION 分支数、区域列）+ 迁移里的**内容指纹**守护防漂移。
  - ⇒ **口径零变化**：迁移建完副本立刻比对它与正本的**内容指纹**（行数 + 全量 md5），不一致直接抛错回滚 —— 「副本 == 正本」由机器证明，不靠人眼比对。生产实测 136 行逐字节一致。
  - **不动** `orders_monthly_atomic_mv` / `analytics_monthly_atomic_mv`：那是既有物化视图的完整定义（`DROP ... CASCADE` + `CREATE`），改了要在生产重建它们 ⇒ 有风险。它们继续读正本，既有行为不变。
  - 新增「建对象前置」机制（`ASSET_PREREQUISITES`）：目标资产的正文引用了别的对象时，那些对象必须先在 —— 副本不存在时建原子层视图会直接报 `relation does not exist`。
  - 顺手删掉 20260805 schema baseline 建的旧版候选集物化视图（只有 7 列、缺 `identity_shop_region`、没有任何对象引用它）；删除时**故意不带 CASCADE** —— 万一有依赖就让迁移失败（fail-closed），而不是悄悄删下游。
  - **实测效果**：全量重算从 113.5 秒降到 **9.2 秒（提速 12.3 倍）**；v7.13.1 物化层的「刷新要 115 秒」才真正降下来 —— 刷新窗口从分钟级回到秒级，不再出现「刷新时全员卡住」。

### 工程

- **迁移侧统一走原生 psycopg2 cursor**（与 schema baseline 同一范式）。SQLAlchemy 的 `exec_driver_sql` 在本仓库锁定的版本 + psycopg2 组合下会把空参数字典（`immutabledict`）交给 `cursor.execute`，而 psycopg2 只接受真正的 `dict`/序列 ⇒ 必然抛 `TypeError: immutabledict is not a sequence`。原生 cursor 走 PostgreSQL **简单查询协议**，多语句由数据库自己切分（`DO $$ ... $$` 不会被切坏）。
- **回滚路径修正**：物化视图的 `downgrade` 改成「先把消费方改回普通视图、再删物化视图」，并且**不再用 `DROP MATERIALIZED VIEW ... CASCADE`** —— CASCADE 会连带删掉 `mart.inventory_backlog_base_mv` 这类**不是 refresh registry 可重建目标**的对象，删了没人重建。
- `scripts/validate_migrations_fresh_db.py` 修掉一个**会吞掉真实报错**的 bug：Windows 下子进程输出按 GBK 解码，迁移一旦报中文/编码错会被当成「空输出」从而掩盖真因。
- **验证**：全新库 fail-closed 迁移门禁通过（迁移 + 数据同步关键列校验 + ORM Schema 一致性校验全绿）；后端大范围回归失败集 diff **新增失败 = 0**。


## [v7.13.1] - 2026-11-04 - 修复物化视图建表超时预算 + 收口 CI 格式与 lint 欠账

### 修复

- **v7.13.0 首次发布失败的根因修掉**：迁移 `20261105` 建物化视图时被 PostgreSQL 的 `statement_timeout`（生产 `2min`）掐断 —— 全量重算一遍原子视图实测就要 **114.6 秒**（`SELECT count(*) FROM semantic.fact_orders_atomic`，38,607 行），`CREATE` 还要把 38,607 行写进物化存储并建 4 个索引，必然超时。迁移现在把语句超时临时提到 **30 分钟**，结束后在 `finally` 里恢复原值 —— 迁移用的连接之后要归还连接池，不能带着 30 分钟超时去污染后续应用查询。
  - v7.13.0 那次失败是**整事务回滚**（alembic 把 `upgrade head` 当一个事务跑，20261104 的 DROP 也一并回滚），生产自动回滚到 v7.12.9，容器全部 healthy、API 200、**零残留** ⇒ 回滚机制本身是有效的，这次要修的是超时预算，不是回滚逻辑。
  - 顺带修正 `sql/semantic/orders_atomic_mv.sql` 里的错误注释：原先写「物化一次约 20 秒」，那是把**单次查询代价**当成了**物化代价**，实测是 114.6 秒。

### 工程

- **CI 红灯收口**：CI Pipeline 连续两版红（上一版 41774788661、本版 41853739109）都不是逻辑问题，是**存量欠账被本次改动触发**：
  - `black --check`：CI 只对**改动文件**跑检查，本次碰到 34 个文件、其中 26 个本来就不符合仓库锁定的 black 25.1.0 ⇒ 统一格式化（纯格式，无语义变化）。
  - `ruff check` 4 处 `F841`（赋值后未使用）：2 处 `params` 是重构遗留（早已改成显式 kwargs 传参）、1 处 `module` 是重复的字典查找（`_module_core_plan()` 内部已有同样的查找）、1 处 `current_count` 连带一次无用查询。
  - `Bandit` `B324`：`cache_service.py` 的缓存 key 哈希用了 MD5，命中 HIGH；这是**非安全用途**（只做短摘要，不用于签名/口令），按仓库既有先例显式标注 `usedforsecurity=False`。
  - 本地按 CI 同版本复现验证：black 25.1.0 ✓ / ruff 0.17.3 ✓ / bandit 1.9.4（total=0、matched=0）✓；后端失败集 diff **新增失败 = 0**。

## [v7.13.0] - 2026-11-04 - 下线滞销清理排名模块 + 重排超时预算 + 放宽数据库内存

### 退役

- **「滞销清理排名（月度）」整模块下线**（业务概览页）。这个模块不是慢，是**设计本身有问题**：它把「店铺级月度排名」和「SKU 级库龄/动销」两套口径揉在一张表里，排名口径依赖订单域全量重算，且语义层对不上店的行会落进 `unknown` 桶 —— 排名里会出现"某个不存在的店铺"。前端区块、API 封装、后端端点、服务方法、SQL 视图、刷新注册、缓存预热、事件监听、部署契约一并移除。
- 库存域的「SKU 级滞销清单」（`api.sku_clearance_ranking_module`，走 `mart.inventory_state`）是**另一套东西，保持不变**。
- 同模块的死代码一并清掉：`backend/services/clearance_ranking_service.py`（零活引用）、ORM 模型 `ClearanceRanking` 与死表 `c_class.clearance_rankings`（生产 0 行，唯一写入方就是上面那个 service）、Metabase 遗留 `sql/metabase_questions/clearance_ranking.sql`。**留着那张表等于留着一条"复活已退役模块"的写入路径。**
- 刷新管线模块键 `clearance_ranking` 更名为 `inventory_backlog`（它真正持有的是库存积压资产组），基表与全部下游仍在同一模块内 —— 「基表与它的全部下游必须同属一个模块」这条不变量没有被破坏。
- 迁移 `20261104_drop_clearance_ranking_module`：DROP 视图（不带 CASCADE）+ DROP 死表（fail-closed：非空则中止）+ 清理 `ops.dashboard_asset_state` / `ops.data_freshness_log` / `ops.data_lineage_registry` 里的僵尸行，避免新监控把已退役对象报成 missing。
- 部署期默认视图重建目标从 `api.clearance_ranking_module` 换成 `api.business_overview_inventory_backlog_module`。

### 性能

- **超时预算重排，504 变成可读的 500**：原来 nginx `proxy_read_timeout` = 60s 与后端 DB `statement_timeout` = 60s **完全相等**，DB 报错与 nginx 掐连接同时发生，nginx 永远先断 ⇒ 用户只看到 504 空白页，后端那条可读的"查询超时"永远送不到浏览器。现在是 **DB 60s < 前端 axios 120s < nginx 300s**（nginx 读/写超时 60s → 300s，前端 dashboard 超时 70s → 120s），DB 先失败、后端如实返回 500、nginx 如实转发。
- **原子层物化：业务概览与 B 成本页的 20 秒级慢查询根治**。根因是 `mart.shop_day_kpi` 读的 `semantic.fact_orders_atomic` 是**普通视图**，每次请求都要 9 张订单表全量 UNION + `ROW_NUMBER()` 去重 + 逐行 LATERAL 身份解析，且 PostgreSQL **无法把 `metric_date` 过滤下推到窗口函数之下**（EXPLAIN 实测：9 张表全部 Seq Scan，单日聚合约 20.2 秒）。
  - 新增两个物化视图 `semantic.fact_orders_atomic_mv` / `semantic.fact_analytics_atomic_mv`，正文就是对应普通视图的正文（`SELECT * FROM <普通视图>`）⇒ **口径零变化**：同一份定义、同一套去重、同一套身份解析、同一批行，物化只改变「什么时候算」。
  - **为什么不是"按粒度换源重建 MV"**：生产测绘显示订单事实共 38,607 行 = 月 36,624（GMV 93.79%）+ 周 1,506（3.86%）+ 日 477（2.35%），且去重窗口在生产上一次都没合并过（38,607 组 = 38,607 行）。纯月表源会少算 1,983 行订单（GMV 6.2%）⇒ B 成本金额漂移 ⇒ 换源方案已否决。
  - **为什么不用 `DROP MATERIALIZED VIEW ... CASCADE`**：CASCADE 会连带删掉 `mart.hr_shop_monthly_profit`、`mart.inventory_backlog_base_mv`（不是 registry 可重建目标）与 B 成本链（不在 bootstrap 计划里）⇒ 删了没人重建。改用「存在则 REFRESH（原地刷新）/ 不存在则 CREATE」：不删任何下游，也没有「视图短暂消失」的窗口；且 MV 正文引用的是普通视图，普通视图更新后 MV 刷新即跟进，不会漂移。
  - 6 个慢消费方改读物化视图：`mart.shop_day_kpi` / `shop_week_kpi` / `platform_day_kpi` / `platform_week_kpi` / `b_cost_shop_month` / `api.b_cost_analysis_order_detail_module`。
  - 迁移 `20261105_create_atomic_materialized_views`：建两个 MV + 4 个索引，并用 `sql/` 资产文件重建 6 个消费方视图（视图定义的 SSOT 仍是资产文件，迁移不抄第二份）。
  - 顺带修正 `api.business_overview_operational_metrics_module` 的依赖表：它的 SQL 资产里有一处 `LEFT JOIN mart.shop_day_kpi`，但依赖表里没写 → 可能拿到旧日粒度数据。
- 数据库容器内存上限 2G → 4G：线上实测上限只有 1.5GiB，而 `shared_buffers=512MB` + `work_mem=32MB×4` 并行 worker 在重分析查询时瞬时占用很高，历史上有过 OOMKilled（内核杀 PG → 连接重置 → nginx 记 502）。

### 验证

- 后端大范围回归（`backend/tests/data_pipeline` + 刷新队列 + `tests/`）与 HEAD 基线做**失败集 diff**：0 个新增失败；8 个清仓排名相关用例随模块下线一并移除。
- 前端哑测试门禁：静态路径检查 0 问题、运行时"没跑起来"0 问题，普通断言失败 8 个（与基线一致）。
- 生产只读实测：清仓排名 504 已从 nginx 错误日志消失；`store-analysis/shops` 现为 404（v7.12.9 已退役，非本次范围）。

## [v7.12.9] - 2026-11-04 - 退役 5 个失效模块 + 监控存在性校验 + 依赖单一真相源

### 退役

- 彻底清理 5 个已失效模块：店铺分析、店铺管理、财务报表、汇率管理、会计期间 —— 前端路由/菜单/权限/组件/API 封装、后端端点与 service、SQL 资产、权限目录条目一并删除。
- 删除 Metabase 时代的死 stub router `backend/routers/dashboard_api.py` 与 `backend/services/annual_cost_aggregate.py`。
- 清理 `annual_summary` 全部 service 方法、5 个 `api.annual_summary_*` / `api.store_analysis_*` SQL 资产与 `mart.shop_hour_traffic_kpi`。
- 权限目录从 59 项收敛到 54 项，系统角色默认权限同步收敛；`ensure_system_roles()` 启动时自动对齐已有角色，无需手工改生产库。
- 生产库清理 9 个僵尸目标的 14 条血缘边与 9 条新鲜度记录（先清理后上线，避免新监控把已退役对象报成 missing）。

### 依赖

- 新增 `requirements.lock.txt`（116 个包的完整传递依赖闭包，全部 `==` 钉死），根 `requirements.txt` 收敛为 51 项运行时直接依赖。
- 删除 `backend/requirements.txt` —— 它与根清单有 26 个包互相矛盾，正是 v7.12.7 依赖漂移的根源。
- 后端与采集镜像改为单步 `pip install -r requirements.lock.txt`，不再分两步互相覆盖。
- 镜像依赖门禁基线从 7 扩到 116 且从 lock 自动推导，新增「禁止浮动范围 / 必须单步安装 / 镜像内无锁外包」三项检查。

### 监控

- `/freshness` 新增 `object_exists`、`recorded_status`、`status="missing"` 与 `missing_targets`；`/lineage` 新增 `target_object_exists`、`source_object_exists` 与 `missing_objects` —— 不再只信「上次刷新时的结果」。
- 逻辑目标别名（`semantic.alias_registry` → `semantic.semantic_field_aliases`）登记在册，并用守护测试强制新逻辑目标必须登记，避免把活目标误报成 missing。

### 验证

- 后端全量回归 181 个失败用例 ID 逐个拿到 HEAD worktree 对照，0 个新增失败。
- 生产验收：5 个容器 0 重启、路由 619 → 612、权限目录 59 → 54、47 个监控目标 missing 为空、前端 bundle 无退役标识残留。

## [v7.12.8] - 2026-11-04 - 钉死 Celery 全链路依赖，修掉 kombu 漂移引发的 celery 崩溃循环

### 修复

- 根因：`kombu` 从 5.6.2 漂到 5.7.0，而 kombu 5.7.0 硬性要求 `redis-py>=6.1.0`，与钉死的 `redis==5.0.1` 冲突，导致 celery-worker / celery-beat 上线即抛 `kombu.exceptions.VersionMismatch` 并进入崩溃循环。pip 安装期不报错，只有运行时才炸。
- 把 Celery 全链路依赖（kombu / amqp / billiard / redis）全部钉死。
- 新增镜像依赖门禁：构建期比对镜像内实际版本与清单一致，让这类运行时不兼容在 CI 就暴露。
- CI 增加 celery 冒烟作业。

### 决策

- 按业务拍板「只修根因、不回退」执行，未回退版本。

## [v7.12.7] - 2026-11-03 - 巡店会话复用收尾 —— profile 唯一载体彻底落地

### 重构

- 废弃会话文件体系，登录态只保留持久化 profile 一个载体；删除旁路 profile 分支与店铺级遗留路径。
- 正式采集统一走持久化 profile，顺序路径不再读写会话文件；并行快照改为纯内存。
- 账号会话锁改为跨进程实现并对齐 profile 生命周期，父子进程共用同一把 Redis 锁。
- 打通账号级代理链路：代理进入浏览器与 context，凭据不再泄漏到日志与组件配置。
- 删除遗留采集中心老程序（app.py / handlers.py）。

### 清理

- 磁盘清理 2.13 GB；同步收敛会话诊断字段与外围遗留物告警语义。

### 文档

- 补生产 compose 事实源与 Redis 认证形态；记录 GitHub HTTPS 不通时走 SSH-443 的镜像同步解法。
- 落地可复用的 pytest 失败集合 diff 工具与基线快照导出。

## [v7.12.6] - 2026-11-02 - 巡店会话复用 + 店铺身份/别名治理（含语义层区域分流）

### 店铺身份

- 别名表加区域维度，店铺账号新增内部标准名 `internal_code` 及账号管理页编辑入口。
- 改名走联动流程，老数据不断、新数据不串；未匹配别名面板补出现次数与认领提示。
- 多候选不再静默归一，落 unknown + 告警码；写侧与查侧规范化统一，认领了不再匹配不上。

### 巡店与会话

- 打开窗口时按账号推导 work tag，人工路径不再共用平台级 session；slugify 保留非 ASCII 身份，做到一账号一巡店窗口。
- 会话新鲜度只认 `saved_at`，30 天过期机制恢复有效；让巡店读取路径与会话写入路径完全一致。

### 入库

- 补齐 `catalog_files` 店铺账号身份，`data_hash` 去重作用域改用稳定身份编号，避免改名后重复入账。

### 语义层

- 区域参与身份匹配，同名品牌店按站点分流；修复第一批语义层改造遗留的 6 条测试回归。

## [v7.12.5] - 2026-11-01 - 把「近30天销量（库存采集）」加到真正在用的积压明细表

### 新增

- 在业务概览真正在用的「高积压风险产品」积压明细表加上「近30天销量（库存采集）」列。

## [v7.12.4] - 2026-11-01 - 把「近30天销量」露到接口与页面

### 新增

- SKU 级滞销清单接口与页面新增「近30天销量」字段，并明确标注它是库存数据域口径（不是销售域口径）。

## [v7.12.3] - 2026-10-31 - 滞销清单近30天动销换源 + 数据库设计校验 API 500 修复

### 修复

- 滞销清单「近30天动销」恒为 0：根因是跨系统对账本身不成立（平台拿「数据来源」比「销售渠道」、两侧 SKU 口径不对称、大小写未归一），改为直接用妙手清单自带的窗口销量（库存数据域口径）。
- 修好 `/api/database-design/*` 全线 500。
- 贴单费未配置时按 0 计，不再让整条利润链算不出来。
- 迁移演练用例改用隔离容器，不再在 CI 上撞本地库。

## [v7.12.2] - 2026-10-31 - SKU 大小写归一 + 库存状态层生产触发路径补齐

### 修复

- 库存侧与订单侧同一件商品 SKU 只有大小写不同就配不上（实测 6 个 SKU、库龄 47~60 天、全部 ≥30 天本来都该进榜）整件漏在榜外；两侧 `sku_key` 统一套 `LOWER()` 归一。
- 库存状态层在生产从不出数的根因定位：「有写入方」不等于「会被写入」，状态层缺稳定触发路径。修法为部署补重建 + 刷新判据从「事件带 `data_domain=inventory`」改成「本次刷新目标含库存事实」。

### 测试

- 修正两条过期的部署契约断言；前端 `manualChunksCycle` 测试在无构建产物时显式跳过（修掉 CI 门禁自己抓出的第 5 个哑测试）。

## [v7.12.1] - 2026-10-31 - 生产视图重建接入部署流程 + 采集同步四批根源性修复

### 部署

- 生产环境原本不会重建改过的视图（`AUTO_BOOTSTRAP_DASHBOARD_ASSETS_ON_STARTUP=false`，且刷新与 bootstrap 都跳过已存在的普通视图）。现在由部署脚本 Phase 2.7 / 2.7b 自动重建，失败即中止部署并回滚，不再需要人工去服务器上跑。

### 采集同步

- 四批根源性修复：模板契约、状态语义、统一读表头、变体接管、traffic 收敛。
- 契约晋升：模板升级后被旧契约钉死的文件自动放行。
- 「无模板」落终态，终止 8 个文件的无限重试闭环。
- 兜底入队签名缺陷修复（缺必填参数导致兜底链路 100% 失效）+ 测试库隔离护栏 + 代码新鲜度全树校验。
- 保存发布状态机、家族校验口径与契约失效显式化；域限定列名识别 + 工作台自动归一，打通「源文件变动 → 工作台更新 → 正常同步」。
- 修复模板工作台用视图子集覆盖全量绑定，导致去重字段被静默丢弃。

### 看板

- 滞销榜恒 0 行修复；修正 DB 超时预算倒置并治理 clearance-ranking 慢查询。

## [v7.12.0] - 2026-10-26 - 发版前阻断项修复 + 商品中心 SKU 定价底线 + 库存库龄管道恢复

### 定价

- 新增商品中心 SKU 定价底线（最低售价）与定价纪律规则表：纯计算服务、成本线/纪律线/降级链/档位匹配、迁移与 ORM 骨架、SKU 列表注入定价底线字段、前端定价设置抽屉与利润测算护栏。
- 达人佣金计入利润试算（与最低售价同一口径），利润版本留痕；参考售价表头改黑。
- 最低售价覆盖值未保存时提示「保存后生效」，避免被误读为未生效。

### 库存库龄

- 恢复库存库龄管道（断点定位 + 验收标准），新增 SKU 级滞销排名读模型与服务端点（真库龄口径）。
- 滞销判据换血成「距上次进货天数」；修好库龄刷新从未入队的断链（`DATA_INGESTED` 事件改为 await 入队）。
- 妙手库存字段映射模板 v3（28 列）。
- 库龄看板页新增 SKU 级滞销清单页签；滞销清单视图去掉 8.8 秒的 `backlog_base` 取数路径。

### 采集

- 妙手库存域采集整改：筛选组件按真实页面结构重写、仓库范围筛选定位器按取证修正、日期面板交互修正（收日期必须用 Tab）、维度下拉限定范围。
- B1 增量筛选组件 + B3 水位线与断档补采，水位线增量窗口接进采集执行链；采集后自动 upsert 状态层。
- 采集组件 lint 引擎抽公共模块 + CLI + CI 告警模式；执行器向组件注入 logger 与步骤回调，库存域按阶段上报事件并在失败时留截图。

### 修复

- 数据同步三层收口：收尾不再把正常请求打成 500、就绪判定加缓存与超时保护；并发共享数据库会话导致概览接口 500 的修复 + 两道自动化守卫。
- 数据刷新不再重建普通视图，死锁按可重试处理。
- 补上业务概览积压卡的缓存失效；修本地启动暴露的资产链 DROP 顺序、date_range 契约与漏注册视图问题。
- 发布阻断项：迁移回归、两处 NameError、重复路由、门禁对齐。

### 测试

- 补 data_hash 幂等性的端到端契约测试；堵住另外两个「往真实库写测试用户 + 假通过」的文件。

## [v7.11.25] - 2026-10-17 - 进货价导入脚本与对账工具落地

### 新增

- 新增进货价导入脚本骨架与 xlsx 解析器，用于解析进货价表。
- 新增 `reconcile()` 对账函数与 `fetch_db_sku_keys()` 拉取库内 SKU 主键的辅助函数。
- 新增脚本 CLI 入口、校验查询与报告输出能力。

### 数据

- 新增基于备份与事务的 `apply_update` 更新流程，落库前先生成备份并在事务中执行。

## [v7.11.24] - 2026-09-18 - 前端 nginx 的 IPv6 监听指令移入 server 块

### 修复

- 把 `listen [::]:80;` 从 nginx 配置顶层移入 `server` 块内部。
- 修复前端镜像中该指令作用域不合法导致 nginx 无法正常启动的问题。

## [v7.11.23] - 2026-09-18 - 前端镜像固定 nginx 版本并短路 IPv6 入口

### 修复

- 前端基础镜像的 nginx 版本固定为 `nginx:1.27-alpine`，不再跟随浮动版本。
- 前端容器入口脚本在处理 IPv6 监听时直接短路，跳过原有的 IPv6 分支逻辑。

## [v7.11.22] - 2026-09-18 - 前端健康检查改用 curl

### 修复

- 前端容器健康检查命令由 `wget` 改为 `curl`。
- 避免镜像内缺少 `wget` 导致健康检查持续判定失败。

## [v7.11.21] - 2026-09-18 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:321321`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.11.20] - 2026-09-18 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:32132`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.11.19] - 2026-09-17 - 清理根目录临时调试报告并发布后端优化

### 修复

- 移除根目录下遗留的临时调试报告文件。
- 后端完成一轮优化改进。

## [v7.11.18] - 2026-09-17 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:3213`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.11.17] - 2026-09-17 - 权限模块优化

### 优化

- 对权限相关逻辑做了一轮优化。
- 本版本区间内仅包含这一项权限相关提交，无其他可归纳的功能改动。

## [v7.11.16] - 2026-09-16 - 商品中心物流商规则支持编辑删除

### 新增

- 商品中心的物流商规则支持编辑与删除操作。
- 物流商规则列表按仓库维度排序，加载过程写入日志。

### 修复

- `loadRules` 请求失败时把错误信息透出到前端界面。
- `loadRules` 请求失败时补充表格加载状态处理，并回显鉴权状态便于定位失败原因。

## [v7.11.15] - 2026-09-16 - 前端界面优化

### 优化

- 对前端界面做整体优化，改进页面展示与交互效果。
- 本版本区间内仅包含这一项前端优化提交。

## [v7.11.14] - 2026-09-16 - 商品中心利润工作台与妙手进货库存导出落地

### 新增

- 商品中心新增直营量与利润草稿、人民币仓储参考成本计价、平台 SKU 利润工作台与站点 SKU 经营利润流程。
- 新增妙手进货导出标准 V2 组件 `MiaoshouPurchaseExport` 与妙手库存导出标准 V2 组件 `MiaoshouInventoryExport`，配套 `purchase_config` / `inventory_config` 选择器与 `TargetPage.PURCHASE` 目标页导航分支。

### 修复

- 妙手进货导出改用 `page.expect_download` 捕获下载、移除 `_close_progress_dialog`，并等待进度对话框与搜索结果可见后再操作，状态页签改为通过 URL 参数切换。
- 妙手日期选择器接入 `PurchaseSelectors` 并把触发兜底扩展到进货页标签，进货导出 `preset_map` 补齐英文键以对齐订单与库存导出。
- 采集模块把进货数据域接入快捷采集与配置面板，并在配置模板与店铺能力中启用，未知能力域回填默认值并同步测试断言。
- 商品中心统一人民币成本契约，拒绝未换算的外币采购成本，关闭计费与审计缺口，并消解默认物流规则的选择歧义。

### 数据

- 商品中心主数据与历史利润写入纳入审计，SPU SKU 绑定变更、仓库写入、分类变更全部留痕并对重算成本预估设门禁；利润工作台支持分页并保留规则历史，分类体系调整后重新拉直 current schema 迁移链。

### 文档

- 补记进货导出进度等待、日期选择器兜底与进货前端启用方案的规格与分支历史，并整理分支评审遗留问题。

### 部署

- 发布流程在 PowerShell 下不再因 `git fetch` 进度输出而中断。

## [v7.11.13] - 2026-09-11 - Git 镜像同步治理与商品中心采购物流流程补齐

### 新增

- 商品中心采购物流流程补齐，支持物流商规则与多采购单批次。

### 修复

- Git 镜像同步默认走 GitHub SSH 通道，同时保留 HTTPS 镜像的默认配置不被覆盖。
- 镜像同步捕获 `git fetch` 进度输出，不再因进度信息中断同步。
- 物流批次分摊保留分摊血缘信息。

### 部署

- 治理 GitHub 与 CNB 主分支的镜像同步流程，并补齐对应的契约测试。

### 数据

- 八月重置补充前置校验：重置期间静默写入、无薪资覆盖时阻止重置、管理员身份改由公开角色接口校验，并统一生产店铺佣金月份列口径。
- 清空八月月度业务输入，同时下线周度滞销排名。

## [v7.11.12] - 2026-09-10 - 滞销排名视图契约变更后自动重建

### 修复

- 滞销排名视图在契约发生变更后触发重建，使视图定义与新契约保持一致。

## [v7.11.11] - 2026-09-10 - 商品中心与月度滞销分析接入飞书投影

### 新增

- 新增商品中心与月度滞销分析功能。
- 完成商品成本与飞书投影的收尾实现。

### 修复

- 本地启动流程与 current schema 对齐。
- 加固商品投影与物流契约，并保留库存语义视图的兼容性。
- 记录飞书投影的每一次投递尝试，便于排查投递失败。

### 重构

- 布尔条件改用 SQLAlchemy 谓词表达式实现。

## [v7.11.10] - 2026-09-05 - 费用与月度人事配置流程对齐、八月重置前置校验补齐

### 修复

- 对齐费用流程与月度人事配置流程。
- 八月重置期间静默写入，无薪资覆盖时阻止重置。
- 八月重置的管理员身份改由公开角色接口校验，并补齐八月 V2 重置前置检查。

### 数据

- 清空八月月度业务输入，统一生产店铺佣金月份列口径。

## [v7.11.9] - 2026-08-28 - 清空八月月度业务输入

### 数据

- 清空八月月度业务输入。

## [v7.11.8] - 2026-08-28 - 无薪资覆盖时阻止八月重置

### 修复

- 八月重置前增加薪资覆盖校验，未覆盖时阻止重置执行。

## [v7.11.7] - 2026-08-28 - 重置管理员身份改由公开角色接口校验

### 修复

- 重置操作的管理员身份改由公开角色接口校验。

## [v7.11.6] - 2026-08-28 - 八月 V2 重置前置检查与佣金月份列口径修正

### 修复

- 店铺佣金改用生产环境的月份列口径。
- 支持八月 V2 重置的前置检查流程。

## [v7.11.5] - 2026-08-28 - V2 月度刷新与八月重置自动化

### 新增

- 自动化 V2 月度刷新与八月重置流程。
- 新增生产环境的 V2 dry-run 工作流。

### 部署

- V2 dry-run 改为在已部署的后端容器内执行。

## [v7.11.4] - 2026-08-27 - V2 利润口径拆分迁移到 current schema

### 修复

- 在 current schema 中补齐 V2 利润口径拆分的迁移。

## [v7.11.3] - 2026-08-27 - V2 迁移执行器纳入生产镜像

### 部署

- 将 V2 迁移执行脚本打包进生产镜像。

## [v7.11.2] - 2026-08-27 - 部署备份改为在远端 shell 执行

### 部署

- 部署流程中的备份命令改为在远端 shell 中执行。

## [v7.11.1] - 2026-08-27 - V2 利润口径迁移护栏与人力成本口径统一

### 新增

- 新增受保护的 V2 利润口径迁移 dry-run，迁移不完整时阻断执行。
- 新增带审计的受保护历史重开阶段。
- 人力成本策略改为仅支持 V2，并在人力模块展示固定的 V2 利润口径。

### 修复

- 收入计算中保留 V2 人力分摊状态，校验 V2 人力分摊完整性，并串行化迁移 dry-run 的金额处理。
- 工资刷新统一收敛到 V2 利润口径。
- 店铺状态筛选口径对齐，停用店铺的恢复入口可被发现，切换状态时保留店铺身份信息。

## [v7.11.0] - 2026-08-23 - 个人绩效目标工作台与运营绩效整数化评分落地

### 新增

- 新增个人绩效目标契约与个人绩效目标工作台，配套受控个人绩效服务、工作台 API 与受控目标录入审计。
- 新增运营绩效的整数化评分与自动整数数据契约，支持结构化运营绩效录入，并从受控目录推导运营规则。

### 修复

- 受控个人范围成为判定权威，范围未确认前阻断受控收入发放，部分受控绩效收入按门禁放行。
- 受控个人绩效并发加锁加固，月度绩效依赖串行化，工资确认不再自锁。
- 个人绩效的降级、遗留写入、审计状态与历史月份均加保护，禁止破坏性降级并限制遗留读取。
- 运营绩效结算强制要求运营项完成，无效运营规则阻断完成，评分快照与店铺身份在运营条目中保留。

### 数据

- 新增仅面向门店的运营目录 v3，并保护运营目录版本历史。

### 测试

- 补充受控个人结果降级、个人目标迁移往返、绩效锁定与运营结算收入等测试，并更新 current schema 头契约测试。

### 文档

- 编写个人绩效目标工作台的设计文档，明确自动运营绩效评分与运营店铺范围口径。

## [v7.10.3] - 2026-08-17 - 迁移备份辅助脚本纳入后端镜像

### 部署

- 将迁移备份辅助脚本打包进后端镜像。

## [v7.10.2] - 2026-08-17 - 月度运营绩效工作台落地与本地重建流程加固

### 新增

- 实现月度运营绩效工作台，并完成绩效模块的整体优化。
- 本地采集迁移启动流程加固，增强重建过程的诊断信息。

### 修复

- 本地重建直接加载本地重建环境，校验并拒绝非法重建 URL，校验重建目标身份，展示受保护的重建计划，并收敛仪表盘就绪检查范围。
- 本地重建保留连接凭证，本地管理引导的配置与目标范围被隔离并受限。
- 本地控制台启动恢复正式采集控制台启动，简化开发态启动流程并保证离线可用。
- 迁移备份脚本输出按 UTF-8 解码，避免中文乱码导致解析失败。

## [v7.10.1] - 2026-08-10 - 发版 CI 门禁打通与运营数据迁移隔离加固

### 修复

- 打通 v7.10.1 发版 CI 门禁，同时保持发布 compose 校验过程输出安静。
- 隔离 v7.10.1 的遗留运营目标，隔离环境下的运营发布迁移进一步加固。
- 数据库中冻结遗留运营记录，切换期间共享基础设施网络，回滚时保留遗留运营写入。

### 测试

- 部署网络集成测试改为按需开启，默认不进入常规门禁。

## [v7.10.0] - 2026-08-10 - 月度运营绩效工作台设计与 current schema 迁移链建立

### 新增

- 新增月度运营绩效工作台。
- 新增店铺订单指标预占能力。

### 修复

- 发版前置检查加入 current schema 校验。
- 支持仅个人参与的绩效结算。
- 已结算工资的绩效重算加锁，避免结算后被改写。

### 重构

- 建立 current schema 的迁移链。

### 文档

- 完成运营绩效工作台的设计文档，补充结算设计的安全护栏。

## [v7.9.3] - 2026-08-06 - 本地控制台输出保持可见

### 修复

- 修复本地控制台输出不可见的问题。

## [v7.9.2] - 2026-08-05 - 工资结算锁定与成本佣金输入冻结

### 新增

- 完成工资结算锁定。
- 工资成本与佣金输入在结算后被锁定不可修改。

### 修复

- 迁移测试改用临时可用端口，解决端口占用问题。
- 复制月度店铺指派数据，避免月度切换时丢失归属关系。

## [v7.9.1] - 2026-08-05 - 基于工资投影人力成本与本地运维控制台

### 新增

- 新增本地运维控制台。
- 人力成本改为基于工资数据投影计算。

## [v7.9.0] - 2026-08-04 - 员工目标统一为店铺共享责任

### 新增

- 员工目标口径统一为店铺维度的共享责任。

## [v7.8.11] - 2026-08-04 - 月度绩效统一百分制并对齐结算利润口径

### 新增

- 月度绩效统一为 100 分制刻度，绩效口径与结算利润口径对齐。

### 修复

- 发布时初始化云同步接收端。
- 可选的绩效配置迁移增加护栏，避免配置缺失时迁移失败。

### 文档

- 补充绩效收入计算方式的说明文档。

## [v7.8.10] - 2026-08-03 - 回填历史目标分配比例

### 数据

- 回填历史月度目标的分配比例数据。

## [v7.8.9] - 2026-08-03 - 员工目标分配契约与月度绩效结算补全

### 新增

- 新增员工目标分配契约。
- 统一账号边界与员工目标口径。

### 修复

- 补全月度绩效结算流程。

## [v7.8.8] - 2026-07-07 - 常规迭代发布

### 发布

- 本版本区间内仅包含一条提交，提交说明为占位文本（`feat:321231`），无可归纳的功能改动。
- 本次发布沿用上一版本的功能基线。

## [v7.8.7] - 2026-07-07 - 采集动态时间窗口与本地 PWCLI 检查面板

### 新增

- 采集支持动态时间窗口，并新增批量时间策略控制项。
- 新增本地 PWCLI 检查面板。

### 修复

- 修复 Shopee 月度订单金额被覆盖的问题。
- 妙手自定义日期区间输入框交互稳定化，动态时间窗口按自定义区间方式执行。

### 优化

- PWCLI 会话保存时机改由用户自行决定。

### 文档

- 明确 PWCLI 面板的保存流程。

## [v7.8.6] - 2026-06-29 - CNB 镜像同步流程简化与生产启动加固

### 部署

- 简化 CNB 的 Git 同步流程。
- 加固生产环境启动流程与 CNB 镜像同步。

## [v7.8.5] - 2026-06-29 - 生产部署迁移门禁加固

### 部署

- 加固生产部署的迁移门禁，发版前必须通过迁移校验。
- 本版本区间内没有额外功能提交，属于迁移门禁加固的发布版本。

## [v7.8.2] - 2026-06-29 - 生产部署迁移门禁加固

### 部署

- 加固生产部署的迁移门禁，发版前必须通过迁移校验。

## [v7.8.1] - 2026-06-29 - 云同步自动恢复与生命周期监控加固

### 新增

- 自动化云同步恢复流程。
- 加固云同步的生命周期管理与监控能力。

### 修复

- 云同步完成后的自动刷新逻辑加固。

### 部署

- 更新本地配置、依赖与部署文档。

## [v7.5.7] - 2026-06-24 - 订单类模板治理非破坏性放宽

### 修复

- 订单类模板的治理规则放宽，容许不破坏既有结构的变更。

### 发布

- 本版本区间内另含一条说明为占位文本的提交（`feat:321321`）。

## [v7.5.6] - 2026-06-23 - 模板哈希键按语义绑定归一与自动刷新优化

### 修复

- 模板哈希键按语义绑定归一化，避免同一语义的键产生不同哈希值。

### 优化

- 自动刷新与自动任务流程得到优化。

## [v7.5.2] - 2026-06-19 - 上线部署版本

### 部署

- 完成本版本的上线部署。
- 本版本区间内没有功能提交，属于纯部署发布版本。

## [v7.5.1] - 2026-06-19 - 店铺身份标准化与语义哈希治理、云同步自恢复

### 新增

- 店铺身份采集流程标准化。
- 远端同步能力可用，并支持恢复卡死的云同步任务。
- 云同步 SSH 隧道可自动启动。
- 新增语义契约模板治理与语义哈希策略治理，动态模板哈希选项一并修正。

### 修复

- 统一人力佣金与利润底线口径。
- 采集任务启动方式标准化。

### 部署

- 完成本版本的上线部署。

## [v7.2.9] - 2026-06-11 - 业务概览模块布局紧凑化与模板更新工作台收尾

### 优化

- 业务概览模块布局改为紧凑排布。
- 业务概览排名趋势展示优化。
- 前端界面与排版整体优化。

### 修复

- 模板更新工作台与仪表盘交互细节收尾修正。

## [v7.2.8] - 2026-06-10 - 上传功能修复

### 修复

- 修复上传链路的问题。
- 本版本区间内仅包含这一项上传相关改动。

## [v7.2.7] - 2026-06-09 - 自动入库任务治理加固与伴随日期身份哈希自动化

### 新增

- 自动化计算伴随日期的身份哈希。

### 修复

- 加固自动入库任务的治理能力。
- 约束模板语义哈希参与计算的字段范围。
- 加固自动入库重建流程的恢复能力。

### 部署

- 完成上线准备与落地优化。

## [v7.2.2] - 2026-06-09 - Shopee 店铺身份采集流程加固

### 修复

- 加固 Shopee 店铺身份采集流程。

### 重构

- 统一格式化 v7.2.1 的数据入库改动代码。

## [v7.2.1] - 2026-06-09 - B 类产品月报入库日期异常修复

### 修复

- 修复 Shopee products monthly 自动入库在线程池内丢失文件日期、模板日期规则和表头绑定上下文的问题。
- 阻断 B 类入库在无可靠业务日期时使用处理当天作为 `metric_date` 静默写入。
- 对带 `catalog_files.date_from/date_to` 的入库结果增加业务日期范围校验，防止 4/5 月文件写入 6 月业务日期。
- 修正 Shopee products monthly 的模板规则来源和 UPSERT 更新字段，使月报按文件月份入库并可正确更新。
- 修复 `sales_targets_a` 平台列迁移，兼容 fresh DB 的 `shop_id/year_month` 列和生产库旧中文列。

### 数据

- 清理并重入库 14 个 2026-06-08 处理的 Shopee products monthly 异常文件，近期异常日期扫描归零。

## [Unreleased] - 组件版本管理模块重构 (optimize-component-version-management)

### 组件版本管理

- 组件版本测试执行一致性：测试时执行 `version.file_path` 对应实现，adapter 支持 override 注入
- 生产执行器按 file_path 加载：`_load_component_with_version` 使用 `load_python_component_from_path`，`_execute_python_component` 当 component dict 含 `_python_component_class` 时直接使用该类
- 删除规则放宽：可删除条件调整为 `!is_testing && !is_active`，稳定版禁用后也可删除
- 验证码步骤 unconditional 暂停：图形验证码步骤到达即等待 1s → 截图 → raise VerificationRequiredError
- 实际执行文件展示：版本列表增加 file_path 列
- 录制保存创建新版本：component_name 由 platform+component_type+data_domain+sub_domain 推导；版本号应用层语义解析递增；新版本默认非稳定
- 前端 export 保存传 data_domain/sub_domain

### 新增

- `backend/services/component_name_utils.py`：component_name 标准化、版本号解析
- `ComponentLoader.load_python_component_from_path`：按 file_path 加载，模块名唯一避免 sys.modules 污染

---

## [v4.20.0] - 2026-01-08 - 系统管理模块 API 完整实现

### 核心功能

#### 1. 系统日志与审计日志增强

- ✅ 系统日志 API（`GET /api/system/logs`）
  - 支持按级别、模块、用户、时间范围筛选
  - 分页查询（最大 100 条/页）
  - 日志详情查看（`GET /api/system/logs/{log_id}`）
  - 日志导出（Excel/CSV 格式）
  - 清空日志功能（管理员权限）
- ✅ 审计日志增强
  - 增强筛选功能（操作类型、资源类型、用户、IP 地址、时间范围）
  - 审计日志详情查看（包含变更前后对比）
  - 审计日志导出功能

#### 2. 安全设置 API

- ✅ 密码策略管理（`GET/PUT /api/security/password-policy`）
  - 最小长度、复杂度要求、过期时间、历史密码检查
  - 动态配置，实时生效
- ✅ 登录限制配置（`GET/PUT /api/security/login-restrictions`）
  - 最大失败尝试次数、账户锁定时长
  - IP 白名单管理（`GET/POST/DELETE /api/security/ip-whitelist`）
  - 动态配置，替换硬编码常量
- ✅ 会话管理配置（`GET/PUT /api/security/session-config`）
  - 会话超时时间、并发会话限制
  - 支持动态配置会话超时（集成到 auth_service）
- ✅ 2FA 配置（`GET/PUT /api/security/2fa-config`）
  - 启用/禁用 2FA、强制要求 2FA

#### 3. 数据备份与恢复 API

- ✅ 数据备份功能（`POST /api/backup/create`）
  - 支持数据库备份、文件备份、完整备份
  - Docker 环境适配（使用 pg_dump、tar、zip）
  - 备份记录管理（`GET /api/backup/list`）
  - 备份下载（`GET /api/backup/{backup_id}/download`）
- ✅ 数据恢复功能（`POST /api/backup/{backup_id}/restore`）
  - 多重安全防护（维护窗口检查、多管理员确认、强制确认）
  - 备份验证、恢复前自动备份
  - 恢复状态跟踪
- ✅ 自动备份配置（`GET/PUT /api/backup/auto-config`）
  - 备份频率、保留策略、备份时间窗口

#### 4. 系统维护 API

- ✅ 缓存清理（`GET/POST /api/maintenance/cache/*`）
  - Redis 缓存状态查询
  - 按类型清理缓存（全部、用户会话、数据缓存）
  - Docker 环境适配（redis:6379）
- ✅ 数据清理（`GET/POST /api/maintenance/data/*`）
  - 系统日志清理、临时文件清理
  - 数据状态查询
  - 安全措施（管理员权限、确认机制）
- ✅ 系统升级（`GET/POST /api/maintenance/upgrade/*`）
  - 升级检查、升级执行
  - 多重确认、自动备份
  - P3 功能，不推荐使用（建议通过 CI/CD 完成）

#### 5. 通知配置 API

- ✅ SMTP 配置（`GET/PUT /api/notification-config/smtp`）
  - SMTP 服务器配置（服务器、端口、TLS、用户名、密码）
  - 密码加密存储
  - 连接测试、测试邮件发送
- ✅ 通知模板管理（`CRUD /api/notification-config/templates`）
  - 模板类型（系统通知、告警通知、审批通知）
  - 模板变量支持
  - 模板激活/停用
- ✅ 告警规则管理（`CRUD /api/notification-config/alert-rules`）
  - 告警级别（critical、warning、info）
  - 告警条件（JSON 格式）
  - 通知方式（email、sms、in_app）
  - 通知对象配置

#### 6. 系统配置增强 API

- ✅ 系统基础配置（`GET/PUT /api/system/config`）
  - 系统名称、版本、时区、语言、货币
  - 配置持久化存储（SystemConfig 表）
- ✅ 数据库配置（`GET/PUT /api/system/database/config`）
  - 数据库连接信息查看（敏感字段加密）
  - 数据库配置更新（保存为 pending 状态）
  - 数据库连接测试（`POST /api/system/database/test-connection`）
  - Docker 环境适配（从容器环境变量读取）

#### 7. 权限管理增强 API

- ✅ 权限树 API（`GET /api/permissions/tree`）
  - 按模块分组的权限树结构
  - 支持层级展示
- ✅ 权限列表 API（`GET /api/system/permissions`）
  - 系统预定义权限列表（60+权限）
  - 支持按分类筛选
  - 权限树结构（`GET /api/system/permissions/tree`）

### 技术改进

#### 架构合规性

- ✅ 100% SSOT 合规（所有 ORM 模型在`modules/core/db/schema.py`定义）
- ✅ Contract-First 开发（所有 API 先定义 Pydantic 模型，后实现业务逻辑）
- ✅ 异步架构统一（所有服务类仅支持 AsyncSession）
- ✅ 路由前缀统一（`/api/system/*`、`/api/security/*`等）

#### 数据模型

- ✅ 新增表：`system_logs`、`security_config`、`backup_records`、`smtp_config`、`notification_templates`、`alert_rules`、`system_config`
- ✅ 数据库迁移脚本（手动执行，避免 Alembic 编码问题）

#### 安全措施

- ✅ 所有管理 API 需要管理员权限（`require_admin`）
- ✅ 敏感数据加密存储（密码、SMTP 密码）
- ✅ 限流保护（`role_based_rate_limit`）
- ✅ 输入验证（Pydantic 模型验证）
- ✅ 审计日志记录（所有配置变更）

#### Docker 环境适配

- ✅ 数据库备份使用`pg_dump`连接`postgres:5432`
- ✅ 文件备份使用容器内部路径（`/app/data`、`/app/downloads`、`/app/logs`）
- ✅ Redis 连接使用`redis:6379`
- ✅ 数据库配置从容器环境变量读取

### 前端集成

- ✅ 创建`frontend/src/api/system.js`，包含所有系统管理 API 客户端函数
- ✅ 支持系统日志、安全设置、备份恢复、系统维护、通知配置、系统配置、权限管理等所有 API

### 文档更新

- ✅ 更新`CHANGELOG.md`
- ✅ API 文档自动生成（OpenAPI/Swagger）

### 已知限制

- ⚠️ 数据恢复实际逻辑需要 Celery 异步任务支持（基础框架已完成）
- ⚠️ 自动备份配置需要集成到 Celery 定时任务
- ⚠️ 系统升级功能标记为 P3（不推荐使用），建议通过 CI/CD 完成
- ⚠️ 通知模板变量替换需要在使用时实现
- ⚠️ 告警规则触发逻辑需要监控系统支持

---

## [v4.19.0] - 2026-01-05 - 用户注册审批与账户管理

### 核心功能

#### 1. 用户注册与审批流程

- ✅ 新增用户注册功能（`POST /api/auth/register`）
  - 支持用户名、邮箱、密码、姓名等信息注册
  - 密码强度验证（至少 8 位，包含字母和数字）
  - 统一错误消息（防止用户名/邮箱枚举攻击）
  - 注册频率限制（5 次/分钟）
- ✅ 用户状态管理
  - pending（待审批）：注册成功，等待管理员审批
  - active（已激活）：审批通过，可以正常使用
  - rejected（已拒绝）：审批被拒绝
  - suspended（已暂停）：账户被管理员暂停
- ✅ 数据库触发器自动同步`status`和`is_active`字段
- ✅ 用户审批记录表（`user_approval_logs`）记录所有审批操作

#### 2. 管理员审批功能

- ✅ 待审批用户列表（`GET /api/users/pending`）
- ✅ 批准用户（`POST /api/users/{user_id}/approve`）
  - 自动分配默认角色（operator）
  - 记录审批日志
- ✅ 拒绝用户（`POST /api/users/{user_id}/reject`）
  - 必须填写拒绝原因
  - 记录拒绝日志
- ✅ 用户审批页面（`/admin/users/pending`）

#### 3. 密码管理

- ✅ 密码重置功能（`POST /api/users/{user_id}/reset-password`）
  - 管理员可以重置用户密码
  - 支持指定新密码或生成临时密码
  - 重置后清除账户锁定状态
- ✅ 账户锁定机制
  - 5 次登录失败后锁定账户 30 分钟
  - 管理员可以手动解锁账户（`POST /api/users/{user_id}/unlock`）
  - 登录失败次数记录（`failed_login_attempts`）

#### 4. 会话管理

- ✅ 会话记录表（`user_sessions`）
  - 记录用户登录会话信息（设备、IP、登录时间、最后活跃时间）
  - 支持会话过期时间管理
- ✅ 会话管理 API
  - 获取活跃会话列表（`GET /api/users/me/sessions`）
  - 撤销指定会话（`DELETE /api/users/me/sessions/{session_id}`）
  - 撤销所有其他会话（`DELETE /api/users/me/sessions`）
- ✅ 会话管理页面（`/settings/sessions`）
  - 显示活跃会话列表
  - 当前设备标识
  - 登出此设备/登出所有其他设备

#### 5. 系统通知机制

- ✅ 通知数据模型（`Notification`表）
  - 通知类型：user_registered, user_approved, user_rejected, password_reset, account_locked, account_unlocked, user_suspended, system_alert
  - 支持未读/已读状态管理
  - 支持关联用户信息
  - **新增优先级字段**（high/medium/low）
- ✅ 通知 API
  - 获取通知列表（`GET /api/notifications`）- 支持分页、过滤和优先级排序
  - 获取分组通知列表（`GET /api/notifications/grouped`）- 按类型分组统计
  - 获取未读数量（`GET /api/notifications/unread-count`）
  - 标记已读（`PUT /api/notifications/{id}/read`）
  - 标记全部已读（`PUT /api/notifications/read-all`）
  - 删除通知（`DELETE /api/notifications/{id}`）
  - **新增快速操作 API**（`POST /api/notifications/{id}/action`）
- ✅ 自动通知触发
  - 新用户注册时通知所有管理员（高优先级）
  - 用户审批通过时通知用户
  - 用户审批拒绝时通知用户
  - 密码重置时通知用户
  - 账户锁定/解锁时通知用户
  - 账户被暂停时通知用户
- ✅ **WebSocket 实时通知**
  - JWT 认证的 WebSocket 连接（`/api/ws`）
  - 实时推送通知到用户
  - 心跳机制和自动重连
  - 连接数限制和速率限制
  - 降级到 HTTP 轮询
- ✅ **浏览器原生通知**
  - 通知权限管理
  - 桌面通知显示（可配置）
  - 通知偏好设置（`/settings/notifications`）
  - 内容验证和 XSS 防护
- ✅ **通知快速操作**
  - 从通知面板直接批准/拒绝用户
  - 完整权限验证和审计日志
- ✅ **通知分组和优先级**
  - 按类型分组显示通知
  - 高优先级通知特殊样式
  - 优先级筛选功能
- ✅ 前端通知组件
  - 顶部栏通知图标（带未读数量徽章）
  - 通知下拉面板（最近 10 条通知，带快速操作按钮）
  - WebSocket 实时更新未读数量
  - 通知列表页面（支持过滤、分页、批量操作、分组视图）

#### 6. 前端实现

- ✅ 登录页面（`/login`）
  - 支持用户名/密码登录
  - 账户状态检查（pending/rejected/suspended/inactive）
  - 账户锁定提示
  - Open Redirect 防护
- ✅ 注册页面（`/register`）
  - 用户注册表单
  - 密码强度提示
  - 注册成功提示
- ✅ 路由守卫
  - 登录状态检查
  - 权限验证
  - 公开路由处理

### 数据库变更

#### 新增字段（`dim_users`表）

- `status` (VARCHAR): 用户状态（pending/active/rejected/suspended/deleted）
- `approved_at` (TIMESTAMP): 审批时间
- `approved_by` (BIGINT): 审批人 ID（外键）
- `rejection_reason` (TEXT): 拒绝原因
- `failed_login_attempts` (INTEGER): 登录失败次数
- `locked_until` (TIMESTAMP): 账户锁定截止时间

#### 新增表

- `user_approval_logs`: 用户审批记录表
- `user_sessions`: 用户会话表
- `notifications`: 系统通知表

#### 数据库触发器

- 自动同步`status`和`is_active`字段

### API 变更

#### 新增端点

- `POST /api/auth/register` - 用户注册
- `GET /api/users/pending` - 获取待审批用户列表
- `POST /api/users/{user_id}/approve` - 批准用户
- `POST /api/users/{user_id}/reject` - 拒绝用户
- `POST /api/users/{user_id}/reset-password` - 重置用户密码
- `POST /api/users/{user_id}/unlock` - 解锁用户账户
- `GET /api/users/me/sessions` - 获取活跃会话列表
- `DELETE /api/users/me/sessions/{session_id}` - 撤销指定会话
- `DELETE /api/users/me/sessions` - 撤销所有其他会话
- `GET /api/notifications` - 获取通知列表
- `GET /api/notifications/unread-count` - 获取未读通知数量
- `GET /api/notifications/{id}` - 获取单个通知详情
- `PUT /api/notifications/{id}/read` - 标记单个通知为已读
- `PUT /api/notifications/read-all` - 标记全部通知为已读
- `DELETE /api/notifications/{id}` - 删除单个通知
- `DELETE /api/notifications` - 删除所有已读通知

#### 修改端点

- `POST /api/auth/login` - 增强用户状态检查、账户锁定检查、会话创建
- `POST /api/auth/refresh` - 更新会话`last_active_at`

### 错误代码

新增错误代码（4005-4010）：

- `4005`: AUTH_ACCOUNT_PENDING - 账号待审批
- `4006`: AUTH_ACCOUNT_REJECTED - 账号已拒绝
- `4007`: AUTH_ACCOUNT_SUSPENDED - 账号已暂停
- `4008`: AUTH_ACCOUNT_INACTIVE - 账号未激活
- `4009`: AUTH_ACCOUNT_LOCKED - 账号已锁定
- `4010`: AUTH_ACCOUNT_NOT_LOCKED - 账号未锁定

### 安全增强

- ✅ 统一错误消息（防止用户名/邮箱枚举攻击）
- ✅ 注册 API 限流（5 次/分钟）
- ✅ 账户锁定机制（5 次失败锁定 30 分钟）
- ✅ Open Redirect 防护（前端验证 redirect 参数）
- ✅ 会话管理（支持查看和撤销活跃会话）

### 测试

- ✅ 安全测试（限流、枚举攻击、权限绕过、Open Redirect、CSRF）
- ✅ 单元测试（注册 API、审批 API、登录 API）
- ✅ 集成测试（完整注册-审批-登录流程）

### 文档

- ✅ 用户注册指南（`docs/guides/USER_REGISTRATION_GUIDE.md`）
- ✅ 管理员审批指南（`docs/guides/ADMIN_APPROVAL_GUIDE.md`）
- ✅ 测试总结（`backend/tests/TEST_SUMMARY.md`）
- ✅ 测试指南（`backend/tests/README_TESTING.md`）

### 迁移说明

1. **数据库迁移**

   - 运行迁移脚本添加新字段和表
   - 确保`operator`角色存在
   - 创建数据库触发器

2. **现有用户处理**

   - 现有用户状态自动设置为"active"
   - `is_active`字段自动同步

3. **管理员账号创建**
   - 使用`scripts/create_admin_user.py`创建管理员账号
   - 默认管理员：用户名`xihong`，密码`~!Qq1`1`

### 已知问题

无

### 后续计划

- Phase 5: 通知机制（可选）
  - 新用户注册时通知管理员
  - 审批结果通知用户

---

## [v4.8.0] - 2025-12-29 - 数据采集模块异步化改造与 Python 组件集成

### 核心改造

#### 1. Python 组件异步化

- 将 38 个平台组件从同步转为异步 (`def run` -> `async def run`)
- Shopee 平台: 17 个组件 (login, navigation, orders_export, products_export 等)
- TikTok 平台: 12 个组件 (login, navigation, date_picker, shop_selector 等)
- Miaoshou 平台: 9 个组件 (login, navigation, export, overlay_guard 等)

#### 2. Python 组件适配层

- 新增 `modules/apps/collection_center/python_component_adapter.py`
- `PythonComponentAdapter` 类提供统一的组件调用接口
- 支持 `login()`, `navigate()`, `export()`, `call_component()` 方法
- 自动密码解密 (`EncryptionService.decrypt_password()`)

#### 3. Executor V2 重构

- 添加 `use_python_components = True` 配置开关
- 新增 `_execute_python_component()` 方法
- 新增 `_execute_with_python_components()` 完整执行流程
- 支持直接调用 Python 组件，跳过 YAML 解析

#### 4. 组件加载器增强

- 新增 `load_python_component()` 方法
- 新增 `validate_python_component()` 方法
- 新增 `list_python_components()` 方法
- 支持通过 inspect 模块读取组件元数据

#### 5. 录制工具优化

- 移除 Codegen 模式支持
- 统一使用 Inspector 模式 (`page.pause()` + Trace)
- 移除 `_launch_playwright_codegen_subprocess()` 函数

#### 6. TraceParser 增强

- 新增 `generate_python_skeleton()` 方法
- 支持从 Trace 文件生成 Python 组件骨架代码
- 新增 `generate_component_from_trace()` 便捷函数

### 数据同步对齐（v4.8.0 新增）

#### 7. 文件命名标准化

- 使用 `StandardFileName.generate()` 生成标准文件名
- 格式: `{platform}_{data_domain}[_{sub_domain}]_{granularity}_{timestamp}.xlsx`
- 与数据同步模块完全对齐

#### 8. 文件存储路径标准化

- 采集完成后移动文件到 `data/raw/YYYY/` 目录
- 数据同步模块仅扫描此目录
- 自动删除临时文件

#### 9. 伴生文件格式标准化

- 使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 文件
- 伴生文件与数据文件在同一目录
- 包含 `business_metadata` 和 `collection_info` 完整元数据

#### 10. 文件注册自动化

- 采集完成后自动调用 `register_single_file()` 注册到 `catalog_files` 表
- 添加注册失败的错误处理和日志

#### 11. Python 组件测试工具更新

- 更新 `tools/test_component.py` 支持 Python 组件加载和测试
- 更新 `tools/run_component_test.py` 支持 `.py` 文件路径
- 更新 `backend/routers/component_versions.py` 支持 Python 组件测试
- 新增 `test_python_component()` 和 `_test_python_component_with_browser()` 方法

### 组件管理功能完善（v4.8.0 第二阶段）

#### 12. YAML 组件清理

- 新增 `scripts/cleanup_yaml_components.py` 清理脚本
- 支持将 YAML 文件移动到 `backups/yaml_components_YYYYMMDD/`
- 支持禁用 ComponentVersion 表中的 YAML 记录
- 支持 `--dry-run` 预览模式

#### 13. Python 组件批量注册

- 新增 `scripts/register_python_components.py` 批量注册脚本
- 扫描 `modules/platforms/` 下所有 Python 组件
- 自动读取组件元数据并注册到 ComponentVersion 表
- 支持 `--platform` 和 `--dry-run` 参数

#### 14. 批量注册 API

- 新增 `POST /component-versions/batch-register-python` API 端点
- 返回注册统计和详细结果
- 支持指定平台过滤

#### 15. 组件录制工具保存逻辑更新

- `RecorderSaveRequest` 模型支持 `python_code` 和 `data_domain`
- 保存 Python 组件到 `modules/platforms/{platform}/components/`
- Python 代码语法验证（`ast.parse`）
- 更新覆盖逻辑：文件路径相同时更新现有版本

#### 16. 前端组件管理功能

- 添加"批量注册 Python 组件"按钮
- 版本列表显示组件类型（Python/YAML）
- 新增 `batchRegisterPythonComponents` API 方法

#### 17. 稳定版本唯一性保证

- 增强 `promote_to_stable()` 方法
- 自动取消相同 component_name 的其他稳定版本
- 自动取消相同 file_path 的其他稳定版本

### Windows 兼容性

#### 日志 Emoji 替换

- 创建 `scripts/verify_no_emoji.py` 验证脚本
- 替换 `modules/platforms/` 下所有 emoji 为 ASCII 符号
- 标准替换: [OK], [FAIL], [WARN], [SCAN]

### 新增文件

- `modules/apps/collection_center/python_component_adapter.py` - Python 组件适配层
- `scripts/async_component_transformer.py` - 异步改造辅助脚本
- `scripts/verify_no_emoji.py` - Emoji 验证脚本
- `scripts/cleanup_yaml_components.py` - YAML 组件清理脚本
- `scripts/register_python_components.py` - Python 组件批量注册脚本
- `docs/guides/PYTHON_COMPONENT_TEMPLATE.md` - Python 组件编写模板

### 修改文件

- `modules/apps/collection_center/executor_v2.py` - 添加 Python 组件支持 + 文件处理对齐
- `modules/apps/collection_center/component_loader.py` - 添加 Python 组件加载
- `backend/routers/component_recorder.py` - 移除 Codegen 模式 + Python 组件保存
- `backend/routers/component_versions.py` - 支持 Python 组件测试 + 批量注册 API
- `backend/services/component_version_service.py` - 增强稳定版本唯一性保证
- `backend/utils/trace_parser.py` - 添加 Python 骨架生成
- `tools/test_component.py` - 支持 Python 组件测试
- `tools/run_component_test.py` - 支持 Python 组件路径
- `frontend/src/views/ComponentVersions.vue` - 批量注册按钮 + 组件类型显示
- `frontend/src/api/index.js` - 批量注册 API 方法
- `modules/platforms/*/components/*.py` - 异步化 + emoji 替换

### 验收标准 (已完成)

1. [OK] 所有 38 个 Python 组件成功转为异步版本
2. [OK] executor_v2 支持 Python 组件执行
3. [OK] 登录组件使用统一的密码解密逻辑
4. [OK] Windows 控制台无 UnicodeEncodeError (核心组件)
5. [OK] 组件加载器支持 Python 组件加载
6. [OK] 录制工具仅支持 Inspector 模式
7. [OK] Python 组件支持调用子组件
8. [OK] Trace 解析器生成 Python 代码骨架
9. [OK] 文件命名使用 StandardFileName.generate()
10. [OK] 采集文件保存到 data/raw/YYYY/ 目录
11. [OK] 伴生文件使用 .meta.json 格式
12. [OK] 文件自动注册到 catalog_files 表
13. [OK] Python 组件测试工具可正常使用
14. [OK] 架构验证脚本通过

---

## [v4.16.0] - 2025-12-08 - 数据库架构统一和端口配置优化

### 🚨 重大修复

#### 1. 解决双数据库数据分散问题

- ⭐⭐⭐ **问题根因**：本地 PostgreSQL 18 和 Docker PostgreSQL 15 同时运行，数据分散在两个数据库
- ⭐⭐⭐ **数据迁移**：将本地 PostgreSQL 的所有数据（72.63MB）迁移到 Docker PostgreSQL
- ⭐⭐⭐ **端口统一**：使用 15432 端口（避开 Windows 保留端口 5433-5832）
- ⭐⭐⭐ **服务禁用**：永久禁用本地 PostgreSQL 服务，防止端口冲突

#### 2. 配置文件更新

- ✅ `.env` - POSTGRES_PORT=15432, DATABASE_URL 更新
- ✅ `env.example` - 端口配置示例更新为 15432
- ✅ `backend/utils/config.py` - 默认端口改为 15432
- ✅ `docker/postgres/init-tables.py` - 默认连接 URL 更新

#### 3. .env 文件编码修复

- ✅ 修复 UnicodeDecodeError 编码问题
- ✅ 确保 .env 文件使用 UTF-8 编码

### 📊 数据库状态（迁移后）

| Schema  | 表数量 | 说明                                |
| ------- | ------ | ----------------------------------- |
| a_class | 7      | A 类配置数据                        |
| b_class | 28     | B 类业务数据（含 26 个 fact\_\*表） |
| c_class | 4      | C 类计算数据                        |
| core    | 18     | 核心系统表                          |
| public  | 106    | 公共表                              |

### 🔧 连接配置

| 组件        | 主机                 | 端口  |
| ----------- | -------------------- | ----- |
| Python 后端 | localhost            | 15432 |
| Metabase    | host.docker.internal | 15432 |
| pgAdmin     | postgres             | 5432  |

### 📄 新增文档

- `docs/DATABASE_MIGRATION_COMPLETE.md` - 迁移完成报告
- `docs/DATABASE_ARCHITECTURE_PROPOSAL.md` - 架构提案和预防措施

### ⚠️ 注意事项

- 本地 PostgreSQL 服务已永久禁用（StartupType=Disabled）
- 云端部署时可根据需要调整 POSTGRES_PORT
- 所有组件必须连接到同一个 Docker PostgreSQL 实例

---

## [v4.15.0] - 2025-12-05 - 优化数据同步以适应实际工作场景 ⭐

### 🎯 核心优化

#### 1. 货币代码变体识别

### 🎯 核心优化

#### 1. 货币代码变体识别

- ⭐ **智能表头变化检测**：识别货币代码变体（如 BRL、COP、SGD），将其视为同一字段的不同变体
- ⭐ **字段名归一化**：在表头变化检测前，将货币变体字段归一化为基础字段名（移除货币代码）
- ⭐ **货币代码提取**：从字段名中提取货币代码，存储到`currency_code`系统字段（String(3)）
- ⭐ **数据存储优化**：
  - `raw_data` JSONB 中字段名归一化（不含货币代码）
  - `currency_code`字段存储货币代码
  - `header_columns`保留原始字段名（含货币代码）
- ⭐ **智能匹配策略**：
  - 如果只有货币代码差异，视为匹配（不触发变化检测）
  - 如果还有其他字段变化，正常触发变化检测

#### 2. 库存数据 UPSERT 策略

- ⭐ **UPSERT 策略**：对于库存数据域，使用 UPSERT（INSERT ... ON CONFLICT ... UPDATE）而非 INSERT ... ON CONFLICT DO NOTHING
- ⭐ **更新字段配置**：定义哪些字段在冲突时应该更新
  - 更新字段：`raw_data`, `ingest_timestamp`, `file_id`, `header_columns`, `currency_code`
  - 保留字段：`metric_date`, `platform_code`, `shop_id`, `data_domain`, `granularity`, `data_hash`
- ⭐ **数据域特定策略**：
  - `inventory`域：使用 UPSERT（更新而非插入）
  - 其他域（orders/products/traffic/services/analytics）：使用 INSERT（跳过重复）

### 📊 数据库变更

- ✅ 所有 `fact_raw_data_*` 表新增 `currency_code` 字段（VARCHAR(3), nullable=True, index=True）

### 🔧 技术实现

#### 新增文件

- `backend/services/currency_extractor.py` - 货币代码提取和字段名归一化服务

#### 修改文件

- `backend/services/template_matcher.py` - 表头变化检测（货币变体识别）
- `backend/services/data_ingestion_service.py` - 数据入库时提取和存储货币代码
- `backend/services/raw_data_importer.py` - UPSERT 实现和 currency_code 字段存储
- `backend/services/deduplication_fields_config.py` - 策略和更新字段配置

### ✅ 测试

- ✅ 货币变体识别测试（16 个测试用例全部通过）
- ✅ 表头变化检测测试（2 个测试用例全部通过）
- ✅ 去重策略配置测试（7 个测试用例全部通过）
- ✅ 性能测试（字段名归一化和货币代码提取性能影响<0.5%）

### 📈 性能影响

- **写入性能影响**：<0.5%（几乎可忽略）
- **查询性能提升**：10-100 倍（按货币筛选可以使用索引）

### 📝 文档

- ✅ 新增文档：`docs/V4_15_0_DATA_SYNC_OPTIMIZATION.md` - 完整的功能说明和使用指南
- ✅ 新增文档：`docs/V4_15_0_EMPTY_FILE_HANDLING.md` - 空文件处理策略说明

### 🐛 Bug 修复

#### 空文件处理优化

- ⭐ **提前检测空文件**：在读取文件后立即检测（第 239 行），避免后续不必要的处理
- ⭐ **成功标记**：空文件返回`success=True`，避免用户混淆（之前返回`success=False`导致前端显示"失败"）
- ⭐ **重复处理防护**：检查`[空文件标识]`，避免重复处理空文件
- ⭐ **状态管理优化**：区分空文件和重复数据，提供更准确的状态信息
- ⭐ **性能提升**：减少不必要的计算和数据库操作（规范化、数据清洗等）

### 🎯 成功标准

1. ✅ 货币代码变体不再触发表头变化检测（如果只有货币差异）
2. ✅ 货币代码正确提取并存储到`currency_code`字段
3. ✅ 字段名归一化正确（`raw_data`中字段名不含货币代码）
4. ✅ 库存数据更新而非重复插入（同一商品+仓库只有一条记录）
5. ✅ 其他数据域保持现有行为（orders/products 使用 INSERT 策略）
6. ✅ 向后兼容现有模板和数据
7. ✅ 性能不受影响（写入性能影响<0.5%，查询性能提升 10-100 倍）

---

## [v4.14.2] - 2025-11-27 - 重构 DSS 架构下的必填字段验证设计 ⭐

### 🔄 架构重构

#### 核心变更

- ⭐ **移除所有必填字段验证**：不再要求 product_id、platform_sku 等标准字段名
- ⭐ **只验证数据格式**：日期、数字等格式验证（如果字段存在且不为空）
- ⭐ **支持中英文字段名**：验证器同时支持中英文字段名（如"产品 ID"、"商品编号"等）
- ⭐ **允许空值**：PostgreSQL 支持 NULL 值，允许字段为空

#### 设计原则

1. 表头字段完全参考源文件的实际表头行
2. PostgreSQL 只做数据存储（JSONB 格式，保留原始中文表头）
3. 目标：把正确不重复的数据入库到 PostgreSQL 即可
4. 去重通过 data_hash 实现，不依赖业务字段名

#### 修改的文件

- `backend/services/enhanced_data_validator.py` - 重构`validate_inventory`函数
- `backend/services/data_validator.py` - 重构所有验证函数（orders、products、traffic、services、analytics）

#### 影响

- ✅ 数据不再因为缺少标准字段名而被隔离
- ✅ 支持任意格式的表头字段名（中文、英文、混合）
- ✅ 数据入库更加灵活，符合 DSS 架构设计原则
- ✅ 去重机制通过 data_hash 实现，不依赖业务字段名

### 📝 相关文件

- `backend/services/enhanced_data_validator.py` - 库存数据验证器（已重构）
- `backend/services/data_validator.py` - 其他数据域验证器（已重构）

---

## [v4.14.1] - 2025-11-27 - 删除字段映射审核模块，完全迁移到数据同步 ⭐

### 🗑️ 清理工作

#### 1. 删除字段映射审核模块

- ✅ **删除菜单项**: `frontend/src/config/menuGroups.js` - 移除 `/field-mapping` 菜单项
- ✅ **删除路由**: `frontend/src/router/index.js` - 移除 `/field-mapping` 路由定义
- ✅ **归档组件**: `FieldMappingEnhanced.vue` → `backups/20250131_field_mapping_audit/FieldMappingEnhanced.vue`
- ✅ **清理引用**:
  - `frontend/src/App.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/Header.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/SimpleHeader.vue` - 删除字段映射审核标题映射
  - `frontend/src/components/common/SimpleSidebar.vue` - 删除字段映射审核菜单项
- ✅ **修复跳转**: `frontend/src/views/DataBrowser.vue` - 将"跳转到字段映射审核"改为"跳转到数据同步-模板管理"
- ✅ **清理权限**: `frontend/src/stores/user.js` - 移除 `field-mapping` 权限
- ✅ **更新注释**: `frontend/src/api/index.js` - 更新废弃 API 注释

#### 2. 迁移说明

- ✅ **替代方案**: 所有字段映射审核功能已完全迁移到"数据同步-模板管理"模块
- ✅ **数据浏览器**: 字段映射跳转现在指向 `/data-sync/templates`
- ✅ **保留功能**: 字段映射辞典 API 和模板管理 API 仍然保留，供数据同步功能使用

### 📝 相关文件

- `backups/20250131_field_mapping_audit/FieldMappingEnhanced.vue` - 归档的字段映射审核组件
- `frontend/src/config/menuGroups.js` - 已删除字段映射审核菜单项
- `frontend/src/router/index.js` - 已删除字段映射审核路由
- `frontend/src/views/DataBrowser.vue` - 已更新跳转逻辑

---

## [v4.14.0] - 2025-02-01 - 清理 Superset 相关文件，迁移到 Metabase ⭐

### 🗑️ 清理工作

#### 1. 归档 Superset 相关文件

- ✅ **归档**: 35 个 Superset 相关文件已移动到`backups/20250201_superset_cleanup/`
  - Docker 配置: `docker-compose.superset.yml`, `superset_config.py`
  - 文档: 14 个 Superset 相关文档
  - 脚本: 13 个 Superset 相关脚本
  - SQL 文件: `create_superset_views.sql`, `refresh_superset_materialized_views.sql`
  - 代码文件: `backend/routers/superset_proxy.py`, `frontend/src/components/SupersetChart.vue`
- ✅ **更新**: `backend/main.py`移除 superset_proxy 路由引用
- ✅ **原因**: 项目从 Superset 迁移到 Metabase 作为唯一 BI 工具

#### 2. 移除 Streamlit 依赖

- ✅ **更新**: `requirements.txt`移除 Streamlit 相关依赖
  - 移除: `streamlit>=1.28.0`
  - 移除: `streamlit-aggrid>=0.3.0`
  - 移除: `streamlit-antd-components>=0.3.0`
  - 移除: `streamlit-option-menu>=0.3.6`
- ✅ **原因**: 项目已完全迁移到 Vue.js 3 前端，不再使用 Streamlit

### 📝 相关文件

- `backups/20250201_superset_cleanup/README.md` - 归档说明
- `requirements.txt` - 已移除 Streamlit 依赖
- `backend/main.py` - 已移除 superset_proxy 引用

---

## [v4.13.3] - 2025-11-22 - 修复数据流转显示问题：source_catalog_id 未设置 ⭐

### 🐛 Bug 修复

#### 1. 修复数据流转显示 Fact 层数据为 0 的问题

- ✅ **问题**: 数据已入库到 Fact 层，但数据流转显示 Fact 层数据为 0
- ✅ **原因**: `upsert_product_metrics`函数中`source_catalog_id`字段未正确设置，导致无法通过`source_catalog_id`查询 Fact 层数据
- ✅ **修复**:
  - `backend/services/data_ingestion_service.py`：在调用`upsert_product_metrics`前为每行数据设置`source_catalog_id = file_record.id`
  - `backend/services/data_importer.py`：在`upsert_product_metrics`函数中添加 fallback 逻辑，如果行数据中没有`source_catalog_id`，则使用`file_record.id`
- ✅ **数据修复**: 使用`scripts/fix_source_catalog_id_final.py`修复了 1092 条已存在数据的`source_catalog_id`字段
- ✅ **验证**: 数据流转 API 现在正确显示 Fact 层数据数量（1092 条）

### 📝 相关文件

- `backend/services/data_ingestion_service.py`：修复数据入库时的 source_catalog_id 设置
- `backend/services/data_importer.py`：修复 upsert_product_metrics 函数的 fallback 逻辑
- `scripts/fix_source_catalog_id_final.py`：数据修复脚本（修复已存在数据）

---

## [v4.13.2] - 2025-11-22 - 修复任务日志查询 API 的数据库字段错误 ⭐

### 🐛 Bug 修复

#### 1. 修复数据流转显示 Fact 层数据为 0 的问题

- ✅ **问题**: 数据已入库到 Fact 层，但数据流转显示 Fact 层数据为 0
- ✅ **原因**: `upsert_product_metrics`函数中`source_catalog_id`字段未正确设置，导致无法通过`source_catalog_id`查询 Fact 层数据
- ✅ **修复**:
  - `backend/services/data_ingestion_service.py`：在调用`upsert_product_metrics`前为每行数据设置`source_catalog_id = file_record.id`
  - `backend/services/data_importer.py`：在`upsert_product_metrics`函数中添加 fallback 逻辑，如果行数据中没有`source_catalog_id`，则使用`file_record.id`
- ✅ **影响**: 数据流转查询现在可以正确显示 Fact 层数据数量

---

## [v4.13.2] - 2025-11-22 - 修复任务日志查询 API 的数据库字段错误 ⭐

### 🐛 Bug 修复

#### 1. 修复 FactProductMetric.file_id 字段错误

- ✅ **问题**: 任务日志查询 API 返回 500 错误，提示`fact_product_metrics`表不存在`file_id`字段
- ✅ **原因**: `FactProductMetric`表使用`source_catalog_id`字段关联文件，而非`file_id`
- ✅ **修复**:
  - `backend/routers/auto_ingest.py`第 527 行：修复`get_task_logs`函数
  - `backend/routers/auto_ingest.py`第 627 行：修复`get_file_logs`函数
- ✅ **影响**: 任务日志查询和文件日志查询功能恢复正常

### 📝 相关文件

- `backend/routers/auto_ingest.py`：修复数据库查询字段
- `openspec/changes/improve-data-sync-reliability/BUGFIX_FactProductMetric_file_id.md`：Bug 修复文档

---

## [v4.13.1] - 2025-01-31 - 完成可选功能：数据流转可视化和丢失数据导出 ⭐

### ✅ 新增功能

#### 1. 数据流转可视化（100%完成）

- ✅ **ECharts 饼图可视化**: 在 FieldMappingEnhanced.vue 中添加数据流转可视化图表
  - 显示 Fact 层、丢失数据、隔离区的数据分布
  - 自动更新图表数据
  - 响应式布局支持
  - 窗口大小变化时自动调整

#### 2. 丢失数据导出功能（100%完成）

- ✅ **后端 API**: 添加`/api/raw-layer/export-lost-data/{file_id}`端点
  - 支持 orders/products/traffic/analytics/inventory 域
  - 导出为 Excel 格式（使用 pandas 和 openpyxl）
  - 包含丢失数据的详细信息
- ✅ **前端导出按钮**: 在对比报告中添加导出按钮
  - 当有丢失数据时显示导出按钮
  - 支持一键导出丢失数据到 Excel

### 📝 相关文件

- `backend/routers/raw_layer_export.py`：丢失数据导出 API 端点
- `frontend/src/views/FieldMappingEnhanced.vue`：数据流转可视化图表和导出按钮
- `frontend/src/api/index.js`：导出丢失数据 API 方法

---

## [v4.13.0] - 2025-01-31 - 提升数据同步可靠性 ⭐
