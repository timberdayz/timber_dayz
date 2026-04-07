## MODIFIED Requirements

### Requirement: 重查询接口 Redis 缓存
系统 SHALL 对依赖 Metabase 或复杂 DB 聚合的读重查询接口提供 Redis 缓存，与业务概览 Dashboard 接口策略一致，以降低延迟与并发对系统的影响；缓存按查询参数生成 key，TTL 内相同参数命中缓存；Redis 不可用时降级为直接查询，不阻塞接口。

#### Scenario: 绩效与 HR 统计接口缓存
- **WHEN** 客户端请求绩效 scores 或 HR 店铺/年度利润统计接口（相同查询参数）
- **THEN** 若 Redis 可用且该参数在 TTL 内已缓存，系统返回缓存结果并可带 X-Cache: HIT
- **AND** 若未命中则执行原查询，成功响应写入缓存后返回
- **AND** 仅成功响应写入缓存，异常或错误响应不写入

#### Scenario: 缓存降级
- **WHEN** Redis 不可用或 cache_service 未注入
- **THEN** 上述重查询接口仍按原逻辑直接访问 Metabase/DB 并返回结果
- **AND** 不因缓存层导致接口失败或阻塞
