# B类成本分析页面设计

## 1. 背景

当前系统里：

- A 类成本有明确前端入口：[费用管理](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/finance/ExpenseManagement.vue)
- 总成本有年度总览入口：[年度数据总结](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/AnnualSummary.vue)
- B 类成本没有独立、标准、可复用的前端查看页面

这会导致“每个店铺的商品货款成本、仓库操作费、平台费用”只能停留在设计定义或局部 SQL / 服务代码里，不能在前端形成稳定工作台。

本设计的目标，是新增一个只读的 B 类成本分析页面，优先解决“看得见、能核对、能下钻”的问题，而不是先做导出或手工维护。

## 2. 设计目标

### 2.1 第一目标

- 提供独立的 B 类成本前端页面
- 默认展示“店铺月汇总”
- 支持按平台、店铺、月份筛选
- 支持从店铺汇总下钻到订单明细
- 明确展示 B 类成本构成，而不是只给一个总数

### 2.2 非目标

第一期不做以下内容：

- 不做手工录入或修改
- 不做导出 Excel / CSV
- 不做 A 类和 B 类混合维护
- 不做复杂图表大屏
- 不做外部财务软件联动

## 3. 方案比较

### 方案 A：在费用管理页面增加 B 类 Tab

优点：

- 用户入口统一
- 复用现有财务页语义

缺点：

- A 类是人工录入管理，B 类是系统自动分析，职责不同
- 同一页面同时承载“录入”和“分析”，后续会快速变重
- 容易让用户误以为 B 类也可以手工维护

### 方案 B：在年度数据总结页增加 B 类区块

优点：

- 能直接和总成本、GMV 放在一起看
- 对管理层总览友好

缺点：

- 年度数据总结页本身已经是总览页，不适合承担排查工作台
- 不利于订单级下钻
- 会继续放大“总览页越来越重”的问题

### 方案 C：新增独立页面“B类成本分析”

优点：

- 职责清晰，和 A 类费用管理天然分离
- 可以先看店铺月汇总，再看订单明细
- 后续导出、异常核对、成本专题都可以在同一页面演进

缺点：

- 需要新增路由、接口和页面

### 推荐

采用方案 C。

原因：

- 最符合 A 类与 B 类本质不同的业务模型
- 最容易承接“商品货款成本”这个核心诉求
- 最符合仓库当前 Dashboard 的模块化演进方向

## 4. 页面定位

### 4.1 页面名称

- 中文：`B类成本分析`
- 英文内部命名：`BCostAnalysis`

### 4.2 路由与权限

- 前端路由：`/b-cost-analysis`
- 页面标题：`B类成本分析`
- 建议图标：`DataAnalysis`
- 访问角色：`admin`、`manager`、`finance`
- 建议权限码：`b-cost-analysis`

角色范围与 [费用管理](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/router/index.js) 当前角色集合保持一致。

### 4.3 页面归属

该页面应视为财务分析页，不归属到 A 类录入页。

建议放在财务扩展路由区域，和：

- `/expense-management`
- `/finance-reports`

同级存在。

## 5. 第一阶段交互设计

### 5.1 页面默认形态

默认打开后展示“店铺月汇总”。

原因：

- 用户第一眼最关心的是哪个店铺 B 类成本高
- 店铺月汇总更适合管理和对比
- 订单明细更适合排查，不适合作为默认入口

### 5.2 顶部筛选区

第一期筛选项：

- 月份：必选，格式 `YYYY-MM`
- 平台：可选，支持单选
- 店铺：可选，支持单选或搜索选择

第一期只做月度分析，不在页面上支持年度切换。

原因：

- B 类成本天然接近订单和月度经营节奏
- 年度口径可以后续复用月度聚合结果补上

### 5.3 KPI 卡片

顶部展示 6 张卡片：

- `B类总成本`
- `采购金额`
- `仓库操作费`
- `平台费用合计`
- `GMV`
- `B类成本占 GMV 比`

其中：

- `B类总成本 = 采购金额 + 仓库操作费 + 平台费用合计`
- `GMV = paid_amount 汇总`
- `B类成本占 GMV 比 = B类总成本 / GMV`

### 5.4 主表：店铺月汇总

主表按“平台 + 店铺 + 月份”聚合，建议字段：

