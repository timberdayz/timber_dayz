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

### 遗留

- 用户侧：下一轮采集后核「新增月份认不出 = 0」—— ⚠️ **只能从 2026-12 起算**（11 月是事故现场）。
- v7.21.0：律 3 的候选名单副本物化视图仍是旧定义 ⇒ 部署流水线需先 `DROP` 再按资产重建，并加副本定义守护。

## Notes

- The completion state above reflects the work merged into `main` (latest closure commit around 2026-05-06).
- Parallel/specialized tracks should keep their own plan documents and be referenced from here when they are merged.

## Audit

- Plans closure audit (documentation-only): `docs/superpowers/findings/2026-05-06-plans-closure-audit.md`
