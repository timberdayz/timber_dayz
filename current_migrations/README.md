# Current Schema Migration Chain

`current_migrations/` is the independent, post-history Alembic chain.
Historical `migrations/versions/` remains read-only and is never used by the
deployment or application startup migration entrypoints.

## 别裸跑 `alembic upgrade head`

仓库根目录的 `alembic.ini` 指的是**只读历史链**（`migrations/`，97 个版本）。
当前唯一的迁移事实源是 **`alembic-current.ini`** → `current_migrations/`，
版本表是 `public.current_schema_alembic_version`。

```bash
# 唯一正确的姿势（部署 / 启动 / 校验 / 本地升库都用这个）
python -m alembic -c alembic-current.ini upgrade head
```

- **生产镜像里根本没有历史链**（`migrations/` 与 `alembic.ini` 都不 COPY 进镜像），
  部署与启动入口一律走 `alembic-current.ini` ⇒ 生产面天然不会跑错链。
- **裸跑**（不带 `-c alembic-current.ini`）会走历史链：推进 `core.alembic_version`，
  并可能执行与当前结构冲突的旧迁移。历史链第一条（`20260112_v5_0_0_schema_snapshot`）
  在现代库上就会因「表已存在」失败并回滚，但版本表已经被推进 ⇒ 难恢复。
- `core.alembic_version` **两边都有意保留、不要删**：在生产上它是当前基线的
  「出处标记」（`20260805_payroll_backfill_audit`），在开发库上它是历史链的进度留档
  （`20260917_add_platform_label_fee`）。
- `alembic.ini` 之所以还留着：仓库里有 4 处契约测试直接读历史链的事实
  （迁移本身作为「口径出处」被静态钉住），删它要连带改一大片历史契约。
- ⚠️ `alembic.ini` **必须保持纯 ASCII**：alembic 用 locale 编码读它
  （Windows 上是 GBK），UTF-8 中文注释会让 `alembic` 直接读崩。

`current_schema_20260805` is a reviewed static DDL baseline generated from the
read-only production schema at legacy revision `20260805_payroll_backfill_audit`.
It includes the schemas, tables, constraints, indexes, functions, triggers,
views, materialized views, and required catalog data present in that source.
Archived `core.alembic_version` and `public.alembic_version` tables are excluded:
new databases are versioned only by `public.current_schema_alembic_version`.
The baseline generator also excludes retired `public.sales_targets` and the
retired `core.data_quarantine.platform` / `data_type` fields.

`current_schema_20260808_operation_performance_workbench` is the first
increment after that production baseline. It adds the operation-performance
workbench catalog and rules. It does not silently collapse duplicate shop
overrides; legacy adoption is rejected before any write when a manual data
resolution is required.

The only approved legacy adoption mapping is version-controlled in
`support_policy.json`. The wrapper performs read-only revision and schema
fingerprint checks, stamps `current_schema_20260805` only after they pass, and
then upgrades to the current head. A production database retains its legacy
version table and business data; a fresh database does not create any archived
version table. Dashboard runtime bootstrap may still refresh its assets, but
the static schema objects that existed in the approved source are part of this
baseline. `scripts/bootstrap_postgresql_dashboard.py` remains the lifecycle
owner for dashboard refresh operations after deployment.
