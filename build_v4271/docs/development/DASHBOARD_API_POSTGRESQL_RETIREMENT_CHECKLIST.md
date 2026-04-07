# Dashboard API PostgreSQL Cutover Checklist

## Goal

在完全下线旧 `backend/routers/dashboard_api.py` 之前，确认 PostgreSQL 路由与服务层已经覆盖所有主链路接口，并且具备可回退、可验证、可观测能力。

## Retirement Buckets

### Remove Now

These are not part of the PostgreSQL primary path and should be removed from active runtime/docs behavior immediately.

- old README guidance that still treats Superset/Metabase as the default dashboard entry
- old `docs/AGENT_START_HERE.md` guidance that tells agents to build new dashboard work through Metabase Question
- default runtime exposure of `archive/metabase/backend/routers/metabase_proxy.py`
- default startup checks and banners in `run.py` that make Metabase look like a required service

### Historical Reference Only

These assets are no longer valid runtime rollback paths, but may still remain temporarily while historical scripts/docs are cleaned up.

- `archive/metabase/backend/routers/dashboard_api.py`
- `archive/metabase/backend/routers/metabase_proxy.py`
- `archive/metabase/backend/services/metabase_question_service.py`
- `archive/metabase/scripts/init_metabase.py`
- `archive/metabase/scripts/verify_deploy_phase35_local.py`
- `archive/metabase/scripts/verify_deploy_full_local.py`
- `archive/metabase/config/metabase_config.yaml`
- `archive/metabase/docker/docker-compose.metabase.yml`
- `archive/metabase/docker/docker-compose.metabase.dev.yml`
- `archive/metabase/docker/docker-compose.metabase.4c8g.yml`
- `archive/metabase/docker/docker-compose.metabase.lockdown.yml`

## Current Status

### 已由 PostgreSQL 路由/服务覆盖
- `business_overview_kpi`
- `business_overview_comparison`
- `business_overview_shop_racing`
- `business_overview_traffic_ranking`
- `business_overview_inventory_backlog`
- `business_overview_operational_metrics`
- `clearance_ranking`
- `annual_summary_kpi`
- `annual_summary_trend`
- `annual_summary_platform_share`
- `annual_summary_by_shop`
- `annual_summary_target_completion`

### 仍需最终确认的事项
- 启动日志中明确打印当前 Dashboard 路由来源
- PostgreSQL 路由的真实数据库级接口验证范围继续扩大
- 历史 Metabase 资产何时转入 archive/legacy 目录

## Cutover Preconditions

- `backend/tests/data_pipeline` 全绿
- `USE_POSTGRESQL_DASHBOARD_ROUTER=true` 的应用级验证通过
- `ops` 路由可正常查看 `status / freshness / lineage`
- 关键业务页面 smoke 验证通过

## Final Retirement Steps

1. 保持 PostgreSQL Dashboard 作为唯一运行时主链
2. 验证关键页面与关键接口行为
3. 观察 `ops.pipeline_run_log`、`ops.data_freshness_log`
4. 确认 `archive/metabase/backend/routers/dashboard_api.py` 等历史资产已完成归档
5. 评估其余更外围的历史 Metabase 脚本是否继续留在原路径还是再归档

## Detailed Runbook

Use:

- `docs/development/POSTGRESQL_DASHBOARD_POST_GREY_DECOMMISSION_RUNBOOK.md`
