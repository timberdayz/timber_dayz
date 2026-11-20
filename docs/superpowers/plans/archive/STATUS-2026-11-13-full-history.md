> ⚠️ **这是归档件，不是当前状态索引。**
>
> 当前状态索引在 `docs/superpowers/plans/STATUS.md`（瘦身后约 250 行）。
> 本文件是 **2026-11-13「批次 F-2 台账瘦身」时被整体移出的历史记录**：
> 下方正文是瘦身前 `docs/superpowers/plans/STATUS.md`（commit `cb953b59`）的
> **逐字节副本，零删改**，只在这一段提示之前加了说明。
>
> - 瘦身前行数：**1,659 行 / 27 个章节**
> - 正文 SHA-256（不含本提示块）：`364EFC16D104E748DAEAB312D06022EA36BFF3D7E16A20467031FF07E31DE104`
> - 为什么归档：STATUS.md 当时是「当前未结 + 历史流水账」的混合体，每上一个批次
>   就往里追加一大节 ⇒ 真源被淹没（律 1 被稀释）、且台账自己成了「越做越重」的证据。
> - 归档规则与守护见 `docs/superpowers/plans/STATUS.md` 的「台账瘦身约定」节，
>   守护文件 `backend/tests/test_status_index_slim_contract.py`。

# Plans Status Index

This file exists to keep plan state consistent and easy to hand off.

## Project Simplification (Phases 1–6)

- Phase 1: `docs/superpowers/plans/2026-04-30-project-simplification-phase1-plan.md` — **complete**
- Phase 2: `docs/superpowers/plans/2026-05-04-project-simplification-phase2-domain-registration-plan.md` — **complete**
- Phase 3: `docs/superpowers/plans/2026-05-05-project-simplification-phase3-service-and-shared-boundaries.md` — **complete**
- Phase 4: `docs/superpowers/plans/2026-05-05-project-simplification-phase4-frontend-domain-reorg.md` — **complete**
- Phase 5: `docs/superpowers/plans/2026-05-05-project-simplification-phase5-schema-ssot-decomposition.md` — **complete**
- Phase 6: `docs/superpowers/plans/2026-05-05-project-simplification-phase6-closure.md` — **complete**

Closure inventory:
- `docs/superpowers/findings/2026-05-05-phase6-closure-inventory.md`

## Shop Identity & Session Reuse (2026-11)

- Batch 1: `docs/superpowers/plans/2026-11-01-shop-identity-and-session-reuse-batch1.md` — **complete**
- Batch 2: `docs/superpowers/plans/2026-11-01-shop-identity-and-session-reuse-batch2.md` — **complete**
- Spec: `docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md`

Scope: 巡店会话复用（一账号一巡店窗口、会话新鲜度以 `saved_at` 为准、人工会话落盘）
与店铺身份治理（别名规范化、候选唯一才归属、内部标准名、改名联动、区域感知匹配）。

Live deployment verified:
- `current_migrations/versions/20261101_shop_identity_region_and_code.py` 已应用
  （live 版本戳 `current_schema_20261101_shop_identity_region_and_code`）
- 语义层 47 个视图经 `scripts/rebuild_views.py` 重建 + MATVIEW 刷新；
  `fact_orders_atomic` 43 列 / `fact_analytics_atomic` 34 列 /
  `fact_orders_monthly_atomic` 18 列 / `fact_analytics_monthly_atomic` 22 列
- 存量回填：`core.shop_accounts.internal_code` 52/52、
  `public.catalog_files.shop_account_id` 460/460（原 87）
- 存量归属不变：tiktok 行数 `2473 / 1448 / 505 / 289 / 124 / 90 / 75`（与改造前基线一致）

### 语义层一致性收尾（2026-11-01）

现象：`semantic.fact_analytics_monthly_atomic` 在 live 上是 20 列，仓库文件是 22 列。

根因（不是视图定义写错，是**运行期代码栈与库不同步**）：
- 本地常驻栈 `xihong_erp_celery_worker` / `xihong_erp_celery_beat` 以
  bind mount 方式挂载 **main 工作区** 的 `sql/` 与 `backend/`，跑的是 main 的代码；
- `backend/tasks/refresh_queue_tasks.py` 的 `dashboard_refresh_safety_net`
  （celery beat 每 5 分钟）检测到看板资产漂移后重建视图，用的是 **main 的旧 SQL 资产**：
  - `sql/semantic/analytics_monthly_atomic.sql`（旧版 20 列）→ 把 live 从 22 列改回 20 列；
  - `sql/semantic/shop_identity_resolution_candidates.sql`（旧版 7 列）→
    对 live 上已升级为 8 列的候选视图做 `CREATE OR REPLACE VIEW` →
    `cannot drop columns from view` → 该目标 skipped，流水线 `partial_failed`；
- 于是形成「每 5 分钟回退一次 + 持续报错」的循环（`ops.pipeline_run_log` 15:16–15:36 可查）。

处置（已完成）：
1. 把分支的 7 个 `sql/semantic/*.sql` + `backend/services/data_pipeline/refresh_registry.py`
   同步到 **main 工作区**（`git checkout feature/shop-identity-batch1 -- <paths>` +
   `git reset -- <paths>`，**未提交、未暂存**）。常驻栈因此改用分支的视图定义，
   不再回退、也不再报错；分支合并后 main 工作区会自动变干净。
2. 用分支资产重建 `semantic.fact_analytics_monthly_atomic` → 恢复 22 列；
3. 执行 `scripts/bootstrap_postgresql_dashboard.py --module all` 对齐资产指纹，
   `ops.dashboard_asset_state` 两个模块均回到 `status=ready`、指纹一致。

注意：main 工作区当前有 8 个未提交的 modified 文件（上述 7 个 SQL + 1 个 registry），
这是**部署态**而非分支改动；`git checkout -- sql/semantic backend/services/data_pipeline/refresh_registry.py`
即可回退，但回退后常驻栈会重新把 live 降回 20 列。

### 分支引入的测试夹具回归（已修，commit `be62d2d8`）

- 现象：候选视图（Task 17）新增 `core.shop_accounts.shop_region` /
  `core.shop_account_aliases.shop_region` 依赖后，三个 data_pipeline 测试的**夹具表缺列**，
  创建视图直接失败 → 共 8 条 failed。
- 修复：三个夹具补 `shop_region` 列；`test_b_cost_analysis_semantic_sql.py`
  补建候选视图；`test_granularity_alignment_sql.py` 补一条可唯一归属 `shop-a` 的
  `shop_accounts` 行（计划口径「候选唯一才归属」，候选 0 → `unknown`）。
- 结论：这三个文件由 8 failed 转为全绿。
- ✅ **那条「仍有 2 条失败」的记录已过期（2026-11-13 复核）**：
  本地实测 `backend/tests/data_pipeline/test_granularity_alignment_sql.py` → **7 passed / 0 failed**。
  两条各有各的归宿，不是被忽略：
  `test_shop_month_kpi_does_not_fallback_to_daily` 的断言随薄封装改读 MV 而**修复**；
  `test_annual_summary_shop_month_does_not_force_missing_costs_to_zero` 随
  `sql/mart/annual_summary_shop_month.sql` 退役而**用例被删**（提交 `f34eee24` 退役清理时一并处理）。
- ⚠ **但新的覆盖缺口由此暴露**：`backend/tests/data_pipeline/`（130 个文件）**不在 CI 覆盖范围内**
  ——CI 只跑「改动文件 + `tests/unit` + 根 `tests/` 无 DB 子集」，
  `deploy-production.yml` 只额外跑 3 个库存文件做发布门禁。
  ⇒ 上面这 7 条绿是**本地跑出来的，不是 CI 守住的**。

### 发布（v7.12.6，2026-11-02）—— 已上线

- 分支以 `--ff-only` 合并进 main（main @ `7d43a43f`，50 commits / 63 files / +11667 −310），
  `scripts/sync_main_mirrors.ps1 -Sync` 已把 main 同步到 **GitHub + CNB 双远端**
  （`XIHONG_GIT_MIRROR_SYNCED=7d43a43f`），未使用单远端 push / force push。
- tag `v7.12.6` 已推送到 GitHub 与 CNB，触发 GitHub Actions「Deploy to Production」
  run `41330766206`，**全部作业 success**。
- **local_console 启动失败的根因已消除**：live 版本戳
  `current_schema_20261101_shop_identity_region_and_code` 现在落在
  `get_supported_current_revisions()` 支持链的 head 上，
  `scripts/run_current_schema_migrations.py --preflight-only` 返回
  `[OK] Current-schema preflight passed: upgrade`。
- 发布前门禁：后端 26 文件总验收 **318 passed**；
  `scripts/verify_release_local.py --skip-build` **exit=0**
  （fresh-db 迁移 + 迁移后 ORM Schema 一致性 + 云同步验证 + compose config + 部署前检查）；
  前端 `npm run build` exit=0，`collectionTasksStatusUi` 6/6。
- 生产部署核对（run 日志 + 站点探测）：
  - Phase 1.5 只读预检通过；Phase 2 `[OK] Current-schema migration action completed: upgrade`
  - schema gate：`current_revision == head_revision == current_schema_20261101_shop_identity_region_and_code`，
    `missing_tables` / `missing_columns` 皆空
  - Phase 2.6 `[OK] PostgreSQL Dashboard assets are ready`
  - Phase 2.7 `[OK] Dashboard view definitions rebuilt`；Phase 2.7b `[OK] rebuilt view definitions present`
  - Phase 3a `[OK] Inventory age full rebuild completed`；Phase 3a' `[OK] Inventory state full rebuild completed`
  - backend healthy、celery worker + celery beat 已启动、nginx `/health` 通过、
    `[OK] Application cutover completed. Tags: Backend=v7.12.6, Frontend=v7.12.6`
  - 站点探测：`/api/health` 与 `/healthz/ready` 均返回 `version=v7.12.6`、
    `database=connected`、`dashboard=ready`
- **关于「Phase 2.7 只重建了 `api.clearance_ranking_module`」**：本次改动的 7 个
  `sql/semantic/*` 资产**确实生效了**。MV 重建用 `DROP MATERIALIZED VIEW ... CASCADE`
  把依赖它们的整层看板视图连带清空，随后的 bootstrap 把 47 个目标全部重新执行
  （部署日志里 **0 条「跳过重建」、0 条失败**），因此生产视图定义与仓库一致。
- **遗留的发布工具缺口（不阻塞本次发布）**：Phase 2.7 的重建目标清单写死为
  `api.clearance_ranking_module`，并未按 `sql/` 差异自动计算，而
  `RELEASE_CHECKLIST.md` 声称「改了 `sql/` 的视图部署会自动重建」。本次靠 CASCADE
  连带重建兜住了，但这是运气不是机制 —— 后续应把目标清单改成按 tag 差异计算。
- **重复入账边界（务必知悉）**：`data_hash` 口径由 `scope:shop_id` 切到
  `scope:shop_account_id`，已入库文件的 hash 失效；自动入库只处理 `status='pending'`，
  历史月份已入库文件不会被自动重入库，因此本次**不做生产事实层全量重建**。
  唯一例外：**严禁对历史月份文件手动重触发 ingest**（会重复入账），
  确需重采请先按文件粒度 delete 再重扫重入库。

### 发布（v7.12.7 ~ v7.12.9，2026-11-03 ~ 11-04）—— 均已上线

三次发布连成一条线：**v7.12.7 出事故 → v7.12.8 修根因 → v7.12.9 第二轮收尾**。

#### v7.12.7（2026-11-03）—— 事故

- **现象**：celery-worker / celery-beat 上线即崩溃循环，日志是 `kombu.exceptions.VersionMismatch`。
- **根因**：`kombu` 从 5.6.2 漂到 **5.7.0**；而 `kombu 5.7.0` **硬性要求 `redis-py>=6.1.0`**，
  与仓库钉死的 `redis==5.0.1` 直接冲突。**pip 安装期不报错**（两个包各自都装得上），
  只有 celery 真跑起来才炸 ⇒ 典型的「依赖漂到运行时才暴露」。
- **决策（用户拍板）**：**只修根因，不回退**。

#### v7.12.8（2026-11-03）—— 根因修复，已上线

- commit `c957ad5`，注解 tag `v7.12.8`（tag 对象 `abd41a14`），已推 GitHub + CNB。
- 做法：传递依赖全部**钉死** + 新增**镜像依赖门禁**（构建期比对镜像内实际版本 vs 清单）
  + CI 增加 **celery 冒烟**，让这类运行时不兼容能在 CI 里提前暴露。
- 生产验收通过。

#### v7.12.9（2026-11-04）—— 第二轮收尾，已上线

- 3 条提交，一一对应用户拍板的三项内容，可独立回退：
  `a044f46b` fix(deps) / `f34eee24` refactor(退役) / `ff33dff7` feat(监控)。
- 注解 tag `v7.12.9`（tag 对象 `0aba36b7`），已推 GitHub + CNB
  （**先 GitHub 触发部署，再 CNB 出镜像**，保持 CNB 永不领先 GitHub）。

**1) 彻底清理 5 个退役模块**（店铺分析 / 店铺管理 / 财务报表 / 汇率管理 / 会计期间）

- 前端：路由、菜单、权限、组件、API 封装全删；生产 bundle 里 10 个退役标识 **0 匹配**。
- 后端：删 store-analysis 路由（7 条）+ `annual_summary` 方法与 SQL 资产；
  删 Metabase 时代的死 stub router `backend/routers/dashboard_api.py`；
  权限目录 **59 → 54**，系统角色默认权限同步收敛
  （`ensure_system_roles()` 启动时自动对齐已有角色，**无需手工改生产库**）。
- 生产库：清掉 9 个僵尸目标（14 条血缘边 + 9 条新鲜度记录）。**先清理后上线**，
  避免新监控把已退役对象报成 missing。

**2) 依赖单一真相源**

- 新增 `requirements.lock.txt`：**116 个包**的完整传递依赖闭包，全部 `==`
  （取自生产 v7.12.8 实测 `pip freeze`）。
- `requirements.txt` 收敛为 **51 项**运行时直接依赖；`requirements-dev.txt` 补全；
  **删除 `backend/requirements.txt`**（它与根清单有 26 个包互相矛盾，正是 v7.12.7 漂移的源头）。
- 镜像改**单步** `pip install -r requirements.lock.txt`（不再分两步互相覆盖）。
- 门禁 `verify_image_dependency_pins.py` 基线 7 → 116 且**从 lock 自动推导**，
  另加「禁止浮动范围 / 必须单步安装 / 镜像内无锁外包」三项检查。

**3) 监控存在性校验**

- `/freshness` 新增 `object_exists` / `recorded_status` / `status="missing"` / `missing_targets`；
  `/lineage` 新增 `target_object_exists` / `source_object_exists` / `missing_objects`。
- 逻辑目标别名（`semantic.alias_registry` → `semantic.semantic_field_aliases`）登记在册，
  并用**守护测试**强制新逻辑目标必须登记，否则会把活目标误报成 missing。

**4) 回归判定**

- 后端全量：151 failed / 4639 passed / 30 errors / 12 skipped。
- 把 **181 个失败用例 ID** 拿到 HEAD worktree **逐个重跑**对照 ⇒ **0 个新增失败**
  （唯一"差异"用例在 HEAD 上失败一模一样，是既有的环境变量污染，不是本次回归）。

**生产验收（全部通过）**

| 检查项 | 结果 |
| --- | --- |
| 5 个容器 | backend-api / celery-worker / celery-beat / frontend / nginx 全 running，镜像均 v7.12.9 |
| 重启次数 | 全部 **0** |
| API 版本 / 路由数 | v7.12.9；619 → **612**（正好少 7 条 store-analysis） |
| dashboard 状态 | `ready`；迁移 head 不变 |
| 新监控 freshness | **47 个目标，missing = []** |
| 退役权限目录 | 59 → **54**，`retired_still_present = []` |
| store-analysis 端点 | **[]**（生产 openapi 零匹配） |
| 库存积压 `unknown_restock_row_count` | **0**（视图与底表交叉核对一致） |
| SKU 级滞销清单 / 店铺月度滞销榜 | **513 行 / 165 行** |

**本轮附带发现（非阻塞，已记入 V2 清单）**：库存积压看板的**库龄分档与业务定价档位没对齐** ——
看板分档 `<30 / 90~180 / >=180`（30~90 天无档），业务定价档 `0 / 60 / 90 / 120`；
生产实测 **167 个 SKU（货值 47,430）已被业务判为「滞销30天」**，在看板风险分层里却显示
`中度 0 / 重度 0 / 活跃 30`，另有 321 行（货值 150,756，占总货值 63%）两套体系都不落点。
**数据是对的，只是展示分档不一致** ⇒ 按 `AGENTS.md` 记入 post-launch V2 清单，
本轮不改口径。详见 `docs/guides/VERIFICATION_MATRIX.md`。

### 临时/测试内容清理（2026-11-02）

已清理：

- `%TEMP%` 下 47 个 `probe_*.py` / `erp_*.py` 临时探针脚本
- 3 个旧 worktree（`baseline-check` / `baseline-refresh-queue` / `verify-frontend-baseline`）
  及本任务自身的 `.worktrees/shop-identity-batch1` 与已合并分支 `feature/shop-identity-batch1`
- `temp/` 下 19 个测试产物目录、`temp/outputs/` 下 45 个历史报告文件
- `logs/` 下 400 个历史前端启动日志
- 4 个已停止的遗留容器（`goofy_hopper` / `xihong_erp_backend_collector` /
  `xihong_erp_backend_api` / `xihong_erp_migrate`）
- 13 个历史遗留镜像（`release-publish-20260916-*`、`xihong-erp-backend-smoke:*`、
  `codex-cloud-sync-runtime-ops-*`、`xihong_erp-backend-collector:latest`、
  `xihong_erp-backend:latest` 及 4 个 `<none>` 悬空镜像）

主动保留：

- 业务数据：`temp/outputs/` 的 412 个 xlsx/xls、`data/raw` 914 个文件
- 命名持久卷：`xihong_erp_*`、`docker_*`
- 运行中容器与 `logs/backend-local.out.log` / `.err.log`（本地后端仍在写）
- 回滚锚点镜像：`xihong_erp-backend:deploy-20260531`、`xihong_erp-frontend:deploy-20260531`、
  `xihong_erp-celery-worker:latest`、`xihong_erp-celery-beat:latest`（运行中在用）

**未清理（受安全策略拦截，需人工执行）**：

- ~~11 个 testcontainers 遗留的 postgres 匿名悬空卷。`docker volume rm` 被本地安全策略
  判定为不可逆销毁而拦截，需在 Docker Desktop 里手动清理~~ ——
  **已于 2026-11-13（批次 E-1）清理完毕**：11 个匿名卷全删、0 失败；
  13 个具名卷（含 `xihong_erp_postgres_data`）完好无损。
  复发风险已由 E-2（清理接进 pytest 会话收尾 + CI 步骤）与
  E-3（40 处 testcontainers 收敛成一个会话级容器）从根上消掉。
  详见下方「批次 E」。

### 待业务确认（不阻塞实施）

- `3c店` 冲突取舍
- 两个 disabled 主账号是否启用
- TikTok 三店改名归属（含疑似历史误录 `TK新加坡1店`）
- `platform='验证码测试账号'` 脏行处理（当前保留并已分配 internal_code）
- 10 个文件命中已停用账号 `shopee_sg_chenewei666_local` 是否接受回填

### 运营提示

- ~~Task 13 让「30 天过期」真正生效，需知会运营。~~ —— **已作废**：该 Task 13
  实现的是**会话文件**（`data/sessions/**`）的 30 天过期门禁，而会话文件体系已被
  「Session Profile-Only Architecture」整体废除（见上方条目），30 天门禁随之下线，
  **无需再知会运营**。本机 `data/sessions/` 残留的 19 个会话文件也不再被任何代码读取；
  磁盘清理已于 2026-11-03 完成（`data/sessions/` → 备份 → 观察 → **备份已按用户决定
  提前销毁**；另清 17 个店铺级孤儿 profile 目录、1 个已停用主账号目录与
  `data/session_profiles/`）。

## Session Profile-Only Architecture (2026-11)

