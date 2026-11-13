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
| 47 处真静默 | 分批清理（跨 4 域 27 文件，pre-launch 要求拆） |
| 74 个带 BOM 的路由文件 | 单独一批清理（本批已用 `utf-8-sig` 兜住，不阻塞） |
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
  1. **轮换那 15 个店铺账号的密码**（公开 ⇒ 必须视为已泄露），
     并同步更新生产库 `core.shop_accounts` 与采集机账号库；
  2. **历史清理**（`git filter-repo`）—— 会作废全部已发布 tag（含 `v7.24.0`），
     **本会话明确不做**；
  3. **删除生产机上的 `/opt/xihong_erp/.env.production.passwords.txt`**（旧密钥副本）——
     属生产写操作，须走发版流程或人工执行；
  4. 确认 `.env.cleaned` 里的旧 `SECRET_KEY` / `JWT_SECRET_KEY` / `METABASE_API_KEY`
     在**任何**环境都还活着 —— 本次只比对了生产与本机，**未覆盖**已下线的旧环境。

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



- The completion state above reflects the work merged into `main` (latest closure commit around 2026-05-06).
- Parallel/specialized tracks should keep their own plan documents and be referenced from here when they are merged.

## Audit

- Plans closure audit (documentation-only): `docs/superpowers/findings/2026-05-06-plans-closure-audit.md`
