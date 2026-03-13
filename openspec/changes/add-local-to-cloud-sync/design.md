# Design: 本地→云端 B 类表定时同步

## Context

- 本地环境执行数据采集（4 时段：6:00、12:00、18:00、22:00），结果写入本地 PostgreSQL 的 `b_class` schema；B 类表由 `PlatformTableManager` 动态创建，表名为 `fact_{platform}_{data_domain}_{granularity}` 或带 `sub_domain`，无固定 ORM 表列表。
- 云端需要定期获得本地 B 类数据，用于看板与报表；需一套与采集错峰、可维护、支持增量的同步方案。

## Goals / Non-Goals

- **Goals**：4 时段定时同步（与采集错开约 30 分钟）；表列表运行时从 information_schema 枚举 b_class，不维护固定表名单；**对每表先结构对齐（云端表与本地列一致）、再数据同步**；按表增量、断点更新、单表失败不阻塞、可重试；配置通过环境变量。
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

- **决策**：每张表按「时间字段」做增量（b_class 表优先使用 `ingest_timestamp`；若无则 `updated_at`/`created_at`）；若表无统一时间字段，则文档约定「全量一次」或跳过并记日志。每表 last_sync 时间或游标存于本地（配置表或脚本可写的状态文件），下次仅同步该时间之后的数据。
- **理由**：减少全量传输与云端写入量，便于 Cron 频繁执行；幂等 upsert 保证重复执行不产生重复行。
- **替代**：每次全量——数据量大时耗时长、占带宽，不采纳。

### 4. 单表失败不阻塞、退出码与日志

- **决策**：单表同步失败时记录错误日志并继续其他表；脚本结束时的退出码区分成功/失败（如 0=全部成功，非 0=存在失败），便于 Cron 或监控告警。日志使用 ASCII 符号（如 [OK]、[ERROR]），避免 Windows 下 Emoji 导致 UnicodeEncodeError。
- **理由**：部分表因权限、网络、结构差异失败时，不影响其他表同步；运维可据退出码与日志定位并重试单表。
- **替代**：单表失败即中止——一次失败导致整次同步无效，不采纳。

### 5. 配置与安全

- **决策**：云端库连接串通过环境变量（如 `CLOUD_DATABASE_URL`）提供；脚本不打印明文密码，仅 masked 或「已设置」类提示；.env.example 或部署文档只写变量名与格式示例。
- **理由**：与项目「敏感配置不入库、不写死」一致；便于不同环境切换目标库。

### 6. 结构对齐优先于数据同步（表头一致性）

- **决策**：对每张 b_class 表，在同步行数据**之前**先执行「结构对齐」：以本地为该表结构的唯一来源，确保云端表存在且列集合与本地一致（仅追加缺失列，不删列、不改类型）。完成后再执行增量数据同步。
- **具体做法**：
  1. 从本地 `information_schema.columns`（schema='b_class', table_name=当前表）读取该表列名列表；
  2. 若云端不存在该表：按与 `PlatformTableManager._create_base_table` 一致的基础 DDL 在云端建表（可从表名解析 platform/data_domain/sub_domain/granularity，或复用/调用现有建表逻辑）；**云端建表时必须省略**对 `catalog_files(id)`、`field_mapping_templates(id)` 的外键约束，避免插入时因云端无对应 id 而失败；
  3. 若云端已存在该表：仅对「本地有而云端无且属于动态列」的列执行 `ADD COLUMN IF NOT EXISTS "col" TEXT`；动态列 = 列名不在 b_class 系统列集合中（与 `_create_base_table` 及 period 列一致），避免误将系统列补成 TEXT；
  4. 然后按既有增量策略同步该表的行数据。
- **理由**：B 类表表头会随用户更新模板/核心字段而在本地通过 `sync_table_columns` 增加列；若不同步结构，云端缺列会导致 INSERT 报错或数据不一致。先对齐结构可保证稳定（不写不存在的列）、幂等（IF NOT EXISTS）、与现有「只加不删」策略一致，且开销小（多数轮次仅做元数据比较，无 DDL）。
- **替代**：仅同步固定列 + raw_data——云端无动态列，看板需改查 raw_data，不采纳。按列交集同步——云端永远得不到新列，表头不一致，不采纳。

## Cron 与命令示例

- **Cron 表达式**：`30 6,12,18,22 * * *`
- **示例命令**（路径按实际部署替换）：
  `30 6,12,18,22 * * * cd /path/to/xihong_erp && python scripts/sync_local_to_cloud.py >> logs/sync_local_to_cloud.log 2>&1`

## 与现有脚本的关系

- 若复用 `scripts/migrate_selective_tables.py`：需增加「不传 --tables 时自动枚举 b_class」分支，以及可选的「仅同步 b_class」模式（如 `--schema b_class`）；保留现有 `--source`、`--target`、`--incremental`、`--where` 等参数。
- 若新建 `scripts/sync_local_to_cloud.py`：可内部调用迁移逻辑或封装相同能力，并在 `docs/guides/DATA_MIGRATION_GUIDE.md`、`docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md` 中增加「本地→云端 4 时段同步」章节，指向本设计与 Cron 示例。

### 7. 云端 UPSERT 冲突键与主键

- **决策**：云端幂等写入的 ON CONFLICT 目标必须与本地 `raw_data_importer` 一致：非 services 表使用 `(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)`；services 表使用 `(data_domain, sub_domain, granularity, data_hash)`。同步脚本需从表名解析 data_domain（及 services 时的 sub_domain）以选用正确冲突子句。同步行**不包含 id**，由云端自增；冲突时按业务键 UPDATE，避免序列不同步问题。

### 8. 首次运行与空表列表

- **决策**：某表无 last_sync 时视为**全量**（无下界），同步该表所有行后写入 last_sync = max(ingest_timestamp)。枚举 b_class 结果为空时，记录日志并正常退出（exit 0），不视为失败。

## Open Questions

- last_sync 存储位置：每表 last_sync 存于「本地 DB 的配置/状态表」还是「脚本可读写的 JSON/文件」——实现时选定一种并在文档中写明。
- 无时间字段的 b_class 表：若存在，采用「首次全量后跳过」或「始终跳过并记日志」之一，在实现时确定并在文档中写明。
