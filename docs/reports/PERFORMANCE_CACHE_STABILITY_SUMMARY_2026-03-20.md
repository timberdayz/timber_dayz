# 性能与缓存稳定性结论

日期：2026-03-20

## 当前已确认结论

### 1. 年度汇总缓存链路

以下结论继续成立：

1. `annual-summary/target-completion` 的真实 500 根因已修复
2. `annual-summary/*` 已统一到同一套缓存与 singleflight 实现
3. 年度汇总整页冷缓存并发样本已经恢复稳定

### 2. 高频页面整页压测

已纳入样本的真实高频页面：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. `MyIncome`

#### backend 链路

已有整页样本：

- `temp/outputs/performance_full_pages_1773992062.json`

有效结论：

1. `BusinessOverview` 成功
2. `AnnualSummary` 成功
3. `PerformanceDisplay` 成功
4. `MyIncome` 旧样本中的失败已被证实来自登录链路，而非接口自身逻辑

#### nginx 链路

已有整页样本：

- `temp/outputs/performance_full_pages_1773996601.json`

有效结论：

1. `BusinessOverview` 成功
2. `AnnualSummary` 成功
3. `PerformanceDisplay` 成功
4. `MyIncome` 旧样本中的失败同样已被证实来自登录链路

### 3. MyIncome 认证链路修复与正式回补样本

根因：

1. 高频登录时 `POST /api/auth/login` 会偶发 `500`
2. 根因是 `user_sessions.session_id` 冲突
3. 冲突来自：
   - `session_id = sha256(access_token)`
   - 同秒内 token 可重复生成

修复：

1. 在 access token 和 refresh token 中加入唯一 `jti`

回归验证：

1. 回归测试：
   - `backend/tests/test_auth_token_uniqueness.py`
2. `backend`：
   - `10` 次重复 `login + me/income` 全部 `200`
   - 单次登录后 `10` 并发 `me/income` 全部 `200`
3. `nginx`：
   - `10` 次重复 `login + me/income` 全部 `200`
   - 单次登录后 `10` 并发 `me/income` 全部 `200`

正式回补样本：

- `temp/outputs/my_income_page_retest_1774024014.json`

结果：

1. `backend:8001`
   - `20/20` 成功
   - 成功率 `100%`

2. `nginx`
   - `20/20` 成功
   - 成功率 `100%`

结论：

- `MyIncome` 当前可以重新纳入高频页面稳定结论

### 4. 读写混合压测

结果文件：

- `temp/outputs/performance_mixed_1773996562.json`

当前结论：

1. `backend` 链路 `10/10` 迭代成功
2. `nginx` 链路 `10/10` 迭代成功
3. 当前低风险写流量没有击穿核心读路径

### 5. BusinessOverview 子接口拆分压测

新增探针：

- `scripts/business_overview_split_probe.py`

对应测试：

- `backend/tests/test_business_overview_split_probe.py`

结果文件：

- `temp/outputs/business_overview_split_probe_latest.json`

当前 `20` 轮样本结论：

1. `comparison`
   - 最慢
   - 首轮冷启动约 `2721.75ms`
   - 汇总 `p95_ms = 143.68`

2. `kpi`
   - 次慢
   - 首轮冷启动约 `1920.63ms`
   - 汇总 `p95_ms = 104.13`

3. 其余接口
   - `shop_racing` `p95_ms = 60.47`
   - `traffic_ranking` `p95_ms = 25.48`
   - `operational_metrics` `p95_ms = 99.07`

4. 所有接口当前样本下均为 `200`

### 6. BusinessOverview 稳定长稳复验

新增稳定长稳脚本：

- `scripts/business_overview_long_run.py`

对应测试：

- `backend/tests/test_business_overview_long_run.py`

结果文件：

- `temp/outputs/business_overview_long_run_latest.json`

当前 `10min` 样本（`600s`，`30s` 间隔）：

1. `20/20` 轮成功
2. 整页成功率 `100%`
3. `page_p95_ms = 2585.95`
4. 分接口 `p95`
   - `comparison = 2585.36`
   - `kpi = 1739.57`
   - `operational_metrics = 1572.84`
   - `shop_racing = 843.26`
   - `traffic_ranking = 204.02`

### 7. 对旧 10 分钟样本的结论修正

旧结果文件：

- `temp/outputs/performance_long_run_1773997324.json`

旧结论显示：

1. 页面成功率 `87.5%`
2. `page_p95_ms = 42400.72`

但在新的稳定脚本下没有复现同等级别长尾或失败，因此当前更合理的判断是：

1. 旧 `10min` 样本不能继续作为当前基线结论
2. 新的稳定长稳脚本结果应替代旧样本成为当前基线

## 当前边界

目前可以较稳妥地确认：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. `MyIncome`

以上页面当前都已具备有效样本支撑。

## 仍未完全覆盖的边界

1. 连接池内部指标仍未完整采集
2. 更多高频页面仍可继续扩展
3. 更长时间窗口（例如 30min / 1h）仍可继续验证

## 下一步优先级

1. 打通系统监控接口或补更准确的连接池采样
2. 扩展更多真实高频页面
3. 将当前脚本纳入固定回归流程
