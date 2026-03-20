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
4. `MyIncome` 在修复前样本中出现失败，但该失败现已定位为登录链路问题，不再直接归因于 `/api/hr/me/income` 本身

#### nginx 链路

结果文件：

- `temp/outputs/performance_full_pages_1773996601.json`

有效结论：

1. `BusinessOverview` 成功
2. `AnnualSummary` 成功
3. `PerformanceDisplay` 成功
4. `MyIncome` 修复前样本中失败，但同样已定位为登录链路问题

### 3. 读写混合压测

结果文件：

- `temp/outputs/performance_mixed_1773996562.json`

当前结论：

1. `backend` 链路 `10/10` 迭代成功
2. `nginx` 链路 `10/10` 迭代成功
3. 当前低风险写流量没有击穿核心读路径

### 4. MyIncome 失败根因

本轮新增确认的根因：

1. `/api/hr/me/income` 本身不能稳定复现业务错误
2. 问题出在登录链路
3. `POST /api/auth/login` 在高频登录时会偶发 `500`
4. 根因是会话记录使用：
   - `session_id = sha256(access_token)`
5. 由于 token 在同秒内可重复生成，导致不同登录请求生成相同的 `session_id`
6. 最终触发：
   - `user_sessions.session_id` 唯一键冲突
7. 登录失败后，后续压测请求退回到无效 token，才出现 `401`

修复方式：

1. 为 access token 和 refresh token 增加唯一 `jti`
2. 从根源上消除同秒重复 token 导致的会话 ID 冲突

修复后验证：

1. 新增回归测试：
   - `backend/tests/test_auth_token_uniqueness.py`
2. 连续创建同一用户 token 现在已唯一
3. `20` 个并发 `login + me/income` 回归验证：
   - `backend`：`20/20` 成功
   - `nginx`：`20/20` 成功

### 5. 长时间稳定性

已有样本：

- `temp/outputs/performance_long_run_1773997324.json`

当前状态：

1. `10min` backend 长稳样本曾显示成功率下降与长尾放大
2. 但在服务器日志中，本轮对应时间窗口没有发现同等级的 `business-overview` 5xx/503 证据
3. 当前更合理的判断是：
   - 该问题仍未闭环
   - 需要用稳定压测脚本重新复验
   - 不能直接据此下最终产品结论

## 当前边界

目前可以较稳妥地确认：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`

以上页面在 `backend` 与 `nginx` 下都已有成功样本。

以下范围仍需继续确认：

1. 修复后 `MyIncome` 的正式整页压测样本
2. `backend` 的 10 分钟以上长稳复验
3. 连接池内部指标与更细粒度资源曲线

## 下一步优先级

1. 用修复后的登录链路重新跑 `MyIncome` 整页高并发样本
2. 用稳定脚本重新跑 `backend` 长稳样本，确认此前退化是否为脚本侧噪声
3. 打通系统监控接口或补充更准确的连接池观测
