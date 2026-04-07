# 技术设计：DSS架构重构

## Context（背景）

### 当前痛点
1. **字段映射系统复杂度高**：多层转换、多个验证函数、文件多次读取
2. **KPI计算硬编码**：每个KPI都需要在Python中实现计算逻辑
3. **数据流混乱**：A/B/C类数据处理逻辑分散在多个文件中
4. **维护成本高**：新增数据域需要修改多处代码
5. **扩展性差**：用户无法自助进行数据分析

### 业务目标
- 系统定位从"数据采集工具"升级为"企业级ERP决策支持系统"
- 用户角色从"数据录入员"升级为"数据分析师"
- 核心价值从"数据存储"升级为"数据洞察"

### 约束条件
- 必须保持100%向后兼容（现有数据和功能）
- 必须支持渐进式迁移（分阶段上线）
- 必须符合SSOT原则（Single Source of Truth）
- 必须考虑Windows平台兼容性

## Goals / Non-Goals（目标与非目标）

### 目标（Goals）
1. **简化后端架构**：后端专注于数据ETL，不再负责复杂的KPI计算
2. **引入BI工具**：使用Metabase作为核心计算和可视化引擎
3. **简化PostgreSQL表结构**：删除三层视图架构，Metabase直接查询原始表，按data_domain+granularity分表存储
4. **增强前端体验**：嵌入交互式图表，保留现有页面布局
5. **提升可维护性**：配置驱动开发，减少硬编码逻辑
6. **降低学习成本**：选择非技术人员友好的BI工具，类似Excel的编辑体验

### 非目标（Non-Goals）
1. ❌ 不重写现有的数据采集模块（完全保留）
2. ❌ 不迁移历史数据到新表结构（零数据迁移）
3. ❌ 不立即删除旧代码（保留3个月降级路径）
4. ❌ 不改变前端技术栈（继续使用Vue.js 3）

## Decisions（技术决策）

### 决策1：选择Metabase作为BI层

**选项对比**：

| 工具 | 优势 | 劣势 | 评分 |
|------|------|------|------|
| **Metabase** | 开源、简单易用、非技术人员友好、类似Excel体验、可嵌入 | 功能较Superset略弱 | ⭐⭐⭐⭐⭐ |
| Apache Superset | 功能强大、SQL原生 | 学习曲线陡、需要SQL知识 | ⭐⭐⭐ |
| Grafana | 监控强大、开源 | 不适合业务BI | ⭐⭐ |
| 自研BI | 完全控制 | 开发成本极高（6个月+） | ⭐ |

**最终决策**：**Metabase**

**理由**：
1. ✅ **非技术人员友好**：拖拽式查询构建器，类似Excel数据透视表
2. ✅ **学习成本低**：30分钟即可上手，无需SQL知识
3. ✅ **类似Excel的编辑体验**：支持公式编辑，符合用户习惯
4. ✅ 支持iframe嵌入和REST API集成
5. ✅ 声明式KPI定义（可视化查询构建器+自定义字段）
6. ✅ 开源免费，社区活跃
7. ✅ 支持Docker部署，与现有架构一致
8. ✅ 支持日/周/月切换和店铺维度筛选（通过Dashboard参数）

### 决策2：PostgreSQL表结构简化（删除三层视图架构）

**架构设计**：

