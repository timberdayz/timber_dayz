# Change: 工作台新增「年度数据总结」模块

## Why

1. **业务概览定位**：业务概览面向日/周/月的数据查看与跟进，数据来源以**日度**为主（生产环境每日采集）；历史日度数据不完整（测试阶段仅部分账号、部分时段采集），且 30+ 店铺逐日采集成本高，无法支撑「对去年全年做总结」的需求。
2. **年度审视需求**：需要对去年（或任意年/月）做总结与审视，使用与业务概览一致的核心 KPI（GMV、订单数、转化率等），用于评估店铺年度表现、为来年人力/推广/营销成本配置提供依据。
3. **数据源约束**：年度总结应基于**月度粒度**数据——B 类模型（Orders、Analytics 等）已有 monthly 粒度；不依赖日度，避免历史日度不全与采集量过大的问题。

因此，在业务概览所在的工作台模块下，新增「年度数据总结」子模块：数据来自各 B 类模型但**仅用月度粒度**，粒度切换为**月度/年度**，支持环比（月度较上月、年度较去年），面向全店铺/全账号汇总与按店铺下钻；并增加**成本与产出**区块（总成本、GMV、成本产出比、ROI、毛利率、净利率），支撑年度审视与来年成本配置。

## What Changes

### 1. 数据层（Metabase）

- **新增 Metabase Question**（如 `annual_summary_kpi`）：
  - 数据源：Orders Model、Analytics Model 等，**仅使用 `granularity = 'monthly'`** 的数据。
  - 参数：`granularity`（monthly / yearly）、`period`（YYYY-MM 或 YYYY）；对比期由 SQL 内根据粒度计算（上月或去年）。
  - 返回：核心 KPI（GMV、订单数、买家数、转化率、客单价、销售单数等）+ 对比期 KPI + 环比/同比。
- **成本与产出数据**（可与上合并或单独 Question）：
  - **产出**：GMV 使用 Orders Model 的 `paid_amount`（实付），仅 monthly 粒度汇总。
  - **成本**：总成本 = 运营成本 + 货款成本（COGS）。运营成本来自 `a_class.operating_costs`（租金、工资、水电费、其他成本）按年月汇总 + `fact_expenses_month` 的 `base_amt` 按 `period_month` 汇总；货款成本来自订单/库存成本（若有利润或成本字段则 GMV−利润或 SUM(成本)，否则从库存流水或 fact 表按周期汇总）。若 Metabase 不便跨 schema 关联，可由后端聚合成本后与 KPI 合并返回。
  - 返回字段：`total_cost`、`gmv`、`cost_to_revenue_ratio`（总成本/GMV）、`roi`（(GMV−总成本)/总成本）、`gross_margin`（(GMV−COGS)/GMV）、`net_margin`（(GMV−总成本)/GMV），及对比期与环比/同比。
- **按店铺下钻**：`annual_summary_by_shop`，按店铺/平台汇总月度或年度指标（含 GMV、总成本、成本产出比、毛利率、净利率、ROI），用于「店铺年度表现」表格与来年成本评估下钻。
- **趋势数据**：支持按月份的时间序列（GMV、总成本、利润），用于前端折线图。
- **平台占比**：按平台（如 Shopee、TikTok、其他）汇总 GMV，用于饼图。
- 所有相关 SQL **显式约束** `WHERE granularity = 'monthly'`（订单/分析侧），避免误用日度。

### 2. 后端 API