- Plan: `docs/superpowers/plans/2026-11-02-collection-profile-only-architecture.md`
- Spec: `docs/guides/COLLECTION_SESSION_LIFECYCLE.md` (v3.1)

## Shop Identity Future-Proofing & Observability (2026-11)

- Plan: `docs/superpowers/plans/2026-11-10-shop-identity-future-proofing-and-observability.md`
- 触发：采集机交来的 10 项问题单（`docs/` 外的采集机本地报告）→ 本地主干逐项复核
- 业务决策（2026-11-10）：**沿用 2026-11-06 决定 —— 只保未来，历史数据不修**

批次 1（代码加固，走 PR）已完成，7 笔提交，PR **#3**：
`https://github.com/timberdayz/timber_dayz/pull/3`
（分支 `feature/2026-11-10-shop-identity-future-proofing`，base `main` @ `eece117a`，7 commits / 13 files）

| 项 | 提交 | 内容 | 状态 |
|---|---|---|---|
| 1.1 | `4aa5d8ad` | 入库收敛信号优先级 → `shop_account_id` 优先（与 SSOT / 语义层候选池对齐） | ✅ |
| 1.2 | `bccdb889` | 采集导出路径的**反向**守护（主数据取不到编号 ⇒ 绝不回退 `cnsc_shop_id`） | ✅ |
| 1.3 | `88504f70` | `--check --json` 序列化加固（datetime/date/Decimal 归一化收敛到一个入口） | ✅ |
| 1.4 | `570bbc43` | celery 注入 `CLOUD_DATABASE_URL` + 容器内回环地址重写（**只在容器里**重写） | ✅ |
| — | `07c56053` | 方案文档 + 本索引条目 | ✅ |
| — | `6d356743` | STATUS 补 PR 链接、订正验证数字 | ✅ |
| — | `1c3f6a76` | 纯排版：compose 守护用例按 CI 侧 black 换行（见下方「已知坑」） | ✅ |

验证：目标测试集 **197 passed**；`scripts/diff_pytest_junit.py` 判定 **NEW failures = 0**（ADDED 45 条，1 条改名 `test_numbering_wins_over_label` → `test_account_id_wins_over_platform_number`）。

**已知坑（CI 格式门禁）**：CI 的 `test` job 跑在 **Python 3.11**（`ubuntu-latest` + `setup-python`），
本地是 **Python 3.13**。两端是**同一个** `black==25.1.0`（`requirements-dev.txt` 钉死，CI 装的是
`black-25.1.0-cp311` wheel），但对 `assert 条件, (消息)` 这种**括号换行写法**给出不同排版：
3.11 侧要求折成 `assert (\n    条件\n), 消息`，3.13 侧接受原写法。

- ⇒ 本地 `black --check` 绿灯 **不等于** CI「Code formatting check」绿灯
  （PR #3 前两次 CI run `42837783313` / `42838611430` 都红在这一步）。
- ⇒ 本 PR 已统一成**两侧都接受**的新写法（`1c3f6a76`，纯排版，断言语义与消息文本一字未动）。
- ⇒ 后续改动：提交前按 3.11 侧排版写（消息折到条件后面），别只信本地 `--check`。

**已知坑（CI rerun 挂 `security-scan`，仓库既有问题、非本 PR 引入）**：
`security-scan` job 靠 `scripts/ci_changed_python_files.py` 算「本次改动到的文件」，
该脚本先 `git fetch origin <base> --depth=1` 再 `git merge-base HEAD origin/<base>`
（`scripts/ci_changed_python_files.py:43-44`）。**rerun 时仓库已是 shallow**，
`merge-base` 直接非零退出 ⇒ 脚本报 `CalledProcessError` ⇒ 整个 job 挂掉。
**push 触发的全新 run 不受影响**（`1c3f6a76` 那轮就是全绿）。

- ⇒ 看到这个报错（`Command '['/usr/bin/git', 'merge-base', 'HEAD', 'origin/main']' returned
  non-zero exit status 1`）时，**推一个新 commit 触发全新 run**，不要用 rerun。
- ⇒ 同一 job 另有一类抖动：`Failed to FinalizeArtifact: ... ECONNRESET`（上传 artifact 时
  撞上 runner 与 GitHub 存储的瞬断），同样是重跑即恢复。

### 批次落地台账（2026-11-11 收口）

| 批次 | 内容 | PR | 状态 |
|---|---|---|---|
| 批次 1 | 入库收敛按账号章 / 采集导出堵回退 / 巡检连接补齐 | #3 | ✅ 已合并 |
| 批次 0 | 只读对账脚本（T1~T4） | #4 | ✅ 已合并 —— **2026-11-11 已在采集机执行**（见下） |
| 批次 2 | 主数据对齐执行器（默认 dry-run） | #5 | ✅ 已合并 —— **2026-11-11 已在采集机执行**（见下） |
| 批次 3.5 | 僵尸 run 回收扩到全族并留痕 | #6 | ✅ 已合并 |
| 批次 3.2 | 语义层可解析性巡检（按月分档） | #7 | ✅ 已合并 |
| 批次 3.6 | 看板指纹收敛 + 顺序链 | #8 | ✅ 已合并 |
| SSOT-1 | 店铺身份唯一台账声明 + 认人优先级收敛到一处 | #9 | ✅ 已合并 |
| 批次 3.3 | 数据新鲜度分档 + 补通知出口 | #10 | ✅ 已合并 |
| 律 3 | 派生层口径收回（物化副本改为从正本取数） | #11 | ✅ 已合并（**存量库的定义未变**，见「已知未落地项」） |
| 批次 4.1 / 4.2 | 孤儿记账行清理 + 「云端为历史基准」口径 | #12 | ✅ 已合并 |
| 批次 3.4 | 采集失败主动告警（三通道 + 同轮错误聚类） | #13 | ✅ 已合并 |
| 守护修复 | 批次 3.5 漏改守护测试 fake ⇒ main 上的存量红 | #14 | ✅ 已合并 |
| 批次 3.7 | 同步侧双基准守卫 | #15 | ✅ 已合并 |
| 批次 4.3 | 同步矛盾行台账 + 手工重发入口 | #16 | ✅ 已合并 |
| 发版收口 | v7.20.0：版本号 + CHANGELOG + 台账收口 | #17 | ✅ 已合并 —— **v7.20.0 已上线** |
| **热修 v7.20.1** | 矛盾行「能定位到行」+ 守卫契约与实现对齐（复核发现的 2 处「应修」+ 4 处「建议」） | #18 | ✅ 已合并 —— **v7.20.1 已上线** |

**批次 0 / 批次 2 的实际执行结果（2026-11-11，采集机本机，隧道 15433 在线）**

| 项 | 结果 |
|---|---|
| T1 登记信息逐条比对 | 52 个账号，**50 条完全一致**；2 条差异**只出现在 `updated_by`** —— 本地 `manual:fix_shop_identity_alignment` vs 云端 `system:backfill`。**这正是设计要求**（「修改人由工具统一写，不接受来自云端的对齐值」）。实质字段（编号 / 状态 / 店名 / 启用 / 角色）**逐条相等** |
| T1 待对齐账号 | **0** ⇒ 编号对齐**此前已执行完毕**（`updated_by` 已带对齐工具的落款） |
| T2 错别名 | 本地原有 2 条 `former_platform_shop_id`（1 条 `self_alias` + 1 条 `unclaimed`）、云端 **0** 条 |
| T3 双认领 | 本地 **0**、云端 **0** ✅ |
| T4 探测记录 | 本地 8 条全 `failed`（2026-11-02 ~ 11-08）；「把正确编号降级为别名」的写入最后发生在 **2026-11-05**，此后**未再新增** ✅ |
| 批次 2 实际改动 | 账号 **0** 条（已对齐）、别名 **1** 条（删 `alias_id=46`，`1391124228`，是 `shopee_sg_hx_home_local` **自己编号的冗余副本**）⇒ **待删别名清单已清零** |
| 历史事实行 | `b_class.fact_*` **67 张表行数 0 变化**；`core.shop_accounts` 内容指纹未变；候选池正本/副本指纹未变（72 行 / `md5=cf586d9c8e27911ed762855025a1b57b`）✅ |
| 别名认领数 | 1 → **0** ⇒ 别名路不再认领任何经营店的平台编号（SSOT 收回）✅ |
| 剩下一条 `unclaimed` 别名 | **保留**（不删）：主人店 `shopee_sg_eternalbloom_local` 在**两端都是停用** ⇒ 进不了候选池；即使将来该店被重新启用，候选池 SQL 的 `NOT EXISTS` 规则也会**自动把它排除**（别名路不许认领经营店编号）⇒ 不会产生双认领。它保留了「该店曾用过的编号」这条历史语义 |

**批次 3.1（云端巡检生效）没有独立 PR** —— 它的代码就是批次 1.4（celery 注入
`CLOUD_DATABASE_URL`，随 #3 合并）。它「生效」的条件不是代码，而是**采集机上到云端的
SSH 隧道 15433 在线**：隧道不通时巡检仍然是 `skipped`，采集机上看不到云端真实水位。
⇒ 隧道在线与批次 0 是同一个前置条件（2026-11-11 实测：隧道在线时批次 0 一次跑通）。

⚠️ **还差最后一步（用户侧）**：配置 `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE`
（分档巡检的报警分界线；不配则一律不报警，宁可漏报不误报）。

**独立复核 + v7.20.1 热修（2026-11-11）**

批次 3.7 的独立复核（只读，10 个核实点）结论：**无阻断项**；核心设计经得起复核
（判定口径正确、SSOT 未分叉、历史数据边界与检查点推进语义未被破坏、事件台账落点合规）。
但报了 **2 处「应修」+ 4 处「建议」**，其中 **3 处「建议」与 1 处「应修」是实打实的功能缺口**，
已在 **v7.20.1** 修掉：

| 编号 | 问题 | 影响 | v7.20.1 的处置 |
|---|---|---|---|
| 建议-1 | 生产路径（源行 → 同步负载 → 身份闸门 → 矛盾行台账）**把源行主键丢掉了** | 台账里「源行主键」恒为空 ⇒ 手工重发入口**定位不到行** | `build_sync_payload` 保留源行主键（`id` 不是 canonical 列 ⇒ 写云端时 SQL 仍不绑它） |
| （自发现） | 重发脚本读源行时**只 SELECT 业务列、不 SELECT 主键** | 真库不返回主键 ⇒ 映射键恒为 `"None"` ⇒ 每行都被判成「源行已不存在」，**一行也发不出去**且不报错 | 读源行时把主键一起 SELECT 出来 |
| 应修-1 | `load_cloud_identity_registry` 的**建索引在 try 之外** | 云端读得到但建索引炸了 ⇒ 异常冒到 worker ⇒ **整批数据不落云端**（本该退回本地单基准） | 拆行 + 建索引纳入 try，失败即降级为「双基准不可用」 |
| 应修-2 | `test_event_recording_failure_does_not_block_the_sync` 是**空转用例** | 行内身份用的是「账号编码」（两端本来就一样）⇒ 压根不进 `record_mismatch` ⇒ 「记事件失败不阻塞同步」**一直没有测试保护** | 改用**平台编号**制造真不一致 + 断言事件记录器**确实被调用过**；另补「记录器整个抛异常」的第二层兜底用例 |
| 建议-3 | 脱敏对**未编码 `@`** 的口令残留尾巴（`***@ss`） | 形式不干净 | 按**最后一个 `@`** 切 netloc 取完整口令，且**长的先抹** |
| 建议-4 | `partial_success` 兜底文案只写「行内身份矛盾」 | 降级行并不是「矛盾」 | 补「或被双基准降级」 |
| 建议-2 | 三个 `REASON_CLOUD_*` 在守卫内自造了第二份定义 | — | **已在 main 上修复**（改为从台账服务转出），v7.20.1 无需再动 |

⚠️ **教训（与批次 3.5 / 批次 4.3 一脉相承，现在已成一条稳定规律）**：
**假引擎不校验 SQL 的 SELECT 列、也不校验负载的键集 ⇒ 这类「键/列丢失」的单测全绿也测不出来。**
⇒ 守护用例的替身必须**忠实于被测代码依赖的那份契约**
（本版本新增的 `_FaithfulEngine` 只按 SQL 里**实际 SELECT 的列**造行）；
⇒ 本版本 **7 条新用例 + 1 条改写用例**，全部做过**负向验证**（把修复逐个回退 ⇒ 对应用例逐个变红）。


**新增两个 CI 坑（2026-11-11 踩到，均非本方案引入）**：

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

## 已知未落地项（2026-11-11 复核新增，必须留档）

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


---

### 业务语言决策版（2026-11-11）

- Plan: `docs/superpowers/plans/2026-11-11-shop-identity-business-plan.md`
- 定位：同一方案的**决策人视角**（业务语言，零代码术语）。技术口径仍以
  `2026-11-10-shop-identity-future-proofing-and-observability.md` 为准。
- 内容：10 项问题单逐项业务结论 + **4 个复核新发现**（含「身份唯一台账从未被成文声明」
  与「输出键口径仍是平台编号优先」两处裂缝）、「历史不修」边界判定、
  三步走（堵口子 → 对齐台账 → 装雷达）、两条硬性时序、风险与回滚、
  **两项待业务拍板**（采集范围口径 / 告警通道）、业务口径验收清单。

---

## Batch 0 Reconciliation (2026-11)

- Plan: `docs/superpowers/plans/2026-11-10-shop-identity-future-proofing-and-observability.md`（批次 0 章节）
- PR: `https://github.com/timberdayz/timber_dayz/pull/4`
- 分支：`feature/2026-11-10-shop-identity-batch0-reconciliation`

### 交付物

| 文件 | 内容 |
|---|---|
| `scripts/verify_shop_identity_reconciliation.py` | 只读对账脚本：同时连本地库与云端库，输出 T1~T4 四张表 |
| `tests/test_shop_identity_reconciliation_script_contract.py` | 契约守护测试（13 条，纯源码 / 纯函数，不连库） |

### 四张表

| 表 | 内容 | 喂给谁 |
|---|---|---|
| T1 | `core.shop_accounts` 两边按 `shop_account_id`（业务键，跨库唯一）对齐，逐条比对 6 个登记字段 | 批次 2 的「改哪些」 |
| T2 | `alias_type='former_platform_shop_id'` 别名全量，标注自别名 / 跨账号认领 / 无人认领 | 批次 2 的「删哪些」 |
| T3 | 同一 `(platform, identity_value)` 指向 >1 个账号 | unknown 成因 |
| T4 | 探测记录近 N 天分布 **+ 近 N 天新增别名数** | 污染是否绝迹 |

### 只读保证（由契约测试强制）

- 全部 SQL 为 `SELECT` / `WITH` —— 测试用 **AST 逐条**校验每个 `_fetch_all(...)` 的 SQL 首词；
- 连接串只从环境变量读，源码内无 `postgresql://` 字面量；
- `.env` 用 `setdefault` 语义加载（先到先得、不覆盖）——
  本机 `.env.local` 的 `CLOUD_DATABASE_URL=` 是**空值**，覆盖会把云端连接串清空；
- 输出里的连接串摘要脱敏（口令用 `make_url()` 解析，百分号编码自动解码）。

### 实测（本地库 vs 本地库，验证 SQL 与幂等性）

- 两次运行输出**完全一致**（除 `generated_at`）⇒ 满足「纯只读、无副作用」；
- schema 自检：三张表与关键列**全部齐全**；
- T2 查出 **1 条自别名** —— `shopee_sg_hx_home_local` 的别名值 `1391124228`
  **等于它自己当前的 `platform_shop_id`**（自别名 ⇒ 同一串身份值既被账号认领、又被存成别名）；
- T4：近 30 天新增 `former_platform_shop_id` 别名 **2 条**，
  集中在 **2026-11-05 12:07:42 ~ 12:08:39**（57 秒内 2 条）—— 污染写入确实发生过。

> ⚠ 以上在**本地开发库**上跑的；采集机的真实对账结果以采集机执行为准。

### 采集机执行

```powershell
# 前提：到云端的 SSH 隧道 15433 在线
python scripts/verify_shop_identity_reconciliation.py --output output/reconciliation-20261110.json
```

可选项：`--days 30`（T4 窗口）、`--sections T1,T2`（只跑部分段落）。
退出码：`0` 正常产出 / `2` 执行失败（连不上库、缺表缺列）。

## 店铺身份「保未来」守护落地（2026-11-11）

- Plan: `docs/superpowers/plans/2026-11-11-shop-identity-guard-activation.md`
- 主题：把「工具」变成**真的在跑的守卫**

### 三个参数（决定性数据 ⇒ 决定性取值）

| 参数 | 取值 | 依据 |
|---|---|---|
| `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE` | `2026-12-01` | 云端 2026-11 的 unknown 占比 **56.69%**（事故现场）；分档按月 ⇒ 配 11-12 会让 11 月整月进「新问题」档、巡检每小时都红、告警当场作废。配 12-01 ⇒ 2026-02~11 全归 `known_legacy` 不报警，12 月起进守护区间 |
| `SHOP_IDENTITY_SEMANTIC_UNKNOWN_RATE_THRESHOLD` | `0` | 默认 0.05 会放过「新增月份只剩 1~2 行认不出」；设 0 后只要有 1 行就报（该月 0 行时比率 0 不报） |
| `SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED` | `1`（开） | 复用批次 3.4 的站内信 / webhook / 钉钉三条通道；通知失败不影响同步 |

### 交付物

| 文件 | 作用 |
|---|---|
| `backend/tasks/cloud_sync_integrity_tasks.py` | 公开入口 `resolve_cloud_database_url_from_env()`（私有名保留为委托别名）+ 巡检**探活**与**本地留痕** |
| `scripts/verify_semantic_unknown_by_month.py` | 只读逐月看云端「认不出店」占比（口径直接复用巡检，不另写一份） |
| `scripts/watch_cloud_sync_tunnel.ps1` | 隧道**看门狗**：探测 → 自愈（先清僵死 ssh 进程）→ 留痕；`-InstallScheduledTask` 注册计划任务 |
| `docker-compose.prod.yml` / `.dev.yml` / `.collection-cloud-sync.yml` | 把三个开关与 `CLOUD_DATABASE_URL` 显式传进 celery worker / beat / collector |
| `env.*.example` × 6 | 三个开关的语义与取值约束（留空 = 未启用 = 不误报） |
| `tests/` × 4 新文件 | 43 条契约守护（口径不分叉 / 只读 / 脱敏 / 参数不漂移 / 幂等 / 不碰容器 / 留痕不掩盖原异常） |

### 已落地位置

- 本机 `.env.collection.local`（采集机）：三件套全配；
- 生产 `/opt/xihong_erp/.env`：四键就位（备份 `.env.bak.20261111_114118`）⇒ **容器重建后生效**（随 v7.21.0 部署）；
- 本机计划任务 `XihongCloudSyncTunnelWatchdog`：每 2 分钟自愈隧道（实测：杀掉 ssh ⇒ 1 秒内恢复；端口已通 ⇒ 不起第二条隧道）。
  - **2026-11-12 修正**：任务动作原本是 `powershell.exe -NoProfile ...` 直接跑，而本机默认终端宿主是
    Windows Terminal ⇒ **每 2 分钟弹一次可见终端窗口**（用户报告「突然闪一个黑框」，无法判断是否被入侵）。
    改为 `conhost.exe --headless powershell.exe ...` 后实测 **0 个可见窗口**，隧道自愈逻辑与留痕完全不变。
    源码 `Install-WatchdogScheduledTask` 已同步修正（防复发），并加契约守护
    `test_watchdog_task_action_never_flashes_a_window`。

### 遗留

- 用户侧：下一轮采集后核「新增月份认不出 = 0」—— ⚠️ **只能从 2026-12 起算**（11 月是事故现场）。
- v7.21.0：律 3 的候选名单副本物化视图仍是旧定义 ⇒ 部署流水线需先 `DROP` 再按资产重建，并加副本定义守护。

## 律 3 落地：候选集副本改为「从正本取数」（2026-11-11）

- Plan: `docs/superpowers/plans/2026-11-11-identity-candidates-copy-rebuild.md`
- 主题：把「派生层口径收回」从**仓库资产**变成**存量库里的事实**

### 生产实测（2026-11-11，云端库只读探测）