- 平台
- 店铺
- 月份
- GMV
- 采购金额
- 仓库操作费
- 平台费用合计
- B类总成本
- B类成本占 GMV 比
- 毛利率参考值
- 净利率参考值
- 操作列：`查看订单明细`

字段说明：

- `毛利率参考值 = (GMV - 采购金额) / GMV`
- `净利率参考值 = (GMV - B类总成本) / GMV`

这里明确使用“参考值”命名，避免与年度总览页里尚未完全统一的全域利润口径混淆。

### 5.5 下钻：订单明细抽屉

点击某店铺行后，打开订单明细抽屉或侧边栏，而不是直接跳新页面。

原因：

- 能保留筛选上下文
- 操作成本更低
- 第一期开发表面积更可控

订单明细字段建议：

- 订单号
- 下单日期
- 平台
- 店铺
- 订单原始金额
- 实付金额
- 采购金额
- 仓库操作费
- 运费
- 推广费
- 平台佣金
- 平台扣费
- 平台代金券
- 平台服务费
- 平台总费用_分项合计
- B类总成本

其中：

- `订单级 B类总成本 = 采购金额 + 仓库操作费 + 平台总费用_分项合计`

第一期不强制在页面展示 `platform_total_cost_derived`，但接口应预留返回，便于后续做字段校验。

## 6. 数据架构设计

### 6.1 设计原则

新页面应遵循当前仓库 Dashboard 标准路径：

`b_class raw -> semantic -> mart -> api -> backend router -> frontend`

不建议把新页面直接建立在 [annual_cost_aggregate.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/annual_cost_aggregate.py) 这种旁路服务之上。

原因：

- `annual_cost_aggregate.py` 当前主要服务于 A+B 汇总口径核对
- 它没有承担标准页面模块的稳定职责
- 它不适合直接扩展成订单下钻页面
- 新页面如果继续旁路直查，后续仍然要返工回标准链路

### 6.2 semantic 层要求

当前 B 类成本字段并未在 PostgreSQL 主链完整贯通。

因此第一期实现前，需要先把以下字段稳定进入订单语义层：

- `purchase_amount`
- `order_original_amount`
- `warehouse_operation_fee`
- `shipping_fee`
- `promotion_fee`
- `platform_commission`
- `platform_deduction_fee`
- `platform_voucher`
- `platform_service_fee`
- `platform_total_cost_itemized`
- `platform_total_cost_derived`

建议落点：

- 扩展 `semantic.fact_orders_atomic` 对应 SQL

### 6.3 mart 层建议

新增一个店铺月聚合 mart，建议命名：

- `mart.b_cost_shop_month`

建议字段：

- `period_month`
- `platform_code`
- `shop_id`
- `shop_key`
- `gmv`
- `purchase_amount`
- `warehouse_operation_fee`
- `shipping_fee`
- `promotion_fee`
- `platform_commission`
- `platform_deduction_fee`
- `platform_voucher`
- `platform_service_fee`
- `platform_total_cost_itemized`
- `total_cost_b`
- `gross_margin_ref`
- `net_margin_ref`

聚合公式：

- `total_cost_b = purchase_amount + warehouse_operation_fee + platform_total_cost_itemized`

### 6.4 api 层建议

建议新增 3 个 API 模块视图：

- `api.b_cost_analysis_overview_module`
- `api.b_cost_analysis_shop_month_module`
- `api.b_cost_analysis_order_detail_module`

职责分别为：

- overview：顶部 KPI
- shop_month：店铺月汇总表
- order_detail：订单明细下钻

### 6.5 backend 路由建议

在 [dashboard_api_postgresql.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/dashboard_api_postgresql.py) 新增独立路由，而不是复用 annual summary 接口。

建议接口：

- `GET /api/dashboard/b-cost-analysis/overview`
- `GET /api/dashboard/b-cost-analysis/shop-month`
- `GET /api/dashboard/b-cost-analysis/order-detail`

查询参数：

- `period_month`
- `platform`
- `shop_id`
- `page`
- `page_size`

说明：

- 第一阶段平台和店铺筛选都按单值处理
- 订单明细接口需要分页

### 6.6 前端 API 建议

在 [dashboard.js](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/api/dashboard.js) 中新增：

- `queryBCostAnalysisOverview`
- `queryBCostAnalysisShopMonth`
- `queryBCostAnalysisOrderDetail`

## 7. 前端页面结构

