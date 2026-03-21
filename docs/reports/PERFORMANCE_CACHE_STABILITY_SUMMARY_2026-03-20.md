# 性能与缓存稳定性结论
日期：2026-03-20

## 当前已确认结论

### 1. 核心页面与缓存基线仍然成立
以下页面当前已有可复验样本支撑：
1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. `MyIncome`

其中：
1. `annual-summary/*` 的缓存与 singleflight 链路已统一
2. 核心看板冷缓存并发结论仍成立
3. `MyIncome` 修复后已重新纳入稳定结论

### 2. `MyIncome` 的真实根因已经修复
根因不是收入查询，而是认证链路：
1. 高频登录时 token 可能在同秒内重复
2. 旧逻辑 `session_id = sha256(access_token)` 会撞 `user_sessions.session_id` 唯一键
3. 后续表现才退化为 `401` 或偶发 `500`

修复：
1. 为 access token 和 refresh token 增加唯一 `jti`

正式样本：
1. `temp/outputs/my_income_page_retest_1774024014.json`

结果：
1. `backend:8001` `20/20` 成功
2. `nginx` `20/20` 成功

### 3. 读写混合压测当前通过
结果文件：
1. `temp/outputs/performance_mixed_1773996562.json`

当前结论：
1. `backend` 链路 `10/10` 成功
2. `nginx` 链路 `10/10` 成功
3. 当前低风险写流量没有击穿核心读链路

### 4. `BusinessOverview` 子接口与长稳样本当前稳定
子接口探针：
1. `scripts/business_overview_split_probe.py`
2. `temp/outputs/business_overview_split_probe_latest.json`

当前结论：
1. `comparison` 仍是最慢子接口
2. `kpi` 次慢
3. 当前样本内所有子接口均返回 `200`

长稳脚本：
1. `scripts/business_overview_long_run.py`
2. `temp/outputs/business_overview_long_run_latest.json`

当前稳定长稳样本（`180s`，`30s` 间隔）：
1. `6/6` 轮成功
2. `page_success_rate = 100%`
3. `page_p95_ms = 2049.86`

### 5. 系统监控与连接池内部指标已纳入样本
修复：
1. `/api/system/*` 路由统一改为复用 `require_admin`

当前已纳入的内部指标：
1. `cpu_peak`
2. `memory_peak`
3. `thread_peak`
4. `sync_pool_checked_out_peak`
5. `async_pool_checked_out_peak`
6. `sync_pool_overflow_peak`
7. `async_pool_overflow_peak`

### 6. 统一性能回归入口已经落地
统一入口：
1. `scripts/verify_performance_regression.py`

当前能力：
1. `ci` 模式
   - 统一执行性能专项相关 pytest
   - 生成摘要文件 `temp/outputs/performance_regression_summary_latest.json`
2. `local` 模式
   - 统一执行 pytest 集合
   - 执行 `high_frequency_pages_probe.py`
   - 执行 `business_overview_split_probe.py`
   - 执行 `business_overview_long_run.py`

CI 接入：
1. `.github/workflows/ci.yml`
2. 当前仅在 `Python 3.11` 矩阵上执行轻量 `--mode ci`

最新本地统一回归摘要：
1. `temp/outputs/performance_regression_summary_latest.json`
2. 当前 `all_passed = true`

## 扩展后的高频页面覆盖

新增页面探针：
1. `scripts/high_frequency_pages_probe.py`

最新结果文件：
1. `temp/outputs/high_frequency_pages_probe_latest.json`

当前已纳入统一入口的真实页面：
1. `UserManagement`
2. `UserApproval`
3. `RoleManagement`
4. `AccountManagement`
5. `DataSyncFiles`
6. `DataQuarantine`
7. `CollectionTasks`
8. `CollectionHistory`
9. `SystemNotifications`
10. `Sessions`
11. `NotificationPreferences`
12. `SystemConfig`
13. `DatabaseConfig`
14. `SecuritySettings`
15. `SystemLogs`
16. `DataBackup`
17. `SystemMaintenance`
18. `AccountAlignment`
19. `NotificationConfig`

当前 `5` 轮样本结论：
1. 上述页面对应请求全部返回 `200`
2. 当前成功率均为 `100%`
3. `DataQuarantine` 已完成 legacy schema 与 `NULL` 过滤兼容修复
4. `Sessions` 已完成响应序列化修复
5. `UserApproval` 已完成路由匹配修复
6. `AccountAlignment` 已完成空源兼容与前端安全返回结构修复
7. `NotificationConfig` 已完成无 SMTP 配置环境下的默认空态修复

## 当前边界
目前可以较稳妥地确认：
1. 核心页面读路径、缓存路径和统一回归入口都已具备有效样本支撑
2. 新增 19 个真实高频页面当前都已纳入本地统一回归
3. `backend` 与 `nginx` 两条链路的关键页面样本都已有正向结果

## 仍未完全覆盖的边界
1. `AccountAlignment` 当前虽然可稳定加载，但当前环境下没有可用 legacy 订单源，因此仍是“空态样本”，不是完整业务数据样本
2. `NotificationConfig` 当前虽然可稳定加载，但当前环境下没有 SMTP 配置，因此仍是“默认空态样本”，不是非空配置样本
3. 更多真实高频页面仍可继续纳入统一入口
4. 更长时间窗口，例如 `30min` 或 `1h`，仍值得继续扩展
5. `executor` 活跃任务维度目前仍未形成稳定样本口径

## 下一步建议
1. 继续扩更多真实高频页面到统一回归入口
2. 若要让 `AccountAlignment` 形成真实业务样本，需要进一步接入当前 DSS 订单源，而不只是空态兼容
3. 若要让 `NotificationConfig` 形成真实业务样本，需要准备一套非空 SMTP 配置样本
4. 如需更强保障，将 `local` live 探针纳入预发或夜间定时回归
5. 如需更深资源观测，继续补 `executor` 活跃任务统计