| 项 | 结果 |
|---|---|
| 副本定义 | 仍是**手抄版**（`core.shop_accounts` / `regexp_replace` / `active_shop_accounts` 都在）⇒ **在自算**，没读正本 |
| 副本行数 / 正本行数 | 72 / 72，双向差集 **0 / 0** ⇒ *当前* 无功能影响 |
| 定义落后 | 副本比正本**少一条**口径（采集方代号不进候选池）⇒ 随时可能静默分叉 |

### 为什么走迁移而不是改部署流水线

* 部署期跑 `rebuild_views.py --all-plain-views` ⇒ **只重建普通视图**，副本不在清单里；
* 「在流水线里 DROP 副本」会打断 `LANGUAGE sql` 的解析函数（依赖被跟踪），
  而让开/换回必须与两个原子层普通视图**同步**做 ⇒ 天然是原子操作，不是流水线步骤。

### 交付物

| 文件 | 作用 |
|---|---|
| `current_migrations/versions/20261225_rebuild_identity_candidates_copy.py` | 让开 → `DROP`（**不带 CASCADE**）→ 按资产重建 → 换回 → 内容逐行比对 + 定义校验 |
| `backend/services/data_pipeline/cloud_sync_integrity_service.py` | 巡检**第五项**「候选集副本口径健康」（`missing`/`drifted`/`diverged`/`ok`/`unknown`） |
| `scripts/verify_identity_candidates_copy.py` | 只读探针，**复用**巡检同一个判定函数 |
| `tests/` × 2 新文件 | 25 条契约守护 |

### 顺带修掉的两个真问题

1. 巡检第五项 `counts.one()` 被调用两次 ⇒ 真库实跑恒为 `unknown`（已修 + 单测假 Result 改成「取一次就关闭」）；
2. 两个守护脚本原来只读进程环境变量 ⇒ 开箱跑报「DATABASE_URL 未配置」（改为 import 前 `load_project_env`）。

### 验证

| 项 | 结果 |
|---|---|
| 本地库真跑迁移 | 成功，版本 → `current_schema_20261225_rebuild_identity_candidates_copy` |
| 迁移后本地副本定义 | `FROM semantic.shop_identity_resolution_candidates`；`legacy_tokens=(none)`；72/72 差集 0/0 |
| 守护脚本（本地） | `ok`，退出码 0 |
| 守护脚本（云端基线） | **`drifted`**，退出码 1 —— 部署前的真实状态，部署后应转 `ok` |

## v7.21.0 发布与部署后实测（2026-11-11）

- PR #21（发版收口，只改 `VERSION`/`CHANGELOG`）CI 13/13 全绿后合并，merge commit `4d4c6e0e`
- tag `v7.21.0` 两端对象一致（GitHub / CNB 均为 `3c55da0f`）
- 部署流水线 `42960141282` **success**，生产容器全部切到 v7.21.0 且 healthy

### 部署后验收快照（只读，口径复用巡检）

| 项 | 部署前 | 部署后 |
|---|---|---|
| 迁移版本 | `current_schema_20261224_shop_identity_conflict_rows` | `current_schema_20261225_rebuild_identity_candidates_copy`（head） |
| 候选集副本 | **`drifted`**（自算） | **`ok`**（从正本取数，72/72，差集 0/0） |
| 逐月 unknown | — | 10 个月全 `known_legacy`，`degraded=0` |

### 生产巡检第一次真跑（不再 skipped）

`CLOUD_DATABASE_URL` 在生产 compose 里接上了 ⇒ 巡检从「永远 skipped」变成真跑：

| 字段 | 值 |
|---|---|
| `identity_candidates_copy_status` | `ok`（72 行） |
| `degraded_semantic_months` | `0`（10 个月全 `known_legacy`） |
| `cloud_database_url_resolution` | `rewritten=false`、`reason=not_loopback_host`（生产「云端」= 自己，主机名 `postgres` 非回环 ⇒ 不改写） |
| `status` | `partial_failed` —— **唯一**失败项是 `stale_cloud_chains`（10 条采集链陈旧） |

⇒ 失败项是**采集停更**的真实信号，正是这次守护要暴露的东西，不是新问题。

## 容器侧云端隧道地址修正（2026-11-11）

- Plan: `docs/superpowers/plans/2026-11-11-container-cloud-tunnel-host-fix.md`
- 主题：让**采集机侧**的云端巡检真的连得上云端（v7.21.0 部署后实测发现）

### 现象

采集机本地库出现 `cloud_sync_integrity_check_unreachable` / `failed`：
`ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 15433)`。
同一时刻隧道看门狗报 `OK`、`ssh` 进程没断 ⇒ **不是隧道掉了，是地址填错了**。

### 根因

`CLOUD_SYNC_TUNNEL_HOST` 一个变量名被**语义相反**的两个环境共用：

- 宿主进程（隧道在本机）⇒ 该填 `127.0.0.1`；
- 容器内（隧道在 Docker 宿主）⇒ 该填 `host.docker.internal`。

compose 插值**优先取进程环境变量**，而采集机启动脚本会把
`.env.collection.local`（正是 `127.0.0.1`）导入进程环境 ⇒ 容器拿到 `127.0.0.1`
⇒ 连到容器自己 ⇒ 必然拒连。容器内实测：`host.docker.internal:15433` 通、`127.0.0.1:15433` 拒。

⇒ 后果是巡检**恒定**报「云端不可达」⇒ 假警报把真信号淹掉 ⇒ 守卫等于没有。

### 修法

容器侧 `CLOUD_SYNC_TUNNEL_HOST` **钉死为字面量** `host.docker.internal`（不再插值）。
宿主侧保持 `127.0.0.1`（`env.collection.local`）—— 代码在「非容器内」时原样保留主机名，不受影响。
**生产 compose 不动**（生产「云端」= 自己，主机名非回环，压根不走隧道改写）。

### 交付物

| 文件 | 作用 |
|---|---|
| `docker-compose.dev.yml`（celery-worker / celery-beat） | 容器侧隧道宿主钉死为字面量 |
| `docker-compose.collection-cloud-sync.yml`（backend-collector） | 同上 |
| `env.collection.local.example` | 写明 `127.0.0.1` 是**宿主语义**，容器侧由 compose 钉死 |
| `tests/test_container_cloud_tunnel_host_contract.py` | 10 条契约守护 |

## PowerShell env 文件读取的编码修正（2026-11-11）

- Plan: `docs/superpowers/plans/2026-11-11-ps-env-file-encoding-fix.md`
- 主题：让 PowerShell **真的把 env 文件读完**（容器侧隧道地址修正时暴露）

### 现象

重建采集机 celery 容器时，`SHOP_IDENTITY_*` 三个变量在容器里是**空的**，
而它们明明白白写在 `.env.collection.local` 里。

### 根因

`scripts/start_collection_formal.ps1` / `scripts/watch_cloud_sync_tunnel.ps1` 的
`Import-EnvFile` 用 `Get-Content $Path`（**没指定编码**）⇒ PS 5.1 按**系统 ANSI(GBK)**
解码无 BOM 文件 ⇒ `.env` 里的**中文注释块**被解坏 ⇒ 解析中断 ⇒
**中文注释之后的每一个变量被静默丢弃**（无任何报错）。

实测：同一份文件，只差编码 —— 不带 `-Encoding` 导入 12 个变量（三件套全丢），
带 `-Encoding UTF8` 全部导入。

⇒ 后果是 compose 插值拿到空值 ⇒ **看起来配了、其实没生效**，且没有任何声音。

### 修法

两处 `Import-EnvFile` 改成 `Get-Content -LiteralPath $Path -Encoding UTF8`。

### 交付物

| 文件 | 作用 |
|---|---|
| `scripts/start_collection_formal.ps1` | `Import-EnvFile` 显式 UTF-8 |
| `scripts/watch_cloud_sync_tunnel.ps1` | 同上 |
| `tests/test_ps_env_file_encoding_contract.py` | 12 条契约守护（显式 UTF8 / `-LiteralPath` / 无 BOM UTF-8 / 两处同步） |

### 部署后实测（采集机）

| 项 | 结果 |
|---|---|
| 容器环境重建后 diff | **仅** `CLOUD_SYNC_TUNNEL_HOST` 变化；三件套恢复 `2026-12-01` / `0` / `1` |
| 容器内云端巡检 | 成功连上云端（`rewritten: True` → `host.docker.internal:15433`），**不再** unreachable |
| 云端巡检 `stale_chains` | 10 → **7**（成功采集的 3 条 shopee 链已刷新到云端） |
| 云端台账 | 巡检结论正常落在云端 `ops.pipeline_run_log`（`cloud_sync_integrity_check`） |

## 采集任务状态 SSOT 收敛 + 文件系统护栏 + 日/周粒度废弃重采（2026-11-11）

- Plan: `docs/superpowers/plans/2026-11-11-task-status-ssot-and-data-dir-guard.md`
- 主题：把「采集任务有哪些状态、哪些能写进任务中心」收成**一处**定义（律 1），
  并补上**文件系统**护栏（数据库/Redis/Celery 早就护了，磁盘漏了）

### 现象一：任务中心的真实失败原因被数据库报错盖掉

9 家 shopee 采集失败后，失败原因显示成
`This Session's transaction has been rolled back due to a previous exception during flush...`
而不是「平台要求滑块验证码，等人工处理」。

### 根因

`public.task_center_tasks` 的 `CHECK` 约束 `chk_task_center_tasks_status` 里
**手抄**了一份状态清单，**漏掉了** `verification_required` /
`verification_submitted` / `manual_intervention_required`。

⇒ 采集走到「等人工处理」时写任务中心被 PostgreSQL 拒（`CheckViolationError`）
⇒ session 事务回滚 ⇒ 上层兜底捕获到的变成事务回滚噪音 ⇒ **真实原因被覆盖**
⇒ 且任务中心里状态是 `failed` 而不是「等待人工处理」
⇒ **前端的人工处理入口拿不到正确状态**。

不是「选错了真源」，是**真源被复制成 6 份、其中一份漂了**：
真源 `collection_task_status.py` 只定义了状态分组，**没定义「任务中心能写哪些状态」**。

### 修法

真源补 `ALL_STATUSES` / `TASK_CENTER_WRITABLE_STATUSES` /
`render_task_center_status_constraint()` / `to_task_center_status()`；
ORM 约束、两个服务、状态映射**全部从真源派生**；
迁移 `20261226_task_center_status_constraint` **从真源渲染**目标表达式（不写死清单）。

顺带补上真源的第三个缺口：`interrupted` 是采集侧真实写入的终态
（服务重启回收），原先真源里**没有**。

### 现象二：测试把假文件写进正式数据目录

`data/raw/2026/` 里混着 **176 个** 11 字节、内容为 `fake-export` 的假文件
（真实采集文件是 89 KB 的有效 .xls）⇒ 排查时差点误判成「订单采了没入库」。

### 根因

`executor_v2._process_collected_files` 用 `get_data_raw_dir()` 决定落盘目录，
而它读**环境变量 `DATA_DIR`**。`backend/tests/conftest.py` 已给
**数据库 / Redis / Celery** 都加了护栏，**唯独漏了文件系统**。

### 修法

根 `tests/conftest.py` 在**模块顶层**（早于任何 import，`get_data_raw_dir` 带
`lru_cache`）把 `DATA_DIR` 指向临时目录；会话结束自检告警。

实测：主工作树跑 `tests/test_executor_v2.py`
修复前每次必写 **8 个文件** ⇒ 修复后 **new = 0**。

清理按「无入库记录 + <64 字节 + 内容含 `fake-export`」**三条同时**满足才删
⇒ 删 176 个；「孤儿但大小正常」663 个 + 已登记 487 个**全部保留**。

### 交付物

| 文件 | 作用 |
|---|---|
| `backend/services/collection_task_status.py` | 状态真源扩展（全集 / 可写集合 / 渲染 / 映射）+ 补 `interrupted` |
| `modules/core/db/schema_parts/collection.py` | ORM 约束改为从真源渲染 |
| `backend/services/collection_config_run_service.py` | 状态集合从真源派生 |
| `backend/domains/collection/routers/collection_schedule.py` | 同上 |
| `backend/domains/collection/routers/collection_tasks.py` | 状态映射调用真源函数 |
| `current_migrations/versions/20261226_task_center_status_constraint.py` | 约束对齐迁移（从真源渲染） |
| `modules/core/shop_identity_ssot.py` | 快照层加「日/周整体废弃重采」例外 |
| `tests/conftest.py` | 文件系统护栏（`DATA_DIR` 隔离 + 会话自检） |
| `backend/tests/test_collection_task_status_ssot_contract.py` | 状态 SSOT 守卫（24 条） |
| `tests/test_collection_data_dir_guard_contract.py` | 文件系统护栏守卫（7 条） |

### 实测

| 项 | 结果 |
|---|---|
| 迁移演练（本地真库） | 升级前写 `manual_intervention_required` **被拒**（复现 bug）；升级后 13 状态全可写、`bogus_status` 仍被拒；降级后约束**逐字恢复** |
| 护栏实测 | 修复前每次写 8 个文件 ⇒ 修复后 **0 个** |
| 污染清理 | 删 176 个；清理后 `data/raw` 里 <64 字节文件 **0 个** |
| 基线（改动前） | 根 `tests/` 738 passed / 5 skipped / 0 failed；`backend/tests/` 5664 passed / 8 skipped / 0 failed |

### 日/周粒度数据处置（用户 2026-11-11 决策）

「日、周粒度的数据都存在大量问题，本地和云端的日、周粒度数据都可以先进行清理了」

⇒ **先改声明再执行**：`modules/core/shop_identity_ssot.py` §③ 快照层原写
「既定决策不修（只保未来）」⇒ 新增明确例外 `DISPOSABLE_GRANULARITIES = ('daily','weekly')`
⇒ **整体废弃重采**（不是逐行订正 —— 删干净了就不会撞 upsert 冲突键）。

⚠️ 月粒度 / 快照粒度**仍不修**（经营口径基准，错了要人工判断）。

| 项 | 本地 | 云端 |
|---|---|---|
| 日/周行合计（已删） | **2211** | **2641** |
| 月/快照行 | 不动 | 不动 |
| 备份 | `%TEMP%\mcode_granularity_backup_20261111\LOCAL_*.jsonl`（完整行数据，可逐行恢复） | `CLOUD_*.jsonl` |

⚠️ **连带**：3 个 semantic 物化视图读日/周事实表 ⇒ 删了不重刷 = 白删。
第一次直接 `REFRESH MATERIALIZED VIEW` **全部超时失败**
（连接池默认 `statement_timeout=120s`，而 `fact_orders_atomic_mv` 生产实测就要 **115 秒**）
⇒ 改走仓库正主路径 `refresh_runner.execute_sql_target()`
（已封装临时抬高超时、MV 锁、索引补齐、MV 不存在时自愈）。

⇒ **但走正主路径第一次仍然「报成功、数据没变」** ⇒ 根因见下 ①。

### 本轮实测出来的三个「真问题」（都不是本批引入的，是暴露出来的）

#### ① `execute_sql_target()` 不提交 ⇒ `REFRESH MATERIALIZED VIEW` 被回滚

`backend/services/data_pipeline/refresh_runner.py::execute_sql_target()`
**自己不提交事务** —— 提交是上层 `execute_refresh_plan()` 的活
（它每个目标后调 `await _commit_if_possible(db)`）。

而 PostgreSQL 的 `REFRESH MATERIALIZED VIEW` 是**事务性**的：
没提交就关会话 ⇒ 整个事务回滚 ⇒ 物化视图内容**原样保留**。

⇒ 症状极具迷惑性：**6 个目标全报 ok，MV 里的 daily/weekly 行一行没少**。
⇒ 不是仓库的 bug，是调用方（探针脚本）漏了 `commit`。
⇒ 补上 `await db.commit()` 后重刷，**两端 3 个 MV 的 daily/weekly 残留全部归零**：

| | `fact_orders_atomic_mv` | `fact_analytics_atomic_mv` | `fact_products_atomic_mv` | 正本 `semantic.fact_orders_atomic` |
|---|---|---|---|---|
| 本地 | 34883（daily/weekly **0**） | 3728（**0**） | 4761（**0**） | 只剩 monthly 34883 |
| 云端 | 37516（daily/weekly **0**） | 5418（**0**） | 5890（**0**） | 只剩 monthly 37516 |

⚠️ **教训**：凡是走 `execute_sql_target()` 的调用方，**必须自己 commit**
（`execute_refresh_plan()` 内部已经代劳了；绕过它直接调就要自己补）。

#### ② 护栏「设了环境变量」≠「护住了」：`.env` 在 import 期覆盖 + lru_cache 冻住

护栏第一版只在 `tests/conftest.py` 顶层设 `DATA_DIR` ⇒ 主工作树实测 `new = 0`，
看着是好的；**但在 worktree 里跑，又往正式目录写了 8 个文件**。

根因三条叠加：
1. 仓库根 `.env` 里有 **`DATA_DIR=./data`**（相对路径 ⇒ 相对 cwd ⇒ 就是正式目录）；
2. `backend/main.py` / `run.py` 在 **import 时**就调 `load_project_env(project_root)`，
   它的 `load_dotenv(..., override=True)` 把 `DATA_DIR` **覆盖回** `./data`
   （仓库自己的方案文档 `2026-11-07-consolidated-execution-plan.md` 就记着这条：
   「import 时 `load_project_env(override=True)` ⇒ 用例变成顺序依赖」）；
3. `modules/core/path_manager.py::get_data_dir()` 是 `@lru_cache(maxsize=1)`
   ⇒ 第一次调用就把 `./data` **冻住**，之后改环境变量也无效。

⇒ 护栏必须**每个用例前**（`pytest_runtest_setup`）重新写回 `DATA_DIR`
（因为 `.env` 是在**收集期**被加载的，`pytest_configure` 跑在收集**之前**），
并同时 `cache_clear()` 掉 `get_data_dir` / `get_data_raw_dir` /
`get_data_processed_dir` / `get_data_input_dir` 的缓存。

⚠️ **没有**采用仓库的 `XIHONG_TEST_ENV_GUARD` 全局护栏：
那个开关会让 `backend/utils/config.py` 把 `Settings.DATABASE_URL` 强制切到隔离库，
而**根 `tests/` 本来就是要连真实本地库**的 ⇒ 开了反而全红，爆炸半径太大。

#### ③ CI 的 `ruff check <changed files>` 会把**既有**的 E712 也判红

`backend/domains/collection/routers/collection_schedule.py` 里两处
`CollectionConfig.is_active == True` 是**基线就有的**（`main` 的 261/289 行），
但 CI 只对**本 PR 改到的文件**跑 ruff ⇒ 碰了这个文件就会被判红。

⇒ 改成 `CollectionConfig.is_active.is_(True)`：
该列是 `nullable=False` 的 Boolean ⇒ `= true` 与 `IS true` 对**每一行**都等价，
取值集合不变（不是口径改动）。

### 本批回归（worktree，`.env` 已还原成基线条件）

| 范围 | 基线 | 本批 |
|---|---|---|
| 根 `tests/` | 738 passed / 5 skipped / 0 failed | 见下方「失败集 diff」 |
| `backend/tests/` | 5664 passed / 8 skipped / 0 failed | **5688 passed / 8 skipped / 0 failed**（+24 条新守卫） |
| `black==25.1.0` | — | 10 个改动文件全部 clean |
| `ruff 0.17.3` | — | 全部通过 |

⚠️ **根 `tests/` 必须在有 `.env` 的条件下跑**：worktree 默认没有 `.env`
（gitignored）⇒ `tests/test_rebuild_local_current_schema.py` 写的临时
`.env.collection.local`（假口令 `erp_user:password`）会留在进程环境里，
让后面的 `tests/test_v4_3_2_complete_system.py::test_product_hierarchy_ingestion`
去连 15432 ⇒ 报 `password authentication failed`。
⇒ **这是 worktree 环境差异，不是代码回归**（主工作树同一批用例通过）。

## v7.22.0 上线 + 采集机真实采集实跑验收（2026-11-11）

本节只记录**实测结论**，不再改代码。

### 生产部署（决定性）

