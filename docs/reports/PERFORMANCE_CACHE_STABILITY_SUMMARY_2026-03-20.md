# 性能与缓存稳定性结论

日期：2026-03-20

## 当前已确认结论

### 1. 年度汇总缓存链路

以下结论继续成立：

1. `annual-summary/target-completion` 的真实 500 根因已修复
2. `annual-summary/*` 已统一到同一套缓存与 singleflight 实现
3. 年度汇总整页冷缓存并发样本已经恢复稳定

### 2. 核心高频页面整页压测

核心高频页面：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. `MyIncome`

当前结论：

1. `backend` 与 `nginx` 下核心页面已有稳定样本
2. `MyIncome` 曾经的失败已确认来自登录链路，修复后已回补正式样本

### 3. MyIncome 认证链路修复与正式回补样本

根因：

1. 高频登录时 `POST /api/auth/login` 会偶发 `500`
2. 根因是 `user_sessions.session_id` 冲突
3. 冲突来自：
   - `session_id = sha256(access_token)`
   - 同秒内 token 可重复生成

修复：

1. 在 access token 和 refresh token 中加入唯一 `jti`

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

- `MyIncome` 当前可以重新纳入稳定结论

### 4. 读写混合压测

结果文件：

- `temp/outputs/performance_mixed_1773996562.json`

当前结论：

1. `backend` 链路 `10/10` 迭代成功
2. `nginx` 链路 `10/10` 迭代成功
3. 当前低风险写流量没有击穿核心读路径

### 5. BusinessOverview 子接口拆分压测

探针：

- `scripts/business_overview_split_probe.py`

结果文件：

- `temp/outputs/business_overview_split_probe_latest.json`

当前 `20` 轮样本结论：

1. `comparison` 最慢
2. `kpi` 次慢
3. 当前样本下所有子接口均返回 `200`

### 6. BusinessOverview 稳定长稳复验

稳定长稳脚本：

- `scripts/business_overview_long_run.py`

结果文件：

- `temp/outputs/business_overview_long_run_latest.json`

当前稳定长稳样本（`180s`，`30s` 间隔）：

1. `6/6` 轮成功
2. 整页成功率 `100%`
3. `page_p95_ms = 2049.86`
4. 当前主要长尾来源仍是：
   - `comparison`
   - `kpi`

### 7. 系统监控接口与内部指标

修复：

1. `/api/system/*` 路由改为统一复用 `require_admin`

当前已纳入样本的内部指标：

1. `cpu_peak`
2. `memory_peak`
3. `thread_peak`
4. `sync/async pool checked_out`
5. `sync/async pool overflow`

### 8. 扩展后的真实页面覆盖

新增页面探针：

- `scripts/high_frequency_pages_probe.py`

结果文件：

- `temp/outputs/high_frequency_pages_probe_latest.json`

当前已接入统一回归入口的下一批真实页面：

1. `UserManagement`
2. `DataSyncFiles`
3. `CollectionTasks`
4. `CollectionHistory`
5. `SystemNotifications`

当前 `3` 轮样本结论：

1. `UserManagement`
   - 成功率 `100%`
   - `p95_ms = 47.89`

2. `DataSyncFiles`
   - 成功率 `100%`
   - `p95_ms = 100.52`

3. `CollectionTasks`
   - 成功率 `100%`
   - `p95_ms = 37.93`

4. `CollectionHistory`
   - 成功率 `100%`
   - `p95_ms = 49.97`

5. `SystemNotifications`
   - 成功率 `100%`
   - `p95_ms = 48.29`

### 9. 固定回归入口

统一入口：

- `scripts/verify_performance_regression.py`

当前能力：

1. `ci` 模式
   - 统一运行性能专项相关测试
   - 生成摘要文件：
     - `temp/outputs/performance_regression_summary_latest.json`

2. `local` 模式
   - 统一运行：
     - 测试集合
     - 下一批真实高频页面探针
     - `BusinessOverview` 拆分探针
     - `BusinessOverview` 长稳脚本

CI 接入：

- `.github/workflows/ci.yml`

当前接入方式：

1. 在现有 pytest 后新增轻量性能回归入口步骤
2. 仅在 `Python 3.11` 矩阵上执行
3. 默认使用 `--mode ci`

本地验证：

1. `python scripts/verify_performance_regression.py --mode ci`
2. `python scripts/verify_performance_regression.py --mode local`
3. 当前 local 摘要显示所有步骤通过

## 当前边界

目前可以较稳妥地确认：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. `MyIncome`
5. `UserManagement`
6. `DataSyncFiles`
7. `CollectionTasks`
8. `CollectionHistory`
9. `SystemNotifications`

以上页面当前都已具备有效样本支撑。

## 仍未完全覆盖的边界

1. 更多高频页面仍可继续扩展
2. 更长时间窗口（例如 30min / 1h）仍可继续验证
3. `executor` 活跃任务数目前仍为 `N/A`

## 下一步优先级

1. 继续扩展更多真实高频页面到统一回归入口
2. 如需更强保障，将 `local` live 探针纳入更完整的预发/夜间回归
3. 如需更深观察，补执行器活跃任务统计
