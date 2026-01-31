## ADDED Requirements

### Requirement: Dashboard API 查询缓存
系统 SHALL 对业务概览 Dashboard 接口的查询结果进行 Redis 缓存，以减轻 Metabase 与 PostgreSQL 压力，支持 50~100 人并发。

#### Scenario: 缓存命中
- **WHEN** 客户端请求 Dashboard 接口（如 KPI、数据对比、店铺赛马等）且查询参数与已有缓存一致
- **AND** 缓存在 TTL 内未过期
- **THEN** 系统从 Redis 返回缓存数据
- **AND** 不调用 Metabase 与 PostgreSQL

#### Scenario: 缓存未命中
- **WHEN** 客户端请求 Dashboard 接口
- **AND** 缓存不存在或已过期
- **THEN** 系统调用 Metabase Question API 查询数据
- **AND** 仅当查询成功时，将结果写入 Redis 缓存（按 cache_type 与规范化 params 生成 Key）
- **AND** 返回数据给客户端

#### Scenario: 错误不缓存
- **WHEN** Metabase 返回 4xx/5xx 或超时异常
- **THEN** 系统不将错误响应写入缓存
- **AND** 直接向客户端返回错误

#### Scenario: Redis 不可用时降级
- **WHEN** Redis 不可用或连接失败
- **THEN** 系统跳过缓存读写
- **AND** 直接调用 Metabase 查询并返回数据
- **AND** 接口行为与无缓存时一致

#### Scenario: 缓存 TTL
- **WHEN** 系统缓存 Dashboard 查询结果
- **THEN** KPI、数据对比、店铺赛马、流量排名、经营指标使用 TTL 180 秒
- **AND** 清仓排名、库存积压使用 TTL 300 秒
