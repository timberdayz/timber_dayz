# Engineering Status

## Current State

- Repository workflow is `skill-first`
- Active flow is `superpowers` + `planning-with-files`
- `openspec/` is historical archive only
- Normal maintenance goal is to keep `main`, `origin/main`, and `cnb/main` aligned after synchronization work is complete
- Short-lived drift can still happen during active work or when only release tags are pushed

## Active Source Of Truth

- Rule entrypoint:
  - [`AGENTS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/AGENTS.md)
- Tool adapter:
  - [`CLAUDE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/CLAUDE.md)
- Detailed reference:
  - [`docs/DEVELOPMENT_RULES/README.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/DEVELOPMENT_RULES/README.md)

## Commission And Performance Caliber (2026-11-21)

提成与绩效工资的口径已归一，**每个数字只有一个真源**：

| 对象 | 真源 | 说明 |
|---|---|---|
| 提成公式 | [`backend/services/commission_caliber.py`](F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/commission_caliber.py) | 纯函数、无 DB 依赖；工资单 / 结算预览 / 店铺统计 / 月度结算单 / 确认校验全部调它 |
| 档位表 | [`backend/services/performance_coefficient.py`](F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/performance_coefficient.py) | `SCORE_BAND_COEFFICIENTS`（绩效工资唯一入口）/ `RANK_BAND_COEFFICIENTS`（赛马评级，仅展示） |
| 口径决策 | [`docs/adr/2026-11-21-commission-and-performance-caliber-layering.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/adr/2026-11-21-commission-and-performance-caliber-layering.md) | ADR |

最终口径：

- **提成 = max(可分配利润, 0) × 归属提成比**（零系数：赛马与绩效分数都不参与）；
- **绩效工资 = 绩效包 × 绩效分数档位系数**（纯个人，与店铺排名无关）。

工程约束：

- 新增任何提成计算**必须**调用 `commission_caliber`，不得就地复刻公式
  —— `backend/tests/test_commission_single_source.py` 会在绕开时阻断合并；
- 前端**只渲染**后端下发的金额。归属页的「改了还没保存」试算走
  `POST /api/hr/commissions/settlement-preview/estimate`，前端不再本地试算
  —— `frontend/tests/commissionFrontendNoRecompute.test.mjs` 守住这条；
- 页面文案禁用「结算系数」（它曾同时影响提成与绩效工资，现已完全分开）；
  赛马相关列名必须写全「赛马评级（不参与提成计算）」。

## B 类成本分析模块下线 (2026-11-28)

B 类成本分析（`/b-cost-analysis`）已**整体下线**，不再是系统的一部分。

下线原因（审查结论）：该模块自建成本口径与业务概览的真实利润口径不一致，
且**零消费方** —— 财务总览 / 月结 / 绩效 / 产品中心均不读它的任何输出。

- 业务概览的利润取妙手「利润(RMB)」黑盒列（`mart.shop_month_kpi.profit` →
  `finance.shop_profit_basis`），**不拆成本**；
- 本模块自拼 8 列重算，推算利润**每月虚高 2~4 倍**（如 2026-06：妙手 37,005.32
  vs 本模块 158,149.56）；
- `mart.b_cost_shop_month` 只被本模块自己的 3 个 api 视图读，3 个 api 视图只被
  本模块自己的 3 个端点读，3 个端点只被本模块自己的页面调用。

已移除的对象：

| 层 | 移除内容 |
|---|---|
| 前端 | `BCostAnalysis.vue` / `/b-cost-analysis` 路由 / 菜单项 / 3 个 `queryBCostAnalysis*` API 方法 |
| 权限 | 权限码 `b-cost-analysis`（系统权限目录 + manager / finance 默认角色） |
| 后端 | 3 个 `/api/dashboard/b-cost-analysis/*` 端点 / 路由前缀白名单项 / 3 个 `get_b_cost_analysis_*` service 方法 |
| SQL 资产 | `sql/mart/b_cost_shop_month.sql` + `sql/api_modules/b_cost_analysis_*_module.sql`（3 个） |
| 刷新链路 | `PIPELINE_DEPENDENCIES` 与 `SQL_TARGET_PATHS` 各 4 条登记 |
| 数据库 | 4 个视图由 `current_migrations/versions/20261245_drop_b_cost_analysis_views.py` DROP（可 downgrade 重建） |

