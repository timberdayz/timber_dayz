# 业务概览页面深化设计计划（修复版）

## ⚠️ 重要发现：双维护风险和漏洞

### 1. 路由冲突风险（必须修复）

**问题**：
- `backend/routers/dashboard.py` 和 `backend/routers/dashboard_api.py` 都注册在 `/api/dashboard` 前缀下
- 这会导致路由冲突，后注册的路由会覆盖先注册的路由

**解决方案**：
- **步骤0（必须优先执行）**：合并两个文件，统一使用 `dashboard_api.py`
- 检查 `dashboard.py` 的功能，迁移到 `dashboard_api.py`
- 删除 `dashboard.py` 文件
- 更新 `backend/main.py` 中的路由注册

### 2. 前端组件双维护风险

**问题**：
- `BusinessOverview.vue` 已存在，但功能简单
- 如果创建 `BusinessOverviewV2.vue` 会导致双维护

**解决方案**：
- ✅ 增强现有 `BusinessOverview.vue`，不创建新文件
- ✅ 复杂组件可以拆分为独立组件（放在 `frontend/src/components/business/`）
- ✅ 简单组件内联在 `BusinessOverview.vue` 中

### 3. 物化视图重复风险

**问题**：
- 计划中建议新增 `mv_business_overview_*` 视图
- 但已有 `mv_daily_sales`, `mv_weekly_sales`, `mv_monthly_sales`

**解决方案**：
- ✅ 优先复用现有物化视图
- ✅ 如缺少字段，考虑增强现有视图而非创建新视图
- ✅ 检查 `mv_inventory_by_sku` 是否支持滞销查询

---

## 一、页面布局设计（参考门店管理表格模板）

### 1.1 顶部区域：公司整体经营情况

**位置**：页面最上方，横向布局
**内容**：5个核心KPI指标卡片
- **转化率**：订单数/访客数（%）
- **客流量**：总访客数（unique_visitors）
- **客单价**：总销售额/订单数（元）
- **连带率**：订单项总数/订单数（件/单）
- **人效**：销售额/员工数（元/人，如无员工数据则暂不显示）

**设计要点**：
- 每个指标显示：当前值、环比变化（%）、趋势箭头
- 使用颜色标识：绿色（增长）、红色（下降）、紫色（关键指标）
- 参考门店模板的"运营指标"表格样式

### 1.2 中间左侧区域：业务分类汇总（可选）

**说明**：门店模板中有"政策图片"表格，在ERP系统中替换为"业务分类汇总"
**内容**：
- 按平台/店铺/产品类别汇总销售额、达成率等
- 展示业务分类的运营情况

### 1.3 中间右侧区域：日/周/月度数据对比和店铺赛马

**位置**：中间右侧，占据主要空间
**内容**：

#### 1.3.1 数据粒度切换器
- 按钮组：日度 / 周度 / 月度（高亮当前选中）
- 日期选择器：选择具体日期/周/月

#### 1.3.2 核心指标对比表格
**指标列**：
- 销售额（万元）
- 销售数量（件）
- 利润（万元）
- 客流量（人）
- 转化率（%）
- 连带率（件/单）
- 客单价（元）

**对比维度**：
- 今日/昨日/平均值
- 环比变化（%）
- 趋势箭头（↑↓）

#### 1.3.3 店铺赛马（AB分组对比）
**设计**：
- 表格形式：店铺分组（A组/B组，或自定义分组）
- 指标：销售额目标、销售额达成、达成率、排名
- 颜色标识：达成率用绿色/蓝色/红色标识
- 排名显示：第1名/第2名等

### 1.4 底部区域：库存滞销情况

**位置**：页面底部
**内容**：

#### 1.4.1 总滞销汇总（左侧）
- 总库存金额（万元）
- 30天滞销：金额、数量、占比
- 60天滞销：金额、数量、占比
- 90天滞销：金额、数量、占比

#### 1.4.2 60天以上滞销产品列表（中间）
- 表格：金额排名、商品名称、库存数量、库存金额
- 按金额降序排列
- 显示Top N（如Top 20）