| 项 | 结果 |
|---|---|
| 流水线 run `42997345617`（Deploy to Production，tag 触发） | `conclusion=success` |
| 容器镜像 | `backend:v7.22.0` × 3（api / celery_worker / celery_beat）+ `frontend:v7.22.0` + postgres / redis / nginx |
| 容器健康 | 7 个全部 `healthy` |
| 容器内 `VERSION` | `v7.22.0` |
| 公网健康端点 | `https://www.xihong.site/api/healthz/ready` → HTTP 200，`version=v7.22.0` |
| Phase 2.7 视图重建 | 39 个目标全部成功，失败 0（`rebuild_views_20261111_175152.log`） |
| 生产库任务中心约束 | 13 个状态，与真源渲染逐字一致 |
| 生产库迁移 head | `current_schema_20261226_task_center_status_constraint` |
| 生产库日/周粒度残留 | `fact_orders_atomic` / `fact_analytics_atomic` / `fact_products_atomic` 三张表 daily 与 weekly 均为 **0**；正本 `semantic.fact_orders_atomic` 只剩 `monthly=37516` |

### 采集机真实采集实跑（决定性证据）

- 采集机重启到 `v7.22.0`：`/healthz/ready` = 200，database / redis / scheduler /
  queue_runner / leader_lock / playwright 全 ok。
- 触发方式：`POST /api/collection/configs/31/run`（配置 31 = `shopee KR` 月档，
  账号只有 `shopee_sg_hx_home_local` + `shopee_sg_strawberries_store_local`
  两个**当天 05:00 刚采集成功、会话仍有效**的店 ⇒ 不触发新登录、不碰验证码）。
- 结果：config run `264` 状态 `completed`（18:07:19 → 18:09:47）：
  - task `699` `shopee_sg_hx_home_local`：`completed`，71s，1 个文件；
  - task `700` `shopee_sg_strawberries_store_local`：`completed`，68s，1 个文件；
  - 两个任务 `error_message` 均为空，`verification_type` 为空（**没进验证码分支**）。
- 落盘：`data/raw/2026/shopee_analytics_monthly_20261111_180831.xlsx`（10895 B）
  与 `..._180944.xlsx`（10834 B）+ 各自 `meta.json` ⇒ 是真实数据，不是测试残留。
- 任务中心镜像：`public.task_center_tasks` id `2128` / `2129`，
  `status=completed`、`progress_percent=100` ⇒ **本批修的那条写入路径在真实采集里跑通了**。
- 自动入库：celery beat 的 `auto-ingest-pending-files-every-15min` 在 **10:15:00 UTC**
  那拍拾起这 2 个文件（10:00 那拍早于文件落库，所以是空的）：
  `processed=2, success=2, quarantined=0, failed=0, blocked=0, skipped=0`；
  两个文件均 `status=ingested`，同步结果为「**新插入 3 行, 更新 7 行（UPSERT）**」。
- 语义层：`semantic.fact_analytics_atomic` 月档 3728 → **3734**，`max(metric_date)`
  推进到 2026-11-10；粒度仍**只有 monthly**（日/周清理成果没被这次实跑破坏）。

⇒ 采集 → 落盘 → 登记 → 自动入库 → 数据同步（UPSERT）→ 语义层，**全链路实跑通过**。

### 遗留（非代码，需人工）

- **9 家 shopee 的失败与本次代码修复无关**：
  - 5 家「登录组件执行失败」= 平台侧拦截（滑块验证码）⇒ **需人工重登**；
    按用户风控要求，**不得自动重试**。
  - 2 家「transaction has been rolled back」= 本批已修（约束放宽 + 真源派生）。
  - 2 家「浏览器被关闭」= 同轮任务崩溃的连带，修复后重跑即可。
- tiktok 6 个账号登录状态需人工确认；妙手账号验证码需人工回填。
- **14 个采集配置 `schedule_enabled=false`** ⇒ 调度器在跑但不注册采集任务。

### 定时（cron）到底怎么运作（2026-11-11 复核）

定时本来就是**用户自己在界面上开关的**，不需要谁来代设。两层：

| 层 | 接口 | 作用范围 |
|---|---|---|
| 按粒度统一开关 | `GET/POST /api/collection/schedule/granularity/{daily\|weekly\|monthly}` | 该粒度下每个「当前配置」 |
| 单条配置开关 | `GET/POST /api/collection/configs/{id}/schedule` | 指定的那一条 |

- 粒度预设 cron（`backend/domains/collection/routers/collection_schedule.py:46`）：
  `daily = 0 7 * * *`（每天 07:00 采昨天）、
  `weekly = 0 9 * * 1`（每周一 09:00 采上周）、
  **`monthly = 0 9 * * *`（每天 09:00 采「本月累计到最近可采集日」）**。
- 「当前配置」= 按 `(platform, main_account_id, granularity)` 分组，每组取一条：
  优先 `batch_status='active'`，否则取 `updated_at` 最新的
  ⇒ 14 条里实际只有 **12 条**当前配置（config 26 与 40 同组，40 是当前的）。
- APScheduler 的 jobstore 就是**同一个 PG 库的 `apscheduler_jobs` 表**（持久化 ⇒ 重启不丢）；
  实测该表当前**只有 1 条 `daily_cleanup`**（每天 03:00 清理临时文件，与采集无关），
  **一条采集作业都没有** —— 因为 14 条配置全是 `schedule_enabled=false`。
- ⚠️ **风控陷阱在 `monthly` 而不在 `daily`**：`monthly` 预设是 `0 9 * * *` = **每天**跑
  （不是每月一次），而月档范围是 `auto_month_to_date` ⇒ 每天 09:00 会把**全店重登一遍**、
  月档数据整个重采一遍（UPSERT 不膨胀，但**登录次数 = 每天一次全店**）。
  ⇒ 要开定时就开 **daily**；monthly 若也要自动，**别用粒度一键开关**，
  改成逐条 `POST /api/collection/configs/{id}/schedule` 给它 `0 9 1 * *` 这种自定义 cron。
- 定时采集 09:00 触发 → 文件落库 → 自动入库（celery beat `*/15`）在 **09:00 或 09:15**
  那拍拾走 ⇒ **数据进语义层最多滞后 15 分钟**（实测：10:08 落库 → 10:15:00 那拍入库）。

### 每平台单账号冒烟（2026-11-11 20:19 ~ 20:30，用户要求「每平台只登一个账号测」）

用 `POST /api/collection/tasks`（**单账号**，不走整条配置），
`granularity=monthly` + `time_selection={mode: dynamic, strategy: current_month_to_available_day,
available_after_time: "06:00"}` ⇒ 实际时间窗 **2026-11-01 ~ 2026-11-10**
（当天 11-11，平台数据 06:00 后可采 ⇒ 最近可采集日 11-10）。

| 平台 | 账号 | 结果 |
|---|---|---|
| tiktok | `tiktok_my_dawie_mall_local`（上次成功 11-07） | **completed**，1 个文件；登录 → 切店 → 采集 → 落盘 → 自动入库 → 语义层全通 |
| shopee | `shopee_ph_xhkj11_local`（当初被本批 bug 弄挂的那家） | **failed**：`登录组件执行失败` = **平台侧拦截**（会话已过期），非代码问题 |

- tiktok 文件 `tiktok_analytics_monthly_20261111_202228.xlsx`：
  自动入库在 **12:30:00 UTC** 那拍处理（12:15 那拍早于文件落库，是空的）：
  `processed=1, success=1, quarantined=0, failed=0, skipped=0`；
  `public.catalog_files` id `3056` → `status=ingested`；
  语义层 `semantic.fact_analytics_atomic` 月档 3734 → **3738**，`max(metric_date)=2026-11-10`。
- shopee 那次虽失败，但**带回了本批修复的直接证据**：任务中心镜像行
  `status=failed / progress=5% / step=正在登录... / error=登录组件执行失败`
  ⇒ **真实失败原因被原样记录，不再被 `This Session's transaction has been rolled back` 盖掉**。
- 粒度纯度不变：语义层仍是**只有 monthly**，daily/weekly 残留 0；
  历史行归属未动、身份戳未回填。

⇒ **两个平台的采集组件在 v7.22.0 上都跑通了**；剩下的 shopee 失败全部是
**平台侧拦截登录**（会话过期 / 滑块验证码）⇒ 只能人工重登。

## v7.23.0 上线 + 商品中心款货归属收敛 + 隧道看门狗（2026-11-12 ~ 11-13）

- tag `v7.23.0`（tag 对象 `97b7731d`）**双端同一对象**；部署流水线 run `43252281527` 全绿。
- 生产验收（HTTP 直观测）：`/api/healthz/ready` → 200、`version=v7.23.0`、
  `database=connected`、`dashboard=ready`；OpenAPI 含 `/api/spus/options` 与
  `/api/spus/assignable-options`；线上 bundle 已无 `legacyUnselectableCodes` / `PET_DAILY` 硬编码。
- 商品中心收敛（详见 `2026-11-12-product-center-spu-domain-consolidation-v2-debt.md`）：
  两个真源 `product_spu_lifecycle.py` / `product_spu_binding.py`，
  三条 CHECK 约束从真源渲染，值域拆成**两个独立端点**（查 ≠ 挂）。
- 隧道看门狗改 `conhost.exe --headless`（不再弹窗）。
- **顺带修掉三个真缺陷**（都是发版门禁抓出来的，不是这批引入的）：
  black 格式门禁（16 个文件）、`VERSION` 双 BOM（会让 `/healthz/ready` 报 `'\ufeff\ufeffv7.23.0'`）、
  一个 U+FFFD 坏字节。
- **架构 SSOT 门禁修复**：`scripts/verify_architecture_ssot.py` 排除 `.worktrees`、
  Base 判定由文本扫描改为 AST → Compliance **25% → 100%**（4/4 PASS）。

## API 契约门禁：扫描范围空转 + 告警口径失真（2026-11-13）

> 完整方案与实施记录：`docs/superpowers/plans/2026-11-13-api-contract-gate-scope-fix.md`

| 批次 | 提交 | 内容 |
|---|---|---|
| 第一批 | `795cc6d7` | 扫描范围修到真源 + AST 六桶口径 + 聚合报告 + 守护测试 17 例 + 流水线/规范文档/发布清单 |
| 第二批 | `cc51a1c7` | 3 个守卫失效 except 块补失败原因日志（**零行为变更**） |
| 文档 | `de0659c9` | 方案文档状态更新为已验收 |
| 索引 | `ad69df02` | 本索引补记 v7.23.0 与本批两批（此前停在 v7.22.0） |
| 发版 | `0e6ec9c8` | `VERSION` + `CHANGELOG` 同提交，打 tag `v7.24.0` |

### 问题：这道门禁**从未看过一行真实路由代码**

- 扫描范围停在 `backend/routers/` —— 那是 **76 个旧门牌号（兼容垫片），实测零路由定义**；
  82 个真正定义路由的文件早在 `backend/domains/<域>/routers/`。
- ⇒ `--changed-files` 模式（发布门禁用的就是这个）**一个真实路由都匹配不到**，
  每次发版都报「本次发布没有改动 router 文件，跳过验证」并**绿灯放行**
  —— v7.23.0 改了 `product_center.py` 也照样放行。
- ⇒ 告警口径用「正则找 `try:` + 按缩进猜块尾」，报出「518 条缺错误日志」，
  而 AST 重算后真正的静默只有几十处（**9:1 的噪音比**）。

### 修好之后（CI 日志实锤，非本地推断）

```
扫描候选: 158 个文件
本次验证: 158 个文件（其中定义路由的: 80 个）
异常块总数: 886
错误数量: 0
F 真静默（不记、不抛、不返回、不跳过）: 47   ← 需要人看
```

错误数 0 ⇒ **不卡任何一次发版**；报告从 1700+ 行压到 35 行，
完整明细落 `temp/validation_api_contracts.txt`（CI 会自动当 artifact 上传）。

### 口径重新核准（重要教训）

上一轮口头说的「**58 处真静默**」来自一个**没有入库的临时脚本** ⇒ 口径不可复现
（穷举 8 组谓词变体 × 六个桶维度，无一命中 58）。
处置原则是**人工复核 > 拟合数字**：挑出两处差异块人工判定（都是「有意降级」），
据此把 E 桶定成「except 块里只要有任何控制流决策就不算静默」，
重新核准为 **50 处**；第二批补完日志后是 **47 处 / 27 个文件**。
⇒ **数字与口径都写进守护测试**（含 2 条语义锚点 + 2 条守卫锚点），
这正是律 1「真源只能一个，而且必须写在纸上」的由来。

## v7.24.0 上线：门禁第一次真的看了路由代码（2026-11-13）

- tag `v7.24.0`（tag 对象 `802a08ab`）**双端同一对象**，提交 `0e6ec9c8`；
  部署流水线 run `43372513282` 成功，`VERSION` 为纯 7 字节 `v7.24.0`（与 tag 同提交）。
- 部署日志核对：`migration_status=up_to_date`；
  `current_revision == head_revision == current_schema_20261228_bridge_spu_sku_binding_status_constraint`；
  `missing_tables=[]`、`missing_columns=[]`；Phase 2.7 视图重建 40+ 定义全部就位；
  Phase 3a / 3a' 库存重建均 `[OK]`；`Resolved tags: Backend=v7.24.0, Frontend=v7.24.0`。
- 生产独立验收（HTTP 直观测）：`/api/healthz/ready` → 200、`version=v7.24.0`、
  `database=connected`、`dashboard=ready`；首页 200。
- **决定性证据在发布流水线日志里**（不是本地推断）：

  ```
  [INFO] Changed router files: 2
  本次验证: 2 个文件（其中定义路由的: 2 个）
  F 真静默: 0
  ```

  改动前同一位置是「Changed router files: 0」+「跳过验证」**绿灯放行**；
  现在真去验了那 2 个域内路由文件，且真静默 0
  ⇒ **第二批补的日志已被门禁确认生效**。
- 发版提交 CI 三线全绿（CI Pipeline / Validate Data Flow / Docker Build and Push）；
  本地 `scripts/verify_release_local.py --skip-build` exit=0。
- **回归补跑**（本会话前两批只跑了 `backend/tests`，这两个目录当轮没跑）：
  - 根 `tests/` → **746 passed / 5 skipped / 0 failed**（265s）；
    上一版基线 738 passed / 5 skipped / 0 failed，**+8** 是后续批次新增的守护用例。
  - `backend/tests/data_pipeline/`（130 个文件）→ **1235 passed / 1 skipped / 0 failed**（129.6s）
    ⇒ 早先记的「仍有 2 条既有失败」**已过期**，
    `test_granularity_alignment_sql.py` 现为 **7 passed / 0 failed**，两条各有归宿：
    一条随薄封装改读 MV 而**修复**，一条随 `sql/mart/annual_summary_shop_month.sql`
    退役而**用例被删**（提交 `f34eee24` 退役清理时一并处理）。
- 业务概念**零变化**：商品/款/货/归属/各域概念、对外接口、数据库结构全部原样；
  只变「谁来体检」与「新代码写哪条路径」。

### 补跑时顺带挖出来的一个真问题：同一组接口被挂载了两次

- **现象**：`backend/tests/data_pipeline/` 全量补跑（**1235 passed / 1 skipped / 0 failed**）
  时，FastAPI 打出成片 `Duplicate Operation ID` 警告。
- **根因**：`backend/domains/collection/routes.py` 与 `backend/domains/platform/routes.py`
  **各自都 include 了同一批 5 个 router 对象**
  （`main_accounts` / `shop_accounts` / `shop_account_aliases` /
  `platform_shop_discoveries` / `warehouse_name_aliases`），
  且 prefix（`/api`）与 tags 完全相同 ⇒ 同一份实现挂了两遍。
- **实测**（直接数 `app.routes`）：共 **735** 个「方法+路径」条目，
  其中 **24 条被注册两次，涉及 17 个路径**
  （如 `/api/shop-accounts`、`/api/shop-account-aliases`、`/api/warehouse-name-aliases`、
  `/api/main-accounts`、`/api/platform-shop-discoveries`）。
- **影响**：**今天没有功能故障** —— 挂的是同一个 handler 对象，请求命中先注册的那份，行为一致。
  但 ① OpenAPI 里出现重复 `operation_id`（客户端生成器可能重复出方法）；
  ② 违反律 1：同一组接口有**两个挂载点**，将来一处改了 prefix/tags 就会裂成两条不同的路由。
- **为什么门禁没抓到**：API 契约门禁查的是「路由文件里有没有按规范写 except 块」，
  **不查「同一个 router 被挂了几次」** ⇒ 这是门禁的下一个盲区。
  （旧垫片 `backend/routers/*` 已确认**不参与挂载**，只是 import 兼容层，不是本问题的来源。）

### 本会话遗留（已拍板，另排批次）

| 项 | 说明 |
|---|---|
| ~~**发版窗口**~~ | **已完成**：v7.24.0 已上生产并独立验收（run `43372513282`、tag 对象 `802a08ab`、双端一致） |
| 47 处真静默 | 分批清理（跨 4 域 27 文件，pre-launch 要求拆）—— **2026-11-13 复核：口径有偏差，先改判定再补日志**，见下「F 桶口径复核」 |
| 74 个带 BOM 的路由文件 | 单独一批清理（本批已用 `utf-8-sig` 兜住，不阻塞）—— **2026-11-13 复核：实际是 180 个带 BOM 的被跟踪文件（其中 76 个在 routers 目录）**，见下「BOM 现状复核」 |
| **`backend/tests/data_pipeline/` 不在 CI 覆盖内** | 130 个文件只在「本次改动到它们」时才跑 ⇒ 口径漂移可能长期潜伏（同 `tests/unit` 曾经的情况，2026-11-10 实测）。本地实测 **1235 passed / 1 skipped / 0 failed**（130 文件全量），但**CI 守不住** |
| **同一组接口被挂载两次** | `collection/routes.py` 与 `platform/routes.py` 都 include 同一批 5 个 router ⇒ **17 个路径 / 24 个条目双注册**。今天无功能故障，但 OpenAPI 重复 `operation_id`，且门禁查不出来 ⇒ 建议加「router 唯一挂载点」守护用例 |
| **公开仓库里的「生产密码」文件** | `.env.production.passwords.txt` 被 git 跟踪、且 GitHub 仓库是 **PUBLIC**（值已被取代，但公开不可撤回）；仓库自带的密钥门禁也漏了它 ⇒ 需「轮换 + 取消跟踪 + 补门禁」三步，另排批次（详见下节） |
| fail-closed（计数失败即拒删） | 需先定义「引用数未知」状态，**建议随 M5.2 硬删一起做** |
| 款 → 货的层级视图（IA） | **产品演进**，需先定 IA 再动手（见 V2 债文档 §4） |

## 安全发现：公开仓库里跟踪着一份「生产密码」文件（2026-11-13 补跑时发现）

- **对象**：`.env.production.passwords.txt`（599 字节）——`git ls-files` 确认**被 git 跟踪**
  （blob `a414d428`），自初始提交 `634a90ef` 起入库，2026-01-09 经 `372365eb`「docker容器优化」又改过一次。
- **仓库可见性**：GitHub `timberdayz/timber_dayz` = **PUBLIC**
  ⇒ 这份文件里的值**从入库那一刻起就是公开的**，而且**公开仓库的历史不可撤回**。
- **内容**：5 个密钥形状的值（`POSTGRES_PASSWORD` / `REDIS_PASSWORD` / `SECRET_KEY` /
  `JWT_SECRET_KEY` / `ACCOUNT_ENCRYPTION_KEY`），**不是占位符**（长度 15~44，随机形状）。
- **是否等于线上真值**：**不等于**。与本地 `.env.production` 逐项做 SHA-256 比对，
  **5 项全部不同** ⇒ 这是 2025-01 那批已被取代的旧值。
- **有没有现行密钥泄露**：**没有**。把 `.env.production` 里全部敏感类值
  （`SECRET_KEY` / `JWT_SECRET` / `JWT_SECRET_KEY` / `POSTGRES_PASSWORD` /
  `REDIS_PASSWORD` / `ACCOUNT_ENCRYPTION_KEY`）逐个与所有被跟踪的疑似密钥文件比对
  （`.env.cleaned` / `.env.limiter` / `.env.example` / `config/production.example.env` /
  `frontend/.env.development` + 3 个相关 md）⇒ **0 命中**
  （`config/production.example.env` 命中的只有 `POSTGRES_USER` / `POSTGRES_DB`，
  是用户名和库名，不是密钥）。
