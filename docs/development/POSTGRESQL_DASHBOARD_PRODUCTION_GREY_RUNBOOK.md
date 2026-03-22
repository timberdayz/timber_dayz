# PostgreSQL Dashboard Production Grey Runbook

## Goal

在生产环境中对 PostgreSQL Dashboard 路由进行受控灰度，确保可以快速确认路由来源、接口健康、链路 freshness 和回退路径。

## Preconditions

- 预发验证已完成并通过
- `backend/tests/data_pipeline` 全绿
- 已完成 `POSTGRESQL_DASHBOARD_PREPROD_CHECK_REPORT_TEMPLATE.md`
- 已确认旧 `dashboard_api.py` 仍可作为回退路径

## Grey Enable

1. 在目标环境配置中设置：

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=true
```

2. 重启应用后确认启动日志包含：

- `Dashboard router source: PostgreSQL`

## Immediate Checks

执行：

```bash
python scripts/run_postgresql_dashboard_preprod_check.py --base-url <base_url>
```

重点确认：

- `/api/dashboard/business-overview/kpi`
- `/api/dashboard/business-overview/comparison`
- `/api/dashboard/business-overview/shop-racing`
- `/api/dashboard/business-overview/operational-metrics`
- `/api/dashboard/annual-summary/kpi`
- `/api/dashboard/annual-summary/trend`
- `/api/dashboard/annual-summary/platform-share`
- `/api/dashboard/annual-summary/by-shop`
- `/api/dashboard/annual-summary/target-completion`

## Ops Observation

观察：

- `ops.pipeline_run_log`
- `ops.pipeline_step_log`
- `ops.data_freshness_log`
- `ops.data_lineage_registry`

建议记录：

- 最近 5 条 pipeline run 状态
- 最近 10 条 pipeline step 状态
- 关键 dashboard target 的 freshness

## Rollback

若发现关键接口异常、数据不一致、freshness 持续失败，立即回退：

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=false
```

重启后确认日志包含：

- `Dashboard router source: Metabase compatibility`

## Exit Criteria

满足以下条件时，可认为本轮灰度成功：

- 核心 dashboard HTTP smoke 全部 `200`
- `ops` 表中没有持续失败的 freshness / step
- 关键业务数据人工抽查无明显偏差
- 无需执行回退