#### 1.4.3 月度个人滞销转化排名（右侧）
- 表格：排名、人员、金额总计
- 按金额降序排列
- 颜色标识：高金额绿色，低金额红色

---

## 二、数据支撑需求分析

### 2.1 核心字段需求（倒推法）

#### 2.1.1 转化率相关字段
**必需字段**：
- `fact_product_metrics.unique_visitors`（客流量）
- `fact_orders.order_id`（订单数）
- `fact_product_metrics.conversion_rate`（转化率，如已有）

**计算逻辑**：
- 转化率 = 订单数 / 访客数 × 100%
- 需要按日期聚合：日度/周度/月度

#### 2.1.2 客流量相关字段
**必需字段**：
- `fact_product_metrics.unique_visitors`（唯一访客数）
- `fact_product_metrics.metric_date`（日期）

**聚合方式**：
- 日度：按metric_date聚合SUM(unique_visitors)
- 周度：按周聚合SUM(unique_visitors)
- 月度：按月聚合SUM(unique_visitors)

#### 2.1.3 客单价相关字段
**必需字段**：
- `fact_orders.total_amount_rmb`（订单总金额）
- `fact_orders.order_id`（订单数）

**计算逻辑**：
- 客单价 = SUM(total_amount_rmb) / COUNT(DISTINCT order_id)

#### 2.1.4 连带率相关字段
**必需字段**：
- `fact_order_items.order_id`（订单项数）
- `fact_orders.order_id`（订单数）

**计算逻辑**：
- 连带率 = COUNT(fact_order_items) / COUNT(DISTINCT fact_orders.order_id)

#### 2.1.5 人效相关字段
**必需字段**：
- `fact_orders.total_amount_rmb`（销售额）
- `员工表.employee_count`（员工数，如无则暂不显示）

**计算逻辑**：
- 人效 = SUM(total_amount_rmb) / employee_count

#### 2.1.6 库存滞销相关字段
**必需字段**：
- `fact_product_metrics`（inventory域）：库存数量、库存金额
- `fact_product_metrics.metric_date`（日期）
- 需要计算：当前日期 - metric_date = 滞销天数

**计算逻辑**：
- 30天滞销：CURRENT_DATE - metric_date >= 30
- 60天滞销：CURRENT_DATE - metric_date >= 60
- 90天滞销：CURRENT_DATE - metric_date >= 90

### 2.2 物化视图需求（优先复用现有视图）

**现有视图**：
- ✅ `mv_daily_sales`：日度销售汇总
- ✅ `mv_weekly_sales`：周度销售汇总
- ✅ `mv_monthly_sales`：月度销售汇总
- ✅ `mv_inventory_by_sku`：SKU级库存明细

**增强策略**：
- 优先复用现有物化视图
- 如缺少字段（客流量、转化率、连带率），考虑增强现有视图
- 库存滞销查询：使用 `mv_inventory_by_sku` + SQL计算滞销天数

---

## 三、后端API设计（修复双维护风险）

### 3.1 路由冲突修复（步骤0 - 必须优先执行）

**问题**：
- `backend/routers/dashboard.py` 和 `backend/routers/dashboard_api.py` 都注册在 `/api/dashboard` 前缀下

**解决方案**：
1. 检查 `dashboard.py` 的功能
2. 将功能迁移到 `dashboard_api.py`
3. 删除 `dashboard.py` 文件
4. 更新 `backend/main.py` 中的路由注册（删除 `dashboard.router`）

### 3.2 新增API端点（在dashboard_api.py中）

#### 3.2.1 GET /api/dashboard/business-overview/kpi
**功能**：获取5个核心KPI指标（或增强现有 `/overview` 端点）
**位置**：`backend/routers/dashboard_api.py`
**参数**：
- `start_date`（可选）：开始日期
- `end_date`（可选）：结束日期
- `platforms`（可选）：平台筛选（逗号分隔）
- `shops`（可选）：店铺筛选（逗号分隔）

