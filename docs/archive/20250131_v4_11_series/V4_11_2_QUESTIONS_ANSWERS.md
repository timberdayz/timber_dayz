# v4.11.2 用户问题解答

**日期**: 2025-11-15

## 问题1: A类数据配置页面位置

### 📍 配置页面清单

#### 1. 销售战役管理 ⭐

**页面路径**: `/sales-campaign-management`  
**菜单导航**: `销售与分析 → 销售战役管理`  
**页面文件**: `frontend/src/views/sales/CampaignManagement.vue`  
**路由名称**: `SalesCampaignManagement`

**功能**:
- ✅ 创建销售战役
- ✅ 编辑销售战役
- ✅ 删除销售战役
- ✅ 查看战役详情和达成情况
- ✅ 添加/移除参与店铺
- ✅ 手动触发达成率计算

**配置项**:
- 战役名称
- 战役类型（节假日/新品上市/特殊促销）
- 时间范围（开始日期 - 结束日期）
- 目标销售额（万元）
- 目标订单数（可选）
- 参与店铺列表

**访问权限**: `campaign:read`（管理员、经理、运营）

---

#### 2. 目标管理 ⭐

**页面路径**: `/target-management`  
**菜单导航**: `销售与分析 → 目标管理`  
**页面文件**: `frontend/src/views/target/TargetManagement.vue`  
**路由名称**: `TargetManagement`

**功能**:
- ✅ 创建销售目标
- ✅ 编辑销售目标
- ✅ 删除销售目标
- ✅ 目标拆分（店铺拆分/时间拆分）
- ✅ 查看目标详情和达成情况
- ✅ 手动触发达成率计算

**配置项**:
- 目标名称
- 目标类型（店铺目标/产品目标/战役目标）
- 时间周期（开始日期 - 结束日期）
- 目标金额（万元）
- 目标数量（订单数/销量）
- 目标拆分：
  - 店铺拆分：按店铺分配目标
  - 时间拆分：按时间段分配目标

**访问权限**: `target:read`（管理员、经理）

---

#### 3. 绩效权重配置 ⭐

**页面路径**: `/hr-performance-management`  
**菜单导航**: `人力资源 → 绩效管理 → 配置权重`  
**页面文件**: `frontend/src/views/hr/PerformanceManagement.vue`  
**路由名称**: `HRPerformanceManagement`

**功能**:
- ✅ 配置绩效权重（销售额/毛利/重点产品/运营）
- ✅ 查看绩效公示
- ✅ 导出绩效报表

**配置项**:
- 销售额权重（%）
- 毛利权重（%）
- 重点产品权重（%）
- 运营权重（%）
- **约束**: 四项权重总和必须等于100%

**访问权限**: `performance:read`（管理员、经理、运营）

---

### 🗺️ 快速访问

**直接URL**:
- 销售战役: `http://localhost:5173/#/sales-campaign-management`
- 目标管理: `http://localhost:5173/#/target-management`
- 绩效管理: `http://localhost:5173/#/hr-performance-management`

---

## 问题2: 物化视图和数据库表审计

### 📊 物化视图审计结果

#### 当前状态

**总计**: 18个物化视图  
**预期**: 20个物化视图  
**缺失**: 2个物化视图  
**多余**: 0个物化视图

#### ✅ 已存在的物化视图（18个）

**产品域（3个）**:
- ✅ `mv_product_management` - 产品管理核心视图（48 kB, 5索引）
- ✅ `mv_product_sales_trend` - 产品销售趋势（24 kB, 2索引）
- ✅ `mv_product_topn_day` - TopN日排行（16 kB, 1索引）

**销售域（5个）**:
- ✅ `mv_daily_sales` - 日销售（24 kB, 2索引）
- ✅ `mv_weekly_sales` - 周销售（16 kB, 1索引）
- ✅ `mv_monthly_sales` - 月销售（16 kB, 1索引）
- ✅ `mv_order_sales_summary` - 订单销售汇总（24 kB, 2索引）
- ✅ `mv_sales_day_shop_sku` - 日度销售SKU汇总（24 kB, 2索引）

**财务域（4个）**:
- ✅ `mv_financial_overview` - 财务总览（16 kB, 1索引）
- ✅ `mv_pnl_shop_month` - 店铺P&L（16 kB, 1索引）
- ✅ `mv_profit_analysis` - 利润分析（32 kB, 3索引）
- ✅ `mv_vendor_performance` - 供应商绩效（16 kB, 1索引）

**库存域（3个）**:
- ✅ `mv_inventory_summary` - 库存汇总（56 kB, 2索引）
- ✅ `mv_inventory_by_sku` - SKU级库存（56 kB, 6索引）
- ✅ `mv_inventory_age_day` - 库存账龄（16 kB, 1索引）

**流量域（1个）**:
- ✅ `mv_shop_traffic_day` - 店铺流量（16 kB, 1索引）

**C类数据域（2个）**⭐新增:
- ✅ `mv_shop_daily_performance` - 店铺日度表现（24 kB, 2索引）
- ✅ `mv_shop_health_summary` - 店铺健康度汇总（24 kB, 2索引）

#### ⚠️ 缺失的物化视图（2个）

1. **`mv_shop_product_summary`** - 店铺产品汇总
   - **状态**: 代码中引用但数据库中不存在
   - **代码位置**: `backend/services/materialized_view_service.py`的`query_shop_summary`方法
   - **前端位置**: `frontend/src/views/DataBrowser.vue`中列出
   - **日志错误**: 刷新服务一直在尝试刷新但失败（视图不存在）
   - **影响**: ⚠️ **功能受影响** - 店铺维度产品汇总查询无法使用
   - **建议**: **需要创建** - 代码中仍在使用，应创建此视图

