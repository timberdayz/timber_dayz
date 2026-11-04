# 业务概览与 B 成本慢查询根治 —— 设计规格

- 日期：2026-11-04
- 状态：**已实施**（口径零变化方案，见 §4）
- 范围：`sql/semantic/orders_atomic_mv.sql`（新增）、`sql/semantic/analytics_atomic_mv.sql`（新增）、`sql/mart/{shop,platform}_{day,week}_kpi.sql`、`sql/mart/b_cost_shop_month.sql`、`sql/api_modules/b_cost_analysis_order_detail_module.sql`、`backend/services/data_pipeline/refresh_registry.py`、`backend/services/data_pipeline/dashboard_bootstrap.py`、`current_migrations/versions/20261105_create_atomic_materialized_views.py`
- 关联文档：`docs/guides/RELEASE_CHECKLIST.md`、`docs/architecture/DASHBOARD.md`、`CHANGELOG.md`（v7.13.0）

---

## 1. 要解决的业务问题

业务概览页与 B 成本页在生产上**长期 504**，用户看到的是空白页，后端那条可读的「查询超时」永远送不到浏览器。

生产 nginx 错误日志（304MB 全量）里 504 共 164 次，落点集中在 4 个接口：

| 接口 | 504 次数 | 归属页面 |
| --- | --- | --- |
| `/api/dashboard/clearance-ranking` | 多次 | 业务概览·滞销清理排名（**v7.13.0 已随模块下线**） |
| `/api/dashboard/business-overview/bootstrap` | 多次 | 业务概览首屏 |
| `/api/dashboard/business-overview/operational-metrics` | 多次 | 业务概览·经营指标 |
| `/api/dashboard/b-cost-analysis/overview` | 多次 | B 成本分析 |
| `/api/dashboard/b-cost-analysis/shop-month` | 多次 | B 成本分析 |

v7.13.0 已把超时三层重排为 **DB 60s < 前端 axios 120s < nginx 300s**，所以 504 变成可读的 500 —— 但**页面依然打不开**。本规格解决「让它打得开」。

---

## 2. 实测证据（生产，2026-11-04）

### 2.1 接口耗时（容器内直连 127.0.0.1:8000）

| 接口 | 耗时 |
| --- | --- |
| `business-overview/kpi` | 0.09s |
| `business-overview/comparison` | 0.08s |
| `business-overview/traffic-ranking` | 0.10s |
| `business-overview/shop-racing` | 0.01s |
| `business-overview/inventory-backlog` | 0.19s |
| **`business-overview/operational-metrics`** | **22.77s** |
| **`business-overview/bootstrap`** | **23.22s** |

`bootstrap` 内部串行调用 kpi + comparison + operational_metrics + traffic + shop_racing ⇒ **它的 23s 就是 operational_metrics 的 23s**。

**结论：慢的只有 `operational-metrics` 一个**（bootstrap 是它的放大器），其余全在 0.2s 以内。

### 2.2 为什么 kpi / comparison / traffic 很快、operational-metrics 很慢

它们都读 `mart.shop_*_kpi`，差别在**粒度分支**：

- `mart.shop_month_kpi` → `semantic.fact_orders_monthly_atomic` → **物化视图** `semantic.fact_orders_monthly_atomic_mv`（36,624 行）⇒ 快。
- `mart.shop_day_kpi` → `semantic.fact_orders_atomic` → **普通视图**，每次请求现场重算 ⇒ 慢。

而 `operational-metrics` 是唯一**必须**读日粒度的接口：它的 `today_sales` / `today_order_count` 来自
`LEFT JOIN mart.shop_day_kpi ds ON ds.period_date = m.anchor_date`。

kpi / comparison / traffic 之所以快，是因为它们的过滤条件（`granularity='monthly'`）能被 PostgreSQL
推进 `UNION ALL` 的每个分支 ⇒ **只算月分支** ⇒ 走物化视图。`operational-metrics` 没有这个分支过滤，
日分支必须实算。

### 2.3 EXPLAIN：慢在哪一段（生产实测）

`EXPLAIN SELECT count(*) FROM mart.shop_day_kpi WHERE period_date = '2026-09-15'` → **20.2 秒**。

执行计划关键片段：

```
->  Subquery Scan on fact_orders_atomic
      ->  Nested Loop Left Join
            ->  Subquery Scan on d
                  Filter: ((d.rn = 1) AND (d.granularity = 'daily') AND (d.metric_date = '2026-09-15'))
                  ->  WindowAgg
                        ->  Sort
                              Sort Key: ...platform_code, ...shop_id, ...data_hash, ...granularity, ...ingest_timestamp DESC
                              ->  Result
                                    ->  Append
                                          ->  Seq Scan on fact_shopee_orders_daily
                                          ->  Seq Scan on fact_shopee_orders_weekly
                                          ->  Seq Scan on fact_shopee_orders_monthly
                                          ->  Seq Scan on fact_tiktok_orders_daily
                                          ->  Seq Scan on fact_tiktok_orders_weekly
                                          ->  Seq Scan on fact_tiktok_orders_monthly
                                          ->  Seq Scan on fact_miaoshou_orders_daily
                                          ->  Seq Scan on fact_miaoshou_orders_weekly
                                          ->  Seq Scan on fact_miaoshou_orders_monthly
```