**返回格式**（与API_CONTRACT一致）：
```json
{
  "kpi": {
    "gmv": 12345.67,
    "orders": 890,
    "conversion_rate": 0.0734,
    "aov": 13.88,
    "traffic": 8624,
    "attach_rate": 1.00,
    "labor_efficiency": 14.76
  },
  "last_update": "2025-10-30T12:00:00Z",
  "source": "mv_daily_sales"
}
```

#### 3.2.2 GET /api/dashboard/business-overview/comparison
**功能**：获取日/周/月度数据对比
**位置**：`backend/routers/dashboard_api.py`
**参数**：
- `granularity`（必选）：daily/weekly/monthly
- `date`（必选）：具体日期（YYYY-MM-DD）
- `platforms`（可选）：平台筛选（逗号分隔）
- `shops`（可选）：店铺筛选（逗号分隔）

**返回**：
```json
{
  "success": true,
  "data": {
    "granularity": "daily",
    "date": "2025-03-17",
    "metrics": {
      "sales_amount": {
        "today": 0.50,
        "yesterday": 15.23,
        "average": 12.45,
        "change": -96.7,
        "change_type": "decrease"
      },
      "sales_quantity": {...},
      "profit": {...},
      "traffic": {...},
      "conversion_rate": {...},
      "attach_rate": {...},
      "avg_order_value": {...}
    }
  }
}
```

#### 3.2.3 GET /api/dashboard/business-overview/shop-racing
**功能**：获取店铺赛马数据（店铺对比排名）
**位置**：`backend/routers/dashboard_api.py`
**参数**：
- `granularity`（必选）：daily/weekly/monthly
- `date`（必选）：具体日期
- `group_by`（可选）：shop/platform（默认shop）

**返回**：
```json
{
  "success": true,
  "data": {
    "groups": [
      {
        "group_name": "A组",
        "shops": [
          {
            "shop_id": "shop_1",
            "shop_name": "店铺1",
            "target": 100.0,
            "achieved": 44.0,
            "achievement_rate": 44.0,
            "rank": 2
          }
        ]
      }
    ]
  }
}
```

#### 3.2.4 GET /api/dashboard/business-overview/inventory-backlog
**功能**：获取库存滞销情况
**位置**：`backend/routers/dashboard_api.py`（或新建 `backend/routers/inventory_backlog.py`）
**参数**：
- `days`（可选）：滞销天数阈值（30/60/90，默认90）
- `platforms`（可选）：平台筛选
- `shops`（可选）：店铺筛选

**返回**：
```json
{
  "success": true,
  "data": {
    "summary": {
      "total_inventory_value": 193.00,
      "backlog_30d": {
        "value": 42.18,
        "quantity": 296,
        "ratio": 22.0
      },
      "backlog_60d": {...},
      "backlog_90d": {...}
    },
    "top_products": [
      {
        "rank": 1,
        "product_name": "HUAWEI FreeBuds Pro 4",
        "inventory_quantity": 16,
        "inventory_value": 23984
      }
    ],
    "personnel_ranking": [
      {
        "rank": 1,
        "personnel": "彭磊",
        "total_amount": 15166
      }
    ]
  }
}
```

### 3.3 现有API增强

#### 3.3.1 GET /api/dashboard/overview（增强）
**位置**：`backend/routers/dashboard_api.py`（已存在，需要增强）
**新增字段**：
- `traffic`：客流量（从 `fact_product_metrics.unique_visitors` 聚合）
- `attach_rate`：连带率（从 `fact_order_items` 和 `fact_orders` 计算）
- `labor_efficiency`：人效（如有员工数据，否则返回null）

**注意**：保持与 `API_CONTRACT.md` 的一致性

---

## 四、前端实现（修复双维护风险）

### 4.1 组件结构（复用现有文件）

**重要**：`BusinessOverview.vue` 已存在，需要增强而非创建新文件