保留：妙手导出侧「B 类成本」的业务定义仍然有效 ——
见 [`COST_DATA_SOURCES_AND_DEFINITIONS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/COST_DATA_SOURCES_AND_DEFINITIONS.md) §3。

守卫生效：
- `backend/tests/data_pipeline/test_refresh_registry_targets.py` 与
  `backend/tests/data_pipeline/test_atomic_materialized_views.py` 反向断言
  **b_cost 不在刷新链里**；
- `frontend/scripts/moduleSunsetUi.test.mjs` 断言路由 / 菜单 / API 层均无 b-cost 残留。

## CI Model

- Default GitHub `CI Pipeline` is change-scoped, not full-repository regression
- Python test job is aligned to `3.11`
- `black`, `ruff`, `bandit`, and secret scan only inspect changed Python files
- `pytest` only runs changed test files in default CI
- Integration-style validations that depend on full external environments should not be folded back into the default CI gate

Key files:
- [`ci.yml`](F:/Vscode/python_programme/AI_code/xihong_erp/.github/workflows/ci.yml)
- [`ci_changed_python_files.py`](F:/Vscode/python_programme/AI_code/xihong_erp/scripts/ci_changed_python_files.py)
- [`pyproject.toml`](F:/Vscode/python_programme/AI_code/xihong_erp/pyproject.toml)

## Release Model

- GitHub deployment remains tag-driven
- Production source of truth is release tags such as `vX.Y.Z`
- `origin/main` is not deployment truth by itself
- Release checklist lives in [`RELEASE_CHECKLIST.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/RELEASE_CHECKLIST.md)

## Deployment Status

- Production deploy flow is healthy
- SSH host key pinning is enabled
- `StrictHostKeyChecking=no` is no longer part of the active deploy flow
- Production compose is expected to read `${DATABASE_URL}` instead of hardcoded database credentials

## Current Non-Blocking Warnings

- Docker build workflows may still show Node 20 deprecation warnings from upstream Docker-maintained GitHub Actions
- Those warnings are currently upstream-action warnings, not repository logic failures
- **`main` 分支的 `Validate Data Flow` 工作流会因 `api.delete` 误报而变红** — **已修复 (2026-11-09)**
  - 现象: `Validate Frontend API Methods` 报「缺失方法调用: delete (2 处)」
    —— 出自 `frontend/src/domains/business/views/finance/ExpenseManagement.vue`
    的 `api.delete(...)` 调用。
  - 根因: `scripts/validate_frontend_api_methods.py` 把 `delete` 放进了
    `_JS_KEYWORDS`, 于是**方法定义**侧看不见
    `frontend/src/api/index.js` 里真实存在的 `async delete(path, config) {}`
    ⇒ 方法侧查不到、调用侧查得到 ⇒ 误报成「缺失」。
  - 为什么**不阻塞发布**: 部署流水线(`deploy-production.yml`)的同一道门禁按
    **「自上个 tag 起的变更文件」**扫描, 该文件不在变更集里 ⇒ 门禁通过。
    只有 `main` 分支的全量扫描工作流会命中。
  - **实际修法**: 没有采用「把 `delete` 从 `_JS_KEYWORDS` 去掉」这个最省事的写法 ——
    现有契约用例 `backend/tests/test_validate_frontend_api_methods_contract.py`
    断言 `delete (true) {` 这种「关键字 + 括号 + 块」形态**不得**被当成方法,
    直接去掉 `delete` 会打破该断言(即削弱既有守护)。
    改为: `delete` 仍留在 `_JS_KEYWORDS` 里, 但**只有紧跟 `async` 时**才按方法定义处理
    (真实写法是 `async delete(path, config = {}) {}`), 其余情形按关键字语句跳过。
    ⇒ 既有断言一条未动, 另新增 4 条守护用例(真方法被识别 / 运算符用法不被识别 /
    真实 API 文件含 `delete` / 真实前端调用不再报缺失)。
  - 效果: 已定义方法数 274 → 275, 缺失方法调用 2 → 0, 校验器退出码 0。
  - 原触发条件(已消除): 下次发布若变更集里包含 `api.delete(...)` 的调用方,
    部署门禁也会误报 ⇒ 现已修复, 该风险不再存在。