```
B类数据表（按data_domain+granularity分表，最多16张）
- Schema: b_class
- 标准数据域：4个数据域 × 3个粒度 = 12张表
  - fact_raw_data_orders_daily/weekly/monthly
  - fact_raw_data_products_daily/weekly/monthly
  - fact_raw_data_traffic_daily/weekly/monthly
  - fact_raw_data_services_daily/weekly/monthly
- 特殊粒度：inventory_snapshot（1张）+ 未来inventory_daily/weekly/monthly（3张）= 4张
- 数据格式：JSONB（raw_data字段，中文字段名）
- 表名：英文（符合规范）
- 字段名：JSONB中的键名使用中文（用户友好）

统一对齐表（entity_aliases，1张）
- Schema: b_class（与B类数据表在同一schema，便于关联）
- 替代dim_shops和account_aliases两张表
- 统一管理账号和店铺别名映射
- Metabase通过一张表即可对齐所有信息

A类数据表（7张，使用中文字段名）
- Schema: a_class
- sales_targets, sales_campaigns, operating_costs
- employees, employee_targets, attendance_records, performance_config
- 所有字段名使用中文（PostgreSQL支持，需要双引号）

C类数据表（4张，使用中文字段名）
- Schema: c_class
- employee_performance, employee_commissions, shop_commissions, performance_scores
- 由Metabase定时计算更新（每20分钟）

核心ERP表（管理表、维度表等）
- Schema: core
- catalog_files, field_mapping_dictionary, dim_platform, dim_shop, dim_product等

财务域表（如需要保留）
- Schema: finance
- po_headers, grn_headers, invoice_headers等（如需要保留）

**Schema分离优势**：
- ✅ 清晰的表分类：B类/A类/C类/核心/财务表分离
- ✅ Metabase中按Schema分组显示，便于管理
- ✅ 查询时需要指定schema或配置search_path
- ⚠️ **注意事项**：
  - 数据浏览器API需要支持多schema查询
  - PostgreSQL search_path需要配置包含所有schema（public, b_class, a_class, c_class, core, finance）
  - 代码中可以使用表名直接访问（无需schema前缀），但API查询时需要指定schema
```

**优势**：
1. ✅ **表结构清晰**：按data_domain+granularity分表，避免不同粒度使用相同表头名称导致的数据混乱
2. ✅ **Metabase直接查询**：无需视图层，Metabase直接查询原始表，灵活创建关联
3. ✅ **中文表头支持**：利用Metabase中文表头支持，用户体验更好
4. ✅ **简化架构**：从53张表简化到31-34张表，维护成本降低
5. ✅ **统一对齐管理**：通过entity_aliases表统一管理所有账号和店铺对齐信息

### 决策3：前端集成策略 - API调用模式

**选项对比**：

| 策略 | 优势 | 劣势 | 决策 |
|------|------|------|------|
| **Option A: API调用 + 自渲染** | 完全控制UI、避免收费功能、灵活度高 | 需要实现图表渲染 | ✅ 选择 |
| Option B: Dashboard嵌入 | 开发成本低 | 需要Embedding功能（可能收费）、UI控制度低 | ❌ 不选 |
| Option C: 完全跳转Metabase | 开发成本最低 | 失去现有页面设计 | ❌ 不选 |

**最终决策**：**Option A - API调用 + Vue自渲染图表**

**理由**：
1. ✅ **避免收费功能**：Metabase的Embedding功能（Interactive Embedding）是收费的，REST API是免费的
2. ✅ **完全控制UI**：前端使用Vue.js + ECharts完全控制图表样式和交互
3. ✅ **灵活度高**：可以根据业务需求自定义图表类型和交互逻辑
4. ✅ **数据来源清晰**：在Metabase中创建Question（查询），前端通过API获取JSON数据
5. ✅ **原生布局保留**：现有页面布局和交互逻辑保持不变

**实现方式**：
1. **数据准备**：在Metabase中创建所有需要的Question（查询），保存Question ID
2. **后端代理API**：提供Metabase Question API代理（统一认证、错误处理、数据格式转换）
3. **前端渲染**：前端调用API获取JSON数据，使用ECharts/Chart.js自己渲染图表