- 在 `backend/routers/dashboard_api.py` 下新增年度总结接口，与业务概览并列：
  - `GET /dashboard/annual-summary/kpi?granularity=monthly&period=2024-12` 或 `granularity=yearly&period=2024`
  - 响应除核心 KPI 外，包含成本与产出：`total_cost`、`gmv`、`cost_to_revenue_ratio`、`roi`、`gross_margin`、`net_margin` 及环比/同比；若成本数据缺失可返回 null，前端展示「暂无数据」。
  - `GET /dashboard/annual-summary/by-shop?granularity=yearly&period=2024`，返回按店铺的 GMV、总成本及四比率（含毛利率、净利率、ROI）。
  - `GET /dashboard/annual-summary/trend?year=2024`（或按 granularity/period 约定），返回月度时间序列：GMV、总成本、利润，供折线图使用。
  - `GET /dashboard/annual-summary/platform-share?granularity=yearly&period=2024`，返回各平台 GMV 占比，供饼图使用。
  - 目标完成率：依赖现有销售目标数据源（如 `/config/sales-targets` 或等价 API），按周期取 GMV 目标、利润目标与完成值，计算完成率。
- **Redis 缓存**：与业务概览一致，KPI 接口支持 Redis 缓存。先按 `cache_service.get("annual_summary_kpi", granularity=..., period=...)` 取缓存，命中则直接返回（可带 `X-Cache: HIT`）；未命中则调用 Metabase/成本聚合，成功后 `cache_service.set(...)` 写入。缓存 key 需包含 granularity、period，若 Redis 不可用则直查 Metabase，不阻塞接口。
- 将 `granularity`、`period` 映射为 Metabase 参数，调用 `MetabaseQuestionService`；若成本需跨表/跨 schema 汇总，可在后端先查 `operating_costs`、`fact_expenses_month` 及订单/库存成本再与 Metabase KPI 结果合并。
- 在 `config/metabase_config.yaml` 与 `init_metabase.py` 中注册新 Question。

### 3. 前端

- **入口**：在 `frontend/src/config/menuGroups.js` 工作台下增加「年度数据总结」，路由如 `/annual-summary`；`router`、`routeDisplayNames` 同步配置。
- **页面**：新建 `AnnualSummary.vue`（或等价名称）。
  - 粒度切换：**仅「月度」「年度」**（与业务概览的日/周/月区分）。
  - 时间选择：粒度=月度时选月份（YYYY-MM）；粒度=年度时选年份（YYYY）。
  - **第一区块**：核心 KPI 卡片（转化率、客流量、客单价、GMV、订单数、连带率、人效）+ 环比/同比（月度=较上月，年度=较去年）。
  - **第二区块**：成本与产出。六张卡片：总成本、GMV（产出）、成本产出比、ROI、毛利率、净利率；每项可带环比/同比。
  - **第三区块（扩展）**：月度/年度趋势折线图（GMV、总成本、利润随月份）；平台占比饼图（Shopee / TikTok / 其他）；目标完成率（GMV 目标、利润目标进度条，依赖目标数据源）。
  - **第四区块（扩展）**：按店铺/平台下钻表格，列：店铺/平台、GMV、总成本、成本产出比、毛利率、净利率、ROI。
- **权限**：与销售目标管理一致，**仅管理员可查看**。在 `backend/services/permission_service.py` 的 SYSTEM_PERMISSIONS 中新增权限 id「annual-summary」（name/description 为年度数据总结，category 为工作台）；在 `frontend/src/config/rolePermissions.js` 中**仅将 `annual-summary` 赋予 admin**，不赋予 manager/operator/finance/tourist；在 `frontend/src/router/index.js` 中年度总结路由的 `meta.permission` 为 `annual-summary`、`meta.roles` 为 `['admin']`（与 `/config/sales-targets` 一致）。侧栏根据路由 meta.permission 过滤，故仅管理员可见该菜单与页面。后端 API 可选使用 `require_permission("annual-summary")` 做二次校验。

### 4. 行为约定

- **环比**：选择「月度」时对比上月；选择「年度」时对比去年。
- **统计范围**：默认全店铺/全账号汇总；可选按平台、店铺筛选或下钻。
- **指标口径**：与业务概览核心 KPI 一致（如 GMV 用 paid_amount、订单数去重方式），便于对外解释。
- **成本与产出口径**：产出=GMV（实付 paid_amount）。总成本=运营成本+货款成本；运营成本= a_class.operating_costs 四列之和（按年月）+ fact_expenses_month.base_amt（按 period_month）；货款成本=订单/库存成本（COGS）。成本产出比=总成本/GMV；ROI=(GMV−总成本)/总成本；毛利率=(GMV−COGS)/GMV；净利率=(GMV−总成本)/GMV。运营成本口径需与财务/业务约定，避免 operating_costs 与 fact_expenses_month 中重叠科目重复计入。
- **比率边界**：当分母为 0（如总成本=0 或 GMV=0）时，对应比率展示为 N/A 或「-」，不展示数值。

