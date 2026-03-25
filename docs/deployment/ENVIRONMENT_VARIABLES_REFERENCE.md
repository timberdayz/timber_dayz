# 环境变量参考文档

> Historical note：本文中的 Metabase 变量段仅保留为历史兼容与归档参考。
> 当前 PostgreSQL-first 运行路径不再把 Metabase 相关变量视为默认必配项。

版本: v4.19.7  
更新: 2026-03-25  
基于: `env.template`

## P0 - 当前必配

- `ENVIRONMENT`
- `DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`

## P1 - 当前建议配置

- 服务监听：`HOST`、`PORT`
- 数据库连接池：`DB_POOL_SIZE`、`DB_MAX_OVERFLOW`、`DB_POOL_TIMEOUT`、`DB_POOL_RECYCLE`
- Redis：`REDIS_URL`、`REDIS_ENABLED`
- 执行器：`CPU_EXECUTOR_WORKERS`、`IO_EXECUTOR_WORKERS`
- 日志：`LOG_LEVEL`、`LOG_FILE`
- Playwright：`PLAYWRIGHT_HEADLESS`、`PLAYWRIGHT_SLOW_MO`、`PLAYWRIGHT_TIMEOUT`

## P2 - 可选配置

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`

## Metabase 配置（Historical / legacy only）

以下变量仅在查看历史兼容资料或归档资产时才有参考价值，
不再属于当前 PostgreSQL-first 运行路径的默认配置：

- `METABASE_URL`
- `METABASE_API_KEY`
- `METABASE_ENCRYPTION_SECRET_KEY`
- `METABASE_EMBEDDING_SECRET_KEY`

## 当前原则

- 当前默认运行链路不再要求配置 Metabase
- 当前部署与验证应以 PostgreSQL-first 文档为准
- 如需查看 Metabase 历史资料，请参考：
  - `docs/development/METABASE_LEGACY_ASSET_STATUS.md`
  - `archive/metabase/README.md`
