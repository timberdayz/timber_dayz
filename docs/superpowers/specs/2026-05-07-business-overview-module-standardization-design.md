# Business Overview Module Standardization (Design)

**Date:** 2026-05-07  
**Status:** Draft (awaiting review)  
**Scope:** PostgreSQL Dashboard router (Business Overview page)

## Goal

在不破坏现有线上/本地调用方式的前提下，统一 Business Overview（排除滞销库存 inventory backlog）模块的：

- 输入参数（统一语义与兼容旧参数）
- 输出字段命名与缺失值策略（避免前端猜测）
- 分层职责（semantic/mart/api/service 的边界）
- 性能策略（哪些必须物化、必须索引、refresh 由谁触发）
- 验收证据链（pytest + curl 响应头 + Postgres 慢 SQL 对齐）

## Non-Goals

- 不在本阶段改造 `inventory-backlog`（滞销库存）相关模块。
- 不引入新的业务口径（除非明确记录为口径变更，并在验收中体现差异）。
- 不重写前端页面；本阶段以 API 契约与 SQL 分层为主。

## Current Scope (Modules)

Business Overview（排除 inventory backlog）按现状包含：

- `bootstrap`（聚合入口，组合多个模块的结果）
- `kpi`
- `comparison`
- `traffic-ranking`
- `operational-metrics`
- `shop-racing`

## Terms / Layer Responsibilities

**Data flow:** `b_class raw -> semantic -> mart -> api -> backend router/service -> frontend`

- `semantic`：标准化原子事实（atomic facts）与必要的身份解析（identity resolution）。
  - 允许：字段清洗、类型转换、最小必要的标准化映射。
  - 禁止：页面口径拼装、跨模块 UI 逻辑、为单个页面临时写大聚合。
- `mart`：可复用的聚合层（按粒度/维度组织），供多个页面/模块复用。
  - 允许：按 `granularity + period_key + platform_code + shop_id` 组织的通用聚合。
  - 禁止：页面专属字段命名、前端展示结构、与 UI 强绑定的 join。
- `api`（`sql/api_modules/*_module.sql`）：页面模块查询层，必须“薄”。
  - 允许：筛选（period/platform/shop）、字段挑选、轻量 join。
  - 禁止：大范围 regexp/union/高成本聚合（应下沉至 semantic/mart 并物化/索引）。
- `service/router`：入参归一化、缓存策略、聚合多个模块（bootstrap）、观测、错误包装。
  - 允许：将旧参数映射到统一参数；统一缺失值策略；拼装 `bootstrap` 返回结构。
  - 禁止：在 Python 内实现业务口径计算以替代 SQL（避免口径分裂）。

## Unified Input Contract

### Canonical Parameters (Target)

所有 Business Overview 模块（包括 bootstrap 与 5 个模块）最终使用同一组“规范化参数”：

- `granularity`: `daily | weekly | monthly`
- `period_key`: ISO date（`YYYY-MM-DD`），表达该粒度下的“key”：
  - monthly: 月首日（例如 `2026-05-01`）
  - weekly: 周起始日（建议周一，按现有系统约定）
  - daily: 当天日期
- `platform_code`: 可选；不传表示全平台聚合，传表示指定平台
- `shop_id`: 可选；不传表示平台级或全站，传表示店铺级

### Compatibility Parameters (Transitional)

为不破坏现有调用，过渡期保留旧参数并在 service/router 层归一化：

- 时间参数兼容：
  - `month`（`YYYY-MM-DD`）：映射到 `period_key`（monthly）
  - `date`（可能是 `YYYY-MM` 或 `YYYY-MM-DD`）：按 granularity 推导 `period_key`
  - `date_value`（`YYYY-MM-DD`）：映射到 `period_key`
- 平台参数兼容：
  - `platform`：映射到 `platform_code`

### Validation Rules

- 不支持的 `granularity`：直接返回 422（FastAPI validation error）。
- `period_key` 无法解析为合法日期：返回 422。
- 归一化完成后，统一在日志中输出归一化结果（便于定位“为什么查到这段时间/平台”）。

## Unified Output Contract

### Response Envelope

每个模块（含 bootstrap）统一返回：

```json
{
  "meta": {
    "granularity": "monthly",
    "period_key": "2026-05-01",
    "platform_code": "tiktok",
    "shop_id": null,
    "generated_at": "2026-05-07T14:00:00Z",
    "cache": {
      "hit": true,
      "ttl_seconds": 3600
    },
    "warnings": []
  },
  "data": {}
}
```

