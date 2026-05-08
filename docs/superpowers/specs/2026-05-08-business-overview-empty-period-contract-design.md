# Business Overview 空月（Empty Period）口径契约（Design）

**Date:** 2026-05-08  
**Status:** Draft (awaiting review)  
**Scope:** PostgreSQL Dashboard router / service（Business Overview page）

## Background

当前 Business Overview 页面存在两类“空月”风险：

1. **上游入库错位**导致本不应属于当月的数据被归入当月（此问题已在上游解析与 semantic 映射层做了修复与兜底）。
2. **空月展示口径不一致**：页面/接口在“当月没有数据”时，部分字段返回 `null`，部分字段返回 `0`，且缺少可机器识别的“空月状态”标志，前端难以稳定区分“确实为 0”与“无数据/不可计算”。

本设计聚焦第 2 点：定义并落地 **Empty Period（空月）契约**，以提升数据准确性与可解释性，并为后续全量重采/同步提供稳定的验证基座。

## Goals

- 统一 Business Overview 全模块（`bootstrap` + 5 个拆分模块 + `inventory-backlog` 可先不改）的**空月返回值策略**。
- 在 API `meta` 中提供稳定的**空月状态标志与告警**，减少前端“猜测/推断”。
- 保持对现有前端尽可能兼容：`data` 结构不破坏；新增 `meta` 字段为向后兼容扩展。
- 通过契约测试（pytest）把规则固化，避免回归。

## Non-Goals

- 不重写前端页面；仅在必要时建议最小改动（例如 `null` 显示 `--`）。
- 不在本阶段改造采集/入库管线（入库错位已单独修复；采集环境优化后续再做）。
- 不引入新的业务口径，只对“空月/缺失值表示”做标准化。

## Definitions

### Empty Period（空月）

对给定的 `(granularity, period_key, platform_code?, shop_id?)`：

- **空月/空期**：该期在对应模块查询结果中不存在任何可用的事实行/聚合行（典型表现为 `rows == []`，或只有一行但所有核心指标均为 `NULL`）。

> 备注：空月的判断必须由后端统一给出，前端不应通过 `gmv==0` 等条件推断。

### Zero vs Null（业界主流建议）

- **加总/计数类**指标：空月返回 `0`
  - 例：`gmv`、`order_count`、`visitor_count`、`profit`、`traffic`、`sales_quantity`、`sales_amount`、`total_items` 等。
- **比率/均值/变化类**指标：空月返回 `null`
  - 例：`conversion_rate`、`avg_order_value`、`attach_rate`、`change`、`achievement_rate`、各类 `*_rate` 等。

理由：
- `0` 用于表达“该指标在口径上可计算，且结果确实为 0”（可加总、可画图不断点）。
- `null` 用于表达“不可计算/无数据”，避免把“不可得”误导成“0%/0 元”。

## Contract

### Response Envelope（统一返回外壳）

沿用既有 envelope（见 `2026-05-07-business-overview-module-standardization-design.md`）：

```json
{
  "meta": {
    "granularity": "monthly",
    "period_key": "2026-05-01",
    "platform_code": "shopee",
    "shop_id": "123",
    "generated_at": "2026-05-08T01:02:03Z",
    "cache": {"status": "HIT", "hit": true},
    "warnings": []
  },
  "data": { "..." : "..." }
}
```

本设计新增（向后兼容）：

- `meta.data_status`: `"ok" | "empty_period" | "partial" | "unknown"`
  - `empty_period`：本期完全无数据（空月/空期）。
  - `partial`：本期有数据，但部分模块/部分字段缺失（可通过 warnings 给出原因）。
- `meta.is_empty_period`: `true | false`（与 `data_status` 冗余但便于前端消费）

以及增强 `meta.warnings`：
- 当 `empty_period`：至少追加一条标准化 warning，例如：
  - `"empty_period: no rows matched for the requested period"`

### Module-specific rules（空月默认值）

#### 1) `kpi`

空月时：
- `gmv/order_count/visitor_count/profit/labor_efficiency/total_items`：`0`（其中 `labor_efficiency` 若无更明确口径也按 `0` 处理）
- `conversion_rate/avg_order_value/attach_rate`：`null`

#### 2) `comparison`

`comparison` 里同时包含 today/previous/average/target 等。

空月时：
- `metrics.*.today`：加总类为 `0`，比率/均值类为 `null`
- `metrics.*.yesterday/average`：保持与查询结果一致；若同样为空则按空月规则落为 `0/null`
- `metrics.*.change`：`null`（空月不计算变化）
- `target.*`：若 target 不存在则为 `null`；`achievement_rate` 在 `today` 或 target 不可得时为 `null`

> 备注：如果业务希望“空月但有 target”时显示 `achievement_rate=0`，需要另行显式约定；默认仍为 `null`（避免把“无销量”与“无数据”混淆）。

#### 3) `operational-metrics`

空月时：
- 加总/计数：`0`
- 率/均值/变化：`null`
- ranking/list 类型结构：返回 `[]`（而不是 `null`），并标记 `empty_period`

#### 4) `traffic-ranking`

空月时：
- 返回 `[]`
- `meta.is_empty_period=true`

#### 5) `shop-racing`

空月时：
- 返回 `[]`
- `meta.is_empty_period=true`

#### 6) `bootstrap`

空月时：
- `bootstrap.data` 仍返回各子模块的结构化结果（便于前端稳定渲染）
- `bootstrap.meta` 的 `data_status/is_empty_period/warnings` 以“整期”视角给出：
  - 若所有子模块都空：`empty_period`
  - 若部分子模块空：`partial` + warnings 指明是哪个模块空

## Implementation Notes (planned)

### Where to implement

- **Service 层**：在 reducer（如 `reduce_business_overview_kpi_rows` 等）统一实现“空月默认值（0/null/[]）”与“空月判定”。
- **Router 层**：在 `_wrap_business_overview_envelope` / `_build_business_overview_meta` 中添加 `data_status/is_empty_period`，并追加标准化 warnings。

### Empty period detection strategy（建议）

优先基于 rows 判定：

1) `rows == []` -> empty
2) `rows != []` 但所有核心字段均为 `NULL` -> empty（避免 SQL 总是返回一行的情况）

核心字段集合由模块定义（例如 KPI 模块核心字段可用 `gmv/order_count/visitor_count/profit`）。

## Tests (contract)

新增契约测试覆盖：

- `kpi`：空期时 additive=0，ratio=null，`meta.is_empty_period=true`
- `comparison`：空期时 `change=null`，`today` 的 additive=0 ratio=null，`meta.is_empty_period=true`
- `traffic-ranking/shop-racing/operational-metrics`：空期时返回 `[]`，`meta.is_empty_period=true`
- `bootstrap`：空期时子模块结构齐全，`meta.data_status` 与 warnings 合理

测试数据策略：
- 使用现有测试 DB fixture（或临时建表）确保该 period_key 下无匹配行。
- 测试仅验证契约（0/null/[] 与 meta 标志），不绑定具体 SQL 实现细节。

## Open Questions

1) `comparison.target.achievement_rate`：空期但 target 存在时是否要返回 `0`（表示 0% 达成）？
   - 本设计默认 `null`（表示不可得/无数据），如需改为 `0` 需明确业务含义与前端展示策略。

