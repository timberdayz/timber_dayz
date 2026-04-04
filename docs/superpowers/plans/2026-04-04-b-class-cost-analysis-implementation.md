# B类成本分析页面 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个只读的 B 类成本分析页面，让用户能够按月份、平台、店铺查看 B 类成本汇总，并下钻到订单明细核对成本构成。

**Architecture:** 先把 B 类成本字段补齐到 PostgreSQL Dashboard 标准链路 `semantic -> mart -> api -> backend -> frontend`，再新增专用后端接口与前端页面。页面第一期只做店铺月汇总与订单明细抽屉，不做导出、不做编辑、不复用旁路 `annual_cost_aggregate.py` 作为正式数据源。

**Tech Stack:** PostgreSQL views, FastAPI, SQLAlchemy async, Vue 3, Element Plus, Pinia, pytest, Node test runner

---

## File Structure

**SQL / data pipeline**

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\semantic\orders_atomic.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\b_cost_shop_month.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\b_cost_analysis_overview_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\b_cost_analysis_shop_month_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\b_cost_analysis_order_detail_module.sql`

**Backend**

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`

**Frontend**

- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\api\dashboard.js`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\router\index.js`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\finance\BCostAnalysis.vue`

**Tests**

- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_b_cost_analysis_semantic_sql.py`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_b_cost_analysis_api_modules_sql.py`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_postgresql_dashboard_b_cost_routes.py`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\scripts\bCostAnalysisUi.test.mjs`

## Task 1: 把 B 类成本字段贯通到语义层

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\semantic\orders_atomic.sql`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_b_cost_analysis_semantic_sql.py`

- [ ] **Step 1: 先写失败的语义层测试**

覆盖这些断言：

- `semantic.fact_orders_atomic` 必须暴露 `purchase_amount`
- 必须暴露 `order_original_amount`
- 必须暴露 `warehouse_operation_fee`
- 必须暴露六项平台费用字段
- 必须暴露 `platform_total_cost_itemized`
- 必须暴露 `platform_total_cost_derived`

示例断言：

```python
def test_orders_atomic_exposes_b_cost_columns(sql_text: str):
    assert "purchase_amount" in sql_text
    assert "platform_total_cost_itemized" in sql_text
```

- [ ] **Step 2: 运行测试确认当前失败**

Run: `pytest backend/tests/data_pipeline/test_b_cost_analysis_semantic_sql.py -q`

Expected: FAIL，因为当前 `orders_atomic.sql` 只输出了 `platform_total_cost_itemized = 0`，没有完整贯通 B 类字段。

- [ ] **Step 3: 在 `orders_atomic.sql` 中补齐 B 类成本原始映射与清洗**

Required changes:

- 在 `mapped` / `cleaned` 段补充原始字段提取
- 对金额字段使用和现有订单金额一致的清洗方式
- 保持 async / PostgreSQL 主链风格，不新增 Python 旁路处理
- 不删除现有 `sales_amount` / `paid_amount` / `profit` 等字段

必须补齐的字段：

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

- [ ] **Step 4: 定义派生公式**

Required formulas:

- `platform_total_cost_itemized = shipping_fee + promotion_fee + platform_commission + platform_deduction_fee + platform_voucher + platform_service_fee`
- `platform_total_cost_derived = order_original_amount - purchase_amount - profit - warehouse_operation_fee`

Implementation rule:

- 保持空值可识别，避免把“缺字段”误伪装成真实 0
- 仅在最终主链确需聚合时决定是否 `COALESCE`

- [ ] **Step 5: 重新运行语义层测试**

Run: `pytest backend/tests/data_pipeline/test_b_cost_analysis_semantic_sql.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/data_pipeline/test_b_cost_analysis_semantic_sql.py sql/semantic/orders_atomic.sql
git commit -m "feat: expose b cost fields in orders semantic view"
```

## Task 2: 新增 B 类成本 mart 与 API 模块

**Files:**
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\mart\b_cost_shop_month.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\b_cost_analysis_overview_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\b_cost_analysis_shop_month_module.sql`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\sql\api_modules\b_cost_analysis_order_detail_module.sql`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\data_pipeline\test_b_cost_analysis_api_modules_sql.py`

- [ ] **Step 1: 先写失败的 SQL 模块测试**

覆盖这些断言：

- `mart.b_cost_shop_month` 使用 `semantic.fact_orders_atomic`
- mart 聚合输出 `total_cost_b`
- overview module 输出 KPI 所需字段
- shop-month module 输出店铺月汇总字段
- order-detail module 输出订单级字段并支持分页参数契约

