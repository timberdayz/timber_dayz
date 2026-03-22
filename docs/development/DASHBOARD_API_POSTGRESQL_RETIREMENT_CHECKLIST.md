# Dashboard API PostgreSQL Cutover Checklist

## Goal

在完全下线旧 `backend/routers/dashboard_api.py` 之前，确认 PostgreSQL 路由与服务层已经覆盖所有主链路接口，并且具备可回退、可验证、可观测能力。

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
- 生产环境默认值保持旧路由，灰度时显式打开 `USE_POSTGRESQL_DASHBOARD_ROUTER=true`
- PostgreSQL 路由的真实数据库级接口验证范围继续扩大
- 旧 `dashboard_api.py` 保留为回退路径，直到灰度完成

## Cutover Preconditions

- `backend/tests/data_pipeline` 全绿
- `USE_POSTGRESQL_DASHBOARD_ROUTER=true` 的应用级验证通过
- `ops` 路由可正常查看 `status / freshness / lineage`
- 关键业务页面 smoke 验证通过

## Final Retirement Steps

1. 在预发环境默认打开 `USE_POSTGRESQL_DASHBOARD_ROUTER=true`
2. 验证关键页面与关键接口行为
3. 观察 `ops.pipeline_run_log`、`ops.data_freshness_log`
4. 生产灰度开启
5. 灰度稳定后，再考虑移除旧 `dashboard_api.py` 中的 Metabase 主链路依赖
