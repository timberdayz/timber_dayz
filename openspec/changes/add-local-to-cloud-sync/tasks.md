# Tasks: 本地→云端 B 类表定时同步（4 时段）

## 0. 结构对齐（表头一致性）

- [ ] 0.1 实现结构对齐步骤：对每张待同步的 b_class 表，在同步行数据之前执行：（1）从本地 `information_schema.columns`（schema='b_class', table_name=当前表）读取列名列表；（2）若云端无该表，则按与 `PlatformTableManager._create_base_table` 一致的基础 DDL 在云端建表（可从表名解析 platform/data_domain/sub_domain/granularity），**建表时省略**对 catalog_files、field_mapping_templates 的外键；（3）若云端有该表，则仅对「本地有而云端无且列名不在 b_class 系统列集合中」的列执行 `ADD COLUMN IF NOT EXISTS "col" TEXT`；所有 DDL/SQL 使用 schema 限定（b_class."table_name"）
- [ ] 0.2 将结构对齐嵌入同步流程：对每表先执行结构对齐，再执行增量数据同步，保证 INSERT 不因缺列失败；结构对齐与数据同步均支持单表失败不阻塞

## 1. 表枚举与入口

- [ ] 1.1 实现「无 --tables 时从 information_schema 枚举 b_class 下所有 BASE TABLE」
  - SQL: `SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'b_class' AND table_type = 'BASE TABLE'`
  - 脚本支持：显式 `--tables`（兼容现有用法）与「不传 --tables 则自动枚举 b_class」两种模式；枚举结果为空时记录日志并 exit 0
- [ ] 1.2 确定同步脚本入口：扩展现有 `scripts/migrate_selective_tables.py` 或新建 `scripts/sync_local_to_cloud.py`，并在文档中注明推荐入口与参数

## 2. 增量与断点

- [ ] 2.1 为每张 b_class 表确定增量策略：优先按 `ingest_timestamp`（或 `updated_at`/`created_at`）过滤；若无时间字段则采用「首次全量后跳过」或「始终跳过并记日志」之一，在实现时确定并在文档中写明
- [ ] 2.2 实现断点记录：每表 last_sync 时间或游标存于本地（配置表或脚本可读写的状态文件），下次同步仅同步该时间之后的数据；无 last_sync 时对该表全量同步后写入 last_sync；选定存储方式（DB 表 vs JSON 文件）并在文档中写明
- [ ] 2.3 云端写入采用幂等 upsert：ON CONFLICT 目标与 raw_data_importer 一致（非 services: (platform_code, COALESCE(shop_id,''), data_domain, granularity, data_hash)；services: (data_domain, sub_domain, granularity, data_hash)）；同步行不包含 id，由云端自增

## 3. 错误与可观测性

- [ ] 3.1 单表同步失败时记录日志并继续其他表；不因单表失败而中断整次运行
- [ ] 3.2 退出码约定：0=全部成功，非 0=存在失败（可选区分部分失败/全部失败），便于 Cron 告警或监控
- [ ] 3.3 日志输出到可配置路径（如 `logs/sync_local_to_cloud.log`），避免 Windows 下使用 Emoji，使用 ASCII 符号（如 [OK]、[ERROR]）

## 4. 配置与安全

- [ ] 4.1 云端库连接使用环境变量（如 `CLOUD_DATABASE_URL`），不硬编码；在 .env.example 或部署文档中说明变量名与示例格式（不含真实密码）
- [ ] 4.2 确保脚本不打印敏感信息（仅 masked 或「已设置」提示）

## 5. 文档与 Cron 示例

- [ ] 5.1 在 `docs/deployment/` 或 `docs/guides/` 中新增或更新「本地→云端同步」说明，包含：4 时段与采集错峰理由、Cron 示例（`30 6,12,18,22 * * *`）、表枚举策略、环境变量、推荐命令示例
- [ ] 5.2 Cron 示例命令（供复制）：`30 6,12,18,22 * * * cd /path/to/xihong_erp && python scripts/sync_local_to_cloud.py >> logs/sync_local_to_cloud.log 2>&1`（路径按实际部署替换）

## 6. 验收

- [ ] 6.1 验收：不传 --tables 时脚本能正确枚举 b_class 下所有表并对每表执行同步（或跳过无时间字段的表并记日志）
- [ ] 6.2 验收：某表故意失败（如权限/网络）时，其他表仍能同步完成，且退出码非 0、日志中有该表错误信息
- [ ] 6.3 验收：再次运行同一同步，仅增量写入（或 upsert 无重复行），断点/时间过滤生效
- [ ] 6.4 验收（表头一致性）：本地某 B 类表因模板更新新增列后，下一轮同步后云端该表具有相同列且数据同步成功、无 INSERT 缺列错误
- [ ] 6.5 验收：云端建表无 catalog_files/field_mapping_templates 外键；UPSERT 冲突键与本地一致；无 last_sync 时全量同步后断点正确

## 参考：漏洞与遗漏分析

实现前或实现中可对照 `PROPOSAL_GAP_ANALYSIS.md` 逐项闭环，避免外键/补列范围/冲突键/id/首次运行/空表等漏洞。
