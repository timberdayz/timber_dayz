# v7.13.0 验收记录：原子层物化（B2）

- 日期：2026-11-04
- 生产环境：西虹 ERP 云端生产（7 个容器 healthy，部署前版本 v7.12.9）
- 本记录用途：**部署前后口径比对基线**。部署 v7.13.0 后按同一组 SQL 重跑，逐行核对。

---

## 1. 结论速览

| 项目 | 结果 |
| --- | --- |
| 后端失败集 diff（对 HEAD 基线 worktree） | **新增失败 = 0**（51 个共有失败全是仓库既有失败；新增 10 个契约测试；随模块下线移除 9 个用例） |
| 全新库迁移门禁 `scripts/validate_migrations_fresh_db.py` | **通过**（迁移成功 + 数据同步关键列 + 迁移后 ORM Schema 一致性） |
| 全新库物化接线验收 | **通过**（2 个物化视图存在；**6/6** 消费方视图指向物化视图；0 个仍直读普通视图；8 个索引） |
| alembic 链头 | `current_schema_20261105_create_atomic_materialized_views`（生产起点 `...20261104_drop_clearance_ranking_module`） |
| UTF-8 源码卫生 / 仓库规则完整性 | PASS |
| 架构 SSOT | 3 项违规**全部来自仓库内陈旧 worktree** `.worktrees/inventory-aging-pipeline-recovery/`（既有，非本次引入） |

---

## 2. 生产口径基线（部署前，只读）

采集时间：2026-11-04（部署前，生产仍为 v7.12.9）

### 2.1 `mart.shop_day_kpi`（全部日粒度行，37 行）

| period_date | platform_code | shop_id | gmv | order_count | total_items | profit |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-06-06 | shopee | 1308200825 | 1273.52 | 14 | 14 | 348.05 |
| 2026-06-06 | shopee | 1308200832 | 1928.95 | 17 | 21 | 563.33 |
| 2026-06-06 | shopee | 1391124228 | 1487.72 | 15 | 20 | 406.86 |
| 2026-06-06 | shopee | 1407964586 | 1973.97 | 15 | 16 | 628.10 |
| 2026-06-06 | shopee | 1419165604 | 1101.55 | 30 | 32 | 256.87 |
| 2026-06-06 | shopee | 1419169771 | 3994.25 | 48 | 49 | 819.27 |
| 2026-06-06 | shopee | 1540271741 | 222.92 | 5 | 5 | 58.51 |
| 2026-06-06 | tiktok | tiktok_ph_daju_mall_local | 435.26 | 3 | 3 | 252.81 |
| 2026-06-06 | tiktok | tiktok_ph_explorers_mall_local | 4527.77 | 81 | 83 | 638.92 |
| 2026-06-06 | tiktok | tiktok_sg_daone_mall_local | 411.40 | 4 | 4 | 221.34 |
| 2026-06-06 | tiktok | tiktok_sg_hx_home_local | 115.84 | 1 | 1 | 59.91 |
| 2026-06-07 | shopee | 1308200825 | 331.69 | 3 | 3 | 99.59 |
| 2026-06-07 | shopee | 1308200832 | 1574.48 | 18 | 18 | 382.46 |
| 2026-06-07 | shopee | 1391124228 | 350.37 | 3 | 3 | 83.87 |
| 2026-06-07 | shopee | 1407964586 | 2025.36 | 15 | 16 | 628.26 |
| 2026-06-07 | shopee | 1419165604 | 714.73 | 18 | 18 | 159.05 |
| 2026-06-07 | shopee | 1419165607 | 254.43 | 2 | 2 | 139.69 |
| 2026-06-07 | shopee | 1419169771 | 2061.95 | 24 | 25 | 409.09 |
| 2026-06-07 | shopee | 1540271739 | 685.15 | 11 | 14 | 166.73 |
| 2026-06-07 | shopee | 1540271741 | 33.17 | 1 | 1 | 16.13 |
| 2026-06-07 | tiktok | tiktok_my_dawie_mall_local | 78.16 | 1 | 1 | 50.8 |
| 2026-06-07 | tiktok | tiktok_ph_daju_mall_local | 285.23 | 2 | 2 | 132.65 |
| 2026-06-07 | tiktok | tiktok_ph_explorers_mall_local | 1547.59 | 34 | 34 | 199.28 |
| 2026-06-18 | shopee | 1308200825 | 347.67 | 5 | 5 | 109.05 |
| 2026-06-18 | shopee | 1308200832 | 568.43 | 8 | 8 | 134.73 |
| 2026-06-18 | shopee | 1391124228 | 620.08 | 8 | 8 | 101.06 |
| 2026-06-18 | shopee | 1407964586 | 499.61 | 5 | 6 | 172.77 |
| 2026-06-18 | shopee | 1419165604 | 1416.28 | 30 | 35 | 373.80 |
| 2026-06-18 | shopee | 1419165607 | 30.61 | 1 | 1 | 6.05 |
| 2026-06-18 | shopee | 1419169771 | 1008.06 | 22 | 22 | 235.97 |
| 2026-06-18 | shopee | 1540271739 | 174.06 | 4 | 4 | 50.00 |
| 2026-06-18 | shopee | 1540271741 | 181.73 | 2 | 2 | 41.64 |
| 2026-06-18 | tiktok | tiktok_ph_explorers_mall_local | 196.03 | 4 | 6 | 81.32 |
| 2026-06-18 | tiktok | tiktok_sg_daone_mall_local | 81.85 | 1 | 1 | 40.11 |
| 2026-06-18 | tiktok | tiktok_sg_hx_home_local | 42.26 | 1 | 1 | 41.4 |
| 2026-08-16 | tiktok | tiktok_ph_explorers_mall_local | 347.19 | 4 | 4 | 41.37 |
| 2026-08-16 | tiktok | tiktok_sg_daone_mall_local | 280.39 | 3 | 3 | 180.38 |

