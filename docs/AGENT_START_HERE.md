# Agent快速上手指南

## 当前主架构

- Dashboard 主链路是 PostgreSQL-first。
- 当前数据流转是 `b_class raw -> semantic -> mart -> api -> backend -> frontend`。
- PostgreSQL Dashboard 是唯一运行时主链。
- Metabase 不再属于当前运行时设计。

## 你现在应该怎么理解系统

- ORM SSOT 仍然是 `modules/core/db/schema.py`。
- 原始采集数据保留在 `b_class`。
- 标准化层在 `sql/semantic/`。
- 汇总层在 `sql/mart/`。
- 页面模块层在 `sql/api_modules/`。
- Dashboard 主服务入口是 `backend/services/postgresql_dashboard_service.py`。
- Dashboard 新路由入口是 `backend/routers/dashboard_api_postgresql.py`。
- 旧 Dashboard 兼容路由仅作为回退链路。

## 开发 Dashboard 时的规则

### 要做的事

- 新的 Dashboard 查询优先落到 PostgreSQL `semantic / mart / api`。
- 新的页面模块优先接 `dashboard_api_postgresql.py`。
- 需要观测刷新状态时，看 `ops.pipeline_run_log`、`ops.pipeline_step_log`、`ops.data_freshness_log`、`ops.data_lineage_registry`。
### 不要再做的事

- 不要再把新 Dashboard 功能设计成 Metabase Question 主链路。
- 不要再把旧 Dashboard 兼容路由当成默认扩展点。
- 不要再把旧 Metabase 查询服务当成新功能首选依赖。
- 不要再把旧 Metabase 代理接口当成默认运行时必需接口。

## 运行与验证

### 推荐启动

```bash
python run.py
```

### Docker 模式

```bash
python run.py --use-docker
```

### PostgreSQL Dashboard 相关验证

```bash
python -m pytest backend/tests/data_pipeline -q
python scripts/smoke_postgresql_dashboard_routes.py --base-url http://localhost:8001
python scripts/check_postgresql_dashboard_ops.py
```

## 关键文档

- `README.md`
- `CLAUDE.md`
- `docs/development/POSTGRESQL_API_LAYER_GUIDE.md`
- `docs/development/POSTGRESQL_DASHBOARD_ROLLOUT.md`
- `docs/development/POSTGRESQL_DASHBOARD_PREPROD_EXECUTION_CHECKLIST.md`
- `docs/development/POSTGRESQL_DASHBOARD_PRODUCTION_GREY_RUNBOOK.md`
- `docs/development/METABASE_LEGACY_ASSET_STATUS.md`
- `docs/development/DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md`

## 一句话记忆

- 新功能走 PostgreSQL。
- 不再依赖 Metabase 运行时。
- 先看 `semantic / mart / api`，再看 legacy。