### Naming Rules

- 输出字段使用 `snake_case`。
- 同一概念字段名全模块统一（例如：`period_key`, `platform_code`, `gmv`, `order_count`）。

### Missing Value Policy

- “统计口径为 0 的指标”返回 `0`（例如 `order_count=0`）。
- “不可得/无此口径”的指标返回 `null`，并在 `meta.warnings` 给出原因：
  - 例：缺少上游数据、该平台不提供该指标、或分母为 0 的比率类指标。
- 比率类指标（`conversion_rate` 等）分母为 0 时返回 `null`（不返回 0 以免误导）。

## Performance Strategy

### Online Query Allowed Objects

在线请求路径只允许查询：

- `api.*_module`（view）
- 其依赖的 `mart` 聚合（以及必要的 `semantic` 原子事实或物化对象）

禁止在在线请求路径触发：

- 大规模 rebuild（例如 `CREATE MATERIALIZED VIEW ...`）
- 全量 refresh 计划（除非显式的运维/管理入口）

### Materialization (MV) Rules

以下场景必须考虑 MV（并配套索引）：

- 使用 regexp/union 且会被多模块复用的解析逻辑（identity resolution candidates 属于此类）
- 大表聚合且在线重复调用频率高的对象
- 已出现 statement timeout/QueryCanceledError 的关键路径

### Index Rules

对 MV/核心聚合表，必须具备满足 where/join 的索引（按模块查询条件）：

- `period_key`（或 `period_month`/`period_date` 等等价字段）
- `platform_code`
- `shop_id`（若模块支持店铺维度）

### Refresh / Dependency Rules

所有上游依赖必须在：

- `backend/services/data_pipeline/refresh_registry.py`

显式表达（SSOT），确保：

- refresh 顺序可拓扑排序
- 每个模块依赖对象在 refresh 后一致可用
- 可回滚：避免使用 `DROP ... CASCADE` 破坏下游 view

## Observability / Evidence Chain

### Backend Observability

- `bootstrap` 需输出子调用耗时 breakdown（用于快速定位“到底慢在 kpi/comparison/operational 哪一块”）。

### PostgreSQL Slow SQL

验收期间建议开启：

- `log_min_duration_statement=2s`

以便在：

- `docker logs xihong_erp_postgres`

中抓取 `duration:` 证据，并与后端 breakdown 对齐。

验收结束后建议恢复为 `-1` 以减少日志噪音。

## Acceptance Criteria (Phase-2: Standardization)

### Functional Acceptance

- 同一组参数（归一化后）下，各模块口径一致：
  - `period_key` 的含义一致
  - `platform_code`/全平台聚合策略一致
  - 缺失值策略一致（null/0/不可用）
- 若存在口径变更：必须在 spec/报告中明确变更点与原因，并提供对比证据。

### Performance Acceptance

对 Business Overview `bootstrap`：

- cache MISS：P95 < 10s
- cache HIT：P95 < 200ms

对 5 个模块拆分接口（kpi/comparison/traffic-ranking/operational-metrics/shop-racing）：

- 线上/本地探针采样中无超时、无 statement timeout cancel

### Evidence Artifacts (Local)

- 性能回归脚本输出：
  - `temp/outputs/performance_regression_summary_latest.json`
- BO 模块拆分探针输出：
  - `temp/outputs/business_overview_split_probe_latest.json`
  - `temp/outputs/business_overview_long_run_latest.json`
- Postgres 慢 SQL：
  - `docker logs xihong_erp_postgres | findstr duration:`

## Rollback Strategy

- SQL 变更优先采用“同名 view 透出 + 底层替换”为主：
  - 例如：底层新增 `*_mv`，对外维持同名 view，避免上游引用破坏。
- 禁止在 refresh/迁移流程中使用 `DROP ... CASCADE`。
- 每个模块改造按最小 diff 提交，并在 commit message 中标注模块名，便于回滚。

## Planned Execution (High Level)

执行顺序（最小改动、可回滚）：

1. `traffic-ranking`
2. `comparison`
3. `kpi`
4. `operational-metrics`
5. `shop-racing`
6. `bootstrap`（统一聚合与 meta/warnings 输出）

每改一个模块：

- 更新对应 `sql/api_modules/*.sql`（尽量薄）
- 必要时在 `mart/semantic` 增加可复用聚合或 MV + 索引
- 补齐 refresh 依赖（`refresh_registry.py`）并补/更新 pytest
- 重新跑探针与 Postgres 慢 SQL 对齐，输出证据