### 2.2 `mart.shop_week_kpi`（30 行）

| period_week | platform_code | shop_id | gmv | order_count | total_items | profit |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-06-08 | shopee | 1308200825 | 7708.09 | 76 | 89 | 450.10 |
| 2026-06-08 | shopee | 1308200832 | 5793.70 | 66 | 68 | 56.09 |
| 2026-06-08 | shopee | 1391124228 | 4786.33 | 49 | 57 | 625.61 |
| 2026-06-08 | shopee | 1407964586 | 8204.59 | 71 | 76 | 845.66 |
| 2026-06-08 | shopee | 1419165604 | 8527.03 | 198 | 240 | 635.99 |
| 2026-06-08 | shopee | 1419165607 | 281.37 | 2 | 2 | 155.29 |
| 2026-06-08 | shopee | 1419169771 | 7925.26 | 135 | 143 | 488.77 |
| 2026-06-08 | shopee | 1540271739 | 2513.64 | 40 | 42 | 56.19 |
| 2026-06-08 | shopee | 1540271741 | 1369.42 | 25 | 31 | 139.15 |
| 2026-06-08 | tiktok | tiktok_ph_daju_mall_local | 393.54 | 3 | 3 | 75.28 |
| 2026-06-08 | tiktok | tiktok_ph_explorers_mall_local | 5163.67 | 138 | 144 | 436.70 |
| 2026-06-08 | tiktok | tiktok_sg_daone_mall_local | 931.07 | 10 | 10 | 332.50 |
| 2026-06-08 | tiktok | tiktok_sg_hx_home_local | 116.66 | 1 | 1 | 45.43 |
| 2026-06-15 | shopee | 1308200825 | 2339.58 | 26 | 27 | 239.00 |
| 2026-06-15 | shopee | 1308200832 | 5881.02 | 69 | 71 | 144.84 |
| 2026-06-15 | shopee | 1391124228 | 5070.64 | 53 | 60 | 523.97 |
| 2026-06-15 | shopee | 1407964586 | 6242.74 | 59 | 62 | 875.09 |
| 2026-06-15 | shopee | 1419165604 | 7306.18 | 161 | 198 | 574.25 |
| 2026-06-15 | shopee | 1419165607 | 1335.94 | 25 | 26 | -93.67 |
| 2026-06-15 | shopee | 1419169771 | 6602.69 | 123 | 128 | 622.64 |
| 2026-06-15 | shopee | 1540271739 | 1567.74 | 19 | 26 | 344.73 |
| 2026-06-15 | shopee | 1540271741 | 1703.81 | 22 | 28 | 138.93 |
| 2026-06-15 | shopee | 1540271744 | 170.08 | 1 | 4 | 42.33 |
| 2026-06-15 | tiktok | tiktok_my_dawie_mall_local | 73.66 | 1 | 1 | 22.29 |
| 2026-06-15 | tiktok | tiktok_my_flora_mall_local | 59.67 | 1 | 1 | -8.5 |
| 2026-06-15 | tiktok | tiktok_ph_daju_mall_local | 221.97 | 2 | 2 | 38.54 |
| 2026-06-15 | tiktok | tiktok_ph_explorers_mall_local | 1500.72 | 37 | 40 | 288.32 |
| 2026-06-15 | tiktok | tiktok_sg_daone_mall_local | 533.28 | 6 | 6 | 205.40 |
| 2026-06-15 | tiktok | tiktok_sg_hx_home_local | 42.26 | 1 | 1 | 34.5 |
| 2026-06-15 | tiktok | **unknown** | 127.22 | 2 | 2 | 92.93 |

