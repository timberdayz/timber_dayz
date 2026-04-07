# Tasks: 业务概览 Dashboard 性能优化

## 1. CacheService 扩展

- [x] 1.1 在 `cache_service.py` 的 `DEFAULT_TTL` 中新增 `dashboard_kpi`、`dashboard_comparison`、`dashboard_shop_racing`、`dashboard_traffic_ranking`、`dashboard_operational_metrics`（180s）
- [x] 1.2 新增 `dashboard_clearance_ranking`、`dashboard_inventory_backlog`（300s）

## 2. Dashboard API 缓存接入

- [x] 2.0 在各路由函数中注入 `Request` 参数，用于访问 `request.app.state.cache_service`
- [x] 2.0b 使用 `hasattr(request.app.state, 'cache_service')` 检查，与 collection.py 一致（Redis 不可用时未设置）
- [x] 2.1 在 `dashboard_api.py` 中新增 `_normalize_cache_params(params)` 辅助函数（None→空字符串、日期格式统一），确保相同语义生成相同 cache key
- [x] 2.2 KPI 接口 `/api/dashboard/business-overview/kpi` 接入缓存（cache_type: dashboard_kpi，params: month, platform）
- [x] 2.3 数据对比接口 `/api/dashboard/business-overview/comparison` 接入缓存
- [x] 2.4 店铺赛马接口 `/api/dashboard/business-overview/shop-racing` 接入缓存
- [x] 2.5 流量排名接口 `/api/dashboard/business-overview/traffic-ranking` 接入缓存
- [x] 2.6 经营指标接口 `/api/dashboard/business-overview/operational-metrics` 接入缓存
- [x] 2.7 清仓排名接口 `/api/dashboard/clearance-ranking` 接入缓存
- [x] 2.8 库存积压接口 `/api/dashboard/business-overview/inventory-backlog` 接入缓存
- [x] 2.9 仅对成功响应写入缓存，Metabase 异常/4xx/5xx 不缓存
- [x] 2.10 确认 Redis 不可用时各接口仍能正常返回（降级逻辑）

## 3. 部署配置优化（可选，2 核 4G 保持现状）

- [x] 3.1 2 核 4G：保持 `docker-compose.cloud.yml` 中 workers=2，不修改
- [x] 3.2 4 核 8G 及以上：已文档化于 design.md，可按需调整 workers 与连接池

## 4. 验证

- [x] 4.1 手动验证：同一参数重复请求，第二次应命中缓存（X-Cache: HIT，加速约 130x）
- [x] 4.2 手动验证：Redis 停用时，接口仍返回数据（X-Cache: BYPASS，降级正常）
- [x] 4.3 可选：已通过 scripts/test_dashboard_cache.py 验证，50 人压测可后续执行
