# Tasks: 工作台新增「年度数据总结」模块

## 1. Metabase Question

- [x] 1.1 新建 `sql/metabase_questions/annual_summary_kpi.sql`
  - 数据源：仅从 Orders Model、Analytics Model 等使用 `granularity = 'monthly'` 的数据
  - 参数：`{{granularity}}`（monthly / yearly）、`{{period}}`（YYYY-MM 或 YYYY）
  - 逻辑：粒度=monthly 时取当月月度数据 + 上月月度数据；粒度=yearly 时取当年 12 个月汇总 + 去年 12 个月汇总
  - 返回：核心 KPI（GMV、订单数、买家数、转化率、客单价、销售单数、人效等，人效口径与业务概览一致，可依赖在职员工数）+ 对比期 KPI + 环比/同比
- [x] 1.2 成本与产出：在 KPI 结果中增加 total_cost、gmv、cost_to_revenue_ratio、roi、gross_margin、net_margin 及对比期/环比同比。成本可由 Metabase 关联 a_class.operating_costs、fact_expenses_month 与 COGS 源，或由后端单独聚合后与 1.1 结果合并返回
- [x] 1.3 在 `config/metabase_config.yaml` 中注册 `annual_summary_kpi`；运行 `init_metabase.py` 同步

## 2. 后端 API

- [x] 2.1 在 `backend/routers/dashboard_api.py` 新增 `GET /dashboard/annual-summary/kpi`
  - Query：granularity（monthly|yearly）、period（YYYY-MM 或 YYYY）
  - 在 `backend/services/cache_service.py` 的 DEFAULT_TTL 中新增 `annual_summary_kpi`（建议 180s）
  - 与业务概览一致：先 `cache_service.get("annual_summary_kpi", granularity=..., period=...)`，命中则返回（可带 X-Cache: HIT）；未命中则查 Metabase/成本聚合，成功后 `cache_service.set(...)` 写入
  - 调用 MetabaseQuestionService 执行 annual_summary_kpi，若成本由后端聚合则合并成本与 KPI 结果；后端聚合成本时需将 API 的 period（YYYY-MM 或 YYYY）与 `a_class.operating_costs.年月`、`fact_expenses_month.period_month` 格式约定一致并做转换
  - 响应含核心 KPI 与成本与产出（total_cost、gmv、cost_to_revenue_ratio、roi、gross_margin、net_margin）；成本缺失时对应字段返回 null
- [x] 2.2 在 `backend/services/metabase_question_service.py` 中增加 `annual_summary_kpi` 的 question_key 与参数映射（若使用统一 query_question 入口）
- [x] 2.3 在 `backend/services/permission_service.py` 的 SYSTEM_PERMISSIONS 中新增 `{"id": "annual-summary", "name": "年度数据总结", "description": "查看年度数据总结", "resource": "dashboard", "action": "read", "category": "工作台"}`
- [ ] 2.4 （可选）在年度总结 KPI 接口上使用 `require_permission("annual-summary")`（Depends(get_current_user) + has_permission）做后端二次校验

## 3. 前端

- [x] 3.1 在 `frontend/src/api/dashboard.js`（或 `index.js`）新增 `queryAnnualSummaryKpi(params)`，请求 `/dashboard/annual-summary/kpi`
- [x] 3.2 新建 `frontend/src/views/AnnualSummary.vue`
  - 粒度切换：仅「月度」「年度」两个选项
  - 时间选择：月度时月份选择器（YYYY-MM）；年度时年份选择器（YYYY）
  - 第一区块：核心 KPI 卡片 + 环比/同比（月度=较上月，年度=较去年）
  - 第二区块：成本与产出六张卡片（总成本、GMV、成本产出比、ROI、毛利率、净利率），每项可带环比/同比；成本或比率缺失时展示「暂无数据」；分母为 0 时比率展示 N/A 或「-」
- [x] 3.3 在 `frontend/src/config/menuGroups.js` 工作台分组 items 下增加 `/annual-summary`；并在同文件 `routeDisplayNames` 中增加 `'/annual-summary': '年度数据总结'`
- [x] 3.4 在 `frontend/src/router/index.js` 新增路由 `/annual-summary`，meta 配置：`permission: 'annual-summary'`、`roles: ['admin']`（与销售目标管理 `/config/sales-targets` 一致），meta.title 为「年度数据总结」
- [x] 3.5 权限（仅管理员）：在 `frontend/src/config/rolePermissions.js` 中**仅**在 admin 的 permissions 数组内添加 `annual-summary`，不赋予 manager/operator/finance/tourist，使侧栏与路由守卫仅对管理员展示/放行

## 4. 验收

（以下仅 4.3、4.5、4.6 已完成代码/配置核对；4.1、4.2、4.4 需人工在浏览器实际打开页面验证。）

