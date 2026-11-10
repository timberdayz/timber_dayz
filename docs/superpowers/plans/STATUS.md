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
- ⚠ `test_granularity_alignment_sql.py` 仍有 **2 条失败**（与本分支无关）：
  `test_shop_month_kpi_does_not_fallback_to_daily`（断言月度薄封装里含
  `fact_shopee_orders_monthly`，但薄封装早已改为只读 MV）与
  `test_annual_summary_shop_month_does_not_force_missing_costs_to_zero`
  （`sql/mart/annual_summary_shop_month.sql` 已不存在）。
  已在 main 基线 worktree（`25aeba29`）逐条对照：**main 上同样失败**，属既有失败。

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

- 11 个 testcontainers 遗留的 postgres 匿名悬空卷。`docker volume rm` 被本地安全策略
  判定为不可逆销毁而拦截，需在 Docker Desktop 里手动清理：

  ```bash
  docker volume ls -f dangling=true --format '{{.Name}}'   # 逐个核对后删除
  ```

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

批次 0（只读对账，采集机执行）、批次 2（主数据对齐）、批次 3（巡检与告警）、批次 4（清理与文档）**未开始**。

## Notes

- The completion state above reflects the work merged into `main` (latest closure commit around 2026-05-06).
- Parallel/specialized tracks should keep their own plan documents and be referenced from here when they are merged.

## Audit

- Plans closure audit (documentation-only): `docs/superpowers/findings/2026-05-06-plans-closure-audit.md`