```
frontend/src/views/BusinessOverview.vue（增强现有文件）
├── 顶部：BusinessKPICards（5个KPI卡片，内联组件）
├── 中间左侧：BusinessCategorySummary（业务分类汇总，可选）
├── 中间右侧：BusinessComparison（数据对比和店铺赛马）
│   ├── GranularitySelector（粒度切换器，内联组件）
│   ├── MetricsComparisonTable（指标对比表格，内联组件）
│   └── ShopRacingTable（店铺赛马表格，内联组件）
└── 底部：InventoryBacklog（库存滞销）
    ├── BacklogSummary（总滞销汇总，内联组件）
    ├── BacklogProductsTable（滞销产品列表，内联组件）
    └── PersonnelRankingTable（个人排名，内联组件）
```

**设计原则**：
- ✅ 增强现有 `BusinessOverview.vue`，不创建新文件
- ✅ 复杂组件可以拆分为独立组件（放在 `frontend/src/components/business/`）
- ✅ 简单组件内联在 `BusinessOverview.vue` 中
- ❌ 禁止创建 `BusinessOverviewV2.vue` 或类似重复文件

### 4.2 样式设计
- **参考门店模板**：表格布局、颜色标识、数据展示方式
- **企业级UI标准**：符合SAP Fiori设计规范
- **响应式设计**：支持不同屏幕尺寸

### 4.3 数据加载策略
- **初始加载**：页面加载时获取所有数据
- **刷新机制**：支持手动刷新和自动刷新（每5分钟）
- **加载状态**：显示Loading状态和错误处理

---

## 五、实施步骤（修复双维护风险）

### 步骤0：修复路由冲突（必须优先执行）
1. **检查路由注册**：确认 `backend/main.py` 中两个dashboard路由的注册顺序
2. **合并路由文件**：
   - 检查 `dashboard.py` 和 `dashboard_api.py` 的功能差异
   - 将 `dashboard.py` 的功能迁移到 `dashboard_api.py`
   - 删除 `dashboard.py` 文件
   - 更新 `backend/main.py` 中的路由注册
3. **验证路由**：确保所有API端点正常工作

### 步骤1：数据支撑确认（1-2小时）
1. 检查现有数据库字段是否满足需求
2. **确认物化视图复用**：
   - 检查 `mv_daily_sales`, `mv_weekly_sales`, `mv_monthly_sales` 是否包含所需字段
   - 如缺少字段，考虑增强现有视图而非创建新视图
   - 检查 `mv_inventory_by_sku` 是否支持滞销查询
3. 编写数据查询SQL验证数据可用性

### 步骤2：后端API开发（2-3小时）
1. **修复路由冲突**（步骤0）
2. **增强现有API**：
   - 增强 `dashboard_api.py` 中的 `/overview` 端点
   - 新增 `/business-overview/kpi` 端点（或合并到 `/overview`）
   - 新增 `/business-overview/comparison` 端点
   - 新增 `/business-overview/shop-racing` 端点
   - 新增 `/business-overview/inventory-backlog` 端点（或放在 `inventory.py` 中）
3. **编写API测试用例**

### 步骤3：前端页面开发（4-6小时）
1. **增强现有BusinessOverview.vue**（不创建新文件）
2. 实现5个核心KPI卡片组件（内联或独立组件）
3. 实现数据对比和店铺赛马组件
4. 实现库存滞销组件
5. 集成ECharts图表（如需要）

### 步骤4：测试和优化（1-2小时）
1. **路由冲突测试**：确保没有路由冲突
2. **功能测试**：所有API端点正常工作
3. **性能测试**：查询性能符合要求
4. **UI/UX优化**：参考门店模板样式

---

## 六、核心字段清单（最终确定）

### 6.1 必需字段（已存在）
- ✅ `fact_orders.order_id`（订单数）
- ✅ `fact_orders.total_amount_rmb`（销售额）
- ✅ `fact_order_items.order_id`（订单项数）
- ✅ `fact_product_metrics.unique_visitors`（客流量）
- ✅ `fact_product_metrics.conversion_rate`（转化率）
- ✅ `fact_product_metrics.metric_date`（日期）

