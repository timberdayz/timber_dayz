# 性能与缓存稳定性结论

日期：2026-03-20

## 本轮完成内容

1. 修复了 `annual-summary/target-completion` 的真实 500 根因
   - 补上 fallback 查询前的 `rollback()`
   - 将 fallback SQL 恢复为正确列名：`"目标销售额"`、`"目标订单数"`、`"年月"`

2. 将 `annual-summary/*` 路由统一到同一套缓存实现
   - `annual-summary/kpi`
   - `annual-summary/by-shop`
   - `annual-summary/trend`
   - `annual-summary/platform-share`
   - `annual-summary/target-completion`
   - 统一走 `_resolve_cached_payload(...)`
   - 冷缓存时通过 `get_or_set_singleflight(...)` 合并并发回源

3. 清理了 `dashboard_api.py` 年汇总段的重复和脏逻辑
   - 删除了遗留的分叉缓存写法
   - 保留单一实现路径，降低后续维护成本

4. 补齐了针对性测试
   - 单飞缓存路由测试
   - `target-completion` fallback SQL 回归测试

## 本轮验证

### 测试

执行命令：

```powershell
python -m pytest backend/tests/test_runtime_config_alignment.py backend/tests/test_cache_service_singleflight.py backend/tests/test_cache_invalidation_helpers.py backend/tests/test_dashboard_cache_singleflight_route.py backend/tests/test_annual_summary_target_completion.py backend/tests/test_database_schema_verification.py backend/tests/test_component_recorder_lint.py backend/tests/test_performance_management_person_fallback.py backend/tests/test_year_month_format_compatibility.py -q
```

结果：

- `35 passed`

### 单接口运行态

执行接口：

- `http://127.0.0.1:8001/api/dashboard/annual-summary/target-completion?granularity=monthly&period=2026-03`

结果：

- 返回 `200`

### 整页冷缓存并发

结果文件：

- [annual_summary_page_cold_final_1773984011.json](F:/Vscode/python_programme/AI_code/xihong_erp/temp/outputs/annual_summary_page_cold_final_1773984011.json)

关键结果：

1. `backend` 链路
   - 冷缓存
   - `100` 并发页面
   - `100/100` 页面成功
   - `500/500` 请求全部 `200`
   - 页面成功率 `100%`

2. `nginx` 链路
   - 冷缓存
   - `100` 并发页面
   - `100/100` 页面成功
   - `500/500` 请求全部 `200`
   - 页面成功率 `100%`

## 当前结论

现在可以明确确认：

1. 业务总览核心读路径已经稳定
2. 年度汇总整页读路径已经稳定
3. 在冷缓存和多人同时访问的情况下，缓存与单飞机制可以有效防止回源放大
4. 当前架构已经具备支撑 `50~100` 人同时使用核心看板场景的能力

## 仍然需要保持的边界

这份结论当前覆盖的是：

- 核心看板读场景
- 冷缓存与热缓存并发访问
- `backend` 与 `nginx` 两条访问链路

这份结论不等同于：

- 全系统所有页面都做过同等级压测
- 大量写入、同步任务和读流量同时叠加的极限压测
- 长时间持续压测下的资源曲线分析

如果后续还要继续扩展，优先级建议是：

1. 对剩余高频页面补同等级整页压测
2. 增加读写混合压测
3. 将压测结果接入固定回归流程