**技术实现**：
```vue
<!-- 示例：业务概览页面 -->
<template>
  <div class="dashboard">
    <!-- 自定义筛选器（Vue组件） -->
    <el-card class="filter-card">
      <el-date-picker v-model="dateRange" type="daterange" />
      <el-select v-model="platform" />
      <el-radio-group v-model="granularity">
        <el-radio-button label="daily">日度</el-radio-button>
        <el-radio-button label="weekly">周度</el-radio-button>
        <el-radio-button label="monthly">月度</el-radio-button>
      </el-radio-group>
    </el-card>

    <!-- 自己渲染图表 -->
    <div class="chart-grid">
      <div ref="gmvChart" style="width: 100%; height: 400px;"></div>
      <div ref="orderChart" style="width: 100%; height: 400px;"></div>
    </div>
  </div>
</template>

<script>
import * as echarts from 'echarts'
import { getQuestionData } from '@/services/metabase'

export default {
  async mounted() {
    // 获取GMV趋势数据（Question ID: 1）
    const gmvData = await getQuestionData(1, {
      date_range: this.dateRange,
      platform: this.platform,
      granularity: this.granularity
    })
    
    // 使用ECharts渲染
    const chart = echarts.init(this.$refs.gmvChart)
    chart.setOption({
      xAxis: { data: gmvData.rows.map(r => r.date) },
      yAxis: {},
      series: [{
        data: gmvData.rows.map(r => r.gmv),
        type: 'line'
      }]
    })
  }
}
</script>
```

**Metabase Question API调用**：
```javascript
// frontend/src/services/metabase.js
export async function getQuestionData(questionId, filters = {}) {
  // 调用后端代理API
  const response = await api.get(`/api/metabase/question/${questionId}/query`, {
    params: filters
  })
  return response.data
}
```

**后端代理API**：
```python
# backend/routers/metabase_proxy.py
@router.get("/question/{question_id}/query")
async def get_question_data(question_id: int, filters: Optional[Dict] = None):
    """
    获取Metabase Question的查询结果
    使用Metabase REST API（免费）
    """
    # 调用Metabase API: GET /api/card/{id}/query
    # 返回JSON数据
```

### 决策4：A类数据管理 - CRUD界面而非Excel上传

**用户反馈**：
> "目标要长期进行设置，成本也要长期上传，而且都是固定路径，还需要使用excel对我来说很不高效"

**决策**：**采用可编辑表格界面（CRUD）**

**设计**：
```
目标管理界面 (TargetManagement.vue)
- 表格展示：shop/product/campaign级别目标
- 内联编辑：单元格点击即可编辑
- 快速操作：复制上月、批量计算达成率
- 分解功能：按店铺/按时间分解目标

成本配置界面 (CostConfiguration.vue)
- 可编辑表格：所有成本项在一个页面
- 快速填充：一键填充所有店铺的成本率
- 复制上月：复制上月成本配置
```

### 决策6：字段映射系统重构 - 直接保存原始表头

**背景**：
- Metabase支持中文表头，无需映射到英文标准字段
- 用户反馈：中文表头更直观，编辑更便捷
- 现有标准字段映射系统过于复杂，维护成本高

**决策**：**直接保存原始表头，不再映射到标准字段**

**实现方案**：
1. **模板简化**：模板只包含`platform + data_domain + granularity + header_columns`（原始表头字段列表）
2. **数据存储**：使用JSONB存储原始数据，字段名保持原始表头
3. **表头变化检测**：比较当前表头与模板表头，提醒用户更新
4. **删除FieldMappingTemplateItem表**：不再需要字段映射项表

**优势**：
- ✅ 简化系统架构，降低维护成本
- ✅ 利用Metabase中文表头支持，用户体验更好
- ✅ 数据存储更灵活，支持动态字段
- ✅ 减少数据转换环节，降低出错风险

**数据对齐保障**：
- ✅ pandas原生对齐：`pd.read_excel(header=header_row)`保证数据行与表头对齐
- ✅ 字典结构保证：`df.to_dict('records')`保证字段名和数据值一一对应
- ✅ JSONB存储保证：字典序列化为JSON，字段名作为键，数据值作为值
- ✅ 入库前验证：验证字段数量、名称、数据类型

### 决策7：多层数据去重策略

**背景**：
- 订单数据域：同一订单号可能有多个操作（买货、退货、多个产品）
- 流量/服务数据域：没有唯一业务标识，只有日期/时间
- 单字段去重无法满足复杂业务场景

**决策**：**采用多层数据去重策略**

