# Design: 本地→云端 B 类表定时同步

## Context

- 本地环境执行数据采集（4 时段：6:00、12:00、18:00、22:00），结果写入本地 PostgreSQL 的 `b_class` schema；B 类表由 `PlatformTableManager` 动态创建，表名为 `fact_{platform}_{data_domain}_{granularity}` 或带 `sub_domain`，无固定 ORM 表列表。
- 云端需要定期获得本地 B 类数据，用于看板与报表；需一套与采集错峰、可维护、支持增量的同步方案。

## Goals / Non-Goals

- **Goals**：4 时段定时同步（与采集错开约 30 分钟）；表列表运行时从 information_schema 枚举 b_class，不维护固定表名单；按表增量、断点更新、单表失败不阻塞、可重试；配置通过环境变量。
- **Non-Goals**：不实现云端→本地回写；不修改采集逻辑或采集时段。

## Decisions

### 1. 同步时刻与采集错峰

- **决策**：Cron 使用 `30 6,12,18,22 * * *`（6:30、12:30、18:30、22:30），与采集的 `0 6,12,18,22 * * *` 错开 30 分钟。
- **理由**：采集任务与后续同步、入库会占用 I/O 与 CPU；错峰减少资源争抢，并尽量保证同步的是「本时段采集完成并入库后」的数据。
- **替代**：与采集同一时刻——易与采集/同步管道争抢，不采纳。

### 2. 表列表：运行时枚举 b_class，不维护固定 --tables

- **决策**：不维护一份固定的「b_class 表名单」。脚本在运行时执行：
  `SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'b_class' AND table_type = 'BASE TABLE'`，
  对返回的每张表执行增量同步。
- **理由**：B 类表随平台/数据域/粒度动态增加，固定列表易遗漏且需频繁改配置；information_schema 与数据库一致，新增表自动纳入同步。
- **替代**：在代码或配置中维护 b_class 表列表——需在每次新增平台/数据域时更新，易遗漏；不采纳。

### 3. 增量策略与断点

- **决策**：每张表按「时间字段」做增量（如 `updated_at` 或 `created_at`）；若表无统一时间字段，则文档约定「全量一次」或跳过并记日志。每表 last_sync 时间或游标存于本地（配置表或脚本可写的状态文件），下次仅同步该时间之后的数据。
- **理由**：减少全量传输与云端写入量，便于 Cron 频繁执行；幂等 upsert 保证重复执行不产生重复行。
- **替代**：每次全量——数据量大时耗时长、占带宽，不采纳。

### 4. 单表失败不阻塞、退出码与日志

- **决策**：单表同步失败时记录错误日志并继续其他表；脚本结束时的退出码区分成功/失败（如 0=全部成功，非 0=存在失败），便于 Cron 或监控告警。日志使用 ASCII 符号（如 [OK]、[ERROR]），避免 Windows 下 Emoji 导致 UnicodeEncodeError。
- **理由**：部分表因权限、网络、结构差异失败时，不影响其他表同步；运维可据退出码与日志定位并重试单表。
- **替代**：单表失败即中止——一次失败导致整次同步无效，不采纳。

### 5. 配置与安全

- **决策**：云端库连接串通过环境变量（如 `CLOUD_DATABASE_URL`）提供；脚本不打印明文密码，仅 masked 或「已设置」类提示；.env.example 或部署文档只写变量名与格式示例。
- **理由**：与项目「敏感配置不入库、不写死」一致；便于不同环境切换目标库。

## Cron 与命令示例

- **Cron 表达式**：`30 6,12,18,22 * * *`
- **示例命令**（路径按实际部署替换）：
  `30 6,12,18,22 * * * cd /path/to/xihong_erp && python scripts/sync_local_to_cloud.py >> logs/sync_local_to_cloud.log 2>&1`

## 与现有脚本的关系

- 若复用 `scripts/migrate_selective_tables.py`：需增加「不传 --tables 时自动枚举 b_class」分支，以及可选的「仅同步 b_class」模式（如 `--schema b_class`）；保留现有 `--source`、`--target`、`--incremental`、`--where` 等参数。
- 若新建 `scripts/sync_local_to_cloud.py`：可内部调用迁移逻辑或封装相同能力，并在 `docs/guides/DATA_MIGRATION_GUIDE.md`、`docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md` 中增加「本地→云端 4 时段同步」章节，指向本设计与 Cron 示例。

## Open Questions

- last_sync 存储位置：每表 last_sync 存于「本地 DB 的配置/状态表」还是「脚本可读写的 JSON/文件」——实现时按运维偏好与现有配置体系选择。
- 无时间字段的 b_class 表：若存在，是「首次全量后跳过」还是「每次全量」——可在实现时按表量级与需求定策略，并在文档中写明。