> ⚠️ `unknown` 桶有真实金额（127.22 / 2 单）—— 这就是「语义层对不上店」的业务影响，
> 属于 P3（键位统一）范围，本次不动。

### 2.3 `mart.platform_day_kpi` / `mart.platform_week_kpi`

| period | platform_code | gmv | order_count |
| --- | --- | --- | --- |
| 2026-06-06 | shopee | 11982.88 | 144 |
| 2026-06-06 | tiktok | 5490.27 | 89 |
| 2026-06-07 | shopee | 8031.33 | 95 |
| 2026-06-07 | tiktok | 1910.98 | 37 |
| 2026-06-18 | shopee | 4846.53 | 85 |
| 2026-06-18 | tiktok | 320.14 | 6 |
| 2026-08-16 | tiktok | 627.58 | 7 |
| 2026-08-23 | shopee | (空) | (空) |
| 2026-06-08 | shopee | 47109.43 | 662 |
| 2026-06-08 | tiktok | 6604.94 | 152 |
| 2026-06-15 | shopee | 38220.42 | 558 |
| 2026-06-15 | tiktok | 2558.78 | 50 |

---

## 2.4 `mart.b_cost_shop_month` 月度合计（部署前）

采集方式与 §3 ① 完全相同的聚合（直接打在 `semantic.fact_orders_atomic` 上）。
**这次采集本身花了约 10 分钟** —— DB 默认超时 120s 时它根本跑不完，
B 成本页在今天的生产上必然 504。

| period_month | shop_rows | gmv | purchase_amount | wh_fee | platform_itemized |
| --- | --- | --- | --- | --- | --- |
| 2026-01-01 | 17 | 278777.38 | 98317.11 | 29660.74 | 38323.92 |
| 2026-02-01 | 17 | 177683.55 | 60326.57 | 18401.27 | 29045.40 |
| 2026-03-01 | 17 | 223586.03 | 79411.52 | 21441.03 | 43376.45 |
| 2026-04-01 | 17 | 234470.41 | 82810.27 | 26424.66 | 37116.23 |
| 2026-05-01 | 18 | 298669.02 | 119927.98 | 56550.07 | 98610.03 |
| 2026-06-01 | 17 | 545532.62 | 224620.69 | 63548.24 | 169516.79 |
| 2026-07-01 | 16 | 210454.54 | 85918.92 | 21596.22 | 70613.86 |
| 2026-08-01 | 16 | 171655.10 | 68696.38 | 18434.13 | 50587.21 |
| 2026-09-01 | 17 | 180060.88 | 72361.48 | 23854.58 | 57923.25 |
| 2026-10-01 | 16 | 329163.49 | 138438.99 | 24778.94 | 91288.70 |

全量合计（查询输出，非手算）：**168 行** / gmv **2,650,053.02** /
purchase_amount **1,030,829.91** / wh_fee **304,689.88** /
platform_itemized **686,401.84**。