**四层去重机制**：
1. **文件级去重**：基于`file_hash`跳过已处理文件
2. **行内去重**：使用`file_id + row_number + data_hash`唯一标识
3. **跨文件去重**：基于`data_hash`（全行业务字段哈希）识别重复记录
4. **业务语义判断**：相同业务标识但数据不同时，应用更新策略（如"latest wins"）

**性能优化**：
- ✅ 批量计算哈希：使用pandas向量化操作（1000行约50-100ms）
- ✅ 批量查询数据库：使用IN查询替代逐条查询（1次查询替代1000次）
- ✅ 数据库唯一约束：使用`ON CONFLICT`自动去重（1000行约0.05-0.2秒）
- ✅ 批量插入：1次SQL语句处理所有数据

**预期性能**：
- 1000行数据：约0.05-0.2秒（相比逐条处理快50-100倍）
- 10000行数据：约0.5-2秒

### 决策8：合并单元格处理增强

**背景**：
- Excel文件中经常出现合并单元格（如订单号跨2-5行）
- pandas读取合并单元格时，只有第一行有值，后续行是NaN
- 需要智能填充合并单元格的值

**决策**：**增强版合并单元格处理**

**处理策略**：
1. **关键列强制填充**：订单号、订单日期等关键列无论空值占比，强制前向填充（ffill）
2. **智能识别**：扩展订单号识别关键词（订单号、订单编号、订单ID、order_id等）
3. **大文件优化**：大文件（>10MB）也处理关键列，不跳过规范化
4. **边界情况检测**：检测第一行为空、中间空值等异常情况

**处理示例**：
```
原始数据（合并单元格）：
  订单号    订单日期    商品名称
  ORD001   2025-01-01  商品A
  (空)     2025-01-01  商品B  ← 合并单元格
  (空)     2025-01-01  商品C  ← 合并单元格

处理后（已填充）：
  订单号    订单日期    商品名称
  ORD001   2025-01-01  商品A
  ORD001   2025-01-01  商品B  ← 已填充
  ORD001   2025-01-01  商品C  ← 已填充
```

**保障机制**：
- ✅ pandas的`ffill()`方法保证填充准确性
- ✅ 关键列识别机制保证重要字段不遗漏
- ✅ 数据验证机制保证填充后数据正确性

### 决策5：数据迁移策略 - 删除旧表结构，创建新表结构

**原则**：
1. ✅ **开发阶段**：可以删除所有现有表（53张表），历史数据不需要迁移
2. ✅ **生产环境**：如需保留历史数据，提供迁移脚本（从旧表迁移到新表）
3. ✅ **创建新表结构**：按新架构创建约31-34张表
   - B类数据表：最多16张（按data_domain+granularity分表）
   - 统一对齐表：1张（entity_aliases）
   - A类数据表：7张（使用中文字段名）
   - C类数据表：4张（使用中文字段名）
   - 人力管理表：7张（使用中文字段名）
   - 管理表：3张
4. ✅ **删除旧表**：删除所有dim_*表、复杂fact_*表、财务域表、FieldMappingTemplateItem表

**迁移步骤**：
```sql
-- Phase 1: 安全备份（仅生产环境）
pg_dump -h localhost -U user -d xihong_erp > backup_$(date +%Y%m%d).sql

-- Phase 2: 删除旧表结构（开发阶段）
DROP TABLE IF EXISTS dim_* CASCADE;
DROP TABLE IF EXISTS fact_orders CASCADE;
DROP TABLE IF EXISTS fact_order_items CASCADE;
DROP TABLE IF EXISTS po_* CASCADE;
DROP TABLE IF EXISTS grn_* CASCADE;
DROP TABLE IF EXISTS invoice_* CASCADE;
DROP TABLE IF EXISTS field_mapping_template_items CASCADE;
DROP TABLE IF EXISTS dim_shops CASCADE;
DROP TABLE IF EXISTS account_aliases CASCADE;

-- Phase 3: 创建新表结构
-- B类数据分表（最多16张）
CREATE TABLE fact_raw_data_orders_daily (...);
CREATE TABLE fact_raw_data_orders_weekly (...);
CREATE TABLE fact_raw_data_orders_monthly (...);
-- ... 其他B类数据表

-- 统一对齐表
CREATE TABLE entity_aliases (...);

-- A类数据表（7张，中文字段名）
CREATE TABLE sales_targets_a ("店铺ID" TEXT, "年月" TEXT, ...);
CREATE TABLE sales_campaigns_a (...);
CREATE TABLE operating_costs (...);
CREATE TABLE employees (...);
CREATE TABLE employee_targets (...);
CREATE TABLE attendance_records (...);
CREATE TABLE performance_config_a (...);

-- C类数据表（4张，中文字段名）
CREATE TABLE employee_performance (...);
CREATE TABLE employee_commissions (...);
CREATE TABLE shop_commissions (...);
CREATE TABLE performance_scores_c (...);

-- Phase 4: 配置Metabase数据库和表
-- （通过Metabase UI完成，直接连接PostgreSQL原始表）

-- Phase 5: 验证和清理
SELECT COUNT(*) FROM fact_raw_data_orders_daily;
SELECT COUNT(*) FROM entity_aliases;
```

