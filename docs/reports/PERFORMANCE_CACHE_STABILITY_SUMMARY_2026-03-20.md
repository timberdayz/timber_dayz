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
   - 重复 `login + me/income` 通过
   - 单次登录后并发 `me/income` 通过
3. `nginx`：
   - 重复 `login + me/income` 通过
   - 单次登录后并发 `me/income` 通过

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

当前稳定长稳样本（`180s`，`30s` 间隔）：

1. `6/6` 轮成功
2. 整页成功率 `100%`
3. `page_p95_ms = 2049.86`
4. 分接口 `p95`
   - `comparison = 2049.22`
   - `kpi = 1426.69`
   - `operational_metrics = 1316.90`
   - `shop_racing = 824.99`
   - `traffic_ranking = 306.72`

说明：

- 当前长稳样本继续表明 `comparison` 与 `kpi` 是主要长尾来源
- 但整页成功率维持 `100%`

### 7. 系统监控接口与内部指标

本轮修复：

1. `/api/system/*` 路由改为复用现有 `require_admin`
2. 不再依赖错误的 `current_user.role == "admin"` 判断

对应测试：

- `backend/tests/test_system_monitoring.py`

真实管理员链路验证：

1. `POST /api/auth/login` 登录成功
2. `GET /api/system/resource-usage` 返回 `200`
3. `GET /api/system/executor-stats` 返回 `200`
4. `GET /api/system/db-pool-stats` 返回 `200`

当前已纳入长稳样本的内部指标：

1. 资源摘要来自 `business_overview_long_run_latest.json`
2. 当前 `180s` 样本峰值：
   - `cpu_peak = 6.0`
   - `memory_peak = 22.0`
   - `thread_peak = 7`
   - `sync_pool_checked_out_peak = 0`
   - `async_pool_checked_out_peak = 1`

连接池说明：

1. `overflow` 当前为负值，代表池容量仍有余量，并非真正溢出
2. 当前样本下未观察到连接池耗尽迹象

## 当前边界

目前可以较稳妥地确认：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. `MyIncome`

以上页面当前都已具备有效样本支撑。

## 仍未完全覆盖的边界

1. 更多高频页面仍可继续扩展
2. 更长时间窗口（例如 30min / 1h）仍可继续验证
3. `executor` 活跃任务数目前仍为 `N/A`

## 下一步优先级

1. 将当前脚本纳入固定回归流程
2. 扩展更多真实高频页面
3. 如需更深观察，补执行器活跃任务统计