> 核对口径：部署后跑 §3 ①，**逐行**与上表比对（10 行 × 5 个数值列），
> 并核对上面这行合计。以查询输出为准，不要手算。

---

## 3. 部署后必做核对（同一组 SQL，逐行对比）

```sql
-- ① B 成本月度合计：必须与部署前**完全一致**（不是"接近"）
WITH monthly_base AS (
    SELECT date_trunc('month', metric_date)::date AS period_month,
           platform_code, shop_id, currency_code,
           SUM(paid_amount) AS gmv, SUM(purchase_amount) AS purchase_amount,
           SUM(warehouse_operation_fee) AS wh_fee,
           SUM(platform_total_cost_itemized) AS platform_itemized
    FROM semantic.fact_orders_atomic
    GROUP BY 1, 2, 3, 4
)
SELECT period_month, count(*), round(sum(gmv), 2), round(sum(purchase_amount), 2),
       round(sum(wh_fee), 2), round(sum(platform_itemized), 2)
FROM monthly_base GROUP BY period_month ORDER BY period_month;

-- ② 日/周 KPI：与 §2.1 / §2.2 / §2.3 逐行一致
SELECT period_date, platform_code, shop_id, gmv, order_count, total_items, profit
FROM mart.shop_day_kpi WHERE gmv IS NOT NULL
ORDER BY period_date, platform_code, shop_id;

-- ③ 物化层接线
SELECT n.nspname||'.'||c.relname, c.relkind
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='semantic' AND c.relname LIKE '%_atomic_mv' ORDER BY 1;

-- ④ 仍然读普通视图的两个下游（故意不动，必须还在）
SELECT to_regclass('mart.hr_shop_monthly_profit'), to_regclass('mart.inventory_backlog_base_mv');
```

### 通过标准

1. ① 的每月合计与部署前**逐行完全相同**；不一致 ⇒ 停，回滚。
2. ② 与 §2 逐行完全相同。
3. ③ 能查到 `semantic.fact_orders_atomic_mv` 与 `semantic.fact_analytics_atomic_mv`。
4. ④ 两个对象都还在（`inventory_backlog_base_mv` 是 0 行的历史遗留物，但不应被 CASCADE 误删）。
5. `operational-metrics` 与 `bootstrap` P95 < 3s（部署前各约 23s）。
6. B 成本三个接口 P95 < 5s。
7. nginx 错误日志 24h 内新增 5xx = 0。

---

## 4. 部署前已确认的事实（供部署后复核用）

| 事实 | 数值 | 采集方式 |
| --- | --- | --- |
| `core.shop_accounts` | 52 行（enabled 19） | 直查 |
| `core.shop_account_aliases` | 21 行 | 直查 |
| `core.dim_shops` | **0 行** | 直查（看板的显示名 JOIN 永远落空 → 显示名只能靠 `core.shop_accounts` 兜底，属 P2/P6 范围） |
| `core.dim_platforms` | 5 行 | 直查 |
| `core.platform_accounts` | 11 行（旧模型残留） | 直查 |
| 订单事实行数 | 38,607（月 36,624 / 周 1,506 / 日 477） | 直查 |
| 去重窗口是否真的合并过 | **没有**（38,607 组 = 38,607 行） | 直查 |
| 订单事实 GMV 构成 | 月 93.79% / 周 3.86% / 日 2.35% | 直查 |
| 流量事实行数 | 4,431（weekly 与 miaoshou 全 0） | 直查 |
| `semantic.fact_orders_atomic` 上游依赖 | 9 张 B 类表 + `core.shop_accounts` + `semantic.shop_identity_resolution_candidates` | `pg_depend` |
| `semantic.fact_orders_atomic` 是否含 volatile 函数 | **否** | `pg_get_viewdef` 扫描 |
| `mart.b_cost_shop_month` 聚合耗时 | **> 120s（默认超时被打断）** | 直查 |

> 最后一行是本次修复最直接的证据：**B 成本页今天在生产上必然 504**，
> 因为它的聚合根本跑不完 DB 的 60s 超时。
