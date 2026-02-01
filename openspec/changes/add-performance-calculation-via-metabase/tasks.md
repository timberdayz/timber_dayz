# Tasks: 绩效计算 Metabase 方案

## 1. Metabase Question

- [ ] 1.1 创建 `sql/metabase_questions/performance_scores_calculation.sql`
  - [ ] 1.1.1 参数 CTE：`params as (select {{month}}::date as target_date)`
  - [ ] 1.1.2 周期 CTE：`period_scope`（period_start、period_end）
  - [ ] 1.1.3 店铺销售额/利润：从 `{{MODEL:Orders Model}}` 聚合（与 hr_shop_monthly_metrics 一致）
  - [ ] 1.1.4 店铺目标：从 `a_class.target_breakdown` + `a_class.sales_targets` 获取
  - [ ] 1.1.5 得分比例：从 `public.performance_config` 获取 sales_max_score 等（考核周期内生效：effective_from <= period_end AND (effective_to IS NULL OR effective_to >= period_start)）
  - [ ] 1.1.6 **INNER JOIN public.dim_shops**：仅返回 (platform_code, shop_id) 存在于 dim_shops 的店铺，保证 FK 有效
  - [ ] 1.1.7 计算 sales_rate、profit_rate、sales_score、profit_score（达成率>100%得满分，≤100%得达成率×满分）
  - [ ] 1.1.8 key_product_target/key_product_achieved/key_product_score 暂返回 0（无数据源）
  - [ ] 1.1.9 operation_score：从 `c_class.shop_health_scores` 聚合（可选）或 0
  - [ ] 1.1.10 total_score = sales_score + profit_score + key_product_score + operation_score
  - [ ] 1.1.11 返回 platform_code、shop_id、shop_name、sales_target、sales_achieved、sales_rate、sales_score、profit_*、key_product_*、operation_score、total_score

- [ ] 1.2 在 `config/metabase_config.yaml` 中注册 Question 与 Collection
  - [ ] 1.2.1 若 `collections` 中无 "C类数据报表/人力资源"，则新增（hr_shop_monthly_metrics 已使用该 collection）
  - [ ] 1.2.2 在 `questions` 中新增 performance_scores_calculation：name、display_name、description、sql_file、collection: "C类数据报表/人力资源"
  - [ ] 1.2.3 添加 parameters: month (date, required)

- [ ] 1.3 运行 `python scripts/init_metabase.py` 在 Metabase 中创建 Question（或手动创建后配置环境变量）

## 2. 后端 Metabase 服务

- [ ] 2.1 在 `backend/services/metabase_question_service.py` 的 `question_ids` 中新增 `"performance_scores_calculation": int(os.getenv("METABASE_QUESTION_PERFORMANCE_SCORES_CALCULATION", "0"))`
  - [ ] 2.1.1 `_convert_params` 已支持 month 参数（与 hr_shop_monthly_metrics 相同），无需修改
  - [ ] 2.1.2 init_metabase 会从 config 创建 Question；若按名称查 ID 失败，配置 `METABASE_QUESTION_PERFORMANCE_SCORES_CALCULATION`

## 3. 后端 calculate 接口

- [ ] 3.1 修改 `backend/routers/performance_management.py` 的 `calculate_performance_scores`
  - [ ] 3.1.1 获取配置：若传入 config_id 则用指定配置；否则按**考核周期**筛选 `public.performance_config`（effective_from <= period_end AND (effective_to IS NULL OR effective_to >= period_start)），取最新一条；校验存在，返回 404 若不存在
  - [ ] 3.1.2 调用 `get_metabase_service().query_question("performance_scores_calculation", {"month": period + "-01"})`
  - [ ] 3.1.3 遍历返回结果（list of dict），对每行**兼容英文/中文列名**（platform_code 或 平台、shop_id 或 店铺ID 等）
  - [ ] 3.1.4 解析 platform_code、shop_id、period、sales_target、sales_achieved、sales_rate、sales_score、profit_*、key_product_*、operation_score、total_score
  - [ ] 3.1.5 查询 `c_class.performance_scores` 是否存在 (platform_code, shop_id, period)，INSERT 或 UPDATE
  - [ ] 3.1.6 对写入的 scores 按 total_score 降序计算 rank、performance_coefficient 并更新
  - [ ] 3.1.5 计算 performance_coefficient 并更新
  - [ ] 3.1.7 commit 并返回成功信息
  - [ ] 3.1.8 try/except 捕获 Metabase 调用失败，返回明确错误

## 4. 环境与配置

- [ ] 4.1 在 `.env.example` 中添加 `METABASE_QUESTION_PERFORMANCE_SCORES_CALCULATION=0`（可选兜底）
- [ ] 4.2 确认 Metabase 已配置且 Orders Model 可用

## 5. 验证

- [ ] 5.1 执行 `POST /api/performance/scores/calculate?period=YYYY-MM`，确认返回成功
- [ ] 5.2 查询 `c_class.performance_scores` 确认有非零数据（在有订单与目标数据的前提下）
- [ ] 5.3 绩效公示页面展示得分
- [ ] 5.4 得分规则验证：达成率 > 100% 得满分，≤ 100% 得 达成率 × 满分
- [ ] 5.5 历史月份（如 2024-06）计算时，使用该月份生效的配置，而非今日配置
