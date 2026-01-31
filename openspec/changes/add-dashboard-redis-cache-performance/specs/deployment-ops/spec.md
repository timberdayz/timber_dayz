## ADDED Requirements

### Requirement: 并发支撑配置
系统 SHALL 提供可配置的 Gunicorn workers 与 PostgreSQL 连接池参数，以支持 50~100 人同时查询与文件上传下载。

#### Scenario: Gunicorn workers 配置（资源分级）
- **WHEN** 部署至 2 核 4G 服务器
- **THEN** Gunicorn workers 数量 SHALL 保持 2，以避免内存 OOM
- **AND** 主要依赖 Redis 缓存减轻并发压力

#### Scenario: Gunicorn workers 配置（高配置）
- **WHEN** 部署至 4 核 8G 及以上服务器
- **THEN** Gunicorn workers 可调整为 4~5（建议 2*CPU+1）
- **AND** 配置可通过 docker-compose 或环境变量覆盖

#### Scenario: PostgreSQL 连接池配置
- **WHEN** 后端应用连接 PostgreSQL
- **THEN** 连接池 pool_size 与 max_overflow 应通过环境变量配置（不修改代码）
- **AND** 配置确保 `workers × (pool_size + max_overflow)` 不超过 PostgreSQL max_connections