**关键事实：`metric_date = '2026-09-15'` 这个过滤条件没有下推到 9 张表的 `Seq Scan` 上**，
9 张表被全量扫描后才过滤。

---

## 3. 为什么「加日期下推」这条最直觉的路走不通

PostgreSQL **不能**把一个引用了窗口函数输出列的 qual 推到 `WindowAgg` 之下 ——
除非该列出现在窗口的 `PARTITION BY` 或 `ORDER BY` 里。

`semantic.fact_orders_atomic` 的去重窗口是：

```sql
ROW_NUMBER() OVER (
    PARTITION BY platform_code, shop_id, data_hash
    ORDER BY <granularity 优先级>, ingest_timestamp DESC
)
```

`metric_date` 既不在 `PARTITION BY` 也不在 `ORDER BY` ⇒ **任何按 `metric_date` 的过滤都只能发生在窗口之后**。
而窗口之前是 9 张表的原始 JSON 解析（`raw_data->>'...'` + `REGEXP_REPLACE` 清洗）。

⇒ **在视图层面加日期条件是无效的**。要让日粒度变快，只能把「去重 + 身份解析」的结果**物化**，
让重算发生在离线刷新期而不是每次请求。

（`granularity='daily'` 能被下推，是因为 `granularity` 出现在窗口的 `ORDER BY` 里 —— 这也是现有
`mart.shop_day_kpi` 的 `WHERE granularity='daily'` 生效的原因。）

---

## 4. 方案（已实施）：把**整个**原子层物化

### 4.1 生产数据面测绘（决定了方案的形状）

2026-11-04 生产库实测：

| 粒度 | 行数 | GMV 占比 | metric_date 区间 |
| --- | --- | --- | --- |
| monthly | 36,624 | 93.79% | 2026-01-01 ~ 2026-10-01 |
| weekly | 1,506 | 3.86% | 2026-06-08 ~ 2026-06-21 |
| daily | 477 | 2.35% | 2026-06-06 ~ 2026-08-16 |
| **合计** | **38,607** | 100% | — |

流量事实合计仅 4,431 行（shopee daily 10 / monthly 2,993；tiktok daily 72 / monthly 1,356；weekly 与 miaoshou 全 0）。

另有两个关键事实：

1. **去重窗口其实是空转的**：`total_groups = total_rows = 38,607` ⇒ 每个
   `(platform_code, shop_id, data_hash)` 在 9 表联合里唯一出现一次，窗口一次都没合并过。
2. **月表里有成本列**：`b_class.fact_{shopee,tiktok}_orders_monthly` 带
   `采购成本` / `仓库操作费` / `采购金额` 等扩展列；只是现有月度 MV 没选它们。

### 4.2 为什么不是「按粒度各建一个 MV 并换源」

原设想：建 `fact_orders_daily_atomic_mv` + `fact_orders_monthly_cost_atomic_mv`，
消费方换源。**已否决**，因为换源会改变行集合：

- 旧口径 `semantic.fact_orders_atomic` 的行 = daily 477 + weekly 1,506 + monthly 36,624；
- 纯月表源的行 = monthly 36,624。
- ⇒ **B 成本页会少算 1,983 行订单**（GMV 的 6.2%），金额漂移。

换源方案要成立，必须先证明差异为 0；这里差异**必然不为 0**。

### 4.3 采用方案：物化**整个**原子视图（口径零变化）

| 层 | 变更 |
| --- | --- |
| semantic（新增） | `semantic.fact_orders_atomic_mv` = `SELECT * FROM semantic.fact_orders_atomic`<br>`semantic.fact_analytics_atomic_mv` = `SELECT * FROM semantic.fact_analytics_atomic` |
| mart | `shop_day_kpi` / `shop_week_kpi` / `platform_day_kpi` / `platform_week_kpi` 改读两个 MV |
| mart + api | `mart.b_cost_shop_month` / `api.b_cost_analysis_order_detail_module` 改读订单 MV |
| 刷新 | 两个 MV 进 `refresh_registry`（`PIPELINE_DEPENDENCIES` + `SQL_TARGET_PATHS`）+ `dashboard_bootstrap` 的 `business_overview.refresh_targets` |