## Architecture Overview（架构概览）

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         前端层 (Vue.js 3)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ 业务概览      │  │ 销售看板      │  │ 目标管理      │      │
│  │ (Metabase嵌入)│  │ (Metabase嵌入)│  │ (Vue原生)    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                          ↕ (API调用)
┌─────────────────────────────────────────────────────────────┐
│                    后端API层 (FastAPI)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ ETL模块: 数据采集、清洗、验证、入库                    │   │
│  │ A类数据管理: 目标/战役/成本 CRUD API                  │   │
│  │ Metabase集成: 代理API、数据刷新触发                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          ↕ (SQL查询)
┌─────────────────────────────────────────────────────────────┐
│                BI层 (Metabase)                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Dashboard: 业务概览、销售分析、库存监控               │   │
│  │ Dataset: 直接查询PostgreSQL原始表                    │   │
│  │ Question: 交互式图表（折线/柱状/饼图/地图）            │   │
│  │ Query Builder: 拖拽式查询构建器（类似Excel）          │   │
│  │ Custom Fields: 公式表达式计算KPI                      │   │
│  │ Relationships: 灵活创建表间关联                       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          ↕ (SQL查询)
┌─────────────────────────────────────────────────────────────┐
│              PostgreSQL 15+ (简化表结构)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ B类数据表（最多16张，按data_domain+granularity分表）   │   │
│  │   fact_raw_data_orders_daily/weekly/monthly            │   │
│  │   fact_raw_data_products_daily/weekly/monthly         │   │
│  │   fact_raw_data_traffic_daily/weekly/monthly          │   │
│  │   fact_raw_data_services_daily/weekly/monthly         │   │
│  │   fact_raw_data_inventory_snapshot                    │   │
│  │   数据格式：JSONB（raw_data字段，中文字段名）          │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 统一对齐表（1张）                                      │   │
│  │   entity_aliases（替代dim_shops和account_aliases）     │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ A类数据表（7张，中文字段名）                           │   │
│  │   sales_targets_a, sales_campaigns_a, operating_costs │   │
│  │   employees, employee_targets, attendance_records     │   │
│  │   performance_config_a                               │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ C类数据表（4张，中文字段名，Metabase定时计算）         │   │
│  │   employee_performance, employee_commissions         │   │
│  │   shop_commissions, performance_scores_c              │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ 管理表（3张）                                          │   │
│  │   catalog_files, field_mapping_dictionary, etc.       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 数据流图

```
【B类数据流】
Excel文件 → 表头识别 → 模板匹配/创建 → Staging层（原始数据JSONB）
→ 合并单元格处理 → 数据去重（多层策略） → Fact层（按data_domain+granularity分表，JSONB格式，中文字段名）
→ Metabase直接查询原始表 → Metabase计算和关联 → 前端展示

【A类数据流】
前端CRUD → API验证 → 入库A类表（中文字段名） → Metabase直接查询和关联 → 前端展示

【C类数据流】
Metabase定时计算（每20分钟） → 更新C类数据表（中文字段名） → Metabase查询 → 前端展示
```