## Impact

### 受影响的规格

- **dashboard**：ADDED - 年度数据总结能力（月度/年度粒度、仅用月度数据源、环比/同比；核心 KPI + 成本与产出六卡片；扩展：趋势折线图、平台占比饼图、目标完成率、按店铺下钻表格）

### 受影响的代码

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| SQL | `sql/metabase_questions/annual_summary_kpi.sql` | 新增：仅 monthly 粒度，参数 granularity/period，核心 KPI + 成本与产出及环比/同比 |
| SQL | `sql/metabase_questions/annual_summary_by_shop.sql`、`annual_summary_trend.sql`、`annual_summary_platform_share.sql`（或后端聚合） | 按店铺汇总、月度趋势序列、平台 GMV 占比；仅 monthly 粒度 |
| 数据 | `a_class.operating_costs`、`fact_expenses_month` | 成本汇总数据源；若 Metabase 不跨 schema 则后端聚合 |
| 配置 | `config/metabase_config.yaml`、`init_metabase.py` | 注册 annual_summary_* Question 并同步 |
| 后端 | `backend/routers/dashboard_api.py` | 新增 /dashboard/annual-summary/kpi、by-shop、trend、platform-share；目标完成率复用或对接销售目标数据源；Redis 缓存（key 含 granularity/period） |
| 后端 | `backend/services/cache_service.py` | DEFAULT_TTL 中新增 `annual_summary_kpi`（建议 180s），与 dashboard_kpi 一致 |
| 后端 | `backend/services/metabase_question_service.py` | 新 Question 键名与参数映射；可选成本聚合服务 |
| 后端 | `backend/services/permission_service.py` | SYSTEM_PERMISSIONS 新增 annual-summary（工作台） |
| 后端 | `backend/utils/auth.py`（可选） | 年度总结接口使用 require_permission("annual-summary") 做二次校验 |
| 前端 | `frontend/src/views/AnnualSummary.vue` | 新增页面：核心 KPI + 成本与产出（六张卡片）+ 趋势折线图 + 平台占比饼图 + 目标完成率进度条 + 按店铺下钻表格 |
| 前端 | `frontend/src/api/dashboard.js`、`index.js` | 年度总结 API 封装 |
| 前端 | `frontend/src/config/menuGroups.js`、`router/index.js` | 工作台下菜单与路由；路由 meta.permission='annual-summary', meta.roles=['admin'] |
| 前端 | `frontend/src/config/rolePermissions.js` | 仅 admin 的 permissions 数组包含 `annual-summary`（与 config:sales-targets 仅管理员一致） |

### 依赖关系

- **无前置依赖**；依赖现有 B 类模型（Orders、Analytics 等）的 **monthly** 粒度数据已存在或由同步写入。
- 成本与产出依赖：运营成本来自 `a_class.operating_costs`、`fact_expenses_month`；货款成本（COGS）依赖订单/库存事实或利润反推。若某周期成本数据缺失，对应比率可返回 null 或展示「暂无数据」。
- 若历史月度数据缺失，该月/年汇总会偏小或为空，需在数据同步侧保证月度汇总可用。

## 非目标（Non-Goals）

- 不修改业务概览现有日/周/月逻辑与数据源。
- 不在本提案内实现「由日度聚合生成月度」的 ETL；假定使用已有 monthly 粒度数据。
- 目标完成率依赖现有销售目标配置与数据源，不在本提案内新建目标配置模块。
- 本期结论/备注不纳入实现范围：侧重数据展示，不在系统中持久化店铺文字评价。