- **真正的问题有三条**：
  1. 一份**名为「生产密码」的文件躺在公开仓库里**，从初始提交起就公开了；
  2. 只要有任何环境（某台开发机 / 测试机 / 旧服务器）当年照着它生成过密钥，
     那套密钥**现在应视为已泄露**；
  3. **仓库自带的密钥门禁看不见它**：`scripts/check_precommit_secrets.py` 的
     `is_blocked()` 只拦「文件名恰好是 `.env`」和「后缀是 `.key` / `.enc`」，
     ⇒ `.env.production.passwords.txt`（后缀 `.txt`）、`.env.cleaned`、`.env.limiter`
     **全部绕过**。**这道门禁本该在初始提交时就拦住它，实际没有。**
- **建议处置**（另排批次，**需拍板**；本轮只记录，未动代码）：
  1. **先轮换**：确认是否还有环境在用这 5 个值；在用就轮换（公开仓库 ⇒ 视为已泄露）。
  2. **再取消跟踪**：`git rm --cached .env.production.passwords.txt` + 写进 `.gitignore`；
     内容移出仓库，改由部署时从 Secret 注入（与律 1 一致：口令的真源不能是仓库里的文本文件）。
  3. **历史清理（可选、成本高）**：`git filter-repo` 重写历史会**作废全部已发布 tag**
     （含 `v7.24.0` 与所有历史版本）⇒ 必须与双镜像 + tag 策略一起规划，**不能顺手做**。
  4. **补门禁**：`scripts/check_precommit_secrets.py` 的 `is_blocked()` 扩展到
     「以 `.env` 开头」/「文件名含 `password` / `secret` / `credential`」，
     并加守护测试钉死（律 1：门禁的判定口径必须写在测试里）。

> **2026-11-13 更新：批次 C2 已实施**（取消跟踪 + `.gitignore` + 门禁补强 + 守护测试），
> 且**取证结论比原先严重**：公开仓库里不只有密钥，还有**店铺账号密文 + 能解开它的密钥**。
> 详见下面「批次 C2：公开仓库的密钥与账号密文」一节。

## SSH 访问真源文档 + 守护测试（2026-11-13）

- **起因是一次真实的误判**：agent 用 `root@134.175.222.171` 试连，两次
  `Permission denied` ⇒ 判定「本机没有生产 SSH 私钥」，并据此写下
  「部署类核验无法登机」—— 后续多轮判断都建立在这个错误前提上。
- **真相**：隧道与生产运维都用 **`deploy@`** + **`~/.ssh/github_actions_deploy`**，
  这把钥匙**一直在本机**、隧道**一直在跑**（实测 PID 30036、`15433 → 15435`）；
  `root@` 属于**部署流水线**（私钥只在 GitHub Actions Secret `PRODUCTION_SSH_PRIVATE_KEY`），
  **本机刻意不持有** ⇒ 那是设计，不是缺失。
- **新增真源**：`docs/guides/SSH_ACCESS.md` —— 四条通道（GitHub 代码 / 生产运维 /
  云端隧道 / 生产部署）的**账号 ↔ 钥匙 ↔ 用途**表、机器可读配置口径、
  自检清单、常见误判→真相、红线、变更纪律。
- **新增守护**：`tests/test_ssh_access_contract.py`（12 例）——
  钉死「文档 ↔ 脚本」一致（账号、端口、隧道默认值不许漂移）、
  脚本不许把 `root@` 当登录目标、不许口令登录、本机必须持有隧道私钥、
  入口文档必须指向这份真源。
- **CI 覆盖补齐**：`test_ssh_access_contract.py` + `test_cloud_sync_tunnel_watchdog.py`
  + `test_container_cloud_tunnel_host_contract.py` 三份守护**此前根本不在 CI 里跑**
  ⇒ 已进 `ci.yml` 的根契约清单（纯源码，不碰数据库）⇒ **漂移会让 CI 直接变红**。
- **入口已铺好**：`AGENTS.md`（新增 SSH Access 小节 + 文档地图）、
  `docs/ACTIVE_DOCS.md`、`docs/guides/ENVIRONMENT_MODEL.md`、
  `docs/guides/RELEASE_CHECKLIST.md`（"流水线绿 ≠ 验收" 那节给出正确账号与命令）、
  `scripts/watch_cloud_sync_tunnel.ps1` 头部。
- **两处更正作废**：上一轮口头结论「本机无生产 SSH 私钥」「无法登机核验」**均不成立**；
  `deploy@` 实测可登机（VM-0-15-ubuntu，7 个容器全 healthy），
  生产只读核查（容器状态 / nginx 日志 / 只读 SQL）能力是有的。

## 商品中心 SKU 资料页 SPU 缺陷：方案已出，待拍板（2026-11-13）

> 完整方案：`docs/superpowers/plans/2026-11-13-product-center-sku-spu-ui-defect-fix.md`

- **现象（Walter 实际使用中发现）**：筛选框写着 `XH-FASHION-005`，表格却是
  `XH-TOYS-MYTK` 的货；下拉框是空的；行内换款下拉也打不开。
- **根因**：值域工厂 `createSpuSearch` 返回的是**普通对象 + 嵌套 ref**，
  而 Vue **只拆包最外层 ref** ⇒ 模板拿到的不是名单、而是"装着名单的盒子"
  ⇒ ① 下拉恒处于 loading（Element Plus 规则 `options.size > 0 && !loading`）
  ⇒ 选项列表不渲染；② `v-for` 迭代到 ref 的 5 个内部属性 ⇒ 5 个空白项、选不中；
  ③ 选不中 ⇒ 请求**从不带 `spu=`** ⇒ **表格永远不按款筛选**。
- **最小复现**（仓库自带 vue 3.5.22 实跑）：当前写法渲染 **5 个空白项**；
  `reactive` 对照组渲染 **1 个正常项**。
- **证据链**：生产日志 `/api/spus/options?keyword=XH-FASHION-005` → 200 有数据
  （后端没问题）；`/api/skus` 请求**从不带 `spu=`**；
  生产库 `XH-FASHION-005` 当前挂货 **0**（若筛效应为空表，实际 20 行 ⇒ 没筛）；
  1119 条当前归属**无一货挂两款**（数据层干净）⇒ **后端零改动**。
- **为什么利润测算页没事**：那一页的候选来自 `operatingDimensions`（**reactive 数组**）
  ⇒ 正常拆包、参数真发出（日志实证 `...&spu=XH-FASHION-006`）。
  且两者是**两个业务问题**（主数据筛选 vs 定价测算），**不该合并**。
- **方案分三批**：A 修工厂 + 运行时守护测试 + 结构性门禁（必做）；
  B 值域默认候选排序 + 空结果文案（另排，改的是后端口径）；
  C 本会话新发现的两条（接口双挂载、公开仓库密码文件）。
- **SSOT 判定**：**符合** —— 不新增口径、不合并口径，只是把"前端怎么读后端真源"
  从两种写法收敛成一种，并把"界面真的能用"钉进运行时测试。

## 批次 A / B / C 全部实施完成（2026-11-13，本会话）

> 方案文档：`docs/superpowers/plans/2026-11-13-product-center-sku-spu-ui-defect-fix.md`
> （§7 实施记录同步更新）。Walter 拍板：**三个批次在本会话做完，不留给其他会话**。

### 批次 A：商品中心 SKU 资料页的 SPU 下拉/筛选（提交 `f0f95721`）

- **修法**：改**值域工厂** `createSpuSearch` 让它返回 **reactive** 对象
  （`options` / `loading` 是普通值），不是改调用方 ⇒ 一处改动两处下拉同时生效；
  `ProductCenter.vue` L1280 的 `.value` 跟着改；模板不动；**后端零改动**。
- **守护**：`frontend/tests/productCenterSpuOptionsRender.test.mjs`（5 例）——
  ① `Array.isArray(options)`；② `typeof loading === "boolean"`；
  ③ 用 `vue/server-renderer` **真渲染一次**，断言款编码出现在 HTML 里且无空白项；
  ④ 搜索失败清空候选；⑤ 工厂必须 `reactive` 且不许再 import `ref`；⑥ 组件不许取 `.value`。
- **TDD 红侧已验证**：用**旧写法**实跑 ⇒ `Array.isArray` = false、
  `typeof loading` ≠ boolean ⇒ 断言会红；渲染崩在 `this.spu.options.map is not a function`。
- **验证**：前端 **200 passed / 0 failed**；`npm run build` ✓。

### 批次 A 回归修复：值域工厂改名（提交 `1f7cb413`）

- **事故**：批次 A 把局部状态容器命名成了 `api` ⇒ `api.search(query)` 被前端 API 契约门禁
  （`scripts/validate_frontend_api_methods.py`，正则 `(?:this\.)?api\.(\w+)\s*\(`）
  判成「调用了不存在的后端方法 search」⇒ **Validate Data Flow 流水线红**（run `43387187814`）。
- **修法**：局部容器改名 `valueDomain`，注释写明为什么不能叫 `api` ⇒ **不弱化门禁**。
- **教训**：门禁**已存在**（`backend/tests/test_validate_frontend_api_methods_contract.py`
  断言全量扫描 `missing_calls == 0`）—— 是我没在推送前跑后端全量才漏出去。
  ⇒ **推 main 前必须跑完根 `tests/` + 后端全量**。

### 批次 B1：值域默认候选按「当前挂货数」排序（提交 `f8c44012`）

- **问题（生产实测）**：284 个在售款按编码排序时前 50 个是 `XH-BABY-MC` ~ `XH-FASHION-695`，
  `XH-TOYS-MYTK` 排**第 277 位** ⇒ 玩具类几乎永远不在默认候选里。
- **修法**：新增 `_spu_option_order()`（当前挂货数 desc + 编码 asc），
  浏览口径与可绑定口径**共用同一份**排序 ⇒ 不会一个按编码、一个按挂货数。
- **口径纪律**：排序**不是口径**（哪些款可选仍由各自端点的过滤条件决定）；
  挂货数判定引用真源 `current_binding_condition()`；用相关子查询而非 join+group_by。
- **TDD 红侧已验证**：把 `_spu_option_order` 临时改回「按编码排」⇒ **4 条新用例全红**。
- **测试基建**：新增本地 fixture —— SQLite `ATTACH ':memory:' AS core` 后只建
  `dim_spu` / `bridge_spu_sku`（生产表挂在 PostgreSQL 的 `core` schema 下，
  仓库既有 `sqlite_session` fixture 会报 `unknown database core`）。

### 批次 B2：空结果说清原因与下一步（提交 `c121c3f3`）

- **问题**：选中一个当前挂货 0 条的款（生产实测 `XH-FASHION-005`），表格只显示
  笼统的「暂无数据」⇒ 运营以为系统坏了；下拉搜不到也只显示「无数据」。
- **修法**：SKU 表格接 `:empty-text="skuEmptyText"`（按款筛时显示「款 X 当前没有挂货」）；
  两个下拉各接一套 `no-data-text`（浏览口径提示「换个关键词」，可绑定口径提示「先去建款」）。
- **TDD 红侧已验证**：临时拆掉接线 ⇒ **2 条接线用例红**。
- **B3「口径可见标注」取消**：实测浏览口径与可绑定口径的**集合完全相同**
  （生产 284 = 284，差集 0）⇒ 无适用对象，不为不存在的情况写界面；
  且加 `biz_status` 会破坏既有契约 `set(payload) == {"spu","spu_name"}`。

### 批次 C1：同一组接口被挂载两次（提交 `db57034d`）

- **实测（改前）**：development / collector 模式各有 **24 条 (路径, 方法) 重复注册，
  涉及 17 条路径**；production 模式 0 条（**production 根本不注册 collection 域**）。
  FastAPI 生成 OpenAPI 时为每条重复路由打 `UserWarning: Duplicate Operation ID`。
- **修法**：账号类 router（主账号 / 店铺账号 / 店铺别名 / 平台店铺ID发现 / 仓名别名）
  的**唯一挂载点**定在 **platform 域**，删掉 collection 侧那 5 条 include。
  ⚠️ 之所以**不能**反过来删 platform 侧的：production 模式不注册 collection 域
  ⇒ 账号类接口在生产上只由 platform 提供 ⇒ 反过来删会**删掉生产接口**。
- **改后实测**：四种模式（development / collector / collector+local / production）
  重复条目**全部归零**（759 → 735、409 → 385）。
- **守护**（新建 `backend/tests/test_router_unique_mount_points.py`）：
  ① 四种模式都不许有重复 (路径, 方法)；② production/dev 下账号类接口依然存在
  （防「去重复」变「删接口」）；③ 这 5 组端点函数各自只注册一次；
  ④ 生成 OpenAPI 时不许出现 `Duplicate Operation ID` 警告
  —— 这一条才是重复挂载**唯一可观测**的信号（schema 里 operation_id 反而唯一，
  只断言 schema 会得到一条「写完就绿」的假测试）。
- **TDD 红侧已验证**：把 5 条 include 临时放回 ⇒ **6 条守护用例红**。

### 批次 C2：公开仓库的密钥与账号密文（提交见本节末）

- **原发现**：`.env.production.passwords.txt`（599 字节，5 个密钥）自初始提交起公开。
- **本会话取证结论（只读，SHA-256 比对，不打印任何值）**：
  - **现役密钥未泄露**：生产 `/opt/xihong_erp/.env` 与 4 个容器生效环境变量的
    5 个敏感值，与仓库被跟踪文件里的旧值**逐项全不同** ⇒ 生产现役密钥安全。
  - **但泄露的是「已废弃的旧密钥」**：仓库里 `.env.production.passwords.txt` 的 5 个值
    （2025-01 那批）与生产现役值**全部不同**；生产机上还留着一份同名文件
    （部署产物，2026-04-07），内容与仓库里那份**逐字节同源**。
  - **⚠️ 严重升级：密文 + 解密密钥同时公开**。仓库里同时跟踪着
    `accounts.enc`（12,964 字节，Fernet 密文）与 `.env.cleaned`（其中带着
    `ACCOUNT_ENCRYPTION_KEY`）⇒ **实测可用公开仓库里的密钥直接解开 `accounts.enc`**：
    解出 **15 个店铺账号**（Amazon 2 / Shopee 5 / Tiktok 4 / 妙手ERP 2 /
    miaoshou 1 / 验证码测试账号 1），**每个都有非空密码**（长度 8~23），
    还带 `Email account` / `Email password` / `phone` / `proxy_region` 等字段。
    ⇒ 这不是「旧密钥泄露」，而是**店铺账号密码公开**。
  - **生产库未受影响**：生产 `core.shop_accounts` 的密码用**现役** `ACCOUNT_ENCRYPTION_KEY`
    加密，泄露的旧密钥**解不开**（实测 `InvalidToken`）。
- **本批已做（代码侧）**：
  1. **取消跟踪**（`git rm --cached`，本地文件保留）：
     `.env.production.passwords.txt`、`.env.cleaned`、`accounts.enc`、
     `frontend/.env.development`（Mock 开关已从代码里删除，该文件是死文件）。
  2. **`.gitignore`**：`.env.*`（含 `!.env.example` / `!.env.template` / `!.env.limiter`）
     + `*.passwords.txt` + `*.enc`。
  3. **补门禁** `scripts/check_precommit_secrets.py` 的 `is_blocked()`：
     按**规则**拦（`.env` 家族 / 疑似敏感名 + 数据类扩展名 / 加密与密钥后缀），
     不再逐个文件名补；`ALLOWED_BASENAMES` 显式放行 `.env.limiter`
     （限流器运行期配置、纯 ASCII、只有一个开关、**无口令**）。
  4. **守护测试**（新建 `tests/test_secret_files_not_tracked.py`，并进 CI 根契约清单）：
     ① 这 4 个文件不在 `git ls-files` 里；② **全仓扫**：被跟踪文件里没有任何一个
     会被门禁拦下；③ 门禁对泄露文件判拦、**且不误伤**模板/文档/脚本；
     ④ `.gitignore` 真的挡住（`git check-ignore`）。
  5. **真源文档** `docs/guides/ENV_FILE_CONTRACT.md` 增「Repository Tracking Policy」。
- **TDD 红侧已验证**：旧版 `is_blocked()` 对 6 个泄露文件**漏放行 5 个**；
  `HEAD` 里那 4 个文件仍在跟踪 ⇒ 新守护在旧状态下必红。
- **仍需 Walter 拍板（agent 无权也不应自行执行）**：
  1. ~~**轮换那 15 个店铺账号的密码**~~ ——
     **2026-11-13 Walter 决定：不轮换**（判断为不会泄露）。
     ⇒ 本项**关闭**。取证结论本身不变（那些值曾进过公开仓库），
     但「是否轮换」是业务负责人的决定，不是 agent 能替代的判断。
     代码侧止血（取消跟踪 + `.gitignore` + 门禁 + 守护）已完成并在线。
  2. **历史清理**（`git filter-repo`）—— 会作废全部已发布 tag（含 `v7.24.0`），
     **本会话明确不做**；
  3. **删除生产机上的 `/opt/xihong_erp/.env.production.passwords.txt`**（旧密钥副本）——
     属生产写操作，须走发版流程或人工执行；
  4. 确认 `.env.cleaned` 里的旧 `SECRET_KEY` / `JWT_SECRET_KEY` / `METABASE_API_KEY`
     在**任何**环境都还活着 —— 本次只比对了生产与本机，**未覆盖**已下线的旧环境。

### F 桶口径复核（2026-11-13 实测，不是推断）

门禁把每个 ``except`` 块分六桶：A 记了错误日志 / D 显式 raise / B 记了其它级别日志 /
C 结构化 error_response / E 有意降级 / **F 真静默（不记、不抛、不返回、不跳过）**。
当前 F 桶 = **47 处 / 27 文件**，分布：platform 19 / data_platform 14 / business 8 / collection 6。

**逐处复核（AST 级分类）后的真实性质**：

| 实际性质 | 处数 | 说明 |
|---|---|---|
| 模块级可选依赖兜底 | 10 | ``except ImportError: xxx = None`` —— 有意降级，**口径误伤** |
| 函数内"赋值兜底" | 19 | 吞掉异常后用变量兜住 |
| 函数内有副作用但不记日志 | 17 | 例：``except: failures.append({...})`` —— **失败明细已回给调用方** |
| 模块级其他 | 1 | — |

⇒ **真实业务风险不是"出错时用户看不到"，而是"出错时运维在日志里查不到"**：
例如 ``users_admin.py:602`` 批量改用户失败会回 ``ok=False, error_message=...``（用户看得见），
但**日志里一条都没有**，事后只能翻前端返回或加日志重跑。

⇒ **处置顺序（与原台账「分批清理 47 处」不同）**：① 先把 E 桶判准（把"收进结果列表/结构化
返回"认成有意降级），只改判定、不动生产代码 ⇒ 消掉一批误伤；② 剩下的按 4 个域分 4 批补
``logger.warning``，**不改变任何返回行为** ⇒ 零业务风险；③ 补"只拦新增"的守护。
⚠️ 现在这条门禁**错误数恒为 0**（真静默只算 warning），从来没卡过发版 ⇒ 真正开拦之前，
"存量欠账 vs 新增红线"必须分开，否则一开就红一片。

### BOM 现状复核（2026-11-13 实测）