## Risks / Trade-offs（风险与权衡）

### 风险1：Metabase学习曲线
- **风险等级**：低
- **影响**：用户需要学习Metabase基本操作
- **缓解措施**：
  - 提供详细的Metabase使用文档
  - 创建示例Question模板
  - 用户培训（30分钟即可上手，拖拽式操作）

### 风险2：前端嵌入兼容性
- **风险等级**：低
- **影响**：iframe嵌入可能存在跨域或样式问题
- **缓解措施**：
  - 配置Metabase CORS白名单
  - 使用Metabase Embedding API（官方支持）
  - 测试多浏览器兼容性（Chrome/Edge/Firefox）

### 风险3：Metabase定时计算性能
- **风险等级**：中
- **影响**：C类数据定时计算（每20分钟）可能耗时较长（>60秒）
- **缓解措施**：
  - 优化Metabase查询性能（使用索引、限制数据范围）
  - 增量计算策略（只计算最近变化的数据）
  - 定时任务避开业务高峰（凌晨1点）
  - 使用Metabase异步查询功能

### 风险4：Metabase服务稳定性
- **风险等级**：中
- **影响**：Metabase服务宕机影响图表展示
- **缓解措施**：
  - 前端降级策略（Metabase不可用时显示静态图表）
  - Metabase容器健康检查和自动重启
  - 监控告警（Prometheus + Grafana）

### 权衡1：配置复杂度 vs 灵活性
- **权衡**：Metabase配置复杂度低于硬编码KPI
- **决策**：选择Metabase，降低学习成本，提升用户体验
- **理由**：拖拽式操作，类似Excel体验，非技术人员友好；配置驱动开发符合企业级ERP标准

### 权衡2：学习成本 vs 功能强大
- **权衡**：Metabase功能略弱于Superset，但学习成本低
- **决策**：选择Metabase，降低学习成本，满足业务需求
- **理由**：Metabase功能足够满足需求，且非技术人员可快速上手；类似Excel的编辑体验符合用户习惯

## Migration Plan（迁移计划）

### Phase 0: 表结构重构和数据迁移（2周）

**Week 1**：
- [ ] Day 1-2: 备份现有数据库（仅生产环境），创建开发分支
- [ ] Day 3-4: 删除旧表结构（开发阶段：删除所有dim_*表、复杂fact_*表、财务域表）
- [ ] Day 5: 创建B类数据分表（最多16张，按data_domain+granularity）

**Week 2**：
- [ ] Day 1-2: 创建统一对齐表（entity_aliases，1张）
- [ ] Day 3-4: 创建A类数据表（7张，使用中文字段名）
- [ ] Day 5: 创建C类数据表（4张，使用中文字段名）和人力管理表（7张，使用中文字段名）

**验收标准**：
- ✅ 所有新表创建成功（31-34张表）
- ✅ 旧表删除完成（开发阶段）
- ✅ 数据对齐准确性测试通过
- ✅ 合并单元格处理测试通过
- ✅ 数据去重性能测试通过（1000行 < 0.2秒）
- ✅ 中文字段名兼容性测试通过

### Phase 1: Metabase集成和基础Dashboard（2周）

**Week 1**：
- [ ] Day 1-2: 部署Metabase容器（Docker Compose）
- [ ] Day 3-4: 配置PostgreSQL连接，同步B类/A类/C类数据表
- [ ] Day 5: 配置entity_aliases表关联，创建业务概览相关Question（5个Question）

**Week 2**：
- [ ] Day 1-2: 创建5个核心Question（GMV/订单数/转化率/库存/利润），直接查询原始表
- [ ] Day 3-4: 配置Dashboard筛选器（日期范围、店铺、粒度切换）
- [ ] Day 5: 测试和优化Dashboard性能，配置自定义字段（公式表达式）

**验收标准**：
- ✅ Metabase可正常访问（http://localhost:3000）
- ✅ 所有B类/A类/C类数据表在Metabase中可见
- ✅ 业务概览Dashboard包含5个Question
- ✅ 筛选器和日/周/月切换功能正常工作
- ✅ Metabase直接查询原始表，无需视图层

