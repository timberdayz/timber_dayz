# Change: 本地→云端 B 类表定时同步（4 时段）

## Why

1. **混合部署**：本地环境负责数据采集（Playwright/API），采集结果写入本地 PostgreSQL 的 `b_class` schema；云端环境需要基于这些数据做看板、报表与多端协同，需定期将本地 B 类数据同步到云端，减少云端直连本地或人工导库。
2. **与采集错峰**：采集已在 4 个时段执行（6:00、12:00、18:00、22:00，见 `collection_scheduler` 的 `daily_realtime`）；同步应在采集完成后执行，避免与采集争抢资源，并保证同步的是「本时段采集完成后的数据」。
3. **可维护性**：B 类表由 `PlatformTableManager` 按 `fact_{platform}_{data_domain}_{granularity}` 等规则动态创建，不宜维护固定表名单；需用「运行时从 information_schema 枚举 b_class 下所有表」的方式，保证新增平台/数据域/粒度时无需改同步配置。

## What Changes

### 1. 同步时段与 Cron

- **4 时段**：与采集错开约 30 分钟，建议 Cron 为 `30 6,12,18,22 * * *`（6:30、12:30、18:30、22:30）。
- 采集沿用现有 `0 6,12,18,22 * * *`（`backend/services/collection_scheduler.py` 中 `CRON_PRESETS['daily_realtime']`）。

### 2. 表列表策略：动态枚举 b_class

- **不维护固定 `--tables` 列表**。
- 运行时用 SQL 枚举 b_class 下所有基表：
  `SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'b_class' AND table_type = 'BASE TABLE'`。
- 对每张表做**增量同步**（按表的时间字段或 last_sync 断点），单表失败不阻塞其他表，支持重试。

### 3. 同步脚本/工具行为

- **输入**：本地 DB URL（默认当前环境）、云端 DB URL（如 `CLOUD_DATABASE_URL` 环境变量）。
- **逻辑**：连接本地 → 枚举 b_class 表 → 对每表增量读取（时间范围或游标）→ 导出/压缩或直连写入云端 → 云端幂等 upsert。
- **断点**：每表记录 last_sync 或按时间字段过滤，避免全量重传。
- **错误**：单表失败记日志并继续其他表；退出码区分「全部成功 / 部分失败 / 全部失败」便于 Cron 告警。
- **配置**：支持通过环境变量配置（如 `CLOUD_DATABASE_URL`），敏感信息不入库、不写死。

### 4. 与现有能力的关系

- 可复用或扩展现有 `scripts/migrate_selective_tables.py`（支持 `--source`、`--target`、`--incremental`、`--where`）；若新建脚本，需与 `docs/guides/DATA_MIGRATION_GUIDE.md`、`docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md` 等文档对齐，并在文档中说明「本地→云端 4 时段」的推荐用法与 Cron 示例。

## Impact

### 受影响的规格

- **deployment-ops**：ADDED 本地→云端 B 类表定时同步（4 时段、动态 b_class 表枚举、增量、断点、单表失败不阻塞、Cron 与配置约定）。

### 受影响的代码与文档

| 类型     | 位置/模块                          | 修改内容 |
|----------|-------------------------------------|----------|
| 脚本/工具 | `scripts/migrate_selective_tables.py` 或新建 `scripts/sync_local_to_cloud.py` | 支持「无 --tables 时枚举 b_class」、增量、断点、错误策略 |
| 配置     | 环境变量 / .env.example（不提交敏感值） | `CLOUD_DATABASE_URL` 等说明 |
| 文档     | `docs/deployment/` 或 `docs/guides/` | 本地→云端同步方案、Cron 示例（如 `30 6,12,18,22 * * *`）、表枚举策略 |

### 不修改

- 采集调度与采集逻辑不变；仅在部署/运维侧增加「定时同步」的 Cron 与脚本。
- `modules/core/db/schema.py` 与 B 类表创建逻辑不变；同步只读 b_class 下已有表。

### 依赖关系

- 依赖现有：PostgreSQL、information_schema、现有迁移/同步脚本（若复用）。
- 无前置变更阻塞；实现时需确认 b_class 下表的统一时间字段或约定 last_sync 存储位置（如本地配置表或脚本状态文件）。

## 部署与日常运作流程（概要）

本变更与「本地/云端部署角色区分」（变更 `add-local-cloud-deployment-role`）配合使用时，建议流程如下，便于核对避免出错。

### 部署核心流程

1. **发布新版本**：打 tag（如 v4.XX.XX）→ `git push origin v4.XX.XX` → CI 对同一 tag 构建两个镜像（默认 + full）并推送到镜像仓库。
2. **云端部署**：拉取默认镜像（无 Playwright）→ 配置 `ENABLE_COLLECTION=false`、`DATABASE_URL=` 云端库 → 启动。
3. **本地采集环境部署**：在那台机器上拉取 -full 镜像（带 Playwright）→ 配置 `ENABLE_COLLECTION=true`、`DATABASE_URL=` 本地库、`CLOUD_DATABASE_URL=` 云端库 → 配置 Cron 执行本地→云端同步脚本（如 `30 6,12,18,22 * * *`）→ 启动。

### 日常运作核心流程

1. **四时段（如 6:00、12:00、18:00、22:00）**：本地执行采集 → 数据同步写入本地 b_class。
2. **错峰（如 6:30、12:30、18:30、22:30）**：本地执行本地→云端同步脚本，将 b_class 增量推到云端库。
3. **云端**：应用只读云端库，不跑采集、不跑同步脚本；前端/看板展示最新数据。

详细步骤与核对清单见 `add-local-cloud-deployment-role` 的提案与部署文档。

## Non-Goals

- 不在此变更中实现「云端→本地」回写或双向同步。
- 不修改采集时段或采集模块代码。
- 不强制要求所有 B 类表必须有同一时间字段；可按表约定或跳过无时间字段的表（仅全量一次或由运维手动触发）。
