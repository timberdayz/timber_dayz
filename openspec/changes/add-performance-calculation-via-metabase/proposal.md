# Change: 绩效计算通过 Metabase SQL 实现

## Why

当前绩效管理存在以下问题：

1. **计算逻辑未实现**：`POST /api/performance/scores/calculate` 仅为 TODO 占位，使用固定 0 值写入，导致绩效公示页面所有得分显示为「—」
2. **SQL 与 Metabase 未利用**：业务概览、人员店铺归属已通过 Metabase Question（如 `business_overview_comparison`、`hr_shop_monthly_metrics`）实现 SQL 计算，绩效计算应沿用同一模式
3. **数据流向不清晰**：需明确绩效计算的读取表（订单、目标、配置）与写入表（`c_class.performance_scores`）

采用**方案 A**：在 Metabase 中编写 SQL Question 执行绩效计算，后端调用 Metabase 获取结果并写入 `c_class.performance_scores`，与现有 `hr_shop_monthly_metrics`、`business_overview_comparison` 的架构一致。

## 前置依赖（实现顺序）

- **须先完成 add-performance-and-personal-income 的 Phase 0（Public 表迁移至 A/C 类）**：本方案 SQL 与后端依赖 `a_class.sales_targets`、`a_class.target_breakdown`、`c_class.performance_scores`、`c_class.shop_health_scores` 已存在；若上述表仍在 `public`，则 Metabase Question 与 calculate 接口会因表不存在而失败。
- **推荐顺序**：先完成 add-performance-and-personal-income Phase 0（迁移 + 引用更新 + 验证），再实施本提案。

## What Changes

### 1. 新增 Metabase Question：performance_scores_calculation

- **SQL 文件**：`sql/metabase_questions/performance_scores_calculation.sql`
- **参数**：`{{month}}`（YYYY-MM-DD，月初日期）
- **数据源**：
  - `{{MODEL:Orders Model}}`：销售额、利润（与 hr_shop_monthly_metrics 一致）
  - `a_class.target_breakdown`、`a_class.sales_targets`：销售额目标
  - `public.performance_config`：得分比例（sales_max_score、profit_max_score 等）— **注意**：该表当前在 public schema
  - `c_class.shop_health_scores`（可选）：运营得分
  - `public.dim_shops`：**必须 INNER JOIN**，确保返回的 (platform_code, shop_id) 满足 `c_class.performance_scores` 外键约束
- **返回**：按店铺返回 platform_code、shop_id、shop_name、sales_target、sales_achieved、sales_rate、sales_score、profit_*、key_product_*、operation_score、total_score
- **得分规则**：达成率 > 100% 得满分，≤ 100% 得 达成率 × 满分

### 2. 配置 Metabase

- 在 `config/metabase_config.yaml` 的 `questions` 中注册 `performance_scores_calculation`
- **Collection**：`C类数据报表/人力资源`（与 hr_shop_monthly_metrics 一致）
- 运行 `python scripts/init_metabase.py` 在 Metabase 中创建 Question
- 在 `backend/services/metabase_question_service.py` 中增加 `performance_scores_calculation` 的 question_ids

### 3. 后端 calculate 接口实现

- `POST /api/performance/scores/calculate` 改为：
  1. **config_id**：若传入则使用指定配置，否则使用**考核周期内生效**的配置（`effective_from <= period_end AND (effective_to IS NULL OR effective_to >= period_start)`）
  2. 调用 Metabase `performance_scores_calculation` Question（传入 `month=period + "-01"`）
  3. 遍历返回结果，**解析时兼容英文/中文列名**（与 hr_shop_monthly_metrics 调用方一致）
  4. 对每行 INSERT 或 UPDATE `c_class.performance_scores`（SQL 已通过 INNER JOIN dim_shops 保证 FK 有效）
  5. 按 total_score 降序计算 rank、performance_coefficient 并写入

### 4. 数据流不变

- **读取**：Metabase SQL 从 b_class 订单表、a_class.target_breakdown、a_class.sales_targets、public.performance_config、c_class.shop_health_scores、public.dim_shops 读取
- **写入**：后端仅写入 `c_class.performance_scores`
- **展示**：`GET /api/performance/scores` 继续从 `c_class.performance_scores` 读取（与 platform_accounts 合并）

## Impact

### 受影响的规格

- **hr-management**：MODIFIED - 绩效计算数据源与流程

### 受影响的代码与数据

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| SQL | `sql/metabase_questions/performance_scores_calculation.sql` | 新建 - 绩效计算 SQL，**INNER JOIN dim_shops** |
| 配置 | `config/metabase_config.yaml` | 新增 performance_scores_calculation Question，collection: C类数据报表/人力资源 |
| 服务 | `backend/services/metabase_question_service.py` | 新增 question_ids（month 参数已有支持） |
| 路由 | `backend/routers/performance_management.py` | 实现 calculate_performance_scores：考核周期内生效配置、Metabase 调用、中英文列名兼容 |
| 环境 | `.env.example` | 可选：`METABASE_QUESTION_PERFORMANCE_SCORES_CALCULATION=0` |

### 数据表汇总

| 操作 | Schema | 表 | 说明 |
|------|--------|-----|------|
| **读取** | b_class | fact_*_orders_* | 通过 Orders Model |
| **读取** | a_class | target_breakdown | 店铺目标分解 |
| **读取** | a_class | sales_targets | 目标主表 |
| **读取** | public | performance_config | 得分比例（当前在 public） |
| **读取** | public | dim_shops | **必须 JOIN**，保证 FK 有效 |
| **读取** | c_class | shop_health_scores | 运营得分（可选） |
| **写入** | c_class | performance_scores | 后端 calculate 写入 |

## 成功标准

- [ ] Metabase Question `performance_scores_calculation` 可被 init_metabase 创建
- [ ] `POST /api/performance/scores/calculate?period=YYYY-MM` 调用 Metabase 并正确写入 `c_class.performance_scores`
- [ ] 绩效公示页面展示非空得分（在有订单与目标数据的前提下）
- [ ] 得分规则符合：达成率 > 100% 得满分，≤ 100% 得 达成率 × 满分
- [ ] 历史月份计算时使用该月份生效的配置（非今日生效）

## 非目标（Non-Goals）

- 不修改绩效公示/绩效管理的展示逻辑（仍从 performance_scores 读取）
- 不实现重点产品目标/达成（若暂无数据源，先返回 0 或 null）
- 不迁移或修改 performance_config 表结构