### Phase 2: 前端集成和A类数据管理（2周）

**Week 1**：
- [ ] Day 1-2: 开发Metabase图表嵌入组件（MetabaseChart.vue）
- [ ] Day 3-4: 改造业务概览页面，集成Metabase图表
- [ ] Day 5: 测试浏览器兼容性和响应式布局

**Week 2**：
- [ ] Day 1-2: 开发目标管理增强界面（复制上月、批量计算）
- [ ] Day 3-4: 开发成本配置界面（可编辑表格）
- [ ] Day 5: 开发战役管理界面（类似目标管理）

**验收标准**：
- ✅ 业务概览页面成功集成Metabase图表
- ✅ 目标管理、成本配置、战役管理界面上线
- ✅ 所有CRUD操作通过测试
- ✅ 日/周/月切换和店铺筛选功能正常工作

### Phase 3: 人力管理模块和C类数据计算（2周）

**Week 1**：
- [ ] Day 1-2: 创建人力管理表结构（employees, employee_targets, attendance_records等）
- [ ] Day 3-4: 在Metabase中同步人力管理表
- [ ] Day 5: 验证中文字段名显示正常

**Week 2**：
- [ ] Day 1-2: 配置Metabase定时计算任务（每20分钟更新C类数据）
- [ ] Day 3-4: 创建员工绩效、提成计算Question
- [ ] Day 5: 验证定时任务正常运行，C类数据表正常更新

**验收标准**：
- ✅ 人力管理表结构创建完成
- ✅ Metabase定时计算任务正常运行（每20分钟更新一次）
- ✅ C类数据表正常更新（employee_performance, employee_commissions, shop_commissions）

### Phase 4: 测试、优化、文档（1周）

- [ ] Day 1-2: 端到端测试（E2E）
- [ ] Day 3: 性能优化和压力测试
- [ ] Day 4: 文档编写（用户手册+开发文档）
- [ ] Day 5: 团队培训和知识转移

**验收标准**：
- ✅ 所有测试用例通过（100%覆盖）
- ✅ 性能指标达标（API P95 < 500ms）
- ✅ 文档完整（README、API文档、用户手册）

### 回滚计划

如果Phase 1/2/3/4遇到严重问题，可按以下步骤回滚：

1. **保留Phase 0成果**：新表结构不影响现有功能，可保留
2. **禁用Metabase集成**：移除前端Metabase组件，恢复旧版图表
3. **回滚A类数据管理**：恢复Excel上传方式（保留3个月）
4. **数据完整性检查**：验证所有核心业务功能正常
5. **恢复旧表结构**：如果新系统有问题，可以恢复旧表结构（3个月内，仅生产环境）

## Open Questions（待解决问题）

1. **Metabase权限管理**：如何与现有用户系统集成？
   - **建议**：Phase 2实现JWT认证集成
   
2. **Metabase定时计算刷新时机**：除了定时任务，是否需要手动触发？
   - **建议**：提供API接口，前端添加"刷新数据"按钮，触发Metabase计算任务
   
3. **移动端适配**：Metabase图表是否支持移动端？
   - **建议**：Phase 4测试，Metabase原生支持响应式布局

4. **数据安全**：Metabase如何控制数据访问权限？
   - **建议**：使用Metabase Row Level Security（RLS）和用户组权限
   
5. **日/周/月切换实现**：如何在Metabase中实现粒度切换？
   - **建议**：使用Metabase Dashboard参数，通过URL参数传递granularity

## References（参考文档）

- [Metabase官方文档](https://www.metabase.com/docs/)
- [Metabase Embedding指南](https://www.metabase.com/docs/latest/embedding/introduction)
- [PostgreSQL物化视图最佳实践](https://www.postgresql.org/docs/current/rules-materializedviews.html)
- [SAP ERP架构参考](https://www.sap.com/products/erp.html)
- [Oracle ERP架构参考](https://www.oracle.com/erp/)

