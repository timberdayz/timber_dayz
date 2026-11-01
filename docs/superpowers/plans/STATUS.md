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

### 发布前置条件（未完成，需业务决策）

- 分支**未合并 main、未打 tag、未 push**。
- 原因：`data_hash` 口径由 `scope:shop_id` 切到 `scope:shop_account_id`，全部 460 个已入库文件的
  hash 失效；计划 Task 10 Step 6 要求**事实层全量重建必须先于新 dedup 口径代码上线**，
  否则再采会重复入账。当前 live 各非空事实表 `rows == distinct_data_hash`（无重复），
  但仍需先做一次事实层重建（`RefreshQueueService` 或按文件粒度 delete+重扫+重入库）。
- 另：仓库部署是 tag 驱动，`main` 需走 `scripts/sync_main_mirrors.ps1`，
  AGENTS.md 禁止单远端 push / force push。

### 待业务确认（不阻塞实施）

- `3c店` 冲突取舍
- 两个 disabled 主账号是否启用
- TikTok 三店改名归属（含疑似历史误录 `TK新加坡1店`）
- `platform='验证码测试账号'` 脏行处理（当前保留并已分配 internal_code）
- 10 个文件命中已停用账号 `shopee_sg_chenewei666_local` 是否接受回填

### 运营提示

- Task 13 让「30 天过期」真正生效，需知会运营。
  本机 `data/sessions/` 实测 19 个会话文件中 16 个已超 30 天
  （最旧 2025-08-18），仍有效的仅 3 个：
  tiktok `chenzeweinbnb@163.com`（2026-10-07）、
  miaoshou `miaoshou_real_001`（2026-10-26）、
  shopee KR（2026-11-01）。真实环境影响量需在生产评估。

## Notes

- The completion state above reflects the work merged into `main` (latest closure commit around 2026-05-06).
- Parallel/specialized tracks should keep their own plan documents and be referenced from here when they are merged.

## Audit

- Plans closure audit (documentation-only): `docs/superpowers/findings/2026-05-06-plans-closure-audit.md`
