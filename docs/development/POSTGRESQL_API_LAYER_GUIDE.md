# PostgreSQL API Layer Guide

## Goal

冻结当前 Dashboard 与年度汇总主链路的页面模块、数据源类型和返回契约，作为后续 `Metabase -> PostgreSQL` 切换的基线。

## First-Wave Cutover Scope

首批切换范围仅覆盖线上主链路中最核心、最频繁使用、且已经高度依赖 Metabase Question 的模块：

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

## Current Module-To-Source Mapping

| Module | Route | Current Source Type | Current Query Key |
|---|---|---|---|
| `business_overview_kpi` | `/api/dashboard/business-overview/kpi` | `metabase_question` | `business_overview_kpi` |
| `business_overview_comparison` | `/api/dashboard/business-overview/comparison` | `metabase_question` | `business_overview_comparison` |
| `business_overview_shop_racing` | `/api/dashboard/business-overview/shop-racing` | `metabase_question` | `business_overview_shop_racing` |
| `business_overview_traffic_ranking` | `/api/dashboard/business-overview/traffic-ranking` | `metabase_question` | `business_overview_traffic_ranking` |
| `business_overview_inventory_backlog` | `/api/dashboard/business-overview/inventory-backlog` | `metabase_question` | `business_overview_inventory_backlog` |
| `business_overview_operational_metrics` | `/api/dashboard/business-overview/operational-metrics` | `metabase_question` | `business_overview_operational_metrics` |
| `clearance_ranking` | `/api/dashboard/clearance-ranking` | `metabase_question` | `clearance_ranking` |
| `annual_summary_kpi` | `/api/dashboard/annual-summary/kpi` | `hybrid_metabase_postgresql` | `annual_summary_kpi` |
| `annual_summary_by_shop` | `/api/dashboard/annual-summary/by-shop` | `postgresql_service` | `annual_cost_aggregate_by_shop` |
| `annual_summary_trend` | `/api/dashboard/annual-summary/trend` | `metabase_question` | `annual_summary_trend` |
| `annual_summary_platform_share` | `/api/dashboard/annual-summary/platform-share` | `metabase_question` | `annual_summary_platform_share` |
| `annual_summary_target_completion` | `/api/dashboard/annual-summary/target-completion` | `postgresql_sql` | `annual_summary_target_completion` |

## Not In Scope For First Wave

- 任意不属于 `dashboard_api.py` 主链路的后台管理/治理页面
- 原始采集、上传、字段映射管理页
- 低频、内部使用、尚未绑定前端主页面的 Metabase 内容
- 彻底删除 Metabase 服务本身

## Compatibility Rule

切换阶段必须遵守以下兼容规则：

1. 前端页面 URL、请求参数名、响应 JSON 顶层结构保持不变。
2. 页面模块级数据结构保持不变，除非先更新契约测试并完成前端同步。
3. 任何 PostgreSQL 新实现都必须先经过与当前 Metabase 结果的双路对齐验证。
4. 未通过对齐验证前，不允许默认切换生产主链路。

## Recommended Execution Order

1. 冻结契约与模块映射。
2. 构建 `semantic` 标准化层。
3. 构建 `mart` 通用汇总层。
4. 构建 `api` 页面模块视图层。
5. 新增后端 PostgreSQL 直查服务与特性开关。
6. 进行双路对齐验证。
7. 灰度切换。
