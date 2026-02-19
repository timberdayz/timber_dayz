# Tasks: 未缓存重查询接口接入 Redis 缓存

## 1. CacheService 配置

- [ ] 1.1 在 `backend/services/cache_service.py` 的 `DEFAULT_TTL` 中新增：
  - `performance_scores`: 180
  - `performance_scores_shop`: 180
  - `hr_shop_profit_statistics`: 300
  - `hr_annual_profit_statistics`: 300
  - （可选）`expense_summary_monthly`: 300，`expense_summary_yearly`: 300
  - （可选）`target_by_month`: 180，`target_breakdown`: 180

## 2. 绩效接口（P0）

- [ ] 2.1 在 `backend/routers/performance_management.py` 中为 `GET /scores` 增加 Request 依赖
- [ ] 2.2 规范化查询参数（period、platform 等），调用 `cache_service.get("performance_scores", **params)`；命中则返回并带 X-Cache: HIT
- [ ] 2.3 未命中时执行原 Metabase/DB 查询，成功则 `cache_service.set("performance_scores", response, **params)`
- [ ] 2.4 对 `GET /scores/{shop_id}` 同理，缓存 key 含 shop_id 及查询参数

## 3. HR 店铺/年度统计（P0）

- [ ] 3.1 在 `backend/routers/hr_management.py` 中为 `GET /shop-profit-statistics` 增加 Request 依赖
- [ ] 3.2 以 month 等参数做 cache key，先 get 后 set（成功时），TTL 使用 hr_shop_profit_statistics
- [ ] 3.3 对 `GET /annual-profit-statistics` 以 year 等参数做缓存，TTL 使用 hr_annual_profit_statistics

## 4. 可选：费用与目标（P1）

- [ ] 4.1 在 `backend/routers/expense_management.py` 为 GET /summary/monthly、/summary/yearly 增加缓存读写（参数含月份/年份及筛选）
- [ ] 4.2 在 `backend/routers/target_management.py` 为 GET /by-month、GET /{id}/breakdown 增加缓存读写

## 5. 验收

- [ ] 5.1 同一参数两次请求绩效 scores 或 HR 统计，第二次响应为缓存命中（X-Cache: HIT 或等价）
- [ ] 5.2 关闭或断开 Redis 后，上述接口仍可正常返回数据（降级直查）
- [ ] 5.3 异常/错误响应未写入缓存