**口径零变化的根据**：物化视图的正文**就是**普通视图的正文（`SELECT * FROM <普通视图>`）——
同一份定义、同一套去重、同一套身份解析、同一批行。物化只改变「什么时候算」，不改变「算什么」。

**一个 MV 同时修好 3 个 504 接口**：日/周粒度 KPI 与 B 成本页读的都是这一层；
只做日粒度 MV 的话，B 成本页仍然是 20 秒级。

### 4.4 刷新为什么用「存在则 REFRESH / 不存在则 CREATE」而不是 `DROP ... CASCADE`

`DROP MATERIALIZED VIEW ... CASCADE` 会连带删掉下游视图，而下游里有两类删不得的对象：

- `mart.hr_shop_monthly_profit`、`mart.inventory_backlog_base_mv`
  —— **不是 refresh registry 的可重建目标**，被删掉就没人重建；
- `mart.b_cost_shop_month`、`api.b_cost_analysis_order_detail_module`
  —— **不在 dashboard bootstrap 的 core 计划里**，同样没人重建 ⇒ B 成本页直接挂。

改用原地 `REFRESH MATERIALIZED VIEW` 后：
- 物化视图的**正文引用的是普通视图**，普通视图用 `CREATE OR REPLACE VIEW` 更新 ⇒
  MV 的刷新永远跟着普通视图的最新定义走，不会出现「文件改了但 MV 还是旧定义」的漂移；
- 刷新期间不删任何对象 ⇒ 没有「视图短暂消失」的窗口，也没有「重建漏掉」的风险。

代价：刷新期间物化视图持 ACCESS EXCLUSIVE 锁，读取排队约 20 秒 —— 但这与今天的
「每次请求都要 20 秒」相比是净收益。

### 4.5 仍然读普通视图（故意不动）的两个下游

- `mart.hr_shop_monthly_profit`（薪资链路）、`mart.inventory_backlog_base_mv`
  —— 它们不是 registry 可重建目标，改读物化视图会有「被 CASCADE 删掉且无人重建」的风险。
  这条约束由 `backend/tests/data_pipeline/test_atomic_materialized_views.py` 守住。

---

## 5. 口径核对结论（原本唯一的真实风险，已消解）

原规格把「口径对账」列为实施第 0 步：**差异必须为 0 才能切换**。

采用 §4.3 的方案后，这条风险**在结构上被消解** —— 物化视图与普通视图是同一份定义，
不存在「两套口径」可比对。切换前仍做了一次只读核对，确认了 §4.1 的数据面事实
（38,607 行的粒度构成与 GMV 占比），正是这份事实否决了换源方案。

验收口径改为：**物化视图与普通视图逐行一致**（结构上恒等），
且 6 个消费方视图的聚合结果不变。

---

## 6. 实施步骤（已完成）

1. **只读测绘**（生产）：行数 / 粒度构成 / GMV 占比 / 视图依赖图 / volatile 检查。→ 得出 §4.1、§4.2。
2. 新增两个物化视图资产（`sql/semantic/orders_atomic_mv.sql`、`sql/semantic/analytics_atomic_mv.sql`）。
3. 6 个消费方改读物化视图。
4. `refresh_registry` 注册两个 MV + 依赖顺序；`dashboard_bootstrap` 的 `business_overview.refresh_targets` 登记。
5. 迁移 `current_migrations/versions/20261105_create_atomic_materialized_views.py`：
   建两个 MV + 索引 + 用 `sql/` 资产重建 6 个消费方视图。
6. 顺带修正 `api.business_overview_operational_metrics_module` 的依赖表
   （它有一处 `LEFT JOIN mart.shop_day_kpi`，但依赖表里没写 → 可能拿到旧日粒度数据）。
7. 验收：
   - `operational-metrics` 与 `bootstrap` P95 < 3s；
   - B 成本三个接口 P95 < 5s；
   - nginx 错误日志新增 5xx = 0（观察 24h）。

---

## 7. 明确不做的事

- **不**改 `semantic.fact_orders_atomic` 的去重口径（`PARTITION BY` / `ORDER BY`）——
  那会改变所有历史报表的归属。
- **不**换源重建粒度 MV（会丢 1,983 行订单，见 §4.2）。
- **不**为了快而调大 `work_mem` / `shared_buffers` 硬扛 20s 全量重算
  （v7.13.0 已把容器内存上限放宽到 4G，是给重查询留余量，不是用它换正确性）。
- **不**在 api 层直接读 atomic 语义视图 —— `backend/tests/data_pipeline/
  test_business_overview_query_policy_gates.py` 的架构门禁明确禁止
  （`FROM semantic.fact_orders_atomic` 是 forbidden token）。
- **不**把 `mart.hr_shop_monthly_profit` / `mart.inventory_backlog_base_mv` 改读物化视图（见 §4.5）。
