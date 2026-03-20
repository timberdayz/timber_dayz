# 性能与缓存稳定性结论

日期：2026-03-20

## 已完成验证

### 1. 既有缓存稳定性结论

本轮继续沿用并确认此前已经成立的结论：

1. `annual-summary/target-completion` 的真实 500 根因已修复
2. `annual-summary/*` 已统一到同一套缓存与 singleflight 实现
3. 年度汇总冷缓存整页并发在此前样本下已恢复稳定

### 2. 高频页面整页压测

本轮新增覆盖的真实高频页面：

1. `BusinessOverview`
2. `AnnualSummary`
3. `PerformanceDisplay`
4. `MyIncome`

#### backend 链路

结果文件：

- `temp/outputs/performance_full_pages_1773992062.json`

关键结果（`20` 并发页面）：

1. `BusinessOverview`
   - `20/20` 页面成功
   - `page_p95_ms = 4602.52`

2. `AnnualSummary`
   - `20/20` 页面成功
   - `page_p95_ms = 2396.22`

3. `PerformanceDisplay`
   - `20/20` 页面成功
   - `page_p95_ms = 215.73`

4. `MyIncome`
   - `20/20` 页面成功
   - `page_p95_ms = 212.21`

结论：

- 在 `backend` 链路下，这 4 个页面已有一轮有效整页成功样本。

#### nginx 链路

结果文件：

- `temp/outputs/performance_full_pages_1773996601.json`

关键结果（`20` 并发页面）：

1. `BusinessOverview`
   - `20/20` 页面成功
   - `page_p95_ms = 304.60`

2. `AnnualSummary`
   - `20/20` 页面成功
   - `page_p95_ms = 204.59`

3. `PerformanceDisplay`
   - `20/20` 页面成功
   - `page_p95_ms = 228.26`

4. `MyIncome`
   - `0/20` 页面成功
   - `backend` 直连样本中对应失败状态为 `401`
   - `nginx` 样本中出现请求超时，状态统计为 `0`

结论：

- `nginx` 链路已补上正式样本
- 但 `MyIncome` 在整页高并发下不能视为稳定，当前属于明确失败项

### 3. 读写混合压测

#### backend + nginx 混合结果

结果文件：

- `temp/outputs/performance_mixed_1773996562.json`

场景：

- 读侧复用高频核心读接口
- 写侧使用 `POST /api/hr/income/calculate?year_month=2026-03`

关键结果：

1. `backend`
   - `10/10` 迭代成功
   - `iteration_p95_ms = 1575.22`

2. `nginx`
   - `10/10` 迭代成功
   - `iteration_p95_ms = 218.59`

结论：

- 当前读写混合样本下，两条链路都保持 `100%` 成功率
- 说明轻量写流量并未在本轮样本中击穿核心读路径

### 4. 长时间稳定性与资源曲线

#### 60 秒样本

结果文件：

- `temp/outputs/performance_long_run_1773992333.json`
- `temp/outputs/performance_long_run_1773996700.json`

结论：

- 短时间样本下未观察到明显线程数持续爬升
- 但 `backend` 链路 60 秒样本已经出现成功率下降迹象

#### 10 分钟 backend 长稳样本

结果文件：

- `temp/outputs/performance_long_run_1773997324.json`

关键结果：

1. 持续时长：`600s`
2. 采样间隔：`30s`
3. 样本数：`16`
4. 页面成功率：`87.5%`
5. `page_p95_ms = 42400.72`
6. `cpu_peak = 31.1`
7. `memory_peak = 0.62649%`
8. `thread_peak = 83`

结论：

- 10 分钟持续访问样本下，`backend` 链路不能继续视为“长稳完全通过”
- 主要问题不是内存或线程持续爬升，而是页面成功率下降和长尾延迟明显放大
- 当前更像是请求链路或上游依赖在长时间访问下出现间歇性退化

## 当前总体结论

现在可以确认：

1. `BusinessOverview`、`AnnualSummary`、`PerformanceDisplay` 在 `backend` 与 `nginx` 链路下都已有成功整页样本
2. `MyIncome` 不能纳入“高并发整页稳定”结论
3. 读写混合压测在两条链路下都通过了当前样本
4. 60 秒以内短样本可以得到基本稳定结论
5. 10 分钟 `backend` 长稳样本暴露了新的稳定性问题，当前不能宣布长稳通过

## 风险与边界

这份结论目前不等同于：

1. 全系统所有高频页面都已稳定
2. `MyIncome` 页面已经稳定
3. `backend` 长时间持续访问已经稳定
4. 连接池内部曲线已经完整采集

## 下一步优先级

1. 优先排查 `MyIncome` 在高并发整页场景下的认证/超时问题
2. 复盘 `10min` backend 长稳样本中的失败点与长尾来源
3. 打通系统监控 API 或补充更精确的后端内部资源指标