2. **`mv_top_products`** - 顶级产品
   - **状态**: 代码中引用但数据库中不存在
   - **代码位置**: `sql/create_materialized_views.sql`中有创建脚本
   - **前端位置**: `frontend/src/views/DataBrowser.vue`中列出
   - **日志错误**: 刷新服务一直在尝试刷新但失败（视图不存在）
   - **影响**: ⚠️ **功能受影响** - TopN产品排行查询无法使用
   - **建议**: **需要创建** - 代码中仍在使用，应创建此视图
   - **注意**: 与`mv_product_topn_day`功能可能重叠，需要确认是否都需要

#### 📝 物化视图评估

**符合要求程度**: 90%（18/20，缺失2个需要创建）

**结论**: 
- ✅ 核心业务视图全部存在
- ✅ C类数据视图已创建
- ⚠️ 2个视图缺失但代码中仍在使用，需要创建

---

### 📋 数据库表审计结果

#### 当前状态

**总计**: 80张表  
**维度表**: 16张  
**事实表**: 13张  
**其他表**: 51张

#### ✅ 表分类统计

**维度表（dim_*）- 16张**:
- ✅ 核心维度表：平台、店铺、产品、货币、日期等
- ✅ 设计合理，符合星型模型标准

**事实表（fact_*）- 13张**:
- ✅ 核心事实表：订单、产品指标、库存、财务等
- ✅ 设计合理，符合企业级ERP标准

**A类数据表 - 5张**:
- ✅ `sales_campaigns` - 销售战役配置
- ✅ `sales_campaign_shops` - 战役参与店铺
- ✅ `sales_targets` - 目标配置
- ✅ `target_breakdown` - 目标分解
- ✅ `performance_config` - 绩效权重配置

**C类数据表 - 4张**:
- ✅ `shop_health_scores` - 店铺健康度评分
- ✅ `shop_alerts` - 店铺预警
- ✅ `performance_scores` - 绩效得分
- ✅ `clearance_rankings` - 滞销清理排名

**字段映射表 - 6张**:
- ✅ `field_mapping_dictionary` - 字段映射辞典
- ✅ `field_mapping_templates` - 字段映射模板
- ✅ `field_mapping_template_items` - 模板项
- ✅ `field_mapping_audit` - 映射审计日志
- ⚠️ `field_mappings_deprecated` - 已废弃的映射表（v4.5.1）
- ✅ `mapping_sessions` - 映射会话表

#### ⚠️ 可能冗余的表

1. **`data_files`表**:
   - **状态**: 可能与`catalog_files`功能重复
   - **建议**: 检查是否仍在使用，如未使用可考虑归档

2. **`field_mappings_deprecated`表**:
   - **状态**: 已明确标记为废弃（v4.5.1）
   - **建议**: 保留用于历史数据查询，但不应在新代码中使用

3. **`fact_sales_orders`表**:
   - **状态**: 可能与`fact_orders`功能重复
   - **建议**: 检查两个表的区别和使用场景

#### 📝 数据库表评估

**符合要求程度**: 95%（核心表设计合理，少量表需要确认）

**结论**: 
- ✅ 维度表和事实表设计合理
- ✅ A类/C类数据表设计清晰
- ✅ 字段映射表系统完整
- ⚠️ 3张表可能需要进一步确认是否冗余

---

## 🎯 总结和建议

### A类数据配置

**状态**: ✅ **完整**  
**页面**: 3个配置页面全部存在且功能完整  
**建议**: 无，配置页面设计合理

### 物化视图

**状态**: ⚠️ **需要补充**  
**缺失**: 2个视图（`mv_shop_product_summary`, `mv_top_products`）  
**建议**: 
1. **立即行动**: 创建缺失的2个物化视图
2. **原因**: 代码中仍在使用，刷新服务一直在报错
3. **影响**: 店铺产品汇总和TopN产品排行功能无法使用

### 数据库表

**状态**: ✅ **良好**  
**冗余**: 3张表需要确认（`data_files`, `field_mappings_deprecated`, `fact_sales_orders`）  
**建议**: 
1. **检查使用情况**: 确认这3张表是否仍在使用
2. **归档废弃表**: 如果`field_mappings_deprecated`确实废弃，可考虑归档
3. **统一命名**: 确保表命名规范一致

---

## 📋 行动计划

### 优先级1（立即处理）

1. **创建缺失的物化视图**:
   - 创建`mv_shop_product_summary`视图
   - 创建`mv_top_products`视图
   - 更新刷新服务，确保不再报错

### 优先级2（近期处理）

1. **检查冗余表**:
   - 检查`data_files`表的使用情况
   - 检查`fact_sales_orders`与`fact_orders`的区别
   - 确认`field_mappings_deprecated`的状态

2. **更新文档**:
   - 更新物化视图列表（18个 → 20个）
   - 更新数据库表文档

---

## 🔗 相关文档

- [A类数据配置指南](./V4_11_2_A_CLASS_DATA_CONFIGURATION_GUIDE.md) - 详细配置说明
- [物化视图和数据库表审计报告](./V4_11_2_MATERIALIZED_VIEWS_AND_TABLES_AUDIT.md) - 完整审计报告
- [核心数据流程设计](./CORE_DATA_FLOW.md) - 数据流程说明