台账记的「74 个带 BOM 的路由文件」**不准**：实际是 **180 个被跟踪文件带 BOM**
（.py 88 / .md 83 / .vue 3 / .mjs 2 / .yml 1 / .json 1 / .js 1 / .txt 1），
其中路径含 router/routes 的 **76 个**（``backend/routers`` 62 + ``backend/domains/*/routers`` 12）。

**实测影响面（含对原判断的更正）**：

| 场景 | 实测结果 |
|---|---|
| YAML | ✅ **无害** —— ``yaml.safe_load`` 吃 BOM 正常，GitHub Actions 正常。``.github/workflows/deploy-production.yml`` 确实带 BOM，但部署一直跑得通（v7.25.0 / v7.26.0 都用它发的） |
| JSON | ❌ **会崩** —— ``json.loads(open(f, encoding="utf-8").read())`` 直接报 ``Unexpected UTF-8 BOM``。``backend/tests/data_pipeline/fixtures/translation_header_columns.json`` 就是这样，现在靠消费方写 ``encoding="utf-8-sig"`` 兜着（``test_semantic_translation_guardrails.py:97``），**下一个忘了写的人就崩** |
| Python AST | ❌ **会崩** —— ``ast.parse(按 utf-8 读出的文本)`` → ``SyntaxError: invalid non-printable character U+FEFF``。88 个 .py 带 BOM ⇒ 任何"读源码做 AST 分析"的门禁脚本都有这颗雷（仓库自己的门禁都在用 utf-8-sig 绕） |
| 守护覆盖 | ❌ **零覆盖** —— ``scripts/verify_utf8_source_hygiene.py`` 只查乱码特征与 UTF-8 有效性，**不看 BOM** |

⇒ **处置顺序**：① 先补"BOM 不许有"的守护并改成全仓扫（先只对新增/改动报错）；
② 只清"会崩的"那批（.json 1 + .yml 1 + .vue/.mjs/.js 6 + .py 88），**.md 83 个是纯噪音，不清**；
③ 手法用脚本批量去 BOM + **逐字节可逆验证**（.md 文件多，改错难发现）。
⇒ 编码约定最好与批次 D 的 ``.ps1`` 规矩合到同一份文档（仓库形态无 BOM / 采集机形态含中文才带 BOM）。

### 超长函数现状复核（2026-11-13 实测）

lint 规则 ``oversized_function``（>50 行）**本意是管采集组件**（``modules/platforms/**``），
但 CI 把它跑在「本次改动的所有文件」上 ⇒ 全仓真实分布（AST 实测）：

| 范围 | 文件数 | 处数 | 备注 |
|---|---|---|---|
| ``modules/platforms/``（规则本意范围） | 21 | **55** | 集中在 ``date_picker.py`` / ``export.py``，是规则真该治的那批 |
| backend 生产代码 | 237 | 751 | 逐个清不现实 |
| 测试文件 | 194 | **498** | **不该拦** —— 一个用例天然是一条长链路（``test_postgresql_dashboard_service.py`` 有 21 处，最长 297 行），拆开反而更难读 |
| modules 其它 | 83 | 272 | |
| 其它目录 | 478 | 702 | 含 ``tools/``、``archive/`` |

⇒ **方向不是"逐个拆"，而是"先把规则放回它该管的地方"**：
① 测试文件豁免（一次改动消掉 498 处噪音，**最划算**）；
② 生产代码改**增量红线**（只拦本次新写的超长函数，历史不追）⇒ 债务自然收敛，不用大重构；
③ 采集组件那 55 处单独排批（平台脚本失败时最难排查，拆完直接降本）。
⚠️ 本会话 E-3 收尾时撞到过：CI 报新守护函数 62 行超限，但同一测试文件里还有 21 处没人管
—— **说明这条规则在测试文件上是噪音，在采集组件上才是价值**。


## v7.25.0 上线：商品中心 SPU 缺陷收口 + 接口去重挂载 + 密钥门禁补强（2026-11-13）

> 方案与实施记录：`docs/superpowers/plans/2026-11-13-product-center-sku-spu-ui-defect-fix.md` §7

| 项 | 值 |
|---|---|
| tag 对象（双端同一对象） | `20ffd319`（annotated） |
| tag 指向的提交 | `707d9826`（**VERSION 与 tag 同提交**，纯 7 字节 `v7.25.0`） |
| 双镜像 main | GitHub SSH-443 与 CNB HTTPS **同为 `707d9826`**（`git ls-remote` 核对） |
| 发布流水线 | **run `43392504235` = success**（4 个 job 全 success） |
| CI 三线 | Validate Data Flow ✓ / CI Pipeline ✓ / Docker Build and Push ✓ |
| 数据库迁移 | **无**（日志确认 `Skipping database migrations (RUN_MIGRATIONS=0)`） |

**部署后独立验收（agent 自己打的接口，不采信流水线自述）**

| 项 | 结果 |
|---|---|
| `/api/healthz/ready` | HTTP 200 / `version=**v7.25.0**` / `database=connected` / `dashboard=ready` / `runtime_mode=production` |
| 首页 | HTTP 200 |
| 生产容器 | 7 个全 healthy；后端三件套 = `backend:v7.25.0`，前端 = `frontend:v7.25.0` |
| 部署批次 | `bootstrap_postgresql_dashboard_20261113_163211.log` + `rebuild_views_20261113_163211.log` |
| **路由无损**（C1 生产侧证据） | 生产 `/api/openapi.json` 部署前后**完全一致**：510 路径 / 625 操作 / 625 个 operation_id 全唯一 / 0 重复 ⇒ 去重复挂载**没丢接口** |
| **新排序已上线** | 部署后容器内 `_spu_option_order` 出现 3 处；生产库按「当前挂货数 desc、编码 asc」实测头部：`XH-ELEC-GF` 38、`XH-TOYS-YSC` 37、`XH-ELEC-DM` 28、`XH-TOYS-GMGD` 26、`XH-TOYS-ZD` 26、`XH-TOYS-GD` 24、`XH-TOYS-MYTK` 20、`XH-FASHION-006` 18、`XH-FASHION-KLM002` 16、`XH-TOYS-DK` 16 |
| 门禁真的在验 | API 契约门禁 `Changed router files: 1` → `本次验证: 1 个文件` → **`F 真静默: 0`**；前端 API 方法门禁 `缺失方法调用数: 0` |

**批次总表（A / B / C 三批全部落地并随本版上线）**

| 批次 | 提交 | 状态 |
|---|---|---|
| A 前端值域修 reactive | `f0f95721` | ✅ 上线 |
| A 回归（改名避开 API 门禁误报） | `1f7cb413` | ✅ 上线 |
| B1 值域默认排序（挂货数优先） | `f8c44012` | ✅ 上线 |
| B2 空结果文案 | `c121c3f3` | ✅ 上线 |
| C1 接口去重复挂载 | `db57034d` | ✅ 上线 |
| black 格式修复 | `07789728` | ✅ 上线 |
| C2 密钥与账号密文取消跟踪 + 门禁补强 | `c31f77e3` | ✅ 上线（**轮换仍待拍板**） |
| `.dockerignore` 补挡 `.env` 家族 | `d99a8f83` | ✅ 上线 |
| ruff F841 修复 | `707d9826` | ✅ 上线（= tag 指向的提交） |

**⚠️ 仍需 Walter 拍板的两件事**（代码侧已做完止血，历史不可撤回）：

1. **轮换那 15 个店铺账号的密码** —— 公开仓库里 `accounts.enc`（密文）与 `.env.cleaned`
   （解密密钥）同时存在，实测可解出账号密码 ⇒ 公开历史不可撤回 ⇒ 必须视为已泄露。
   轮换后要同步生产库 `core.shop_accounts` 与采集机账号库。
2. **删除生产机上的 `/opt/xihong_erp/.env.production.passwords.txt`**（旧密钥副本，
   与仓库里那份同源）—— 属生产写操作，须走发版流程或人工执行。

（`git filter-repo` 历史清理**不做**：会作废全部已发布 tag，含 `v7.24.0`。）

### 本会话的仓库级回归结果（v7.25.0 发版提交上实测）

| 范围 | 结果 |
|---|---|
| 根 `tests/` | **798 passed / 5 skipped / 0 failed**（基线 758 + 批次 C2 新增 40 例密钥守护） |
| 后端全量 `backend/tests` | **4593 passed / 7 skipped / 0 failed**（基线 4579 + 14） |
| 前端 `frontend/tests` | **207 passed / 0 failed**（原 195 + 批次 A 5 + 批次 B2 7） |
| API 契约门禁 | 0 错 / 65 警告（真静默 47，与基线一致）；发版时 `本次验证: 1 个文件`、`F 真静默: 0` |
| 前端 API 方法门禁 | **0 缺失**（批次 A 回归后恢复） |
| ruff / black（CI 同口径，对全部改动 Python 文件） | 全绿 |
| UTF-8 卫生 / 规则完整性 / 架构 SSOT | 全绿（SSOT 100%） |
| `verify_release_local.py --skip-build` | **exit 0**（"所有检查通过，可以开始部署！"） |



## 本地同步云端 v7.26.0 + 双镜像一致性收尾（2026-11-13）

> 云端已推 `v7.26.0`（「模板治理闭环」）；本地原为纯落后 4 个提交、0 领先（无分叉）。

| 项 | 值 |
|---|---|
| 本地 `main` | 快进到 `1083427d`（= `origin/main`），`VERSION` = `v7.26.0` |
| CNB 收尾 | `main` 由 `d908fa96` 快进到 `1083427d`；补 tag `v7.26.0`（**同一已存在对象** `009a2867`，未重建） |
| 双镜像核对（`git ls-remote`） | GitHub 与 CNB 的 `main` / `v7.25.0` / `v7.26.0` **全部同 SHA 同对象** |
| `sync_main_mirrors.ps1 -Sync` | `XIHONG_GIT_MIRROR_SYNCED=1083427d`（此前因两镜像 SHA 不等被 fail-closed 拦下，收尾后守卫通过） |
| 部署是否被触发 | **否** —— 仓库无 `.cnb.yml`，推 CNB tag 为惰性操作；GitHub 侧部署 run 仍是 `43402306171`（v7.26.0 那次） |
| 生产只读核对 | `/api/healthz/ready` → HTTP 200，`version=v7.26.0`，`database=connected`，`dashboard=ready` |

### 本地回归（v7.26.0 代码）

| 范围 | 结果 |
|---|---|
| 后端全量 `backend/tests` | **4594 passed / 7 skipped / 0 failed** |
| 前端 `frontend/tests` | **207 passed / 0 failed** |
| 根 `tests/` | 初次 **5 failed / 793 passed / 5 skipped** ⇒ 定性后全部归零（见批次 D） |
| CI 三线（`1083427d`） | Validate Data Flow ✓ / CI Pipeline ✓ / Docker Build and Push ✓ |

## 批次 D：`.ps1` 编码约定被 v7.25.0 / v7.26.0 两批打破（2026-11-13）

**根因（读代码得出，不是猜）**：

- `scripts/watch_cloud_sync_tunnel.ps1` 在 `05a359a1`（v7.26.0 发版提交）被**补了 UTF-8 BOM**，
  理由写的是「仓库既有用例全带 BOM」—— **与事实相反**：实测 27 个受跟踪 `.ps1` 里 **26 个无 BOM**；
- 真正的源头是 `e2103f46`（v7.25.0）给它加了一个 `⚠️`（非 ASCII），
  而 2026-11-11 方案明写「看门狗脚本**刻意保持纯 ASCII**」⇒ v7.26.0 用「补 BOM」去兜，
  变成**双重违约**（既非纯 ASCII，又破了「.ps1 全部无 BOM」）；
- **CI 为什么全绿**：`tests/test_ps_env_file_encoding_contract.py` **根本不在 CI 的根契约清单里**
  ⇒ 这份守护从未在 CI 上跑过 ⇒ 典型的「流水线绿 ≠ 验收」。

**处置**：

| 项 | 值 |
|---|---|
| 批次 D 提交 | `341441d6`（脚本 + 守护 + CI 纳管 + 书面真源）、`529060e3`（发布清单补「流水线绿 ≠ 验收」实例） |
| 脚本修复 | 去 BOM；`⚠️` → `NOTE:`（信息不丢，SSH 访问真源的引用保留） |
| 守护补强 | 新增 `test_watchdog_script_is_pure_ascii`；原有「.ps1 无 BOM」用例已覆盖 BOM 回归 |
| **红侧已验** | 修复前两条守护**都红**：BOM 用例红 + 纯 ASCII 用例红（抓到 `0x8f/0x9a/0xa0/0xb8/0xbb/0xbf/0xe2/0xef`） |
| CI 纳管 | `tests/test_ps_env_file_encoding_contract.py` 进 CI 根契约清单（CI 口径下 8 passed，不碰数据库） |
| 书面真源 | `docs/superpowers/plans/2026-11-11-shop-identity-guard-activation.md` 补上守护指向与「不要改用补 BOM」的理由 |
| 另一类失败（非缺陷） | 4 条 `test_executor_v2` 失败 = **本地库缺 v7.26.0 那一级迁移**（`current_schema_20261228_...` → `20261229_template_format_signature`）⇒ 跑 `scripts/run_current_schema_migrations.py` 后 27 passed |
| CI 验收（`341441d6`） | 三线全绿：Validate Data Flow ✓ / CI Pipeline ✓（8 job 全 success）/ Docker Build and Push ✓；**决定性证据**：CI 日志里 `test_ps_env_file_encoding_contract.py` 8 passed（新增守护真的在 CI 上跑），根契约清单在 CI 上 458 passed / 11 skipped |


## 批次 E：Docker 残留治理 + testcontainers 收敛（2026-11-13）

**起因（实测，不是推测）**：本机 Docker 攒下 **22 个悬空卷 + 2 个僵尸容器**，
其中 11 个匿名卷（736 MB）是 testcontainers 的残留。分三步处置，
每一步都有守护、每一步都写进纸上。

### E-1 清理残留（已完成）

| 项 | 值 |
|---|---|
| 匿名卷 | `python scripts/cleanup_test_containers.py --apply` ⇒ **11 个全删、0 失败**（只碰 `com.docker.volume.anonymous` 标签、只删无引用卷、命名卷永不触碰、绝不用 prune） |
| 僵尸容器 | `docker rm -f -v xh-verify-pg`、`docker rm -f xihong_erp_migrate`、`docker rm -f -v bold_einstein` |
| 构建缓存 | `docker builder prune -f` ⇒ 回收 **3.182 GB**（清理后 Build Cache 0B） |
| 边界复核 | 13 个具名卷（含 `xihong_erp_postgres_data`）**全部完好**；匿名卷 0 |

### E-2 清理自动化（提交 `8ad0bba5`）

**先更正一个错误结论**：testcontainers **本身不泄漏** —— 实测正常退出与
`os._exit()` 硬杀都由 Ryuk 正确回收（0 新卷）。真正成因是
**「进程被强杀 + 事后没人跑清理脚本」**：`scripts/cleanup_test_containers.py`
早在 `b716efbb` 就存在（安全边界完好），却除它自己的契约测试外**无任何流程调用**。

| 项 | 值 |
|---|---|
| 改动 | `backend/tests/conftest.py` 加 `pytest_sessionfinish` 钩子（best-effort，`check=False`，可用 `XIHONG_SKIP_TESTCONTAINER_CLEANUP=1` 跳过）+ `.github/workflows/ci.yml` 加清理步骤（`|| true`）+ 新增 `backend/tests/test_cleanup_test_containers_wired_contract.py`（6 条守护） |
| **红侧已验** | 实施前 3 条守护红；把钩子的 subprocess 调用注释掉 ⇒ 守护立刻变红 |
| 行为级验证 | 手工造无主匿名卷 ⇒ 跑一次 pytest 后该卷消失 |
| 门禁 | ruff/black 全绿；两份清理守护 14 passed；受影响测试 22 passed / 2 skipped |

### E-3 data_pipeline 的 40 处 testcontainers 收敛（本次）

**实测基线**：`backend/tests/data_pipeline` = **1274 passed / 1 skipped / 124.01 秒**。
其中 **40 处** `with PostgresContainer("postgres:15") as pg:` 样板（11 个文件），
每个容器启动 **1.76 秒** ⇒ 一轮回归付 **~70 秒**纯启动开销，还各留一个匿名卷。

**方案（先量后定）**：

| 候选 | 实测 | 判定 |
|---|---|---|
| 共用**一个 database** | — | ❌ 会直接红：21 处**裸** `CREATE TABLE`（没有 `IF NOT EXISTS`），其中 3 张表跨文件重名（`core.shop_accounts` 3 文件 / `core.shop_account_aliases` 2 文件 / `semantic.fact_orders_atomic` 2 文件）⇒ 第二个文件报 `relation already exists` |
| **单 session 容器 + 每用例独立 database** | 容器启动 **1.76 s**；`CREATE DATABASE` **0.063 s**；`DROP DATABASE` **0.076 s** | ✅ 既保住「每用例一个干净空库」的语义，又把 ~70 秒降到 ~7 秒 |

**为什么与原语义等价**：原实现每个用例起**全新容器**（库里只有 `public` schema）
⇒ 新建 database 与之等价。且 `refresh_runner._OPS_TABLES_READY_SIGNATURE` 是按
`db_url` 签名的 ⇒ 每个用例的库地址不同 ⇒ 不会被上一个用例的「已就绪」标记跳过建表。

**落地形态**：

- `backend/tests/conftest.py` 新增 `pg_shared_container`（**session 级**，复用会话护栏
  在 import 期起好的那个容器 ⇒ 整个后端测试会话不再多起容器）与
  `pg_database`（**函数级**，每用例一个独立库）；
- 11 个文件 40 处改写成 `async with pg_database() as pg:` —— **用例正文一个字不动**；
- 守护 `backend/tests/test_testcontainers_consolidation_contract.py`（7 条）**进 CI 根契约清单**。

**红侧与验收**：

| 项 | 值 |
|---|---|
| **红侧已验** | 实施前 **6 条守护红**，精确报出 40 处违规与 11 个文件；守护初版误伤 8 个连隔离库的模块（把 `create_async_engine` 当违规）⇒ 收窄为 AST 级判定（只查真实 import 与 `as pg` 的上下文） |
| **逐用例比对** | 改写前后 JUnit XML **逐用例**比对：**1275 个用例集合完全一致、状态零变化** ⇒ **零新增失败** |
| 耗时 | **124.01 秒 → 49.60 秒**（-60%） |
| 残留 | 跑完 **0 个匿名卷、0 个 postgres 残留容器**；13 个具名卷完好 |
| 守护 | 7 passed；ruff/black 全绿；CI 根契约清单已纳管 |
| CI 验收（`82c1aff8` / `463239df`） | 三线全绿（CI Pipeline 8 job 全 success / Validate Data Flow ✓ / Docker Build and Push ✓）；**决定性证据**：CI 上「Run pytest」**129 passed**（改写后的 11 个 data_pipeline 文件 + 新守护**真的在跑**，7 条守护逐条 PASSED）、根契约清单 **481 passed / 11 skipped**；CI 同版本组合（Python 3.11 + pytest 7.4.3 + pytest-asyncio 0.21.1）下同样全绿 |
| 采集组件 lint | CI 的 "Collection component lint"（告警模式 `--fail-on none`，未让流水线红）报出守护函数 62 行超 50 行上限 ⇒ 拆成两个 helper 后 **error 0 / warning 0**（提交 `463239df`）。仓库里既有的 23 处长函数告警（`test_postgresql_dashboard_service.py`）**不是这批引入的**，不在本次范围内动 |

> ⚠️ **踩过的坑（写下来别再踩）**：第一版改写脚本用**列号算术**在原文件里插参数，
> 把插入点算到了别的行（把 `from sqlalchemy.exc import ...` 改成了
> `from spg_databaseqlalchemy.exc import ...`）。
> ⇒ 教训：**机械改写必须做「逆向还原 + 逐字节比对」**（第二版脚本把每个
> 行级 edit 的逆变换写死，验完 107 个 edit 全可逆、还原后与原文件逐字节一致），
> 并且**优先用行级操作，不要用列级算术**。


## 账号设备身份 SSOT 收口（2026-11-13）

- 计划：`docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure.md` — **planned**

**起因（审查读代码得出，非推测）**：「账号设备身份」这一个业务概念同时存在于三处且互相矛盾 ——
① 上位文档 `COLLECTION_SESSION_AND_FINGERPRINT.md:20-23` 要求「从 DeviceFingerprintManager
获取或生成该账号的指纹，**注入** new_context」；② 生效文档 `COLLECTION_SESSION_LIFECYCLE.md`
R8 要求 profile 模式「**不注入**，沿用 profile 原生环境」；③ 磁盘上 `data/device_fingerprints/`
躺着 26 个**全部作废**的指纹文件（19 个孤儿，含 1 个编码乱码 `Tiktok 1µê`）。

**已核对为「对的，不要重复改」**：

| 项 | 判定 |
|---|---|
| R1 真相源唯一 / R2 登录即持久 / R3 人工确认即成立 / R4 读取即信任 | ✅ |
| R5 并行扇出用内存快照 / R6 账号级串行 / R7 正常关闭才落盘 | ✅ |
| **R8 顺序路径**（`runtime_session.py:687` normalize） | ✅ |
| **R8 并行路径**（`executor_v2.py:6231-6241` 复用同一 normalize） | ✅ |

⇒ **验收项 H（顺序与并行指纹口径一致）在主采集链路上已通过**，排查时不要重复改这里。

**待收口（本文计划的批次）**：

| 批次 | 内容 | 性质 |
|---|---|---|
| 1 | 消除双真相源（改上位文档）+ 清 `data/device_fingerprints/` + 新增账号前置检查脚本 | 零生产代码改动 |
| 2 | 设备档案（决策点 A1）：profile 内记录设备档案，人工巡店写入 ⇒ 三条路径同一台设备 | P0 |
| 3 | 指纹机制在 profile 模式下彻底下线（**保留** `DeviceFingerprintManager` 供录制/组件测试等非 profile 路径） | P0 |
| 4 | 新增账号接入体验（面板轮询刷新、白名单前置提示、首登状态可见、清理 2 个测试残留账号） | P1 |
| 5 | 采集跑 profile 副本 / 代理降级为可选 | **记账到 V2**，本次不做 |

**两个待拍板决策点**：

- **决策点 A（并行采集的「分身」）**：R5（并行只开一次 profile）⟹ 并行 context 不挂载 profile ⟹
  R8「沿用 profile 原生环境」在并行路径上**无法完全实现** ⇒ 规范内部存在张力。
  推荐 **A1**：在 `profiles/<平台>/<账号>/.device.json` 记录设备档案（人工巡店时按 CDP 实测写入），
  三条路径共用同一套值 ⇒ 既不改 R5/R6，也不违反 R8 的**理由**（整套一起注入、彼此自洽）。
- **决策点 B（代理/IP 隔离）**：当前业务为国内卖家端直连，规范 D7/P1 的 IP 隔离已成额外复杂度，
  且「代理配坏必须显式失败」给每个新账号增加概念负担。推荐 **B1**：保留能力，但「没配」= 正常直连，
  只对「配了但坏了」显式失败。

**新增账号即时自查**（不等开发）：ID 只用小写字母/数字/下划线；对照现有 6 个 profile 目录确认不撞
（尤其别写成 `shopeeKR` / `Tiktok1店` / `hongxikejimain`）；ID 不可改；platform 必须在白名单内；
店铺 `platform_shop_id` 必填；首次采集前先人工巡店一次。

## 批次 F：减重批（2026-11-13）

**方向（Walter 拍板）**：做减重批 —— 关告警门禁 + 台账瘦身 + 守护分类。
**本批只做减法**：不擅自把只告警步骤升成硬门禁（升门禁属加固方向，另记待办由 Walter 决定）。

**起因**：Walter 问「我们是不是越做越重了」。实测下来确实如此 —— CI 的 `test` job 里有
45 个硬门禁 + 14 个「只告警」步骤（`continue-on-error: true` 或命令自带 `|| true` / `|| echo`
⇒ **无论成败都不改变流水线结果**）；守卫/契约类测试文件 258 个（占测试文件 30%、39,166 行）；
本台账 1,606 行、26 个章节。

### F-1：关掉 6 个纯噪音步骤 + 收窄采集组件 lint（已落地）

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


- Parallel/specialized tracks should keep their own plan documents and be referenced from here when they are merged.

## Audit

- Plans closure audit (documentation-only): `docs/superpowers/findings/2026-05-06-plans-closure-audit.md`

## 发布证据（v7.27.0，2026-11-14）

> 从 `docs/superpowers/plans/STATUS.md` 归档（2026-11-14，v7.28.0 发版时）。
> 该节已完结，且无外部引用 ⇒ 按「台账瘦身约定」移入归档，STATUS.md 只保留最新一次发布。

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

## 发布证据（v7.31.0 + v7.31.1，2026-11-16 ~ 11-17）

> 从 `docs/superpowers/plans/STATUS.md` 归档（2026-11-17，v7.31.1 发版时）。
> 该节已完结，且无外部引用 ⇒ 按「台账瘦身约定」移入归档，STATUS.md 只保留最新一次发布。

| 项 | 证据 |
|---|---|
| tag | `v7.31.0`（对象 `930d15eb`）→ 提交 `37ea0484`；`v7.31.1`（对象 `b04f2c07`）→ 提交 `48fa88ae`；**双镜像 tag 对象一致** |
| main | `ad37f419`；**双镜像 main SHA 一致** |
| 部署流水线 | run `44013238622` **attempt 2 = success**（attempt 1 卡在 CNB 镜像推送 34 分钟 ⇒ 取消后重跑；镜像内容不变，**生产只部署 1 次**） |
| CI 流水线 | main 的三线全 success（44013178635 / 44013178771 / 44013178796） |
| 生产镜像 | `xihong_erp_backend_api` / `frontend` / `celery_worker` / `celery_beat` 全部 **v7.31.1** 且 healthy |
| 版本号 | `GET /healthz/ready` → `{"status":"ready","version":"v7.31.1","database":"connected","dashboard":"ready"}` |
| 迁移 | `current_schema_20261235_price_adjust_baseline_warehouse`（= 链头；v7.31.1 **无新迁移**）；基线主键已是 `(sku_id, platform_code, warehouse_code)` |
| 调价通知积压 | 461 条 `failed` → `abandoned`（载荷与投递日志全留），`price_adjust` 失败任务归零；飞书调价记录表仍 **174 行**、`rev=281` 不变（没写脏数据） |
| 生产代码真表写入 | 已部署代码组装出 `平台=TikTok` ⇒ 真实 `batch_create` **成功**；临时表验证完即删，表数回到 12（**零残留**） |
| deploy-logs | 只多一个批次 `20261117_123908` |
| 本地开发库 | 2026-11-17 升到链头（此前落后 3 个版本，缺 `finance.delivery_rate_rules` 表 / `dim_platforms.delivery_cost_rate` 列 / `price_adjust_baselines.warehouse_code` 列） |

---

## 批次 F：减重批（2026-11-13）· F-4 验收记录

> 从 `docs/superpowers/plans/STATUS.md` 归档（2026-11-17，批次 6 落地时）。
> 该节已完结 ⇒ 按「台账瘦身约定」移入归档；STATUS.md 的「批次 F」节只保留 F-1
> （CI 减重契约守护 `backend/tests/test_ci_weight_reduction_contract.py` 依赖该节里
> 6 条「被移除的只告警步骤」记录）＋ 本段指针。

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

## 发布证据（v7.32.0，2026-11-17）· 批次 6 + 批次 7

> 从 `docs/superpowers/plans/STATUS.md` 归档（2026-11-17，批次 8 落地时）。
> 该节已完结（v7.32.0 已发版、已部署生产、部署后验收通过）⇒ 按「台账瘦身约定」
> 移入归档，STATUS.md 只保留最新一次发布。完整口径与证据见计划文档 §9 / §9.10。


- **批次 6 · 重量段化 + 选择性包邮**（Walter 拍板：承运商按**重量段**定价 ⇒ SKU 不称重只选段；
  跨境电商**选择性包邮** ⇒ 逐 SKU 自选）。四条钉死的口径：重量段**全局一套**（`core.dim_weight_tiers`
  T01–T06 = 0-1/1-5/5-10/10-20/20-30/30kg 以上），老 `weight_kg` **直接删除**；未选段 ⇒ 落**最轻档** +
  `estimated` + `missing_weight_tier`；该段没配价 ≠ 免费 ⇒ 报 `missing_delivery_rate_for_tier`、金额留空；
  包邮开关在 `finance.sku_platform_pricing.free_shipping`（SKU × 平台，**默认不包邮**）：不包邮 ⇒ 尾程不进底线、
  不计利润、不报缺费率；包邮 ⇒ 尾程进底线 + 平台尾程占比进分母（成对生效）。
- **批次 7 · 定价设置修复 + 费率按官方校准 + 看门狗**：「定价设置」原来**没有自己的平台选择器**
  （平台身份靠测算页筛选条件隐式传递 ⇒ 从 SKU 资料页进抽屉是空表单，保存还可能**写错平台**）⇒ 抽屉自带
  平台下拉、保存只写抽屉里的平台、两个入口各叫各的；费率按官方牌价校准（Walter 拍板：自有/三方仓 3PF 口径、
  官方 3PF 尾程标准、TikTok 非 BXP 档）⇒ Shopee 佣金 → **16%**、TikTok → **8.175%**、Shopee SG 尾程 5 档 →
  官方《3PF 收费标准》（商家包邮总额）20.93/25.31/27.97/38.59/62.44 元；看门狗**杀进程前必须再确认「服务端口
  真的不通」**（探针失败 ≠ 服务死了 —— 2026-11-17 误杀事故的根因）。
- **落地物**：迁移 `20261236_weight_tiers` / `20261237_free_shipping_flag` / `20261238_official_platform_fee_rates`；
  服务层 `product_delivery_cost_service.py`、`product_finance_service.py`、`product_pricing_service.py`、
  `product_pricing_query_service.py`；路由 `product_center.py`；前端 `ProductCenter.vue`；看门狗
  `scripts/local_console_processes.py`。
- **守护**：`test_weight_tier_guard.py`（29）、`test_free_shipping_switch.py`（14）、
  `test_official_platform_fee_rates.py`（7）、`test_product_delivery_cost.py`、`test_delivery_rate_currency_guard.py`、
  看门狗 2 条；前端 `frontend/tests/productCenterUi.test.mjs` **102/102**。
- **全量回归**（批次 7 收尾复跑）：后端 **6219 passed / 8 skipped / 0 failed**（498.34s，批次 6 的 6213
  + 本轮 6 条费率守护）；根目录 `tests` **845 passed / 5 skipped / 0 failed**（359.33s）；前端 102/102；
  构建 10.28s（ProductCenter 117.36 kB）；black / ruff 全绿。**本轮自查修掉的降级缺口**：迁移 20261238
  覆盖了平台费率**生效日期**但 `downgrade` 只还原费率 ⇒ 会留下"费率是 1 月实测、日期却是官方调价日"的
  矛盾行 ⇒ 已补还原（回 2026-01-07）+ 守护，并实跑 downgrade → upgrade 往返验证通过。（批次 6 首轮 13 条
  失败的根因与修复见计划文档 §9.9。）**本地库复验**（真实服务层）：Shopee 底线 包邮 126.19 → **121.43**
  （尾程 22.34 → 20.93）、不包邮 **81.74** 不变；TikTok T01 缺尾程费率被正确报出。
- **未完成**：**发版已完成**（v7.32.0，流水线 success，生产 7 容器 healthy、API 200、链头 20261238）；
  生产 1122 个 SKU 重量段全空、平台尾程占比全 NULL ⇒ 发版后需业务录数（见「当前未结」#10）；
  汇率 5.2077 待业务认可；TikTok SG 价目表未提供。
  **本地环境坑**：`uvicorn --reload` 没带 `--reload-dir` ⇒ 改任何 .py 都会热重载后端（详见 §9.10.3，未改）。
- **完整口径与证据**：计划文档 `2026-11-16-product-center-five-batch-optimization.md` §9 / §9.10。

---

## 发布证据（v7.33.0，2026-11-18）· 批次 8

> 来自 `docs/superpowers/plans/STATUS.md` 台账（2026-11-18，批次 8 已完结）。
> 本节已完结（v7.33.0 已发版、已部署生产、部署后验收通过），按「台账瘦身约定」移入归档；
> STATUS.md 只保留最新一次发布（指针见「最新发布：v7.33.0」）。
> 完整口径与证据见计划文档 §9.11。

- **批次 8 · 尾程费率「去汇率层 + 卡片式维护」+ 修好改价 409**（Walter 拍板三条口径）：① 人工填进去的
  就是**人民币**，系统不做汇率换算（后端契约本来就只收 CNY ⇒ 那层汇率壳是前端自己加的有害壳，本批
  **只删前端**，迁移不写）；② 一个「平台 × 仓」= **一张卡**，卡内按全局段表固定顺序列全部 6 段
  （不让人挑段 ⇒ 不会漏段/选错段），缺价段在卡上看得见；③ **改价只进不退**（变了价 ⇒ POST 新版本，
  只改备注 ⇒ PATCH），批量新增只是铺价手段、铺完自动回卡片。
- **实测发现并修掉的硬伤**：卡片改价对**已存在**档位直接 **409「重复行」** ⇒ 核心动作不可用。根因：
  改价时把**原行生效日**一起发出去 ⇒ 旧行闭区间到生效日前一天 ⇒ **区间倒挂** ⇒ 撞检查约束
  `ck_delivery_rate_rules_window`；且历史会被抹掉。⇒ 口径收口到**后端一处（SSOT）**：改价 ⇒
  `effective_from = max(调用方给值, 今天)`、旧行闭区间到前一天；首次录价仍可用调用方给的生效日回填历史；
  新行本身非 active 时不动旧行（避免当期没费率 ⇒ 尾程算不出来）。
- **落地物**：`ProductCenter.vue`、`product_center.py`（`create_delivery_rate_rule`）。**无迁移**。
- **守护**：`backend/tests/test_delivery_rate_card_save_flow.py`（6 条，**真跑路由** + 隔离库每用例独立
  database）、`test_delivery_rate_currency_guard.py`（24 条）、前端 `productCenterUi.test.mjs` **107/107**。
- **全量回归**：后端 **6231 passed / 8 skipped / 0 failed**（446s）；前端 107/107；构建 10.54s
  （ProductCenter 121.33 kB）；black / ruff 全绿。
- **真实栈复验**：本地 8001 实跑「改价 ⇒ 201，新行今天起生效、旧行闭区间到 2026-11-16 并退出当期」
  「只改备注 ⇒ PATCH，行数不变」，验完**本地库已完整还原**（费率 6 行逐字段与原状一致）。
- **发版动作（双镜像纪律）**：提交 `d2e93b78`（功能）/ `b3dee10d`（发版记录）；双镜像 main SHA 一致
  （`b3dee10d74e4f7e6691b380ae0c58c1f95d605c9`，GitHub / CNB / 本地三方一致）；tag `v7.33.0`
  （注解对象 `9e27d89940ace1b47476ac1bfbc1985eb8ccd31d` → commit `b3dee10d`，两端 tag 对象一致）；
  **先推 CNB**（确认未触发部署：最新 run 仍 v7.32.0、deploy-logs 无新批次）→ **再推 GitHub**（触发部署）。
- **发版前置**：`scripts/verify_rules_completeness.py` PASS；`scripts/verify_release_local.py --skip-build`
  **FINAL_EXIT=0**。期间修了一个**本地环境遗留**：云同步 verify 临时库是 v7.20.1 之前的旧脚手架 ⇒ 删库重建后
  EXIT=0（与本批无关，本批 diff 未碰任何 cloud/sync 文件）。
- **流水线**：run **44129043025** —— `check-config` ✔ / `Validate Data Flow (Release Gate)` ✔ /
  `Build and Push Images` ✔（含依赖 pin 门禁、容器启动冒烟）/ `Deploy to Production (Tag Release)` ✔
  11m6s ⇒ **全 success**。API 契约门禁「本次验证: 1 个文件（定义路由的 1 个）」、「F 真静默 0」、前端文件数 1。
- **生产部署后验收（只读实测，2026-11-18 00:5x）**：7 容器全 healthy（backend / frontend / celery×2 镜像均
  `v7.33.0`）；新部署批次 `20261118_005332`；`/healthz/ready` → 200 `version: v7.33.0`
  `runtime_mode: production`；`/api/docs` → 200；前端新资源 `ProductCenter-dfe6a6b9.js`。
- **迁移链头**：`current_schema_20261238_official_platform_fee_rates`（**未变**，本批无迁移）。
- **生产库只读核对**：`finance.delivery_rate_rules` **5 行** = Shopee SG T01–T05 = 20.93/25.31/27.97/38.59/62.44
  （`effective_from` 2026-11-17）；平台成本率**未动**（shopee 0.16 / 2026-01-01 / v3、creator 0.0111、
  other 0.4165、delivery NULL；tiktok 0.08175 / 2026-04-01 / v3、creator 0.0606、other 0.2727、delivery NULL）；
  `core.dim_weight_tiers` 6 档；`core.dim_erp_sku` 1122 行、重量段 **0** 填充；`finance.sku_platform_pricing`
  **0 行**（默认全不包邮）；`finance.fx_rates` **0 行**（生产汇率表是空的）。
- **上线后仍需业务录数**（不阻塞本批）：TikTok SG 尾程价目表缺 T01/T03–T06；本地那档 T02 = 14.84 元的官方
  出处待确认；残差桶 `other_cost_rate` 与 `delivery_cost_rate` 待重算；汇率 5.2077 待业务认可；生产 1122 个
  SKU 重量段全空、包邮开关默认全不包邮。
- **完整口径与证据**：计划文档 `2026-11-16-product-center-five-batch-optimization.md` §9.11。

## 发布证据（v7.34.0，2026-11-19）· 批次 9

> 来自 `docs/superpowers/plans/STATUS.md` 台账（2026-11-19，批次 9 已完结）。
> 本节已完结（v7.34.0 已发版、已部署生产、部署后验收通过），按「台账瘦身约定」移入归档。
> 完整口径与证据见计划文档 `2026-11-19-product-center-cost-floor-caliber-closure.md`。

- **批次 9 · 成本底线口径收口**（Walter 拍板七条口径）：① 平台佣金率**单独进分母**
  （以前藏在桶里 ⇒ 界面上填了**根本不生效**）；② 桶 = 佣金与尾程之外的平台侧按收入比例扣款，
  新值取**结算单实测**（Shopee **3.58%** 服务费 / TikTok **3.11%** 交易手续费，推翻旧推算
  6.49% / 13.89%）；③ 尾程**直接进分子**，「尾程占收入比」列与「成对生效」机制**一并退役**
  （生产该列全 NULL ⇒ 尾程**从来没进过底线**）；④ SPU 两率改**按件折进分子** × `(1+R+D)`
  （行业基准件损率，不再按收入比例扣）；⑤ 头程 / 仓储 / 贴单三块履约按件成本**第一次进底线**；
  ⑥ 利润链**必须同步扣桶**（以前两条链恒差 26.78pt）；⑦ 界面三个手填项合并成「底线成本率合计」。
- **新口径公式**：底线 = (采购 + 头程 + 仓储 + 贴单 + 尾程) × (1 + 退货率 + 货损率)
  ÷ (1 − 平台佣金率 − 桶 − 达人佣金率 − 目标利润率)。
- **SKU 920（生产实测输入）**：现状 157.64（真实利润率仅 **18.28%**，分子漏四块成本）→
  新口径不包邮 **77.20** / 包邮 **118.62** / 体积已录 **136.06**；
  底线上的利润率分别 **25.000% / 24.987% / 25.004%**（精确等于目标利润率）。
- **⚠️ 护栏收口（收紧）**：estimates 底价护栏原本用**不带仓**的底线（偏松）⇒ 形同虚设，
  改为带仓底线、与商品中心页面**同一条**（测试口径 TikTok 30.98 → **57.46**）
  ⇒ 「预计售价偏低」的利润版本保存**会被拦更多**。CHANGELOG 已点名。
- **⚠️ 必填平台费率缺失时利润链整条留白且点名**：`platform_rate_missing_reasons`
  （`missing_platform_fee_rate` / `missing_platform_cost_rate`，与底线链同一套词）；
  桶入参**去掉默认值** ⇒ 漏传当场 `TypeError` 而不是悄悄留白。
- **发版前抓到的两个迁移 bug**（都只在真正跑那条路径时才暴露）：
  ① `op.drop_column(列名, schema=..., table_name=...)` ⇒ TypeError
  ⇒ **整条迁移链在 upgrade 阶段就断**；② `op.add_column(t, sa.Column(..., schema=...))`
  ⇒ TypeError ⇒ **只有跑 downgrade 才暴露**（现有演练只跑 `upgrade head`，看不见它）。
  ⇒ 新增**迁移往返演练守护** `test_batch9_migration_roundtrip.py`
  （baseline → upgrade 20261238 → upgrade head → **downgrade 20261238** → upgrade head，
  断言列恢复、桶值/来源/版本全部还原）。
- **落地物**：新增 `backend/services/product_fulfillment_cost_service.py`（履约按件成本唯一实现）；
  改 `product_pricing_service` / `product_pricing_query_service` / `product_profit_service` /
  `product_finance_service` / `product_center.py`（路由）/ `product_clearance_service` /
  `price_adjust_notify_service` / `modules/core/db/schema_parts/dimensions.py`；
  迁移 `current_schema_20261239_cost_floor_caliber_closure`。
- **守护**：新增 4 个测试文件（迁移往返 / 佣金拆分 / 两率按件折 / 必填费率）、改写 8 个既有守护
  （口径变了守护跟着改，**不许改松**）；前端 `productCenterUi.test.mjs` **113/113**。
- **全量回归**：后端 **4907 passed / 0 failed / 7 skipped**；前端 **578/578**（122 个测试文件）；
  `vue-tsc --noEmit` EXIT=0；ESLint 相对 HEAD 基线**无新增规则类型**；black / ruff 全绿。
- **发版前置**：`scripts/verify_rules_completeness.py` **PASS**（EXIT=0）；
  `scripts/verify_release_local.py --skip-build` **FINAL_EXIT=0**。
- **完整口径与证据**：计划文档 `2026-11-19-product-center-cost-floor-caliber-closure.md`。

### 部署后验收（生产只读实测，2026-11-19 23:16 CST）

| 项 | 证据 |
|---|---|
| 部署流水线 | run **44548833142**（`Deploy to Production`，事件 `push` / tag `v7.34.0`）—— `check-config` ✔ / `Validate Data Flow (Release Gate)` ✔（13 项门禁全绿）/ `Build and Push Images (Release Tag)` ✔ / `Deploy to Production (Tag Release)` ✔ ⇒ **全 success** |
| 镜像推送（本次） | GHCR backend 2m49s（14:56:28→14:59:17）；**CNB backend 仅 20 秒**（15:04:23→15:04:43）、CNB frontend 8 秒 |
| 生产容器 | **7 个全 healthy**：nginx / frontend / backend_api / celery_worker / celery_beat（应用镜像均 `v7.34.0`）+ postgres / redis（Up 9 days，本次**无生产写操作**重启） |
| 版本自报 | `GET /healthz/ready` → `{"status":"ready","version":"v7.34.0","runtime_mode":"production","checks":{"database":"connected","dashboard":"ready"}}`；容器内 `APP_VERSION=v7.34.0` / `APP_ENV=production`；`GET /api/docs` → **200** |
| 前端 | `GET https://127.0.0.1/` → **200**（838 bytes，nginx 301 强制跳 HTTPS）；新产物 **`ProductCenter-60021ab0.js`**（`assets/js` 共 114 个 chunk） |
| 迁移链头 | **`current_schema_20261239_cost_floor_caliber_closure`**（= 本批次 head）；`core.dim_platforms` **已无 `delivery_cost_rate` 列**（退役列确认删除） |
| 费率实测 | shopee 桶 `0.0358`（**3.58%**）/ 佣金 `0.16` / 达人 `0.0111`，`fee_rate_source` = `official_3pf_commission_2026_01_01 + manual_2026_11_19_settlement_ledger_service_fee`；tiktok 桶 `0.0311`（**3.11%**）/ 佣金 `0.08175` / 达人 `0.0606`，`fee_rate_source` = `official_sg_2026_04_01 + manual_2026_11_19_settlement_ledger_transaction_fee`；两者 `fee_rate_version` = **`v4`**；amazon / miaoshou 仍全空（按预期仍属缺料） |
| 残留清理 | 上一轮失败遗留的 5 个 `__predeploy_2825110_1795099298` 容器（Exited、v7.33.0）已 `docker rm` 清空 ⇒ 残留 0；本次部署自身的 staged 容器已由 `discard_staged_application_containers`（脚本 `:181-189`）正常回收 |

### ⚠️ 一次发布事故（已完结，写下来别再踩）

**经过**：首发 run 44538689286 的部署脚本**本来正在正常执行**（`Deploy to production server` 14:41:35→14:49:44），
被我用 `gh run cancel` **误杀** —— 起因是我把「CNB 首次推送 backend 1.16GB 用了 36 分钟」误判成「卡死」。
因 `trap handle_deploy_exit EXIT` **只在脚本进程正常退出时触发**，被 SIGKILL/SIGHUP 杀掉时**不会回滚** ⇒
老容器停在 `__predeploy_*`（Exited）、新容器未接管 ⇒ **生产停机约 27 分钟**。

**两条硬教训**：

1. **不凭「步骤耗时远超历史基准」判死**。取消前必须先取完整 step 时间线 + 日志，确认**确实无进展**。
   本次的决定性对照：同一 tag 的**第二次**推送，CNB backend **只用 20 秒**（≈ v7.33.0 基准 22 秒）
   ⇒ 上次 36 分钟是 **CNB registry 首次接收全新大镜像时的上游吞吐慢**，既不是网络断开也不是卡死。
2. **迁移一旦在生产执行，回滚老版本就不再可行**。本批迁移已在生产库落地（`delivery_cost_rate` 列已删），
   而 v7.33.0 的 ORM 仍映射该列 ⇒ 老容器起手即 `UndefinedColumn` ⇒ 当时**唯一的出路是把 v7.34.0 部署上去**，
   而不是回滚。（⇒ 迁移类发版前应把「回滚可行性」当成显式验收项。）

**重新部署的方式（标准流程，未走手动旁路）**：tag `v7.34.0` 的两端对象本就一致（`aa515a12` → 提交 `b784dbbc`），
已发布 tag 不重写 ⇒ 采用「**删掉 GitHub 上的 tag ref → 重推同一个 annotated tag 对象**」重新触发标准流水线
（`on: push: tags` 收到 create 事件）⇒ 两端 tag 对象**始终保持同一对象**，CNB 端无需任何改动。

## 发布证据（v7.35.0 + v7.35.1，2026-11-19 ~ 11-20）· 批次 10

> 来自 `docs/superpowers/plans/STATUS.md` 台账（2026-11-20，批次 10 已完结）。
> 本节已完结（v7.35.0 首次部署被迁移前置检查挡住 ⇒ v7.35.1 修正后已发版、已部署生产、部署后验收通过），按「台账瘦身约定」移入归档。
> 完整口径与证据见计划文档 `2026-11-19-hr-user-management-optimization.md`。

### 人力资源 + 用户管理模块优化（2026-11-20 **已落地 v7.35.1**）

- Plan: `docs/superpowers/plans/2026-11-19-hr-user-management-optimization.md`
- 起因：离职员工仍平级混排在员工列表与薪资页名单里（前端两页一处显示中文「已离职」、一处显示英文 `inactive`），且人力两页未套用平台统一页面骨架。核对口径：**生产只读核对**（2026-11-19）+ 本地库实测 + 源码比对。
- 生产实证：① 人员店铺归属表、人力成本分摊表在生产均为 **0 行** ⇒ 工资单确认链路必然 409（31 张工资单里 23 张卡在 `draft`）；② 账号库 **347 个 `rejected` 全是自动化测试账号**；③ 存在 **1 条访客档案**（EMP260009 梁曦予，账号最后登录后 16 秒自动建档），而访客身份**无升级出口** ⇒ 永远进不了薪资与收入链路；
  ④ 离职员工李四有 4 张草稿工资单，卡在「月度录入 409 / 确认无门禁」之间；⑤ **两名在职新员工（曾维剑 2026-08-26、文鹏 2026-11-08）入职至今零工资记录** ⇒ 2026-08 之后月份从未被结算过；⑥ **试用期状态在库里从未被使用**（业务口径「试用不发薪」与代码一致，但无人写 `probation`）；⑦ **部门无真源**：档案侧 2/11 有值（外键）、账号侧 5/12 有值（自由文本、后端只写不读）。
- 核心口径变更：**以「最后发薪月」为唯一发钱边界**（不再按 `status` 一刀切），一次性消除「离职当月补录被拦死」与「离职后仍可能生成工资单」两个方向的问题；另新增「转正」与「已作废」两个业务动作。
- 访客转正三层解法：**审批即建档（主路径）+ 显式转正/冲突合并（存量）+ 补齐自动升级（防漏）**。五批落地：① 展示层收口（零数据写入）② 离职/试用/作废语义与最后发薪月 ③ 绑定链路收口与访客转正 ④ 前端重做与拆组件 ⑤ 生产数据修复（须走发版）。
  防误伤清单：不删访客自动建档、不动「确认/发放」放行、不删历史归属、生产不直连写。
- **业务侧 2026-11-20 已拍板**：李四 4 张草稿工资单 = 测试数据 ⇒ 作废（保留行）；叶大望 = 还没注册账号，等后续注册；347 个 rejected 测试账号可清理但不得误伤员工账号（四条件判据，已实测 347 个全中）；曾维剑/文鹏 = 试用员工还没到时间 ⇒ `status='probation'`；部门统一 SSOT ⇒ 组织归属唯一真源 = `employees.department_id` → 部门表，账号侧降级为「注册时填写的部门」。
- **落地补齐的两处口径（集成期发现）**：① 「已作废」必须**可撤销**（一人一月只有一张工资单，作废单占着坑位 ⇒ 误作废一次，那个人那个月就永远发不出钱）⇒ 新增「撤销作废」端点与界面入口；② 作废**不锁月**（只冻结这一张单，同月其他人照常重算、照常确认发放），且作废单**不被刷新改写**（只报「已作废未生成」）。
- **⚠️ v7.35.0 首次部署被迁移的前置检查挡住（保护生效、生产零影响）**：16 个测试账号**走过注册审批** ⇒ 留下「注册审批链」五张表的痕迹（原迁移只清了四张痕迹表，漏了这一层）⇒ 撞外键 ⇒ 迁移报错停下并报清表名与行数；生产回滚到 v7.34.0、数据库仍在 `20261239`。⇒ **v7.35.1 修这一处**（补清该层痕迹 + 删前逐行核对「证明不了就停下」）；**验证方式 = 把生产真实数据（391 账号 / 28 审批实例 / 50 动作日志 / 28 步骤 / 38 待办 / 956 会话）原样回放到本地隔离库** ⇒ 清理 347 个（与批准数量一致）、真实员工账号一个没动、反向用例证明不了就停下。
- **仍待业务侧补录**：11 名员工入职日期、2 名离职员工离职日期、张三最后发薪月；**人员店铺归属 0 行**须在「人员店铺归属」页面重配，否则工资单确认链路仍会 409 —— 第五批无法由代码闭环。

### 部署后验收（生产只读实测，2026-11-20 02:43 CST）

| 项 | 证据 |
|---|---|
| 部署流水线 | run **44587344542**（`Deploy to Production`，事件 `push` / tag `v7.35.1`，耗时 **17m56s**）—— `check-config` ✔ / `Validate Data Flow (Release Gate)` ✔（13 项门禁全绿）/ `Build and Push Images (Release Tag)` ✔ / `Deploy to Production (Tag Release)` ✔ ⇒ **全 success** |
| 配套流水线 | `CI Pipeline` run **44587008983** ✔ / `Validate Data Flow` **44587008891** ✔ / `Docker Build and Push` **44587008948** ✔ / `Outputs Directory Health Check` **44587343593** ✔ ⇒ **全 success** |
| 双镜像一致性 | `main` 同步 SHA = **`e9c12059`**（`XIHONG_GIT_MIRROR_SYNCED`）；tag `v7.35.1` 两端**同一对象** = `518f9312`（GitHub SSH-443 / CNB HTTPS 逐个 `ls-remote` 核对） |
| 生产容器 | **7 个全 healthy**：nginx / frontend / backend_api / celery_worker / celery_beat（应用镜像均 `v7.35.1`）+ postgres / redis（Up 10 days，本次未重启） |
| 版本自报 | `GET /healthz/ready` → `{"status":"ready","version":"v7.35.1",...,"database":"connected","dashboard":"ready"}`；`GET /api/docs` → **200**；`GET /` → **200** |
| 迁移链头 | **`current_schema_20261240_hr_employee_lifecycle`**（= 本批次 head） |
| 账号清理 | `core.dim_user_purge_log` **347 条 / 347 个不同 user_id**（区间 3~389，reason = 「自动清理：残留测试账号」）；**四条判据仍全中的残留 = 0**；现存账号 44 个（active 12 + deleted 32） |
| 误伤核对 | 16 个真实员工账号（admin / xihong / zhangsan / youke / lisi / yehaichuan / qaadmin / WEI / HJJ / DY11_ / 18976425991 / user_XiaoZeng / Debug_Fate / perf_load_admin / playwright_smoke_admin / codex_admin_temp）**一个没动** |
| 审批链清干净 | 「注册审批链」五张表**孤儿行全 0**：审批实例 0 / 动作日志 0 / 审批步骤 0 / 待办 0 / 会话 0（另：`employee_task_logs.actor_user_id` 的 8 行是 **NULL** 而非孤儿 —— 无具体操作人的自动任务，属合法值） |
| 李四 4 张工资单 | id 8 / 22 / 33 / 26（2026-03 / 04 / 06 / 07）**status = `void`** + `void_reason` = 「测试数据，业务确认作废（2026-11-20）」+ `voided_at` = 2026-11-19 18:32:38Z（**行保留** —— 作废是留痕，不是删数据） |
| 发钱边界 | `EMP260004` 李四 `last_payroll_month` = **2026-07**；`EMP260002` 张三 `last_payroll_month` = **NULL**（他没有工资单 ⇒ 结算月未经业务确认 ⇒ **不猜**） |
| 试用状态 | `EMP260010` 曾维剑 = **probation**；`EMP260011` 文鹏 = **probation**；全库分布 active 7 / probation 2 / inactive 2 |
| 状态词表落地 | 约束 `ck_employees_status_lifecycle` 已建：`status ∈ {active, probation, leave, inactive}` 四值 |
| 工资单状态分布 | confirmed 1 / draft 19 / paid 7 / **void 4**（李四那 4 张） |
| 新端点上线 | 生产 OpenAPI **521 条路径**；6 个新端点**全部注册**：`POST /api/hr/employees/{employee_code}/offboard`、`/regularize`、`/promote-visitor`、`/merge-visitor`、`POST /api/hr/payroll-records/{record_id}/void`、`/unvoid`；只读端点 `/api/hr/employees`（get+post）、`/api/hr/payroll-records`（get）、`/api/users/unlinked`（get）均在线 |
| 前端产物 | `HumanResources-2bb1e85d.js` / `EmployeeManagement-de005182.js` / `EmployeeSalary-a395a9c7.js` |
| 本地全量回归 | 修复后后端 **6339 passed / 8 skipped / 0 failed**（比修复前多 2 条 = 新增 `test_hr_purge_registration_traces.py`）；前端 **349/349** + HR 守护 **11/11**；`npm run build` 成功；ruff / black 全绿 |

### ⚠️ 这次为什么多发了一个版本（v7.35.0 → v7.35.1，写下来别再踩）

**经过**：v7.35.0 标签的流水线（run **44580353110**）在**迁移的前置检查**阶段停下 —— 保护机制按设计生效
（拒绝删除、业务零影响、迁移整体回滚、生产仍是 v7.34.0）。根因：347 个候选里有 **16 个测试账号走过注册审批**，
于是留下「注册审批链」五张表的痕迹（原迁移只清了四张**账号级**痕迹表，漏了**审批链**这一层）⇒ 撞外键。

**修法（v7.35.1）**：迁移补齐这一层的清理（**先子后父**：动作日志 → 步骤 → 审批实例 → 待办日志 → 待办参与人 → 待办），
并加两道闸门：① 删除条件**精确限定在候选账号自己的注册审批**（按 `approval_pk` / `task_pk` 限定，不按人删 ⇒
管理员在**别人**审批上的动作不会被误删）；② **逐行核对**（实例须 `user_registration_approval` + `business_key` 匹配、
待办须命中 `approval-task:approval:user_registration_approval:user:<id>:` 前缀、候选账号若是**他人**审批的审批人 ⇒ **停下**），
删账号本体前再查一遍「**一张表都不放过**」的残留引用。

**验证方式**：把生产真实数据（391 账号 / 28 审批实例 / 50 动作日志 / 28 步骤 / 38 待办 / 956 会话）**原样回放到本地隔离库**
再跑本迁移 ⇒ 退出码 0、清理 **347** 个（与业务侧批准数量完全一致）、16 个真实员工账号一个没动、
另 28 个「只中前缀但不满四条判据」的账号也全部保留；**反向用例**（给测试账号造一个不属于自己的业务待办）
证明「证明不了就停下、且数据库原样未变」。

**两条硬教训**：

1. **删数据的迁移必须把「这批数据在别的表里留下过什么痕迹」列全**，而不是只清「直接指向主键的那几张」。
   外键前置检查挡住你是**保护**，不是失败 —— 它替你在生产上做了一次演练。
2. **失败的首发不要原地重做**：v7.35.0 的标签**保持不动**（它是失败尝试的凭证），用**新标签 v7.35.1** 触发部署
   ⇒ 不重写任何已发布历史。

### 本批次的业务侧未结项（代码闭环不了，需要人补）

- **人员店铺归属 0 行**、**人力成本分摊 0 行** ⇒ 工资单确认链路仍会 409（第五批无法由代码闭环），
  须在「人员店铺归属」页面重配或灌入**确认过的历史数据**。
- 11 名员工**入职日期**、2 名离职员工**离职日期**、张三**最后发薪月**需人工补录（迁移只回填可推导的部分）。
- 迁移已执行的 347 个账号**不可逆**（downgrade 明确写「只能从备份恢复」）。

---

## 归档：发布证据（v7.33.0，2026-11-18）· 批次 8

> 本节于 2026-11-21（v7.36.0 发布）从 `docs/superpowers/plans/STATUS.md` 归档而来 ——
> 台账只保留**最新一次**发布，已完结批次的实施记录按批次追加进本归档文件。

### 上一版发布：v7.33.0（2026-11-18，批次 8）

- 商品中心**尾程费率去汇率层 + 卡片式维护 + 修好改价 409**：生产 7 容器 healthy、
  `healthz/ready` = 200 / v7.33.0 / runtime_mode=production、本批**无迁移**（链头仍 `20261238`）、
  Shopee SG 尾程 5 档 = 20.93/25.31/27.97/38.59/62.44 元（**未动**）。完整发布证据见归档
  「发布证据（v7.33.0，2026-11-18）· 批次 8」。
- **上一版**：v7.32.0（批次 6 + 批次 7）—— 证据见归档「发布证据（v7.32.0，2026-11-17）· 批次 6 + 批次 7」。

### 已完成：批次 8 · 尾程费率「去汇率层 + 卡片式维护」（2026-11-18，**v7.33.0 已发版并部署生产**）

- **三条口径（Walter 拍板）**：① 人工填进去的就是**人民币**，系统不做汇率换算
  （后端契约本来就只收 CNY ⇒ 那层汇率壳是前端自己加的有害壳，本批**只删前端**，迁移不写）；
  ② 一个「平台 × 仓」= **一张卡**，卡内固定顺序列全部 6 段（不会漏段/选错段），缺价段看得见；
  ③ **改价只进不退**（变了价 ⇒ POST 新版本，只改备注 ⇒ PATCH）。
- **实测发现并修掉的硬伤**：卡片改价对**已存在**档位直接 **409「重复行」** ⇒ 核心动作不可用。
  根因：改价时把**原行生效日**一起发出去 ⇒ 旧行闭区间到生效日前一天 ⇒ **区间倒挂** ⇒ 撞
  `ck_delivery_rate_rules_window`；且历史会被抹掉。⇒ 口径收口到**后端一处（SSOT）**：
  改价 ⇒ `effective_from = max(调用方给值, 今天)`、旧行闭区间到前一天；首次录价仍可回填历史。
- **落地物**：`ProductCenter.vue`、`product_center.py`（`create_delivery_rate_rule`）。**无迁移**。
- **守护**：`test_delivery_rate_card_save_flow.py`（6 条，真跑路由）、
  `test_delivery_rate_currency_guard.py`（24 条）、前端 107/107；后端全量 **6231 passed / 8 skipped**。
- **完整口径与证据**：计划文档 `2026-11-16-product-center-five-batch-optimization.md` §9.11；
  发布证据见归档「发布证据（v7.33.0，2026-11-18）· 批次 8」。