- **前端测试套件存在一批失败用例 (2026-11-09 实测 11 个)**
  - 范围: `node --test` 跑 `frontend/scripts/*.test.mjs`(102 个文件 / 331 个用例)
    ⇒ 320 通过 / 11 失败。
  - ⚠ 计数是**快照值**, 会随并行开发流变化 —— 记录时工作区正有 HR/结算域的
    改造在推进, 若干失败属于那些改造的中间态。**性质与修法**才是本条的重点。
  - 分布: `domainBridgeInventory` / `employeeTargetAllocation` / ~~`bCostAnalysisUi`~~ /
    `collectionApiContract` / `employeeTaskRoutes` / `collectionEntryPointsContract` /
    `collectionTaskVerificationRecoveryUi` / `myFollowInvestmentIncomeView` /
    `shopAssignmentRules`(文件级崩溃)。
  - ~~`bCostAnalysisUi`~~ 已于 2026-11-28 随 B 类成本分析模块下线一并删除
    (`frontend/scripts/bCostAnalysisUi.test.mjs`)，不再参与测试套件。
  - 性质: **测试与当前源码不同步**, 不是本轮引入:
    - `shopAssignmentRules.test.mjs`: `src/domains/business/views/hr/shopAssignmentRules.js`
      已不再导出 `calculateAllocatableProfit` ⇒ 源码重构后测试没跟上;
    - `myFollowInvestmentIncomeView.test.mjs`: 断言页面含「店铺ID」, 而页面文案已演进;
    - 其余为断言值与当前实现不一致。
  - 为什么**不阻塞发布**: CI 的 `frontend-guard` job 只跑
    `scripts/ci_frontend_test_silence_gate.py`(只报警"压根没跑起来"的哑测试),
    **不执行前端测试本身** ⇒ 这 11 个失败不会让流水线变红。
  - 修法: 逐个核对源码现状后更新断言 —— 必须区分「断言过时」与「真实功能缺失」,
    改错就会把真 bug 变成绿灯 ⇒ 属宽泛重构, 按 `AGENTS.md` 的
    「非阻塞技术债记录而不顺手修」留到 V2 重建时处理。
  - 同批已修: `frontend/scripts/dataSyncSemanticRegistry.test.mjs` 原本也在失败
    (断言 `domainAliasIndex.orders.买家支付` 与字典口径冲突), 已于 2026-11-09 修复。
- **`backend/tests/data_pipeline/test_postgresql_dashboard_service.py` 单跑会失败 (2 个用例)**
  - 现象: 单独跑该文件 ⇒ 2 failed; 放进全量 `backend/tests` 跑 ⇒ 通过
    (实测 `temp/junit_b10.xml` 里该文件失败数 = 0)。
  - 根因: 测试隔离库由 `backend/tests/conftest.py` 用 `Base.metadata.create_all` 建出,
    **不跑 `current_migrations`** ⇒ 迁移产物缺失:
    `finance.employee_labor_cost_allocations` 表不存在、
    `a_class.operating_costs.total_amount` 列不存在。
    全量跑时另一个用例先在同一 session 库执行了迁移, 才把这两处补上。
  - 影响: 只影响**单独调试**该文件; CI 与本地全量回归都绿。
  - 修法: 需要让 conftest 的隔离库也跑迁移链 —— 中等侵入, 且可能与
    `create_all` 冲突 ⇒ 同样留作 V2 处理。
