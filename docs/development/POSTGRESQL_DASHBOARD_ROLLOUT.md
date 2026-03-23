# PostgreSQL Dashboard Rollout Guide

## Goal

在不影响现有线上页面的前提下，将 Dashboard 主链路从旧的 Metabase 兼容路由灰度切换到新的 PostgreSQL 路由。

## Enable

在目标环境显式设置：

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=true
```

未设置或为 `false` 时，系统继续使用旧的 Dashboard 路由作为兼容路径。

## Verify

启动后先确认日志中出现以下其一：

- `Dashboard router source: PostgreSQL`
- `Dashboard router source: Metabase compatibility`

然后重点观察：

- `ops.pipeline_run_log`
- `ops.pipeline_step_log`
- `ops.data_freshness_log`
- `ops.data_lineage_registry`

同时验证关键接口：

- `/api/dashboard/business-overview/kpi`
- `/api/dashboard/business-overview/comparison`
- `/api/dashboard/business-overview/shop-racing`
- `/api/dashboard/business-overview/operational-metrics`
- `/api/dashboard/annual-summary/target-completion`

## Suggested Rollout Order

1. 开发环境开启 `USE_POSTGRESQL_DASHBOARD_ROUTER=true`
2. 运行 `pytest backend/tests/data_pipeline -q`
3. 预发环境开启并做 smoke 验证
4. 观察 `ops` 日志与 freshness 状态
5. 生产环境灰度开启

## Rollback

如需回退，只需将以下开关关闭：

```env
USE_POSTGRESQL_DASHBOARD_ROUTER=false
```

回退后应用会重新走旧的 Dashboard 路由，不需要改动数据库对象或删除 PostgreSQL 资产。

## Notes

- 新旧路由都保留期间，优先通过环境变量控制切换，不直接修改代码默认值。
- 完全下线旧路由前，应先完成 `DASHBOARD_API_POSTGRESQL_RETIREMENT_CHECKLIST.md` 中的项目。