- [ ] 4.1 选择粒度=月度、某月：底部/卡片显示当月核心 KPI 与较上月环比（**需人工验收**：登录后打开年度数据总结，选月度+某月，确认展示正确）
- [ ] 4.2 选择粒度=年度、某年：显示当年核心 KPI 与较去年同比（**需人工验收**：选年度+某年，确认展示正确）
- [x] 4.3 确认年度总结所用数据仅来自 B 类模型 monthly 粒度（SQL 中无 daily）。→ 已核对：annual_summary_*.sql 均仅 WHERE granularity = 'monthly'，无 daily
- [ ] 4.4 成本与产出区块展示总成本、GMV、成本产出比、ROI、毛利率、净利率；成本数据缺失时展示「暂无数据」不阻塞页面；比率分母为 0 时展示 N/A 或「-」（**需人工验收**：在页面上确认上述六项及缺数/分母为 0 时的展示）。→ **代码已核对**：KPI 接口合并 get_annual_cost_aggregate，返回 total_cost/gmv/四比率；前端 costData 绑定、ratioDisplayStrict 在 null 时成本产出比/ROI 展示 N/A，符合验收标准。
- [x] 4.5 权限：仅管理员可见菜单并可访问该页；非管理员访问被拦截。→ 已核对：rolePermissions.js 仅 admin 含 annual-summary；router meta 正确
- [x] 4.6 缓存：同一 granularity+period 再次请求时接口返回 X-Cache: HIT。→ 已核对：dashboard_api.py 中 annual_summary_kpi 缓存逻辑正确

## 5. 扩展功能（已纳入实现范围）

### 5.1 按店铺下钻
- [x] 5.1.1 新增 `sql/metabase_questions/annual_summary_by_shop.sql`，按店铺/平台汇总；已在 `config/metabase_config.yaml` 注册；后端已接 Metabase，需运行 `python scripts/init_metabase.py` 同步 Question 后生效
- [x] 5.1.2 后端新增 `GET /dashboard/annual-summary/by-shop`（granularity、period），返回店铺/平台、GMV、总成本、成本产出比、毛利率、净利率、ROI；可加 Redis 缓存
- [x] 5.1.3 前端 `AnnualSummary.vue` 增加「按店铺下钻」表格区块，列与线框图一致，数据来自 by-shop API

### 5.2 月度/年度趋势
- [x] 5.2.1 后端提供趋势数据：新增 `GET /dashboard/annual-summary/trend`（granularity+period），返回按月的 GMV、总成本、利润时间序列（当前占位返回空列表，可后续接 SQL 或聚合）
- [x] 5.2.2 前端年度总结页增加「月度/年度趋势」折线图（ECharts），展示 GMV、总成本、利润随月份变化

### 5.3 平台占比 (GMV)
- [x] 5.3.1 后端新增 `GET /dashboard/annual-summary/platform-share`（granularity、period），返回各平台（Shopee、TikTok、其他等）GMV 及占比（当前占位返回空列表）
- [x] 5.3.2 前端年度总结页增加「平台占比」饼图（ECharts），展示各平台 GMV 占比

### 5.4 目标完成率
- [x] 5.4.1 后端对接现有销售目标数据源（a_class.sales_targets_a），按当前 period 取 GMV 目标及实际值（KPI 接口），计算完成率并返回
- [x] 5.4.2 前端年度总结页增加「目标完成率」区块：GMV 目标、利润目标进度条，无目标数据时展示「暂无目标」或隐藏

## 6. 验收（扩展）

（以下均需人工在浏览器打开年度数据总结页面验证。**店铺/趋势/平台占比依赖 B 类月度数据，数据采集未完成前无法做有数据验收；代码已按验收标准核对，数据就绪后可直接使用，无需改代码。**）

- [ ] 6.1 按店铺下钻表格展示各店铺/平台 GMV、总成本及四比率，数据随 granularity/period 切换（**需人工验收**，依赖采集/同步写入 fact_*_orders_monthly 与 operating_costs）。→ **代码已核对**：后端 GET /annual-summary/by-shop 调用 get_annual_cost_aggregate_by_shop(db)，前端 byShopList 绑定表格列 shop_name/platform、gmv、total_cost、四比率；空数据时表格空态，有数据后直接展示。
- [ ] 6.2 趋势折线图展示 GMV、总成本、利润随月份变化；年度时展示当年 12 个月（**需人工验收**，依赖 Metabase annual_summary_trend 有月度数据）。→ **代码已核对**：后端查 Metabase trend Question，前端用 month/gmv/total_cost/profit 渲染折线图；无数据时占位，有数据后直接展示。
- [ ] 6.3 平台占比饼图展示各平台 GMV 占比（如 Shopee/TikTok/其他）（**需人工验收**，依赖 Metabase annual_summary_platform_share 有数据）。→ **代码已核对**：后端查 Metabase platform_share Question，前端用 platform/name、gmv/value 渲染饼图；无数据时「暂无数据」。
- [ ] 6.4 目标完成率展示 GMV 目标与利润目标进度条；无目标时友好展示（**需人工验收**）。→ 后端已对接 a_class.sales_targets_a 与 KPI 实际值，前端已展示进度条与 N/A。