### 6.2 需要计算的字段
- ⚠️ **连带率**：需要JOIN fact_order_items和fact_orders
- ⚠️ **人效**：需要员工数据表（如无则暂不显示）
- ⚠️ **库存滞销天数**：需要计算CURRENT_DATE - metric_date

### 6.3 需要新增的字段（如缺失）
- ❓ `fact_product_metrics.inventory_quantity`（库存数量，inventory域）
- ❓ `fact_product_metrics.inventory_value`（库存金额，inventory域）
- ❓ 员工表（如需要人效指标）

---

## 七、风险和注意事项（修复双维护风险）

### 7.1 架构风险（重要）

#### 7.1.1 路由冲突风险（必须修复）
- **风险**：`dashboard.py` 和 `dashboard_api.py` 都注册在 `/api/dashboard` 前缀下
- **影响**：后注册的路由会覆盖先注册的路由，导致部分API不可用
- **解决方案**：合并两个文件，统一使用 `dashboard_api.py`

#### 7.1.2 双维护风险
- **风险**：创建新的 `BusinessOverviewV2.vue` 会导致双维护
- **解决方案**：增强现有 `BusinessOverview.vue`，不创建新文件
- **风险**：创建新的物化视图 `mv_business_overview_*` 可能与现有视图重复
- **解决方案**：优先复用现有物化视图，如 `mv_daily_sales`, `mv_weekly_sales`, `mv_monthly_sales`

### 7.2 数据可用性风险
- **人效指标**：如无员工数据，该指标暂不显示
- **库存滞销**：需要确认inventory域数据是否完整
- **转化率**：需要确认unique_visitors数据是否完整
- **连带率**：需要确认 `fact_order_items` 和 `fact_orders` 的关联关系

### 7.3 性能风险
- **大数据量查询**：使用物化视图优化
- **实时刷新**：考虑缓存策略，避免频繁查询
- **物化视图刷新**：确保物化视图定期刷新（使用现有刷新机制）

### 7.4 UI/UX风险
- **数据加载时间**：显示Loading状态，优化查询性能
- **错误处理**：完善的错误提示和降级方案
- **路由冲突**：确保前端API调用使用正确的端点路径

### 7.5 代码质量风险
- **SSOT合规**：确保所有API端点遵循SSOT原则
- **API契约**：新增API端点需要更新 `API_CONTRACT.md`
- **文档同步**：更新相关文档，避免文档与代码不一致

---

## 八、后续优化方向

1. **实时数据推送**：使用WebSocket实现实时数据更新
2. **数据导出**：支持导出Excel报告
3. **自定义指标**：允许用户自定义KPI指标
4. **数据钻取**：点击指标可钻取到详细数据
5. **移动端适配**：响应式设计优化移动端体验

---

## 九、检查清单（执行前必查）

### 9.1 架构合规检查
- [ ] 确认没有路由冲突（`dashboard.py` 和 `dashboard_api.py`）
- [ ] 确认不会创建重复的前端组件（`BusinessOverviewV2.vue`）
- [ ] 确认不会创建重复的物化视图（`mv_business_overview_*`）
- [ ] 确认所有API端点遵循SSOT原则

### 9.2 数据可用性检查
- [ ] 确认 `fact_product_metrics.unique_visitors` 数据完整
- [ ] 确认 `fact_orders` 和 `fact_order_items` 关联关系正确
- [ ] 确认inventory域数据完整（如需要库存滞销功能）
- [ ] 确认员工数据表是否存在（如需要人效指标）

### 9.3 性能检查
- [ ] 确认物化视图定期刷新
- [ ] 确认查询性能符合要求（<500ms）
- [ ] 确认前端数据加载有Loading状态

### 9.4 文档同步检查
- [ ] 更新 `API_CONTRACT.md`（如新增API端点）
- [ ] 更新 `CHANGELOG.md`（记录变更）
- [ ] 更新相关文档（如需要）

---

**最后更新**：2025-11-10
**状态**：待执行
**优先级**：高（修复路由冲突后执行）

