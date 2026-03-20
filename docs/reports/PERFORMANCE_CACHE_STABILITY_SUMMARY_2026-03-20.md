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

有效样本结果文件：

- `temp/outputs/performance_full_pages_1773992062.json`

有效结论：

1. `BusinessOverview` 成功
2. `AnnualSummary` 成功
3. `PerformanceDisplay` 成功
4. `MyIncome` 修复前样本中出现失败，但该失败已确认来自登录链路，而不是 `/api/hr/me/income` 自身逻辑

#### nginx 链路

结果文件：

- `temp/outputs/performance_full_pages_1773996601.json`

有效结论：

1. `BusinessOverview` 成功
2. `AnnualSummary` 成功
3. `PerformanceDisplay` 成功
4. `MyIncome` 修复前样本中失败，但同样已确认来自登录链路

### 3. 读写混合压测

结果文件：

- `temp/outputs/performance_mixed_1773996562.json`

当前结论：

1. `backend` 链路 `10/10` 迭代成功
2. `nginx` 链路 `10/10` 迭代成功
3. 当前低风险写流量没有击穿核心读路径

### 4. MyIncome 失败根因与修复

本轮新增确认的根因：

1. `/api/hr/me/income` 手工请求可稳定返回 `200`
2. 单 token 并发访问 `/api/hr/me/income` 可稳定返回 `200`
3. 高频登录时 `POST /api/auth/login` 会偶发 `500`
4. 根因是会话记录使用：
   - `session_id = sha256(access_token)`
5. 由于 token 在同秒内可重复生成，导致不同登录请求生成相同的 `session_id`
6. 最终触发：
   - `user_sessions.session_id` 唯一键冲突
7. 登录失败后，后续压测请求退回到无效 token，才表现为 `401`

修复方式：

1. 在 access token 和 refresh token 中加入唯一 `jti`
2. 从根源上消除重复 token 导致的会话 ID 冲突

修复后验证：

1. 回归测试：
   - `backend/tests/test_auth_token_uniqueness.py`
2. `backend`：
   - `10` 次重复 `login + me/income` 全部 `200`
   - 单次登录后 `10` 并发 `me/income` 全部 `200`
3. `nginx`：
   - `10` 次重复 `login + me/income` 全部 `200`
   - 单次登录后 `10` 并发 `me/income` 全部 `200`

### 5. BusinessOverview 子接口拆分压测

本轮新增拆分探针：

- `scripts/business_overview_split_probe.py`

对应测试：

- `backend/tests/test_business_overview_split_probe.py`

结果文件：

- `temp/outputs/business_overview_split_probe_latest.json`

当前 `20` 轮拆分样本结论：

1. `comparison`
   - 是当前最慢的子接口
   - 首轮冷启动样本约 `2721.75ms`
   - 当前 `20` 轮汇总 `p95_ms = 143.68`

2. `kpi`
   - 次慢
   - 首轮冷启动样本约 `1920.63ms`
   - 当前 `20` 轮汇总 `p95_ms = 104.13`

3. 其余接口
   - `shop_racing` `p95_ms = 60.47`
   - `traffic_ranking` `p95_ms = 25.48`
   - `operational_metrics` `p95_ms = 99.07`

4. 所有拆分接口当前样本下均为 `200`
5. 在本轮拆分样本里没有复现此前 `10min` 样本中的 40 秒级长尾

### 6. 长时间稳定性

已有样本：

- `temp/outputs/performance_long_run_1773997324.json`

当前状态：

1. 旧的 `10min` backend 长稳样本显示：
   - 页面成功率 `87.5%`
   - `page_p95_ms = 42400.72`
2. 但本轮新的子接口拆分探针没有复现同级别长尾
3. 因此目前更合理的判断是：
   - 旧样本仍需复验
   - 当前不能直接把它作为已确认的服务端长期稳定性缺陷
   - 需要用稳定脚本重新构造长稳样本

## 当前边界

目前可以较稳妥地确认：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. 修复后的 `MyIncome` 认证链路

以上范围已经具备较强证据支撑。

以下范围仍需继续确认：

1. 修复后 `MyIncome` 的正式整页样本回补
2. `backend` 的稳定长稳复验
3. 连接池内部指标与更细粒度资源曲线

## 下一步优先级

1. 用修复后的登录链路重跑 `MyIncome` 正式整页样本
2. 用稳定的长稳脚本重跑 `backend` 长稳
3. 如需继续深挖，优先盯 `comparison` 与 `kpi`