示例断言：

```python
def test_b_cost_shop_month_uses_semantic_orders(sql_text: str):
    assert "semantic.fact_orders_atomic" in sql_text
    assert "total_cost_b" in sql_text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/data_pipeline/test_b_cost_analysis_api_modules_sql.py -q`

Expected: FAIL，因为这些 SQL 资产当前还不存在。

- [ ] **Step 3: 创建 `b_cost_shop_month.sql`**

Required aggregation:

- group by `period_month`, `platform_code`, `shop_id`, `shop_key`
- 聚合 `gmv`
- 聚合 `purchase_amount`
- 聚合 `warehouse_operation_fee`
- 聚合六项平台费用
- 聚合 `platform_total_cost_itemized`
- 计算 `total_cost_b`
- 计算 `gross_margin_ref`
- 计算 `net_margin_ref`

Formula rules:

- `shop_key = platform_code || '|' || shop_id`
- `total_cost_b = purchase_amount + warehouse_operation_fee + platform_total_cost_itemized`
- `gross_margin_ref = (gmv - purchase_amount) / gmv`
- `net_margin_ref = (gmv - total_cost_b) / gmv`

- [ ] **Step 4: 创建 overview / shop-month / order-detail 三个 API module**

Required responsibilities:

- `b_cost_analysis_overview_module.sql`
  - 输出页面顶部 KPI
- `b_cost_analysis_shop_month_module.sql`
  - 输出店铺月汇总列表
  - 支持按 `period_month`, `platform`, `shop_id` 过滤
- `b_cost_analysis_order_detail_module.sql`
  - 输出订单明细
  - 支持按 `period_month`, `platform`, `shop_id` 过滤

Design rule:

- 不从 `annual_cost_aggregate.py` 复制逻辑
- 一律复用 `semantic` / `mart` 资产

- [ ] **Step 5: 重新运行 SQL 模块测试**

Run: `pytest backend/tests/data_pipeline/test_b_cost_analysis_api_modules_sql.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/data_pipeline/test_b_cost_analysis_api_modules_sql.py sql/mart/b_cost_shop_month.sql sql/api_modules/b_cost_analysis_overview_module.sql sql/api_modules/b_cost_analysis_shop_month_module.sql sql/api_modules/b_cost_analysis_order_detail_module.sql
git commit -m "feat: add b cost analysis mart and api modules"
```

## Task 3: 新增后端 B 类成本分析接口

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\services\postgresql_dashboard_service.py`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\routers\dashboard_api_postgresql.py`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\backend\tests\test_postgresql_dashboard_b_cost_routes.py`

- [ ] **Step 1: 先写失败的路由/服务测试**

覆盖这些场景：

- `GET /api/dashboard/b-cost-analysis/overview` 返回成功
- `GET /api/dashboard/b-cost-analysis/shop-month` 返回成功
- `GET /api/dashboard/b-cost-analysis/order-detail` 返回成功
- `period_month` 缺失时报参数错误
- `page` / `page_size` 只用于订单明细接口

示例断言：

```python
async def test_b_cost_analysis_routes_registered(client):
    response = await client.get("/api/dashboard/b-cost-analysis/overview", params={"period_month": "2026-04"})
    assert response.status_code == 200
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_postgresql_dashboard_b_cost_routes.py -q`

Expected: FAIL，因为当前路由和 service 方法尚不存在。

- [ ] **Step 3: 在 `postgresql_dashboard_service.py` 中新增 3 个查询方法**

Required methods:

- `get_b_cost_analysis_overview(...)`
- `get_b_cost_analysis_shop_month(...)`
- `get_b_cost_analysis_order_detail(...)`

Implementation rules:

- 复用当前 PostgreSQL dashboard service 的查询风格
- 参数校验和现有 annual/business overview 方法保持一致
- 订单明细返回分页结构，至少包含 `items`, `page`, `page_size`, `total`

- [ ] **Step 4: 在 `dashboard_api_postgresql.py` 中新增 3 个路由**

Required routes:

- `GET /api/dashboard/b-cost-analysis/overview`
- `GET /api/dashboard/b-cost-analysis/shop-month`
- `GET /api/dashboard/b-cost-analysis/order-detail`

Required behavior:

- 保持统一 `success_response`
- 保持统一错误码处理
- 接入当前缓存封装 `_resolve_cached_payload`

- [ ] **Step 5: 重新运行后端路由测试**

Run: `pytest backend/tests/test_postgresql_dashboard_b_cost_routes.py -q`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_postgresql_dashboard_b_cost_routes.py backend/services/postgresql_dashboard_service.py backend/routers/dashboard_api_postgresql.py
git commit -m "feat: add dashboard b cost analysis routes"
```

