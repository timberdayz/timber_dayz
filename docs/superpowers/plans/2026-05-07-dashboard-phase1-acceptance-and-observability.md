# Dashboard Phase-1 Acceptance + Observability

**Goal:** 达成 Phase-1 验收线（bootstrap cache MISS P95 < 10s、cache HIT P95 < 200ms），并建立可复现的慢点定位证据闭环（后端 breakdown + Postgres slow SQL）。

## Plan

1. 打通观测闭环
   - 后端：bootstrap 内部拆分子调用耗时日志（kpi/comparison/operational）
   - Postgres：开启 `log_min_duration_statement`（建议 2s）用于验收与定位
2. 统一性能策略（semantic 重计算对象）
   - identity candidates 改为：`*_mv`（物化）+ 索引 + 对外同名 VIEW
   - analytics semantic 视图：identity resolution join 走 `VALUES (...) JOIN`，减少候选扫描
3. 验收采样
   - 提供 cache MISS 采样：每次请求前失效 dashboard cache
   - 采样 15+ 次计算 P95

