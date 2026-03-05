# Tasks: 未缓存重查询接口接入 Redis 缓存

## 1. CacheService 配置

- [x] 1.1 在 `backend/services/cache_service.py` 的 `DEFAULT_TTL` 中新增：
  - `performance_scores`: 180
  - `performance_scores_shop`: 180
  - `hr_shop_profit_statistics`: 300
  - `hr_annual_profit_statistics`: 300
  - `annual_summary_by_shop`: 180，`annual_summary_trend`: 180，`annual_summary_platform_share`: 180，`annual_summary_target_completion`: 180
  - （可选）`expense_summary_monthly`: 300，`expense_summary_yearly`: 300
  - （可选）`target_by_month`: 180，`target_breakdown`: 180

## 2. 绩效接口（P0）

- [x] 2.1 在 `backend/routers/performance_management.py` 中为 `GET /scores` 增加 Request 依赖
- [x] 2.2 规范化**所有影响响应的查询参数**（period、platform_code、shop_id、group_by、page、page_size 等）后参与 cache key，调用 `cache_service.get("performance_scores", **params)`；命中则返回并带 X-Cache: HIT
- [x] 2.3 未命中时执行原 Metabase/DB 查询，成功则 `cache_service.set("performance_scores", response, **params)`
- [x] 2.4 对 `GET /scores/{shop_id}` 同理，缓存 key 含 shop_id 及上述查询参数，保证不同页码/视图不共享缓存

## 3. HR 店铺/年度统计（P0）

- [x] 3.1 在 `backend/routers/hr_management.py` 中为 `GET /shop-profit-statistics` 增加 Request 依赖
- [x] 3.2 以 month 等参数做 cache key，先 get 后 set（成功时），TTL 使用 hr_shop_profit_statistics
- [x] 3.3 对 `GET /annual-profit-statistics` 以 year 等参数做缓存，TTL 使用 hr_annual_profit_statistics

## 4. dashboard_api 年度总结其余接口（P0 补充）

- [x] 4.1 在 `backend/routers/dashboard_api.py` 中为 `GET /annual-summary/by-shop`、`/trend`、`/platform-share`、`/target-completion` 增加 Request 依赖与缓存读写
- [x] 4.2 以 granularity、period 等参数规范化后参与 cache key，先 get 后 set（成功时），TTL 使用对应 annual_summary_* 配置
- [x] 4.3 Redis 不可用时降级直查；异常或错误响应不写入缓存

## 5. 可选：费用与目标（P1）

- [x] 5.1 在 `backend/routers/expense_management.py` 为 GET /summary/monthly、/summary/yearly 增加缓存读写；monthly 的 key 需区分 year_month 有无及取值（不传与传某月结果不同）
- [x] 5.2 在 `backend/routers/target_management.py` 为 GET /by-month、GET /{target_id}/breakdown 增加缓存读写；by-month 的 key 含 month、target_type；breakdown 的 key 含 target_id、breakdown_type 等查询参数

## 6. 验收

- [ ] 6.1 同一参数两次请求绩效 scores、HR 统计或年度总结四接口，第二次响应为缓存命中（X-Cache: HIT 或等价）
- [ ] 6.2 不同查询参数（如 page=1 与 page=2，或不同 group_by）的请求不误命中同一缓存
- [ ] 6.3 关闭或断开 Redis 后，上述接口仍可正常返回数据（降级直查）
- [ ] 6.4 异常/错误响应未写入缓存