## Task 4: 新增前端 B 类成本分析页面

**Files:**
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\api\dashboard.js`
- Modify: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\router\index.js`
- Create: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\src\views\finance\BCostAnalysis.vue`
- Test: `F:\Vscode\python_programme\AI_code\xihong_erp\frontend\scripts\bCostAnalysisUi.test.mjs`

- [ ] **Step 1: 先写失败的前端 UI 测试**

覆盖这些场景：

- 页面默认显示“店铺月汇总”
- 页面首次加载会请求 overview 和 shop-month
- 点击某行“查看订单明细”会打开抽屉
- 抽屉打开时请求 order-detail
- 空数据时显示明确空态文案

示例断言：

```javascript
test('loads shop-month summary by default', async () => {
  assert.match(renderedHtml, /店铺月汇总/)
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `node --test frontend/scripts/bCostAnalysisUi.test.mjs`

Expected: FAIL，因为页面和 API 方法当前不存在。

- [ ] **Step 3: 在 `dashboard.js` 中新增前端 API 方法**

Required methods:

- `queryBCostAnalysisOverview`
- `queryBCostAnalysisShopMonth`
- `queryBCostAnalysisOrderDetail`

Contract rule:

- 参数命名与后端路由保持完全一致
- 不引入未被后端消费的冗余参数

- [ ] **Step 4: 在 `router/index.js` 中新增页面路由**

Required route:

- path: `/b-cost-analysis`
- name: `BCostAnalysis`
- component: `../views/finance/BCostAnalysis.vue`
- roles: `['admin', 'manager', 'finance']`
- permission: `b-cost-analysis`

- [ ] **Step 5: 创建 `BCostAnalysis.vue` 最小可用页面**

Page requirements:

- 页面标题区
- 月份 / 平台 / 店铺筛选区
- 6 张 KPI 卡片
- 店铺月汇总表
- 订单明细抽屉
- 空态和错误态

Interaction rules:

- 默认 `period_month` 为当前月
- 默认加载店铺月汇总
- 不做导出按钮
- 不做编辑动作
- 金额统一两位小数
- 比例统一百分比显示

- [ ] **Step 6: 重新运行前端 UI 测试**

Run: `node --test frontend/scripts/bCostAnalysisUi.test.mjs`

Expected: PASS

- [ ] **Step 7: 运行前端构建验证**

Run: `npm --prefix frontend run build`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/dashboard.js frontend/src/router/index.js frontend/src/views/finance/BCostAnalysis.vue frontend/scripts/bCostAnalysisUi.test.mjs
git commit -m "feat: add b cost analysis page"
```

## Task 5: 端到端验证与文档收尾

**Files:**
- Verify only
- Optionally update docs if route/menu naming needs sync

- [ ] **Step 1: 运行数据链与路由测试**

Run:

```bash
pytest backend/tests/data_pipeline/test_b_cost_analysis_semantic_sql.py -q
pytest backend/tests/data_pipeline/test_b_cost_analysis_api_modules_sql.py -q
pytest backend/tests/test_postgresql_dashboard_b_cost_routes.py -q
```

Expected: PASS

- [ ] **Step 2: 运行前端测试与构建**

Run:

```bash
node --test frontend/scripts/bCostAnalysisUi.test.mjs
npm --prefix frontend run build
```

Expected: PASS

- [ ] **Step 3: 做一次人工契约检查**

Verify:

- 页面展示字段与设计文档一致
- 总成本页面未被误改成 B 类页
- A 类费用管理页未被混入 B 类编辑逻辑
- 所有 B 类页面查询均来自 PostgreSQL 主链

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "test: verify b cost analysis flow"
```

## Notes For Execution

- 严格遵守 TDD：先写失败测试，再补实现。
- 不要把新页面建立在 `backend/services/annual_cost_aggregate.py` 上。
- 不要把 B 类页面并入 `ExpenseManagement.vue`。
- 若执行中发现 `orders_atomic.sql` 的字段清洗差异太大，优先保持字段口径一致，再考虑抽取共用金额清洗片段。
- 若前端构建环境再次出现本地 `vite` 依赖异常，需要在最终结论里明确说明，不要宣称构建通过。

## Execution Order

1. Task 1 语义层字段打通
2. Task 2 mart / api SQL 落地
3. Task 3 后端路由与服务
4. Task 4 前端页面
5. Task 5 验证与收尾