- **同步模板的同步只覆盖了 6 张表里的 1 张 (2026-11-09 实测)**
  - 模板是**运行时数据**(6 张表), 不在 git ⇒ 开发改了模板,
    生产/采集环境**不会自动跟上**; 数据侧另有自动通道
    (`cloud sync` worker, 5 秒轮询), 但它只推**业务数据**, 不推模板。
  - `scripts/sync_templates_to_cloud.ps1` 只 `pg_dump -t field_mapping_templates`
    **一张表**, 而:
    - 254 个模板里只有 66 个带 `header_bindings`、119 个带 `header_columns`;
    - **4748 条**「原始列 → 标准字段」映射在 `field_mapping_template_items` 里 ⇒ 未同步;
    - `families` / `versions` / `variants` / `collection_config_templates` 也都未同步。
  - 同步脚本末尾只校验 `COUNT(*)`, 行数对得上就算成功 ⇒ **漏掉的映射没人知道**。
  - 已补 `scripts/diff_templates.py`(只读): 按**业务键 + 内容指纹**逐条比对 6 张表,
    有差异退出码非 0 ⇒ 可直接当门禁用。已用临时库验证能检出
    「内容不同 / 仅源有 / items 缺失」三类差异, 并配 8 条契约用例锁住
    (只读保证 / 键与指纹不含 id 与时间戳 / 6 张表都在比对范围内)。
  - 待办(**需连生产验证, 尚未动手**): 把 `sync_templates_to_cloud.ps1` 的 dump 范围
    补齐到 6 张表, 并把校验从 `COUNT(*)` 升级为内容级比对。
  - 附带发现: `field_mapping_template_items` 里有 **740 条孤儿**
    (`template_id` 指向已删除的模板); 主表 254 行只有 199 个不同 `template_name`
    (模板族按版本并存) ⇒ 任何按 id 或按模板名做的跨库比对都会失真, **必须用业务键**。

## Retired Modules

- **跟投模块 (follow investment) — 已下线 (2026-11-21)**
  - 业务确认无真实投资人，跟投收益试算 / 跟投记录 / 结算台账整体下线。
  - 前端已摘除：`MyFollowInvestmentIncome.vue` 页面、路由 `/my-follow-investment-income`、
    对应菜单项与显示名、`frontend/src/api/finance.js` 的 10 个跟投 API、
    `frontend/src/stores/financeSettlement.js` 的 4 个跟投切片与 9 个跟投 action；
    `investor` 角色、`'投资人': 'investor'` 映射与 `my-follow-investment-income` 权限点同步摘除。
  - 结算中心（`/financial-management`）内的跟投子视图一并摘除；该页面**已改造完成**为
    只读「月度利润看板」（2026-11-21，见下条），设计与实施计划见
    [`2026-11-21-finance-profit-dashboard-design.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/superpowers/specs/2026-11-21-finance-profit-dashboard-design.md)。
  - 验收清单
    [`FOLLOW_INVESTMENT_AND_SETTLEMENT_ACCEPTANCE_CHECKLIST_2026-05-30.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/FOLLOW_INVESTMENT_AND_SETTLEMENT_ACCEPTANCE_CHECKLIST_2026-05-30.md)
    已整份标注作废。

- **月度利润结算中心 → 只读「月度利润看板」(2026-11-21，同批改造)**
  - 模块**保留但彻底瘦身**：从「会自己算钱的审批表单」改成「只呈现已发生事实的只读看板」。
    看板只回答一句话 —— 这个月赚了多少、分给员工多少、人工调整多少、留下多少。
  - **不再生产金额**：预算制（3 个目标比例 + 3 个目标额 + 差异告警）、审批制、快照冻结
    全部下线；后端**不重命名**（受上线前规则约束），重命名降级为 post-launch V2 治理项。
  - **口径修正三处**：① 人员成本重复扣减（`total_cost` 减掉了利润基数里已扣的固定工资）；
    ② 公司人力成本池二次扣减；③ 人员成本查询缺 `calculation_version` 版本过滤。
    ⇒ **切换后所有历史月份的公司留存数字都会变化（是修正，不是回归）**，
    上线说明必须附「口径切换前后同月对比」。
  - **看板唯一写入口 = 人工调整项**（原因必填，服务端 default 兜底已拆）；每店维度的唯一
    合法来源是 `finance.employee_labor_cost_allocations`。
  - 口径真源：指标词典 `docs/team-skills/sea-metrics-language/`（正本）+
    `scripts/verify_team_skills_sync.py` 机器校验；上线前只读体检脚本
    `scripts/check_monthly_profit_dashboard_readiness.py`。

## Practical Guidance

1. Do not revert default CI back to full-repository lint/test scanning
2. Keep release operations tag-driven
3. Keep repository-specific constraints in `AGENTS.md`, not ad hoc workflow comments
4. When a future session investigates CI failures, inspect the latest GitHub Actions run first before changing rules