### 7.1 页面骨架

页面建议结构：

1. 页面标题区
2. 筛选栏
3. KPI 卡片区
4. 店铺月汇总表
5. 订单明细抽屉

### 7.2 视觉与交互原则

- 沿用现有管理后台 Element Plus 风格，不另起一套视觉系统
- 页面风格与 [ExpenseManagement.vue](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/finance/ExpenseManagement.vue) 保持同类财务页气质
- 重点强调“成本构成可读性”，而不是图表装饰
- 数字格式统一保留两位小数，比例显示为百分比

### 7.3 空状态与错误状态

空状态：

- 无数据时保留筛选区和 KPI 卡片
- 表格区域显示明确文案：`当前筛选条件下暂无 B 类成本数据`

错误状态：

- 页面顶部或表格区显示统一错误提示
- 支持重新加载
- 不把接口失败误显示为 0

## 8. 与现有页面的边界

### 8.1 与费用管理页面的边界

[ExpenseManagement.vue](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/finance/ExpenseManagement.vue) 继续负责：

- A 类成本录入
- A 类成本维护
- A 类成本汇总

不新增 B 类录入能力。

### 8.2 与年度数据总结页面的边界

[AnnualSummary.vue](/F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/AnnualSummary.vue) 继续负责：

- 年度或月度总览
- 总成本和比率概览

不承载订单级 B 类成本下钻。

### 8.3 与旁路成本聚合服务的边界

[annual_cost_aggregate.py](/F:/Vscode/python_programme/AI_code/xihong_erp/backend/services/annual_cost_aggregate.py) 可继续作为：

- A+B 总成本核对参考
- 过渡期校验工具

不作为新 B 类页面的正式数据服务层。

## 9. 风险与注意点

### 9.1 字段口径尚未完全主链化

当前 B 类字段在仓库里已有设计与部分实现，但 PostgreSQL 主链未完全贯通。

因此新页面的前提，不是先画页面，而是先把主链字段打通。

### 9.2 店铺键一致性

B 类页按店铺展示时，必须统一店铺口径。

建议继续使用：

- `shop_key = platform_code|shop_id`

这和成本域既有设计保持一致，也能避免跨平台同 `shop_id` 混淆。

### 9.3 毛利/净利命名风险

由于年度页、旁路服务、订单模型里利润口径尚存在历史差异，B 类页面中涉及利润率的字段建议统一标注为：

- `毛利率参考值`
- `净利率参考值`

避免误解为已经和全系统财务口径完全统一。

## 10. 第一阶段实施范围

第一阶段明确包含：

- 新增独立前端页面 `B类成本分析`
- 默认店铺月汇总
- 支持订单明细下钻
- 新增 B 类专用 dashboard 接口
- 打通 B 类字段的 PostgreSQL 标准链路

第一阶段明确不包含：

- 导出
- 图表专题
- 手工修正
- 财务软件接口
- A/B 联合大盘页

## 11. 测试与验收

### 11.1 后端

需要新增测试：

- API 参数校验测试
- 店铺月汇总聚合正确性测试
- 订单明细分页测试
- 空数据与异常数据测试

### 11.2 前端

需要新增测试：

- 默认加载店铺月汇总
- 筛选触发重新查询
- 点击店铺行打开订单明细抽屉
- 空状态显示
- 接口失败提示显示

### 11.3 验收标准

满足以下条件即视为第一阶段完成：

- 用户能从前端页面稳定查看各店铺月度 B 类成本
- 用户能下钻到订单明细核对成本构成
- 页面中 B 类总成本、采购金额、仓库操作费、平台费用合计口径一致
- 页面不依赖旁路服务直查 raw 表

## 12. 后续演进

第二阶段可考虑：

- 导出当前筛选结果
- 年度视图
- 图表趋势
- 异常成本标记
- 与 A 类成本并排对照视图

第三阶段可考虑：

- 与外部财务系统对账联动
- 多页签成本工作台

## 13. 结论

本设计建议新增独立的 `B类成本分析` 页面，第一期以“店铺月汇总 + 订单明细下钻”为核心，不做导出、不做编辑，并按仓库当前 PostgreSQL Dashboard 标准链路落地。

这样可以在最小范围内补齐 B 类成本前端可见性，同时避免把 A 类录入页、年度总览页和 B 类订单成本工作台混在一起。
